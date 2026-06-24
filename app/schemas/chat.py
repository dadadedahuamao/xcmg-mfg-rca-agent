"""聊天 API 请求 Schema。"""

from typing import Optional

from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    """创建会话请求。"""

    title: Optional[str] = Field(default="新会话", description="会话标题")


class ConversationUpdateRequest(BaseModel):
    """更新会话请求。"""

    title: Optional[str] = Field(default=None, description="新标题")
    pinned: Optional[bool] = Field(default=None, description="是否置顶")
    archived: Optional[bool] = Field(default=None, description="是否归档")


class MessageCreateRequest(BaseModel):
    """创建消息请求。"""

    role: str = Field(..., description="消息角色：user / assistant / system")
    content: str = Field(..., description="消息内容")
    anomaly_type: Optional[str] = Field(default=None, description="异常类型")
    task_id: Optional[str] = Field(default=None, description="RCA 任务 ID")
    report_snapshot: Optional[dict] = Field(default=None, description="RCA 报告快照")
    error: Optional[bool] = Field(default=False, description="是否错误消息")
    metadata: Optional[dict] = Field(default=None, description="附加元数据")


class SummarizeTitleRequest(BaseModel):
    """标题摘要请求。"""

    user_message: str = Field(..., description="用户首条消息内容")


class MessageUpdateRequest(BaseModel):
    """更新消息请求（Task 8 QA：用于同消息报告持久化）。

    任务流：assistant progress 消息先 push 到会话；SSE done 事件触发
    callReportAPI → appendReportToProgressMessage → PATCH 同消息更新
    report_snapshot，避免创建第二条 assistant 报告消息。

    所有字段可选；至少传 report_snapshot 即可完成核心用例。
    """

    content: Optional[str] = Field(default=None, description="消息内容")
    report_snapshot: Optional[dict] = Field(
        default=None, description="RCA 报告快照（用于同消息进度+报告合并）"
    )
    error: Optional[bool] = Field(default=None, description="是否错误消息")
    metadata: Optional[dict] = Field(default=None, description="附加元数据")


# ═══════════════════════════════════════════════════════════════
# 聊天意图识别与路由
# ═══════════════════════════════════════════════════════════════


class ChatExecuteRequest(BaseModel):
    """聊天执行请求 — 意图识别与路由。"""

    message: str = Field(..., description="用户消息文本")
    conversation_id: Optional[str] = Field(default=None, description="关联的会话 ID")


class ChatExecuteResponse(BaseModel):
    """聊天执行响应 — 根据意图返回不同内容。"""

    intent: str = Field(
        ...,
        description="意图类型：knowledge_query / data_query / general_chat / rca_analysis",
    )
    content: str = Field(default="", description="响应文本内容")
    route: Optional[str] = Field(
        default=None, description="路由目标：rca（仅 rca_analysis 时返回）"
    )
    items: Optional[list[dict]] = Field(
        default=None, description="结构化数据项（知识库/数据查询结果）"
    )
    metadata: Optional[dict] = Field(
        default=None, description="附加元数据（如 top_k、score 等）"
    )
