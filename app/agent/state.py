"""RCA 工作流状态定义。"""

import operator
from datetime import datetime
from typing import Annotated, Any, Optional, TypedDict

from pydantic import BaseModel, Field

from app.schemas.api import AnomalyEvent, TaskStatus


class RCAState(BaseModel):
    """RCA 工作流核心状态，贯穿所有节点。"""

    # ── 任务标识 ────────────────────────────────────────────
    task_id: str = ""
    status: TaskStatus = TaskStatus.PENDING
    current_node: Optional[str] = None

    # ── 输入事件 ────────────────────────────────────────────
    event: Optional[AnomalyEvent] = None

    # ── 分析过程 ────────────────────────────────────────────
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    selected_tools: list[str] = Field(default_factory=list)
    tool_call_history: list[dict[str, Any]] = Field(default_factory=list)

    # ── 反思循环 ────────────────────────────────────────────
    reflection_round: int = 0
    draft_rca: Optional[str] = None
    reflection_result: Optional[dict[str, Any]] = None

    # ── 输出 ────────────────────────────────────────────────
    confidence: float = 0.0
    final_report: Optional[dict[str, Any]] = None

    # ── Prompt 工程 ──────────────────────────────────────────
    prompt_history: list[dict[str, Any]] = Field(default_factory=list)

    # ── 元数据 ──────────────────────────────────────────────
    anomaly_type: str = ""
    description: str = ""
    source_system: str = "MES"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
    completed_at: Optional[str] = None

    def model_post_init(self, __context: Any) -> None:
        """初始化后从 event 同步字段。"""
        if self.event and not self.anomaly_type:
            self.anomaly_type = self.event.anomaly_type
            self.description = self.event.description
            self.source_system = self.event.source_system
            self.metadata = self.event.metadata or {}
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def add_hypothesis(self, hypothesis: dict) -> None:
        self.hypotheses.append(hypothesis)

    def add_evidence(self, evidence_item: dict) -> None:
        self.evidence.append(evidence_item)

    def add_tool_call(self, record: dict) -> None:
        self.tool_call_history.append(record)

    def set_reflection(self, result: dict) -> None:
        self.reflection_result = result
        self.reflection_round += 1

    def needs_more_evidence(self) -> bool:
        """判断是否需要更多证据（用于条件边路由）。"""
        if not self.reflection_result:
            return False
        from app.config import settings

        action = self.reflection_result.get("action", "")
        # ESCALATE 也视为不需要更多证据，直接生成报告
        return (
                action == "NEED_MORE_EVIDENCE"
                and self.reflection_round < settings.max_reflection_rounds
        )

    def add_prompt_record(self, node_name: str, prompt: str) -> None:
        """记录节点使用的 Prompt 模板渲染结果。"""
        self.prompt_history.append({
            "node_name": node_name,
            "prompt": prompt,
            "timestamp": datetime.now().isoformat(),
        })

    def get_reflection_action(self) -> str:
        """获取反思行动决策，用于条件边映射。"""
        if not self.reflection_result:
            return "PROCEED"
        action = self.reflection_result.get("action", "PROCEED")
        if action == "ESCALATE":
            return "PROCEED"  # ESCALATE 走 generate_report 路径
        return action


# ═══════════════════════════════════════════════════════════════
# LangGraph 兼容状态（TypedDict + Annotated reducer）
# ═══════════════════════════════════════════════════════════════

