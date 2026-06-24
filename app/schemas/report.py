"""RCA 报告 Schema。"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class Hypothesis(BaseModel):
    """根因假设。"""

    id: str
    description: str
    probability: float = Field(default=0.0, ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    refuting_evidence: list[str] = Field(default_factory=list)
    status: str = "pending"  # pending / confirmed / rejected


class ToolCallRecord(BaseModel):
    """工具调用记录。"""

    tool_name: str
    input_params: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: Optional[str] = None
    duration_ms: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)


class ReflectionResult(BaseModel):
    """反思结果。"""

    action: str = "PROCEED"  # PROCEED / NEED_MORE_EVIDENCE / REJECT_ALL
    reasoning: str = ""
    missing_evidence: list[str] = Field(default_factory=list)
    confidence_adjustment: float = 0.0


class RCAReport(BaseModel):
    """最终 RCA 报告。"""

    task_id: str
    anomaly_type: str
    description: str
    root_cause: Optional[str] = None
    root_cause_category: Optional[str] = None
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    evidence_summary: list[dict[str, Any]] = Field(default_factory=list)
    tool_call_history: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    reflection_rounds: int = 0
    recommendations: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)
