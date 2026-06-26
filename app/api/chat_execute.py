"""聊天意图识别与路由执行模块。

职责：
1. 意图识别：LLM 优先 + 规则 fallback
2. 路由执行：knowledge_query / data_query / general_chat / rca_analysis
"""

import logging
from typing import Any

from app.schemas.chat import ChatExecuteResponse

logger = logging.getLogger(__name__)

# ── 意图类型常量 ──────────────────────────────────────────────
INTENT_KNOWLEDGE_QUERY = "knowledge_query"
INTENT_DATA_QUERY = "data_query"
INTENT_GENERAL_CHAT = "general_chat"
INTENT_RCA_ANALYSIS = "rca_analysis"

# ── 规则 fallback 关键词 ──────────────────────────────────────
_KNOWLEDGE_KEYWORDS = [
    "知识库", "最相关", "记录", "为什么相关", "检索", "查询.*知识",
    "相关.*文档", "相关.*记录", "相关.*知识", "查找.*知识", "搜索.*知识",
    "SOP", "最佳实践", "操作手册", "维修手册",
]
_DATA_KEYWORDS = [
    "查询.*工单", "查询.*数量", "查询.*记录", "统计", "汇总",
    "最近.*天", "最近.*小时", "有多少", "几个", "多少条",
    "工单.*状态", "库存.*数量", "设备.*状态",
]
_RCA_KEYWORDS = [
    "分析.*根因", "根因分析", "分析.*原因", "为什么.*超站",
    "为什么.*故障", "为什么.*异常", "排查.*原因", "定位.*根因",
    "帮我分析", "分析一下", "分析.*问题", "诊断",
    "超站.*分析", "设备.*分析", "物料.*分析", "质量.*分析",
]


def classify_intent(message: str) -> str:
    """意图识别：LLM 优先 + 规则 fallback。

    Args:
        message: 用户消息文本

    Returns:
        意图类型：knowledge_query / data_query / general_chat / rca_analysis
    """
    # 1. 尝试 LLM 分类
    try:
        intent = _classify_via_llm(message)
        if intent:
            return intent
    except Exception:
        logger.warning("LLM 意图分类失败，使用规则 fallback", exc_info=True)

    # 2. 规则 fallback
    return _classify_via_rules(message)


def _classify_via_llm(message: str) -> str | None:
    """通过 LLM 分类意图。"""
    import json
    import re

    from app.llm.client import llm_client

    if not llm_client.enabled:
        return None

    system_prompt = (
        '你是一个意图分类器。分析用户消息，判断其意图类型。\n'
        '只返回一个 JSON 对象，格式：{"intent": "<类型>"}\n'
        '类型只能是以下之一：\n'
        '- knowledge_query: 查询知识库、检索文档、查找SOP/最佳实践/操作手册\n'
        '- data_query: 查询数据库、统计数据、查询工单/库存/设备状态\n'
        '- rca_analysis: 根因分析、排查异常原因、诊断问题\n'
        '- general_chat: 普通闲聊、问候、能力询问、不属于以上三类\n\n'
        '规则：\n'
        '- 提到\u201c知识库\u201d\u201c检索\u201d\u201c最相关\u201d\u201c记录\u201d\u201cSOP\u201d\u201c最佳实践\u201d -> knowledge_query\n'
        '- 提到\u201c查询\u201d\u201c统计\u201d\u201c有多少\u201d\u201c最近X天\u201d\u201c工单数量\u201d -> data_query\n'
        '- 提到\u201c分析根因\u201d\u201c排查原因\u201d\u201c为什么超站\u201d\u201c诊断\u201d -> rca_analysis\n'
        '- 其他 -> general_chat'
    )

    from app.prompts.templates import PromptTemplate

    template_data = {
        "node_name": "intent_classifier",
        "description": "意图分类",
        "system_prompt": system_prompt,
        "user_prompt_template": "{message}",
        "variables": [],
        "temperature": 0.1,
        "max_tokens": 100,
    }
    template = PromptTemplate(template_data)

    try:
        result = llm_client.complete_json(template, message)
        intent = result.get("intent", "").strip().lower()
        valid_intents = {
            INTENT_KNOWLEDGE_QUERY,
            INTENT_DATA_QUERY,
            INTENT_GENERAL_CHAT,
            INTENT_RCA_ANALYSIS,
        }
        if intent in valid_intents:
            return intent
    except Exception:
        pass

    return None


def _classify_via_rules(message: str) -> str:
    """基于规则的关键词匹配分类。"""
    import re

    msg = message.strip()

    # 1. 知识库查询关键词
    for kw in _KNOWLEDGE_KEYWORDS:
        if re.search(kw, msg):
            return INTENT_KNOWLEDGE_QUERY

    # 2. 数据查询关键词
    for kw in _DATA_KEYWORDS:
        if re.search(kw, msg):
            return INTENT_DATA_QUERY

    # 3. RCA 分析关键词
    for kw in _RCA_KEYWORDS:
        if re.search(kw, msg):
            return INTENT_RCA_ANALYSIS

    # 4. 默认普通问答
    return INTENT_GENERAL_CHAT


