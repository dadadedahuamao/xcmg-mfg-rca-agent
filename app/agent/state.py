"""RCA 工作流状态定义。"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.api import AnomalyEvent, TaskStatus
from app.schemas.evidence import Evidence, EvidenceCollection
from app.schemas.report import Hypothesis, ReflectionResult, ToolCallRecord, RCAReport


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