class RCAGraphState(TypedDict, total=False):
    """LangGraph 兼容的 RCA 工作流状态。

    使用 TypedDict 定义，列表字段使用 Annotated[list, operator.add]
    作为 reducer，确保 LangGraph 节点返回的部分 dict 能正确合并。
    """

    # ── 任务标识 ────────────────────────────────────────────
    task_id: str
    status: str
    current_node: Optional[str]

    # ── 输入事件（JSON-safe dict） ──────────────────────────
    event: Optional[dict[str, Any]]

    # ── 分析过程（列表字段使用 operator.add reducer） ──────
    hypotheses: Annotated[list[dict[str, Any]], operator.add]
    evidence: Annotated[list[dict[str, Any]], operator.add]
    selected_tools: Annotated[list[str], operator.add]
    tool_call_history: Annotated[list[dict[str, Any]], operator.add]

    # ── 反思循环 ────────────────────────────────────────────
    reflection_round: int
    draft_rca: Optional[str]
    reflection_result: Optional[dict[str, Any]]

    # ── 输出 ────────────────────────────────────────────────
    confidence: float
    final_report: Optional[dict[str, Any]]

    # ── Prompt 工程 ──────────────────────────────────────────
    prompt_history: Annotated[list[dict[str, Any]], operator.add]

    # ── 元数据 ──────────────────────────────────────────────
    anomaly_type: str
    description: str
    source_system: str
    metadata: dict[str, Any]
    created_at: str
    completed_at: Optional[str]


def rca_state_to_graph_state(state: RCAState) -> RCAGraphState:
    """将 RCAState (Pydantic) 转换为 RCAGraphState (TypedDict)。

    嵌套 Pydantic 对象（如 event）使用 model_dump(mode="json")
    转为 JSON-safe dict，确保 LangGraph 序列化兼容。
    """
    return RCAGraphState(
        task_id=state.task_id,
        status=state.status.value if isinstance(state.status, TaskStatus) else str(state.status),
        current_node=state.current_node,
        event=state.event.model_dump(mode="json") if state.event else None,
        hypotheses=list(state.hypotheses),
        evidence=list(state.evidence),
        selected_tools=list(state.selected_tools),
        tool_call_history=list(state.tool_call_history),
        reflection_round=state.reflection_round,
        draft_rca=state.draft_rca,
        reflection_result=dict(state.reflection_result) if state.reflection_result else None,
        confidence=state.confidence,
        final_report=dict(state.final_report) if state.final_report else None,
        prompt_history=list(state.prompt_history),
        anomaly_type=state.anomaly_type,
        description=state.description,
        source_system=state.source_system,
        metadata=dict(state.metadata),
        created_at=state.created_at,
        completed_at=state.completed_at,
    )


def graph_state_to_rca_state(state: RCAGraphState) -> RCAState:
    """将 RCAGraphState (TypedDict) 转换为 RCAState (Pydantic)。

    从 JSON-safe dict 重建 AnomalyEvent，触发 model_post_init
    以同步 event 字段到顶层。
    """
    event_data = state.get("event")
    event = AnomalyEvent(**event_data) if event_data else None

    # 安全获取可选字段
    _status_raw = state.get("status")
    _reflection_raw = state.get("reflection_result")
    _report_raw = state.get("final_report")

    return RCAState(
        task_id=state.get("task_id", ""),
        status=TaskStatus(_status_raw) if _status_raw else TaskStatus.PENDING,
        current_node=state.get("current_node"),
        event=event,
        hypotheses=list(state.get("hypotheses", [])),
        evidence=list(state.get("evidence", [])),
        selected_tools=list(state.get("selected_tools", [])),
        tool_call_history=list(state.get("tool_call_history", [])),
        reflection_round=state.get("reflection_round", 0),
        draft_rca=state.get("draft_rca"),
        reflection_result=dict(_reflection_raw) if _reflection_raw else None,  # type: ignore[arg-type]
        confidence=state.get("confidence", 0.0),
        final_report=dict(_report_raw) if _report_raw else None,  # type: ignore[arg-type]
        prompt_history=list(state.get("prompt_history", [])),
        anomaly_type=state.get("anomaly_type", ""),
        description=state.get("description", ""),
        source_system=state.get("source_system", "MES"),
        metadata=dict(state.get("metadata", {})),
        created_at=state.get("created_at", ""),
        completed_at=state.get("completed_at"),
    )