# ── 路由执行 ──────────────────────────────────────────────────


def execute_by_intent(intent: str, message: str) -> ChatExecuteResponse:
    """根据意图类型执行对应的处理路径。

    Args:
        intent: 意图类型
        message: 用户消息文本

    Returns:
        ChatExecuteResponse 响应对象
    """
    if intent == INTENT_KNOWLEDGE_QUERY:
        return _execute_knowledge_query(message)
    elif intent == INTENT_DATA_QUERY:
        return _execute_data_query(message)
    elif intent == INTENT_RCA_ANALYSIS:
        return _execute_rca_analysis(message)
    else:
        return _execute_general_chat(message)


def _execute_knowledge_query(message: str, top_k: int | None = None) -> ChatExecuteResponse:
    """执行知识库查询。

    复用 HybridRetriever.search() 检索知识库，
    然后用 LLM 生成可读回答，包含每条记录为什么相关。
    """
    from app.rag.hybrid_retriever import HybridRetriever
    from app.config import settings

    resolved_top_k = top_k or settings.rag_top_k
    retriever = HybridRetriever()
    results = retriever.search(query=message, anomaly_type="", top_k=resolved_top_k)

    if not results:
        return ChatExecuteResponse(
            intent=INTENT_KNOWLEDGE_QUERY,
            content="未找到相关知识库内容，请尝试调整查询关键词。",
            items=[],
            metadata={"top_k": resolved_top_k, "count": 0},
        )

    # 构建 items 列表（结构化结果）
    items = []
    for i, doc in enumerate(results):
        item = {
            "index": i + 1,
            "content": doc.get("content", "")[:500],
            "source": doc.get("source", doc.get("title", "未知来源")),
            "score": round(doc.get("hybrid_score", doc.get("score", 0)), 4),
            "anomaly_type": doc.get("anomaly_type", ""),
        }
        # 添加 rerank_reason 或 score 解释
        score = doc.get("hybrid_score", doc.get("score", 0))
        if score >= 0.7:
            item["relevance_reason"] = "高度相关：关键词和语义均高度匹配"
        elif score >= 0.4:
            item["relevance_reason"] = "中度相关：部分关键词或语义匹配"
        else:
            item["relevance_reason"] = "低度相关：存在弱关联"

        items.append(item)

    # 尝试用 LLM 生成可读回答
    content = _generate_knowledge_answer(message, items)

    return ChatExecuteResponse(
        intent=INTENT_KNOWLEDGE_QUERY,
        content=content,
        items=items,
        metadata={"top_k": resolved_top_k, "count": len(items)},
    )


def _generate_knowledge_answer(message: str, items: list[dict]) -> str:
    """用 LLM 生成知识库查询的可读回答。"""
    try:
        from app.llm.client import llm_client

        if not llm_client.enabled:
            return _build_fallback_knowledge_answer(items)

        items_text = ""
        for item in items:
            items_text += (
                f"\n### 记录 {item['index']}\n"
                f"- 来源: {item['source']}\n"
                f"- 相关度: {item['score']}\n"
                f"- 内容: {item['content']}\n"
                f"- 相关原因: {item['relevance_reason']}\n"
            )

        system_prompt = (
            "你是一个制造业知识库助手。根据检索到的知识库记录，"
            "生成一个清晰、有条理的回答。\n"
            "要求：\n"
            "1. 先总结检索到的核心知识点\n"
            "2. 逐条说明每条记录的内容和为什么与用户查询相关\n"
            "3. 使用中文，简洁专业"
        )

        from app.prompts.templates import PromptTemplate

        template_data = {
            "node_name": "knowledge_answer",
            "description": "知识库回答生成",
            "system_prompt": system_prompt,
            "user_prompt_template": "用户查询: {message}\n\n检索结果:\n{items}",
            "variables": [],
            "temperature": 0.3,
            "max_tokens": 2000,
        }
        template = PromptTemplate(template_data)

        user_prompt = f"用户查询: {message}\n\n检索结果:\n{items_text}"
        return llm_client.complete(template, user_prompt)
    except Exception:
        logger.warning("LLM 生成知识库回答失败，使用 fallback", exc_info=True)
        return _build_fallback_knowledge_answer(items)


