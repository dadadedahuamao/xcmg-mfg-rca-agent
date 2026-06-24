"""聊天 API 路由 — 会话与消息管理。"""

import logging

from fastapi import APIRouter, HTTPException, Response

from app.persistence.chat_repository import ConversationRepository
from app.schemas.chat import (
    ChatExecuteRequest,
    ChatExecuteResponse,
    ConversationCreateRequest,
    ConversationUpdateRequest,
    MessageCreateRequest,
    MessageUpdateRequest,
    SummarizeTitleRequest,
)
from app.api.chat_execute import classify_intent, execute_by_intent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])


# ═══════════════════════════════════════════════════════════════
# 会话管理
# ═══════════════════════════════════════════════════════════════


@router.get("/conversations")
async def list_conversations():
    """获取会话列表。"""
    return ConversationRepository.list_all()


@router.post("/conversations", status_code=201)
async def create_conversation(request: ConversationCreateRequest):
    """创建新会话。"""
    return ConversationRepository.create(title=request.title or "新会话")


@router.patch("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, request: ConversationUpdateRequest):
    """更新会话（重命名 / 置顶 / 归档）。"""
    try:
        if request.title is not None:
            ConversationRepository.rename(conversation_id, request.title)
        if request.pinned is not None:
            ConversationRepository.set_pinned(conversation_id, request.pinned)
        if request.archived is True:
            ConversationRepository.archive(conversation_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str):
    """删除会话。"""
    try:
        ConversationRepository.delete(conversation_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="会话不存在")
    return Response(status_code=204)


# ═══════════════════════════════════════════════════════════════
# 消息管理
# ═══════════════════════════════════════════════════════════════


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(conversation_id: str):
    """获取会话消息列表。"""
    return ConversationRepository.list_messages(conversation_id)


@router.post("/conversations/{conversation_id}/messages", status_code=201)
async def create_message(conversation_id: str, request: MessageCreateRequest):
    """向会话追加消息。"""
    try:
        return ConversationRepository.append_message(
            conversation_id,
            role=request.role,
            content=request.content,
            anomaly_type=request.anomaly_type,
            task_id=request.task_id,
            report_snapshot=request.report_snapshot,
            error=request.error or False,
            metadata=request.metadata,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="会话不存在")


@router.patch("/conversations/{conversation_id}/messages/{message_id}")
async def update_message(
    conversation_id: str,
    message_id: str,
    request: MessageUpdateRequest,
):
    """更新已存在的消息（Task 8 QA：用于同消息报告持久化）。

    任务流：assistant progress 消息先 POST 推送；SSE done 事件触发
    callReportAPI → appendReportToProgressMessage → PATCH 同消息
    写入 report_snapshot，避免创建第二条 assistant 报告消息。

    所有字段可选；至少传 report_snapshot 即可完成核心用例。
    """
    try:
        return ConversationRepository.update_message(
            conversation_id,
            message_id,
            content=request.content,
            report_snapshot=request.report_snapshot,
            error=request.error,
            metadata=request.metadata,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="消息不存在")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ═══════════════════════════════════════════════════════════════
# 聊天意图识别与路由
# ═══════════════════════════════════════════════════════════════


@router.post("/execute", response_model=ChatExecuteResponse)
async def chat_execute(request: ChatExecuteRequest):
    """聊天意图识别与路由执行。

    识别用户消息意图（knowledge_query / data_query / general_chat / rca_analysis），
    并执行对应的处理路径。

    - knowledge_query: 检索知识库并生成可读回答
    - data_query: 执行 Text2SQL 数据查询
    - general_chat: LLM 普通问答
    - rca_analysis: 仅返回 intent + route，前端自行调用 runAnalysis()
    """
    intent = classify_intent(request.message)
    logger.info(
        "聊天意图识别: intent=%s message=%.80s",
        intent,
        request.message,
    )
    return execute_by_intent(intent, request.message)


# ═══════════════════════════════════════════════════════════════
# 标题摘要
# ═══════════════════════════════════════════════════════════════


def _fallback_title(user_message: str) -> str:
    """LLM 不可用时的安全本地标题 fallback。

    不直接截断原文，而是基于消息特征生成通用标题。
    """
    msg = user_message.strip()
    # 检测是否包含异常类型关键词
    anomaly_keywords = {
        "超站": "超站检查问题",
        "设备冲突": "设备冲突问题",
        "物料短缺": "物料短缺问题",
        "质量异常": "质量异常问题",
        "接口超时": "接口超时问题",
        "排程风险": "排程风险问题",
        "http": "网络配置问题",
        "https": "HTTPS配置问题",
        "错误": "系统错误排查",
        "报错": "系统错误排查",
        "失败": "任务失败分析",
        "超时": "超时问题分析",
        "怎么": "技术问题咨询",
        "如何": "技术问题咨询",
        "为什么": "根因分析",
    }
    for keyword, title in anomaly_keywords.items():
        if keyword.lower() in msg.lower():
            return title
    # 通用 fallback
    return "异常分析"


def _summarize_title_via_llm(user_message: str) -> str:
    """通过 LLM 生成简短中文标题。"""
    from app.llm.client import llm_client
    from app.prompts.templates import PromptManager

    pm = PromptManager()
    template = pm.load("summarize_title")
    result = llm_client.complete(template, user_message)
    title = result.strip().strip('"').strip("'").strip("。").strip("，")
    # 限制长度
    if len(title) > 30:
        title = title[:30]
    return title or _fallback_title(user_message)


@router.post("/conversations/{conversation_id}/summarize-title")
async def summarize_title(conversation_id: str, request: SummarizeTitleRequest):
    """为会话生成 LLM 摘要标题并持久化。

    优先调用 LLM 生成简短中文标题，LLM 不可用时使用安全本地 fallback。
    """
    user_message = request.user_message.strip()
    if not user_message:
        raise HTTPException(status_code=422, detail="user_message 不能为空")

    # 尝试 LLM 摘要
    try:
        from app.llm.client import llm_client

        if llm_client.enabled:
            title = _summarize_title_via_llm(user_message)
        else:
            title = _fallback_title(user_message)
    except Exception:
        logger.warning("LLM 标题摘要失败，使用 fallback", exc_info=True)
        title = _fallback_title(user_message)

    # 持久化
    try:
        ConversationRepository.update_title(conversation_id, title)
    except Exception:
        raise HTTPException(status_code=404, detail="会话不存在")

    return {"title": title}
