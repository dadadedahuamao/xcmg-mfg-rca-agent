"""API 请求/响应 Schema。"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AnomalyEvent(BaseModel):
    """异常事件输入。"""

    anomaly_type: str = Field(..., description="异常类型：overstation_check / equipment_conflict / material_shortage / quality_abnormal / interface_timeout / schedule_risk")
    description: str = Field(..., description="异常描述")
    source_system: str = Field(default="MES", description="来源系统：MES/APS/WMS/QMS")
    timestamp: Optional[datetime] = Field(default=None, description="事件时间戳")
    metadata: dict[str, Any] = Field(default_factory=dict, description="附加元数据")


class RCAAnalyzeRequest(BaseModel):
    """RCA 分析请求。"""

    event: AnomalyEvent
    task_id: Optional[str] = Field(default=None, description="可选的任务 ID，不传则自动生成")
    resume_from: Optional[bool] = Field(default=False, description="是否从已有检查点恢复执行")


class RCAAnalyzeResponse(BaseModel):
    """RCA 分析响应。"""

    task_id: str
    status: TaskStatus
    message: str
    events_url: str = Field(default="", description="步骤事件 SSE 端点 URL")


class RCAReportResponse(BaseModel):
    """RCA 报告响应。"""

    task_id: str
    status: TaskStatus
    anomaly_type: str
    description: str
    root_cause: Optional[str] = None
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    reflection_rounds: int = 0
    final_report: Optional[dict[str, Any]] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RCATaskResponse(BaseModel):
    """RCA 任务状态响应。"""

    task_id: str
    status: TaskStatus
    anomaly_type: str
    description: str
    confidence: float = 0.0
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = "healthy"
    version: str
    timestamp: datetime


# ═══════════════════════════════════════════════════════════════
# RCA 步骤事件
# ═══════════════════════════════════════════════════════════════

class StepEvent(BaseModel):
    """RCA 工作流步骤事件。"""

    id: int
    task_id: str
    seq: int
    node_name: str
    event_type: str
    status: str
    title: str
    summary: Optional[str] = None
    detail: Optional[str] = None
    detail_json: Optional[dict[str, Any]] = None
    checkpoint_id: Optional[int] = None
    created_at: str


class StepEventListResponse(BaseModel):
    """步骤事件列表响应。"""

    task_id: str
    events: list[StepEvent]
    count: int