def _build_fallback_knowledge_answer(items: list[dict]) -> str:
    """LLM 不可用时构建知识库查询的 fallback 回答。"""
    if not items:
        return "未找到相关知识库内容。"

    lines = [f"共检索到 {len(items)} 条相关知识库记录：\n"]
    for item in items:
        lines.append(
            f"### 记录 {item['index']}（相关度: {item['score']}）\n"
            f"- 来源: {item['source']}\n"
            f"- 内容摘要: {item['content'][:200]}...\n"
            f"- 相关原因: {item['relevance_reason']}\n"
        )
    return "\n".join(lines)


def _execute_data_query(message: str) -> ChatExecuteResponse:
    """执行数据查询。

    复用 Text2SQLTool 执行自然语言转 SQL 查询。
    """
    try:
        from app.tools.text2sql_tool import Text2SQLTool

        tool = Text2SQLTool()
        result = tool.execute({
            "task_id": "chat-data-query",
            "query": message,
        })

        if result.get("success"):
            data = result.get("data", [])
            sql = result.get("sql", "")
            columns = result.get("columns", [])
            count = result.get("count", 0)

            # 构建回答
            if count == 0:
                content = "查询未返回任何数据。"
            else:
                content = f"查询返回 {count} 条记录。\nSQL: {sql}\n"
                if columns:
                    content += f"字段: {', '.join(columns)}\n"
                # 展示前 5 条
                for i, row in enumerate(data[:5]):
                    content += f"\n{i + 1}. {row}"

            return ChatExecuteResponse(
                intent=INTENT_DATA_QUERY,
                content=content,
                items=data[:20],
                metadata={
                    "sql": sql,
                    "columns": columns,
                    "count": count,
                    "execution_time_ms": result.get("execution_time_ms"),
                },
            )
        else:
            return ChatExecuteResponse(
                intent=INTENT_DATA_QUERY,
                content=f"数据查询失败: {result.get('error', '未知错误')}",
                metadata={"error": result.get("error")},
            )
    except Exception as e:
        logger.warning("数据查询执行失败: %s", e, exc_info=True)
        return ChatExecuteResponse(
            intent=INTENT_DATA_QUERY,
            content=f"数据查询暂时不可用: {str(e)}",
        )


def _execute_general_chat(message: str) -> ChatExecuteResponse:
    """执行普通问答。

    复用 llm_client.complete 生成回答；LLM 不可用时返回明确提示。
    """
    try:
        from app.llm.client import llm_client

        if not llm_client.enabled:
            return ChatExecuteResponse(
                intent=INTENT_GENERAL_CHAT,
                content=(
                    "你好！我是制造业根因分析智能体助手。\n\n"
                    "我可以帮你：\n"
                    "- 🔍 查询知识库：检索 SOP、最佳实践、操作手册\n"
                    "- 📊 查询数据：工单、设备、物料、质量等数据统计\n"
                    "- 🩺 根因分析：分析生产异常事件，定位根因并生成报告\n\n"
                    "请描述你的问题，我会自动识别意图并处理。"
                ),
            )

        system_prompt = (
            "你是一个制造业根因分析智能体助手。你可以帮助用户：\n"
            "1. 查询知识库（SOP、最佳实践、操作手册）\n"
            "2. 查询生产数据（工单、设备、物料、质量）\n"
            "3. 执行根因分析（分析异常事件，定位根因）\n\n"
            "请用中文简洁专业地回答用户问题。"
        )

        from app.prompts.templates import PromptTemplate

        template_data = {
            "node_name": "general_chat",
            "description": "普通问答",
            "system_prompt": system_prompt,
            "user_prompt_template": "{message}",
            "variables": [],
            "temperature": 0.5,
            "max_tokens": 1000,
        }
        template = PromptTemplate(template_data)

        content = llm_client.complete(template, message)
        return ChatExecuteResponse(
            intent=INTENT_GENERAL_CHAT,
            content=content.strip(),
        )
    except Exception as e:
        logger.warning("普通问答 LLM 调用失败: %s", e, exc_info=True)
        return ChatExecuteResponse(
            intent=INTENT_GENERAL_CHAT,
            content=(
                "抱歉，LLM 服务暂时不可用。\n\n"
                "我仍然可以帮你：\n"
                "- 查询知识库（检索 SOP、最佳实践）\n"
                "- 查询生产数据（工单、设备、物料统计）\n"
                "- 根因分析（分析异常事件）\n\n"
                "请描述具体问题，我会尝试用其他方式处理。"
            ),
        )


def _execute_rca_analysis(message: str) -> ChatExecuteResponse:
    """RCA 分析路径：仅返回 intent 和 route，不在此端点内启动工作流。

    前端收到 intent=rca_analysis 后，自行调用 runAnalysis() 触发 RCA 工作流。
    """
    return ChatExecuteResponse(
        intent=INTENT_RCA_ANALYSIS,
        content="已识别为根因分析请求，即将启动 RCA 工作流进行分析...",
        route="rca",
    )
