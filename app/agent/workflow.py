"""RCA 工作流编排器 - 基于 StateGraph 的图编排工作流。

节点拓扑：
    analyze_symptom → generate_hypotheses → select_tool → execute_tool
                                                              ↓
    generate_report ← PROCEED ← reflect ← draft_rca ← observe_evidence
                         ↑                        ↑
                         └── NEED_MORE_EVIDENCE ──┘ (回退到 select_tool)

支持：
- StateGraph 图编排（非简单 for 循环）
- 条件边动态路由
- 循环回退（反思 → 重新选工具）
- 检查点断点恢复
"""

import logging
import time
import uuid
from datetime import datetime
from typing import Optional

from app.agent.state import RCAState
from app.agent.graph import StateGraph
from app.agent.nodes.analyze_symptom import analyze_symptom_node
from app.agent.nodes.generate_hypotheses import generate_hypotheses_node
from app.agent.nodes.select_tool import select_tool_node
from app.agent.nodes.execute_tool import execute_tool_node
from app.agent.nodes.observe_evidence import observe_evidence_node
from app.agent.nodes.draft_rca import draft_rca_node
from app.agent.nodes.reflect import reflect_node
from app.agent.nodes.generate_report import generate_report_node
from app.persistence.checkpointer import Checkpointer
from app.persistence.repositories import RCATaskRepository, StepEventRepository
from app.schemas.api import AnomalyEvent, TaskStatus

logger = logging.getLogger(__name__)

# 节点拓扑顺序（用于断点恢复时确定下一个节点）
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


class RCAWorkflow:
    """RCA 工作流编排器。

    使用 StateGraph 构建 8 节点图编排流程，
    支持条件边路由（反思 → 回退或继续）和检查点断点恢复。
    """

    _NODE_TITLES = _NODE_TITLES

    def __init__(self):
        self.checkpointer = Checkpointer()
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

    def _build_graph(self) -> StateGraph:
        """构建 RCA 工作流的 StateGraph。

        Returns:
            配置好节点和边的 StateGraph 实例
        """
        graph = StateGraph()

        # 注册所有节点
        graph.add_node("analyze_symptom", analyze_symptom_node)
        graph.add_node("generate_hypotheses", generate_hypotheses_node)
        graph.add_node("select_tool", select_tool_node)
        graph.add_node("execute_tool", execute_tool_node)
        graph.add_node("observe_evidence", observe_evidence_node)
        graph.add_node("draft_rca", draft_rca_node)
        graph.add_node("reflect", reflect_node)
        graph.add_node("generate_report", generate_report_node)

        # 普通边：线性执行链
        graph.add_edge("analyze_symptom", "generate_hypotheses")
        graph.add_edge("generate_hypotheses", "select_tool")
        graph.add_edge("select_tool", "execute_tool")
        graph.add_edge("execute_tool", "observe_evidence")
        graph.add_edge("observe_evidence", "draft_rca")
        graph.add_edge("draft_rca", "reflect")

        # 条件边：反思节点根据结果动态路由
        # PROCEED → 生成报告
        # NEED_MORE_EVIDENCE → 回到 select_tool（循环回退）
        graph.add_conditional_edges(
            "reflect",
            _reflect_condition,
            {
                "PROCEED": "generate_report",
                "NEED_MORE_EVIDENCE": "select_tool",
            },
        )

        # 设置入口节点
        graph.set_entry_point("analyze_symptom")

        return graph

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

        # ── 断点恢复 ──────────────────────────────────────────
        resume_from: Optional[str] = None

        if resume:
            checkpoint_state = self.checkpointer.load(task_id)
            if checkpoint_state is not None:
                logger.info(
                    f"从检查点恢复: task_id={task_id}, "
                    f"last_node={checkpoint_state.current_node}"
                )
                state = checkpoint_state
                resume_from = _get_next_node(state)
                if resume_from is None:
                    logger.warning(
                        f"无法确定检查点后续节点，从头开始: task_id={task_id}"
                    )
                    resume_from = None
                    state = self._init_state(event, task_id)
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
            f"resume={resume}, resume_from={resume_from}"
        )

        # ── 构建并编译图 ──────────────────────────────────────
        graph = self._build_graph()
        compiled = graph.compile()

        # 设置节点开始回调：发射 node_started 事件
        def on_node_start(node_name: str, current_state: RCAState) -> None:
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
                    "round": current_state.reflection_round,
                },
            )

        # 设置节点完成回调：保存检查点 + 发射 node_completed 事件
        def on_node_complete(node_name: str, current_state: RCAState) -> None:
            current_state.current_node = node_name
            self.checkpointer.save(current_state)

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

        # 设置节点错误回调：发射 node_error 事件
        def on_node_error(node_name: str, current_state: RCAState, error: Exception) -> None:
            error_msg = str(error)
            error_type = type(error).__name__
            self._emit_event(
                task_id=task_id,
                node_name=node_name,
                event_type="node_error",
                status="failed",
                title=f"{self._node_title(node_name)} 执行失败",
                summary=f"节点 {node_name} 执行异常: {error_msg}",
                detail_json={
                    "node_name": node_name,
                    "round": current_state.reflection_round,
                    "error": error_msg,
                    "error_type": error_type,
                },
            )

        compiled.set_start_callback(on_node_start)
        compiled.set_callback(on_node_complete)
        compiled.set_error_callback(on_node_error)

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
        try:
            state = compiled.invoke(state, resume_from=resume_from)

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
            logger.error(f"RCA 工作流失败: task_id={task_id}, error={e}")
            state.status = TaskStatus.FAILED

            # 发射 task_error 事件
            self._emit_event(
                task_id=task_id,
                node_name="",
                event_type="task_error",
                status="failed",
                title="根因分析失败",
                summary=f"分析过程异常: {e}",
                detail_json={
                    "error": str(e),
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

def _reflect_condition(state: RCAState) -> str:
    """反思节点的条件路由函数。

    根据反思结果决定下一步：
    - PROCEED → 生成最终报告
    - NEED_MORE_EVIDENCE → 回到工具选择，补充证据
    """
    return state.get_reflection_action()


def _get_next_node(state: RCAState) -> Optional[str]:
    """根据当前状态确定下一个要执行的节点（用于断点恢复）。

    处理两种情况：
    1. 普通线性节点 → 取拓扑顺序中的下一个
    2. reflect 节点 → 根据反思结果决定路由
    """
    current = state.current_node
    if current is None:
        return "analyze_symptom"

    # reflect 节点的条件路由
    if current == "reflect":
        action = state.get_reflection_action()
        if action == "NEED_MORE_EVIDENCE":
            return "select_tool"
        else:
            return "generate_report"

    # 普通线性路由：取拓扑顺序中的下一个
    try:
        idx = _NODE_ORDER.index(current)
        if idx + 1 < len(_NODE_ORDER):
            return _NODE_ORDER[idx + 1]
    except ValueError:
        pass

    return None
