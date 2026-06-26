"""聊天 API 路由契约测试 — RED 阶段。

所有测试当前应因路由/模块不存在而失败（404 / ImportError）。
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ═══════════════════════════════════════════════════════════════
# 路由前缀
# ═══════════════════════════════════════════════════════════════

def test_chat_router_prefix_is_api_v1_chat():
    """聊天路由前缀必须为 /api/v1/chat。"""
    from app.api.chat_routes import router

    assert router.prefix == "/api/v1/chat"


# ═══════════════════════════════════════════════════════════════
# GET /api/v1/chat/conversations
# ═══════════════════════════════════════════════════════════════

def test_get_conversations_returns_list():
    """GET /conversations 返回会话列表。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.list_all",
        return_value=[],
    ):
        response = client.get("/api/v1/chat/conversations")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_conversations_empty_when_no_data():
    """无会话时返回空列表。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.list_all",
        return_value=[],
    ):
        response = client.get("/api/v1/chat/conversations")

    assert response.status_code == 200
    assert response.json() == []


# ═══════════════════════════════════════════════════════════════
# POST /api/v1/chat/conversations
# ═══════════════════════════════════════════════════════════════

def test_post_conversations_creates_and_returns_201():
    """POST /conversations 创建会话并返回 201。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    fake_conv = {
        "id": "conv-001",
        "title": "新会话",
        "pinned": False,
        "archived": False,
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    }

    with patch(
        "app.persistence.chat_repository.ConversationRepository.create",
        return_value=fake_conv,
    ):
        response = client.post("/api/v1/chat/conversations", json={"title": "新会话"})

    assert response.status_code == 201
    data = response.json()
    assert data["id"] == "conv-001"
    assert data["title"] == "新会话"


def test_post_conversations_default_title():
    """POST /conversations 不传 title 时默认 '新会话'。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    fake_conv = {
        "id": "conv-002",
        "title": "新会话",
        "pinned": False,
        "archived": False,
    }

    with patch(
        "app.persistence.chat_repository.ConversationRepository.create",
        return_value=fake_conv,
    ):
        response = client.post("/api/v1/chat/conversations", json={})

    assert response.status_code == 201
    assert response.json()["title"] == "新会话"


# ═══════════════════════════════════════════════════════════════
# PATCH /api/v1/chat/conversations/{conversation_id}
# ═══════════════════════════════════════════════════════════════

def test_patch_conversation_rename():
    """PATCH /conversations/{id} 支持重命名。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.rename",
    ) as mock_rename:
        response = client.patch(
            "/api/v1/chat/conversations/conv-001",
            json={"title": "重命名会话"},
        )

    assert response.status_code == 200
    mock_rename.assert_called_once_with("conv-001", "重命名会话")


def test_patch_conversation_pin():
    """PATCH /conversations/{id} 支持置顶。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.set_pinned",
    ) as mock_pin:
        response = client.patch(
            "/api/v1/chat/conversations/conv-001",
            json={"pinned": True},
        )

    assert response.status_code == 200
    mock_pin.assert_called_once_with("conv-001", True)


def test_patch_conversation_archive():
    """PATCH /conversations/{id} 支持归档。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.archive",
    ) as mock_archive:
        response = client.patch(
            "/api/v1/chat/conversations/conv-001",
            json={"archived": True},
        )

    assert response.status_code == 200
    mock_archive.assert_called_once_with("conv-001")


def test_patch_nonexistent_conversation_returns_404():
    """PATCH 不存在的会话返回 404。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.rename",
        side_effect=LookupError("not found"),
    ):
        response = client.patch(
            "/api/v1/chat/conversations/nonexistent",
            json={"title": "不存在"},
        )

    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════
# DELETE /api/v1/chat/conversations/{conversation_id}
# ═══════════════════════════════════════════════════════════════

def test_delete_conversation_returns_204():
    """DELETE /conversations/{id} 返回 204。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.delete",
    ) as mock_delete:
        response = client.delete("/api/v1/chat/conversations/conv-001")

    assert response.status_code == 204
    mock_delete.assert_called_once_with("conv-001")


