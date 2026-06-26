"""RCA 工作流编排器 - 基于官方 LangGraph 的图编排工作流。

节点拓扑：
    analyze_symptom → generate_hypotheses → select_tool → execute_tool
                                                              ↓
    generate_report ← PROCEED ← reflect ← draft_rca ← observe_evidence
                         ↑                        ↑
                         └── NEED_MORE_EVIDENCE ──┘ (回退到 select_tool)

支持：
- 官方 LangGraph StateGraph 图编排
- 条件边动态路由
- 循环回退（反思 → 重新选工具）
- InMemorySaver 检查点
"""

import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Optional, cast

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langchain_core.runnables.config import RunnableConfig

from app.agent.node_adapter import ADAPTED_NODES
from app.agent.state import (
    RCAState,
    RCAGraphState,
    graph_state_to_rca_state,
    rca_state_to_graph_state,
)
from app.persistence.checkpointer import Checkpointer
from app.persistence.repositories import RCATaskRepository, StepEventRepository
from app.schemas.api import AnomalyEvent, TaskStatus

logger = logging.getLogger(__name__)

# 节点拓扑顺序
_NODE_ORDER = [
    "analyze_symptom",
    "generate_hypotheses",
    "select_tool",
    "execute_tool",
    "observe_evidence",
    "draft_rca",
    "reflect",
    "generate_report",
]

# 节点中文标题映射
_NODE_TITLES = {
    "analyze_symptom": "分析异常症状",
    "generate_hypotheses": "生成根因假设",
    "select_tool": "选择查询工具",
    "execute_tool": "执行工具调用",
    "observe_evidence": "观察证据结果",
    "draft_rca": "起草根因结论",
    "reflect": "反思与校核",
    "generate_report": "生成分析报告",
}


_MAX_ERROR_LENGTH = 500