def test_delete_nonexistent_conversation_returns_404():
    """DELETE 不存在的会话返回 404。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.delete",
        side_effect=LookupError("not found"),
    ):
        response = client.delete("/api/v1/chat/conversations/nonexistent")

    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════
# GET /api/v1/chat/conversations/{conversation_id}/messages
# ═══════════════════════════════════════════════════════════════

def test_get_messages_returns_list():
    """GET /conversations/{id}/messages 返回消息列表。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.list_messages",
        return_value=[],
    ):
        response = client.get("/api/v1/chat/conversations/conv-001/messages")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_messages_ordered_asc():
    """消息列表按 created_at ASC 排序。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    fake_messages = [
        {"id": "m1", "role": "user", "content": "第一条", "created_at": "2025-01-01T10:00:00"},
        {"id": "m2", "role": "assistant", "content": "第二条", "created_at": "2025-01-01T10:01:00"},
    ]

    with patch(
        "app.persistence.chat_repository.ConversationRepository.list_messages",
        return_value=fake_messages,
    ):
        response = client.get("/api/v1/chat/conversations/conv-001/messages")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["id"] == "m1"
    assert data[-1]["id"] == "m2"


# ═══════════════════════════════════════════════════════════════
# POST /api/v1/chat/conversations/{conversation_id}/messages
# ═══════════════════════════════════════════════════════════════

def test_post_message_creates_and_returns_201():
    """POST /conversations/{id}/messages 创建消息并返回 201。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    fake_msg = {
        "id": "msg-001",
        "conversation_id": "conv-001",
        "role": "user",
        "content": "你好",
        "created_at": "2025-01-01T00:00:00",
    }

    with patch(
        "app.persistence.chat_repository.ConversationRepository.append_message",
        return_value=fake_msg,
    ):
        response = client.post(
            "/api/v1/chat/conversations/conv-001/messages",
            json={"role": "user", "content": "你好"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["role"] == "user"
    assert data["content"] == "你好"


def test_post_message_nonexistent_conversation_returns_404():
    """POST 消息到不存在的会话返回 404。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.append_message",
        side_effect=LookupError("conversation not found"),
    ):
        response = client.post(
            "/api/v1/chat/conversations/nonexistent/messages",
            json={"role": "user", "content": "你好"},
        )

    assert response.status_code == 404


def test_post_message_missing_role_returns_422():
    """POST 消息缺少 role 字段返回 422。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    response = client.post(
        "/api/v1/chat/conversations/conv-001/messages",
        json={"content": "缺少 role"},
    )

    assert response.status_code == 422


def test_post_message_missing_content_returns_422():
    """POST 消息缺少 content 字段返回 422。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    response = client.post(
        "/api/v1/chat/conversations/conv-001/messages",
        json={"role": "user"},
    )

    assert response.status_code == 422


# ═══════════════════════════════════════════════════════════════
# POST /api/v1/chat/conversations/{conversation_id}/summarize-title
# ═══════════════════════════════════════════════════════════════

def test_summarize_title_endpoint_exists():
    """POST /conversations/{id}/summarize-title 端点应存在并返回 200。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.update_title",
    ) as mock_update:
        response = client.post(
            "/api/v1/chat/conversations/conv-001/summarize-title",
            json={"user_message": "http://ids.chinasie.com/iidp/ 这个网址我用浏览器打开默认就会变成https，怎么解决，只能用http不能用https"},
        )

    assert response.status_code == 200
    mock_update.assert_called_once()
    data = response.json()
    assert "title" in data


def test_summarize_title_returns_short_chinese_title():
    """标题摘要应返回简短中文标题，不能是整段原文截断。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    long_input = (
        "http://ids.chinasie.com/iidp/ 这个网址我用浏览器打开默认就会变成https，"
        "怎么解决，只能用http不能用https"
    )

    with patch(
        "app.persistence.chat_repository.ConversationRepository.update_title",
    ):
        response = client.post(
            "/api/v1/chat/conversations/conv-001/summarize-title",
            json={"user_message": long_input},
        )

    assert response.status_code == 200
    data = response.json()
    title = data.get("title", "")
    # 标题必须是简短中文，不能是原文截断
    assert len(title) <= 30, f"标题过长: {title}"
    # 不能包含完整 URL 原文
    assert "ids.chinasie.com" not in title, f"标题包含原始URL: {title}"
    # 不能是 "http://ids.chinasie..." 这类截断
    assert not title.startswith("http"), f"标题以http开头: {title}"


def test_summarize_title_fallback_when_llm_unavailable():
    """LLM 不可用时标题摘要应有安全 fallback，不是简单原文截断。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    long_input = "A" * 200  # 超长输入

    with patch(
        "app.persistence.chat_repository.ConversationRepository.update_title",
    ):
        response = client.post(
            "/api/v1/chat/conversations/conv-001/summarize-title",
            json={"user_message": long_input},
        )

    assert response.status_code == 200
    data = response.json()
    title = data.get("title", "")
    # fallback 标题不应是原文截断（不应以 "AAAA" 开头）
    assert not title.startswith("AAAA"), f"fallback 标题是原文截断: {title}"
    assert len(title) <= 30, f"fallback 标题过长: {title}"


def test_summarize_title_missing_user_message_returns_422():
    """缺少 user_message 字段返回 422。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    response = client.post(
        "/api/v1/chat/conversations/conv-001/summarize-title",
        json={},
    )

    assert response.status_code == 422


def test_summarize_title_nonexistent_conversation_returns_404():
    """对不存在的会话调用标题摘要返回 404。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.update_title",
        side_effect=LookupError("not found"),
    ):
        response = client.post(
            "/api/v1/chat/conversations/nonexistent/summarize-title",
            json={"user_message": "测试消息"},
        )

    assert response.status_code == 404


# ═══════════════════════════════════════════════════════════════
# Task 8 QA 修复: PATCH message 端点（用于同消息报告持久化）
# ═══════════════════════════════════════════════════════════════


def test_patch_message_updates_report_snapshot():
    """PATCH /conversations/{cid}/messages/{mid} 必须支持更新 report_snapshot。

    任务流：assistant progress 消息先 push，SSE done 事件触发
    callReportAPI → appendReportToProgressMessage → PATCH 同消息更新报告。
    不创建第二条 assistant 报告消息。
    """
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    new_report = {"task_id": "rca-abc", "root_cause": "测试根因", "confidence": 0.9}
    fake_msg = {
        "id": "msg-001",
        "conversation_id": "conv-001",
        "role": "assistant",
        "content": "",
        "task_id": "rca-abc",
        "report_snapshot": new_report,
        "error": 0,
        "metadata": "{}",
        "created_at": "2025-01-01T00:00:00",
    }

    with patch(
        "app.persistence.chat_repository.ConversationRepository.update_message",
        return_value=fake_msg,
    ) as mock_update:
        response = client.patch(
            "/api/v1/chat/conversations/conv-001/messages/msg-001",
            json={"report_snapshot": new_report},
        )

    assert response.status_code == 200, (
        f"PATCH message 端点必须存在并返回 200，实际 {response.status_code}: {response.text}"
    )
    mock_update.assert_called_once()
    # 验证调用参数：必须传入 conversation_id, message_id, report_snapshot
    call_args = mock_update.call_args
    assert call_args.kwargs.get("report_snapshot") == new_report or (
        len(call_args.args) >= 3 and call_args.args[2] == new_report
    ), "update_message 必须接收 report_snapshot 参数"