# 敏感信息掩码模式（key=value 或 key: value 形式）
_SECRET_PATTERNS = [
    (re.compile(r"(password|passwd|pwd)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"(api_key|apikey|api-key)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"(token|access_token|auth_token|bearer)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"(authorization|auth)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"(secret|private_key)\s*[=:]\s*\S+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"sk-[a-zA-Z0-9_-]{20,}"), "sk-***"),
]


def _safe_error_message(error: Exception) -> str:
    """对异常消息进行安全处理：掩码敏感信息并截断过长消息。

    Args:
        error: 原始异常对象

    Returns:
        经过掩码和截断的安全错误消息字符串
    """
    msg = str(error)

    # 掩码敏感信息
    for pattern, replacement in _SECRET_PATTERNS:
        msg = pattern.sub(replacement, msg)

    # 截断过长消息
    if len(msg) > _MAX_ERROR_LENGTH:
        msg = msg[:_MAX_ERROR_LENGTH] + "..."

    return msg


class RCAWorkflow:
    """RCA 工作流编排器。

    使用官方 LangGraph StateGraph 构建 8 节点图编排流程，
    支持条件边路由（反思 → 回退或继续）和 InMemorySaver 检查点。
    """

    _NODE_TITLES = _NODE_TITLES

    def __init__(self):
        self.checkpointer = Checkpointer()
        self._memory_saver = InMemorySaver()
        self._node_start_times: dict[str, float] = {}

    # ── 事件发射 ──────────────────────────────────────────────

    def _emit_event(
        self,
        task_id: str,
        node_name: str,
        event_type: str,
        status: str,
        title: str,
        summary: Optional[str] = None,
        detail_json: Optional[dict] = None,
    ) -> None:
        """发射结构化步骤事件到 StepEventRepository。"""
        try:
            StepEventRepository.append_event(
                task_id=task_id,
                node_name=node_name,
                event_type=event_type,
                status=status,
                title=title,
                summary=summary,
                detail_json=detail_json,
            )
        except Exception:
            logger.warning(
                f"发射事件失败: task_id={task_id}, event_type={event_type}, "
                f"node_name={node_name}",
                exc_info=True,
            )

    def _node_title(self, node_name: str) -> str:
        """获取节点的中文标题。"""
        return self._NODE_TITLES.get(node_name, node_name)

    # ── 图构建 ────────────────────────────────────────────────

    def _build_graph(self):
        """构建 RCA 工作流的官方 LangGraph StateGraph。

        Returns:
            编译后的 LangGraph StateGraph 实例
        """
        graph = StateGraph(RCAGraphState)

        # 注册所有节点（使用适配后的节点函数）
        for node_name in _NODE_ORDER:
            graph.add_node(node_name, cast(Callable[..., Any], ADAPTED_NODES[node_name]))

        # 入口边
        graph.add_edge(START, "analyze_symptom")

        # 线性边
        graph.add_edge("analyze_symptom", "generate_hypotheses")
        graph.add_edge("generate_hypotheses", "select_tool")
        graph.add_edge("select_tool", "execute_tool")
        graph.add_edge("execute_tool", "observe_evidence")
        graph.add_edge("observe_evidence", "draft_rca")
        graph.add_edge("draft_rca", "reflect")

        # 条件边：反思节点根据结果动态路由
        graph.add_conditional_edges(
            "reflect",
            _reflect_condition,
            {
                "PROCEED": "generate_report",
                "NEED_MORE_EVIDENCE": "select_tool",
            },
        )

        # 出口边
        graph.add_edge("generate_report", END)

        return graph.compile(checkpointer=self._memory_saver)

    # ── 主执行方法 ────────────────────────────────────────────

    def run(
        self,
        event: AnomalyEvent,
        task_id: Optional[str] = None,
        resume: bool = False,
        skip_persistence: bool = False,
    ) -> RCAState:
        """执行完整的 RCA 工作流。

        Args:
            event: 异常事件
            task_id: 可选的任务 ID
            resume: 是否从检查点恢复继续执行
            skip_persistence: 跳过任务创建和初始状态更新（由调用方管理持久化）

        Returns:
            最终的 RCAState
        """
        if task_id is None:
            task_id = f"rca-{uuid.uuid4().hex[:12]}"

        # ── 断点恢复（加载自定义检查点状态） ──────────────────
        if resume:
            checkpoint_state = self.checkpointer.load(task_id)
            if checkpoint_state is not None:
                logger.info(
                    f"从检查点恢复: task_id={task_id}, "
                    f"last_node={checkpoint_state.current_node}"
                )
                state = checkpoint_state
            else:
                logger.info(
                    f"未找到检查点，从头开始: task_id={task_id}"
                )
                state = self._init_state(event, task_id)
        else:
            state = self._init_state(event, task_id)

        # ── 持久化任务 ────────────────────────────────────────
        if not resume and not skip_persistence:
            RCATaskRepository.create(
                task_id=task_id,
                anomaly_type=event.anomaly_type,
                description=event.description,
                source_system=event.source_system,
                metadata=event.metadata,
            )
            RCATaskRepository.update_status(task_id, "running")

        logger.info(
            f"开始 RCA 工作流: task_id={task_id}, type={event.anomaly_type}, "
            f"resume={resume}"
        )

        # ── 构建并编译图 ──────────────────────────────────────
        compiled = self._build_graph()

        # ── 发射 task_started 事件 ──────────────────────────────
        self._emit_event(
            task_id=task_id,
            node_name="",
            event_type="task_started",
            status="running",
            title="开始根因分析",
            summary=f"开始分析 {event.anomaly_type}: {event.description}",
            detail_json={
                "anomaly_type": event.anomaly_type,
                "source_system": event.source_system,
            },
        )

        # ── 执行图 ────────────────────────────────────────────
        graph_input = rca_state_to_graph_state(state)
        config: RunnableConfig = {
            "configurable": {"thread_id": task_id},
            "recursion_limit": 50,
        }

        try:
            for chunk in compiled.stream(
                graph_input, config=config, stream_mode="updates"
            ):
                for node_name in chunk:
                    # 发射 node_started 事件
                    self._node_start_times[node_name] = time.time()
                    self._emit_event(
                        task_id=task_id,
                        node_name=node_name,
                        event_type="node_started",
                        status="running",
                        title=f"开始{self._node_title(node_name)}",
                        summary=f"正在执行 {node_name}",
                        detail_json={
                            "node_name": node_name,
                        },
                    )

                    # 获取完整快照并转换回 RCAState
                    snapshot = compiled.get_state(config)
                    current_state = graph_state_to_rca_state(
                        cast(RCAGraphState, snapshot.values)
                    )
                    current_state.current_node = node_name

                    # 保存自定义检查点
                    self.checkpointer.save(current_state)

                    # 发射 node_completed 事件
                    start_time = self._node_start_times.pop(node_name, None)
                    duration_ms = None
                    if start_time is not None:
                        duration_ms = round((time.time() - start_time) * 1000)

                    self._emit_event(
                        task_id=task_id,
                        node_name=node_name,
                        event_type="node_completed",
                        status="completed",
                        title=f"完成{self._node_title(node_name)}",
                        summary=f"{self._node_title(node_name)} 执行完成",
                        detail_json={
                            "node_name": node_name,
                            "round": current_state.reflection_round,
                            "duration_ms": duration_ms,
                        },
                    )

            # ── 获取最终状态 ──────────────────────────────────
            final_snapshot = compiled.get_state(config)
            state = graph_state_to_rca_state(
                cast(RCAGraphState, final_snapshot.values)
            )

            # 标记完成
            state.status = TaskStatus.COMPLETED
            state.completed_at = datetime.now().isoformat()
            if not skip_persistence:
                RCATaskRepository.update_status(
                    task_id, "completed",
                    confidence=state.confidence,
                    reflection_rounds=state.reflection_round,
                )

            # 发射 task_done 事件
            self._emit_event(
                task_id=task_id,
                node_name="",
                event_type="task_done",
                status="completed",
                title="根因分析完成",
                summary=f"分析完成，置信度 {state.confidence:.0%}",
                detail_json={
                    "confidence": state.confidence,
                    "reflection_rounds": state.reflection_round,
                },
            )

            logger.info(
                f"RCA 工作流完成: task_id={task_id}, "
                f"confidence={state.confidence:.2f}, "
                f"rounds={state.reflection_round}"
            )

        except Exception as e:
            safe_msg = _safe_error_message(e)
            logger.error(f"RCA 工作流失败: task_id={task_id}, error={safe_msg}")
            state.status = TaskStatus.FAILED

            # 发射 task_error 事件
            self._emit_event(
                task_id=task_id,
                node_name="",
                event_type="task_error",
                status="failed",
                title="根因分析失败",
                summary=f"分析过程异常: {safe_msg}",
                detail_json={
                    "error": safe_msg,
                },
            )

            if not skip_persistence:
                RCATaskRepository.update_status(task_id, "failed")
            raise

        return state

    # ── 辅助方法 ──────────────────────────────────────────────

    def _init_state(self, event: AnomalyEvent, task_id: str) -> RCAState:
        """初始化 RCA 状态。"""
        return RCAState(
            task_id=task_id,
            event=event,
            status=TaskStatus.RUNNING,
        )


# ═══════════════════════════════════════════════════════════════
# 图辅助函数
# ═══════════════════════════════════════════════════════════════

def _reflect_condition(state: RCAGraphState) -> str:
    """反思节点的条件路由函数。

    将 RCAGraphState 转换为 RCAState 后获取反思行动决策。

    根据反思结果决定下一步：
    - PROCEED → 生成最终报告
    - NEED_MORE_EVIDENCE → 回到工具选择，补充证据
    """
    rca_state = graph_state_to_rca_state(state)
    return rca_state.get_reflection_action()