def test_patch_message_404_for_nonexistent_conversation():
    """PATCH message 对不存在的会话返回 404。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    with patch(
        "app.persistence.chat_repository.ConversationRepository.update_message",
        side_effect=LookupError("not found"),
    ):
        response = client.patch(
            "/api/v1/chat/conversations/nonexistent/messages/msg-001",
            json={"report_snapshot": {"k": "v"}},
        )

    assert response.status_code == 404


def test_patch_message_schema_accepts_report_snapshot():
    """MessageUpdateRequest schema 必须存在并接受 report_snapshot 字段。"""
    from app.schemas.chat import MessageUpdateRequest

    req = MessageUpdateRequest(report_snapshot={"k": "v"})
    assert req.report_snapshot == {"k": "v"}


# ═══════════════════════════════════════════════════════════════
# 聊天意图识别与路由
# ═══════════════════════════════════════════════════════════════


def test_chat_execute_endpoint_exists():
    """POST /api/v1/chat/execute 端点必须存在并返回 200。"""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.main import app
    from app.schemas.chat import ChatExecuteResponse

    client = TestClient(app)
    fake_resp = ChatExecuteResponse(
        intent="knowledge_query",
        content="测试回答",
        items=[],
        metadata={"count": 0},
    )

    with patch(
        "app.api.chat_routes.classify_intent",
        return_value="knowledge_query",
    ), patch(
        "app.api.chat_routes.execute_by_intent",
        return_value=fake_resp,
    ):
        response = client.post(
            "/api/v1/chat/execute",
            json={"message": "查询知识库内容"},
        )

    assert response.status_code == 200, (
        f"POST /api/v1/chat/execute 应返回 200，实际 {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data.get("intent") == "knowledge_query"
    assert "content" in data


def test_chat_execute_knowledge_query_intent():
    """知识库查询类输入应返回 intent=knowledge_query，不触发 RCA 工作流。"""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.main import app
    from app.schemas.chat import ChatExecuteResponse

    client = TestClient(app)
    fake_resp = ChatExecuteResponse(
        intent="knowledge_query",
        content="共检索到 5 条相关知识库记录...",
        items=[
            {"index": 1, "content": "设备维保逾期导致...", "source": "SOP-001"},
        ],
        metadata={"top_k": 5, "count": 5},
    )

    with patch(
        "app.api.chat_routes.classify_intent",
        return_value="knowledge_query",
    ), patch(
        "app.api.chat_routes.execute_by_intent",
        return_value=fake_resp,
    ):
        response = client.post(
            "/api/v1/chat/execute",
            json={
                "message": "查询与工位超站相关的知识库内容，返回最相关的 5 条记录",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data.get("intent") == "knowledge_query", (
        f"知识库查询应返回 intent=knowledge_query，实际: {data.get('intent')}"
    )
    assert len(data.get("content", "")) > 0
    assert data.get("items") is not None


def test_chat_execute_rca_analysis_intent():
    """RCA 分析类输入应返回 intent=rca_analysis，但不启动工作流。"""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.main import app
    from app.schemas.chat import ChatExecuteResponse

    client = TestClient(app)
    fake_resp = ChatExecuteResponse(
        intent="rca_analysis",
        content="已识别为根因分析请求...",
        route="rca",
    )

    with patch(
        "app.api.chat_routes.classify_intent",
        return_value="rca_analysis",
    ), patch(
        "app.api.chat_routes.execute_by_intent",
        return_value=fake_resp,
    ):
        response = client.post(
            "/api/v1/chat/execute",
            json={
                "message": "工位 WS-03 连续 3 小时超站，帮我分析根因",
            },
        )

    assert response.status_code == 200
    data = response.json()
    assert data.get("intent") == "rca_analysis", (
        f"RCA 分析应返回 intent=rca_analysis，实际: {data.get('intent')}"
    )
    assert data.get("route") == "rca", (
        f"RCA 分析应返回 route=rca，实际: {data.get('route')}"
    )


def test_chat_execute_general_chat_intent():
    """普通问答应返回 intent=general_chat，不触发 RCA 工作流。"""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.main import app
    from app.schemas.chat import ChatExecuteResponse

    client = TestClient(app)
    fake_resp = ChatExecuteResponse(
        intent="general_chat",
        content="你好！我是制造业根因分析智能体助手。",
    )

    with patch(
        "app.api.chat_routes.classify_intent",
        return_value="general_chat",
    ), patch(
        "app.api.chat_routes.execute_by_intent",
        return_value=fake_resp,
    ):
        response = client.post(
            "/api/v1/chat/execute",
            json={"message": "你好，请问你能做什么？"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data.get("intent") == "general_chat", (
        f"普通问答应返回 intent=general_chat，实际: {data.get('intent')}"
    )


def test_chat_execute_data_query_intent():
    """数据查询类输入应返回 intent=data_query。"""
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    from app.main import app
    from app.schemas.chat import ChatExecuteResponse

    client = TestClient(app)
    fake_resp = ChatExecuteResponse(
        intent="data_query",
        content="查询返回 3 条记录。",
        items=[{"id": 1, "count": 42}],
        metadata={"sql": "SELECT ...", "count": 3},
    )

    with patch(
        "app.api.chat_routes.classify_intent",
        return_value="data_query",
    ), patch(
        "app.api.chat_routes.execute_by_intent",
        return_value=fake_resp,
    ):
        response = client.post(
            "/api/v1/chat/execute",
            json={"message": "查询最近 7 天的工单数量"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data.get("intent") == "data_query", (
        f"数据查询应返回 intent=data_query，实际: {data.get('intent')}"
    )


def test_chat_execute_missing_message_returns_422():
    """缺少 message 字段应返回 422。"""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    response = client.post("/api/v1/chat/execute", json={})

    assert response.status_code == 422


def test_chat_execute_schema_exists():
    """ChatExecuteRequest 和 ChatExecuteResponse schema 必须存在。"""
    from app.schemas.chat import ChatExecuteRequest, ChatExecuteResponse

    req = ChatExecuteRequest(message="测试消息")
    assert req.message == "测试消息"
    assert req.conversation_id is None

    resp = ChatExecuteResponse(
        intent="knowledge_query",
        content="测试回答",
    )
    assert resp.intent == "knowledge_query"
    assert resp.content == "测试回答"


def test_chat_intent_rules_classify_user_knowledge_example():
    """规则 fallback 必须能将用户截图中的查询诉求识别为知识库查询。"""
    from app.api.chat_execute import _classify_via_rules

    intent = _classify_via_rules(
        "查询与工位超站可能由设备维保逾期、焊枪磨损或设备故障导致相关的知识库内容，"
        "返回最相关的 5 条记录，并说明每条记录为什么相关。"
    )

    assert intent == "knowledge_query"


def test_chat_execute_classify_intent_rules():
    """规则 fallback 必须能正确分类各类输入。"""
    from app.api.chat_execute import _classify_via_rules

    # 知识库查询
    assert _classify_via_rules(
        "查询与工位超站相关的知识库内容，返回最相关的 5 条记录，并说明每条记录为什么相关"
    ) == "knowledge_query"

    # 数据查询
    assert _classify_via_rules("查询最近 7 天的工单数量") == "data_query"

    # RCA 分析
    assert _classify_via_rules(
        "工位 WS-03 连续 3 小时超站，帮我分析根因"
    ) == "rca_analysis"

    # 普通问答
    assert _classify_via_rules("你好，请问你能做什么？") == "general_chat"


def test_chat_execute_rca_does_not_call_analyze_api():
    """rca_analysis 路径不得调用 /api/v1/rca/analyze。"""
    from unittest.mock import patch

    from app.api.chat_execute import _execute_rca_analysis

    resp = _execute_rca_analysis("帮我分析根因")
    assert resp.intent == "rca_analysis"
    assert resp.route == "rca"
    # 确认 content 不包含 task_id（说明没有启动工作流）
    assert "task_id" not in resp.content.lower()


def test_knowledge_query_default_top_k_uses_rag_config(monkeypatch):
    from unittest.mock import Mock

    import app.api.chat_execute as chat_execute
    import app.config

    monkeypatch.setattr(app.config.settings, "rag_top_k", 7)
    monkeypatch.setattr(
        chat_execute,
        "_generate_knowledge_answer",
        Mock(return_value="测试知识库回答"),
    )

    search = Mock(return_value=[
        {
            "content": "设备维保逾期可能导致工位超站",
            "source": "SOP-001",
            "hybrid_score": 0.8,
            "anomaly_type": "overstation_check",
        }
    ])
    retriever = Mock()
    retriever.search = search
    monkeypatch.setattr("app.rag.hybrid_retriever.HybridRetriever", Mock(return_value=retriever))

    response = chat_execute._execute_knowledge_query("查询工位超站知识")

    search.assert_called_once_with(query="查询工位超站知识", anomaly_type="", top_k=7)
    assert response.metadata == {"top_k": 7, "count": 1}
