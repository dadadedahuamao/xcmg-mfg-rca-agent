"""聊天持久化 Repository 契约测试 — RED 阶段。

所有测试当前应因模块/表不存在而失败（ImportError / ModuleNotFoundError）。
"""

import sys
import re
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

def _mock_connection() -> Mock:
    conn = Mock()
    conn.execute.return_value = Mock()
    conn.execute.return_value.fetchone.return_value = None
    conn.execute.return_value.fetchall.return_value = []
    return conn


# ═══════════════════════════════════════════════════════════════
# ADMIN_USER_ID
# ═══════════════════════════════════════════════════════════════

def test_admin_user_id_is_fixed():
    """固定管理员用户 ID 必须为 'admin'。"""
    from app.persistence.chat_repository import ADMIN_USER_ID

    assert ADMIN_USER_ID == "admin"


# ═══════════════════════════════════════════════════════════════
# 创建会话
# ═══════════════════════════════════════════════════════════════

def test_create_conversation_inserts_row():
    """创建会话必须 INSERT 一行并返回完整记录。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    fake_row = {
        "id": "conv-001",
        "title": "新会话",
        "pinned": False,
        "archived": False,
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    }
    conn.execute.return_value.fetchone.return_value = fake_row

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        result = ConversationRepository.create(title="新会话")

    conn.execute.assert_called()
    conn.commit.assert_called_once()
    assert result["id"] == "conv-001"
    assert result["title"] == "新会话"


def test_create_conversation_default_title():
    """创建会话时 title 默认为 '新会话'。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    fake_row = {"id": "conv-002", "title": "新会话", "pinned": False, "archived": False}
    conn.execute.return_value.fetchone.return_value = fake_row

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        result = ConversationRepository.create()

    assert result["title"] == "新会话"


def test_create_conversation_uses_database_timestamp_format():
    """创建会话写入的时间必须使用数据库时间戳文本格式。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchone.return_value = {
        "id": "conv-001", "title": "新会话", "pinned": False, "archived": False,
    }

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.create(title="新会话")

    insert_params = conn.execute.call_args_list[0][0][1]
    created_at = insert_params[3]
    updated_at = insert_params[4]
    timestamp_pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$"
    assert re.match(timestamp_pattern, created_at)
    assert re.match(timestamp_pattern, updated_at)


# ═══════════════════════════════════════════════════════════════
# 列表排序
# ═══════════════════════════════════════════════════════════════

def test_list_conversations_pinned_first():
    """列表查询必须 pinned 优先，再按 updated_at DESC。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    rows = [
        {"id": "c1", "title": "置顶会话", "pinned": True, "archived": False, "updated_at": "2025-01-01"},
        {"id": "c2", "title": "普通会话", "pinned": False, "archived": False, "updated_at": "2025-06-01"},
    ]
    conn.execute.return_value.fetchall.return_value = rows

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        result = ConversationRepository.list_all()

    assert len(result) == 2
    assert result[0]["pinned"] is True
    assert result[1]["pinned"] is False


def test_list_conversations_excludes_archived():
    """列表查询默认排除已归档会话。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchall.return_value = [
        {"id": "c1", "title": "活跃", "pinned": False, "archived": False}
    ]

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        result = ConversationRepository.list_all()

    # 验证 SQL 包含 archived = false 过滤
    sql_called = conn.execute.call_args[0][0].lower()
    assert "archived" in sql_called
    assert len(result) == 1


# ═══════════════════════════════════════════════════════════════
# 重命名
# ═══════════════════════════════════════════════════════════════

def test_rename_conversation_updates_title():
    """重命名会话必须 UPDATE title 和 updated_at。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.rename("conv-001", "新标题")

    conn.execute.assert_called()
    conn.commit.assert_called_once()
    sql_called = conn.execute.call_args[0][0].lower()
    assert "update" in sql_called
    assert "title" in sql_called


def test_update_title_uses_database_timestamp_format():
    """LLM 摘要更新标题时 updated_at 必须使用数据库时间戳格式。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.update_title("conv-001", "摘要标题")

    update_params = conn.execute.call_args_list[0][0][1]
    timestamp_pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$"
    assert re.match(timestamp_pattern, update_params[1])


# ═══════════════════════════════════════════════════════════════
# 置顶
# ═══════════════════════════════════════════════════════════════

def test_pin_conversation_toggles_pinned():
    """置顶操作必须 UPDATE pinned 字段。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.set_pinned("conv-001", True)

    conn.execute.assert_called()
    conn.commit.assert_called_once()
    sql_called = conn.execute.call_args[0][0].lower()
    assert "update" in sql_called
    assert "pinned" in sql_called


# ═══════════════════════════════════════════════════════════════
# 归档
# ═══════════════════════════════════════════════════════════════

def test_archive_conversation_sets_archived():
    """归档操作必须 UPDATE archived = true。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.archive("conv-001")

    conn.execute.assert_called()
    conn.commit.assert_called_once()
    sql_called = conn.execute.call_args[0][0].lower()
    assert "update" in sql_called
    assert "archived" in sql_called


# ═══════════════════════════════════════════════════════════════
# 硬删除级联
# ═══════════════════════════════════════════════════════════════

def test_delete_conversation_cascades_messages():
    """硬删除会话必须级联删除关联消息。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.delete("conv-001")

    conn.execute.assert_called()
    conn.commit.assert_called_once()
    # 至少执行了两次 execute（先删消息，再删会话）
    assert conn.execute.call_count >= 2


# ═══════════════════════════════════════════════════════════════
# 追加消息
# ═══════════════════════════════════════════════════════════════

def test_append_message_inserts_row():
    """追加消息必须 INSERT 一行并返回完整记录。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    fake_msg = {
        "id": "msg-001",
        "conversation_id": "conv-001",
        "role": "user",
        "content": "你好",
        "created_at": "2025-01-01T00:00:00",
    }
    conn.execute.return_value.fetchone.return_value = fake_msg

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        result = ConversationRepository.append_message(
            conversation_id="conv-001", role="user", content="你好"
        )

    conn.execute.assert_called()
    conn.commit.assert_called_once()
    assert result["role"] == "user"
    assert result["content"] == "你好"


def test_append_message_updates_conversation_updated_at():
    """追加消息后必须更新所属会话的 updated_at。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchone.return_value = {
        "id": "msg-001", "conversation_id": "conv-001",
        "role": "user", "content": "测试",
    }

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.append_message(
            conversation_id="conv-001", role="user", content="测试"
        )

    # 验证至少有一条 UPDATE 语句更新了 updated_at
    update_calls = [
        c for c in conn.execute.call_args_list
        if "update" in str(c[0][0]).lower() and "updated_at" in str(c[0][0]).lower()
    ]
    assert len(update_calls) >= 1


def test_append_message_updates_conversation_last_message_at():
    """追加消息后必须同步更新所属会话的 last_message_at。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchone.return_value = {
        "id": "msg-001", "conversation_id": "conv-001",
        "role": "user", "content": "测试",
    }

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.append_message(
            conversation_id="conv-001", role="user", content="测试"
        )

    update_calls = [
        c for c in conn.execute.call_args_list
        if "update" in str(c[0][0]).lower()
        and "last_message_at" in str(c[0][0]).lower()
    ]
    assert len(update_calls) >= 1


# ═══════════════════════════════════════════════════════════════
# 消息排序
# ═══════════════════════════════════════════════════════════════

def test_list_messages_ordered_by_created_at_asc():
    """消息列表必须按 created_at ASC 排序。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchall.return_value = [
        {"id": "m1", "created_at": "2025-01-01T10:00:00"},
        {"id": "m2", "created_at": "2025-01-01T10:01:00"},
        {"id": "m3", "created_at": "2025-01-01T10:02:00"},
    ]

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        result = ConversationRepository.list_messages("conv-001")

    assert len(result) == 3
    assert result[0]["id"] == "m1"
    assert result[-1]["id"] == "m3"


def test_list_messages_filters_by_conversation_id():
    """消息列表必须按 conversation_id 过滤。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchall.return_value = []

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.list_messages("conv-001")

    sql_called = conn.execute.call_args[0][0].lower()
    params = conn.execute.call_args[0][1]
    assert "conversation_id" in sql_called
    assert "conv-001" in params


# ═══════════════════════════════════════════════════════════════
# 连接管理
# ═══════════════════════════════════════════════════════════════

def test_repository_closes_connection_after_operation():
    """每个 Repository 方法执行后必须关闭连接。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchone.return_value = {
        "id": "conv-001", "title": "测试", "pinned": False, "archived": False,
    }

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.create(title="测试")

    conn.close.assert_called_once()


# ═══════════════════════════════════════════════════════════════
# Task 5: task_id 在 assistant 消息中的保存与返回
# ═══════════════════════════════════════════════════════════════

def test_append_message_stores_task_id():
    """append_message 必须将 task_id 写入 chat_messages 表并返回。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    fake_msg = {
        "id": "msg-001",
        "conversation_id": "conv-001",
        "role": "assistant",
        "content": "",
        "task_id": "rca-abc123",
        "report_snapshot": '{"key":"val"}',
        "created_at": "2025-01-01T00:00:00",
    }
    conn.execute.return_value.fetchone.return_value = fake_msg

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        result = ConversationRepository.append_message(
            conversation_id="conv-001",
            role="assistant",
            content="",
            task_id="rca-abc123",
            report_snapshot={"key": "val"},
        )

    assert result["task_id"] == "rca-abc123", (
        "append_message 返回结果必须包含 task_id"
    )
    # 验证 INSERT 语句包含 task_id 列
    insert_sql = conn.execute.call_args_list[0][0][0].lower()
    assert "task_id" in insert_sql, (
        "INSERT 语句必须包含 task_id 列"
    )


def test_append_message_task_id_is_nullable():
    """task_id 字段应为可选，不传时允许为 None。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    fake_msg = {
        "id": "msg-002",
        "conversation_id": "conv-001",
        "role": "user",
        "content": "你好",
        "task_id": None,
        "created_at": "2025-01-01T00:00:00",
    }
    conn.execute.return_value.fetchone.return_value = fake_msg

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        result = ConversationRepository.append_message(
            conversation_id="conv-001", role="user", content="你好"
        )

    # user 消息不传 task_id 应正常返回
    assert result["role"] == "user"
    assert result["content"] == "你好"


def test_list_messages_includes_task_id():
    """list_messages 返回的消息必须包含 task_id 字段。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    fake_messages = [
        {
            "id": "m1", "role": "user", "content": "问题",
            "task_id": None, "created_at": "2025-01-01T10:00:00",
        },
        {
            "id": "m2", "role": "assistant", "content": "",
            "task_id": "rca-abc123", "report_snapshot": '{"key":"val"}',
            "created_at": "2025-01-01T10:01:00",
        },
    ]
    conn.execute.return_value.fetchall.return_value = fake_messages

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        result = ConversationRepository.list_messages("conv-001")

    assert len(result) == 2
    assert result[0].get("task_id") is None, (
        "user 消息 task_id 应为 None"
    )
    assert result[1].get("task_id") == "rca-abc123", (
        "assistant 消息 task_id 必须为 'rca-abc123'"
    )


# ═══════════════════════════════════════════════════════════════
# Task 8 QA 修复: update_message repository 方法
# ═══════════════════════════════════════════════════════════════


def test_update_message_method_exists():
    """ConversationRepository 必须提供 update_message 静态方法。"""
    from app.persistence.chat_repository import ConversationRepository

    assert hasattr(ConversationRepository, "update_message"), (
        "ConversationRepository 必须提供 update_message 静态方法以支持 PATCH 消息"
    )
    assert callable(getattr(ConversationRepository, "update_message")), (
        "update_message 必须可调用"
    )


def test_update_message_executes_update_sql():
    """update_message 必须执行 UPDATE 语句并 commit。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    fake_msg = {
        "id": "msg-001",
        "conversation_id": "conv-001",
        "role": "assistant",
        "content": "",
        "task_id": "rca-abc",
        "report_snapshot": '{"k":"v"}',
        "error": 0,
        "metadata": "{}",
        "created_at": "2025-01-01T00:00:00",
    }
    conn.execute.return_value.fetchone.return_value = fake_msg

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        result = ConversationRepository.update_message(
            conversation_id="conv-001",
            message_id="msg-001",
            report_snapshot={"k": "v"},
        )

    conn.commit.assert_called_once()
    # 遍历所有 execute 调用，找到含 UPDATE 的 SQL
    update_calls = [
        c for c in conn.execute.call_args_list
        if "update" in str(c[0][0]).lower()
    ]
    assert update_calls, "update_message 必须执行至少一条 UPDATE 语句"
    update_sql = update_calls[0][0][0].lower()
    assert "chat_messages" in update_sql
    assert "report_snapshot" in update_sql
    assert result["id"] == "msg-001"


def test_update_message_filters_by_conversation_and_message_id():
    """update_message 的 SQL 必须按 conversation_id 和 message_id 过滤。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchone.return_value = {
        "id": "msg-001", "conversation_id": "conv-001",
        "role": "assistant", "content": "", "task_id": "rca-abc",
        "report_snapshot": '{"k":"v"}',
    }

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.update_message(
            conversation_id="conv-001",
            message_id="msg-001",
            report_snapshot={"k": "v"},
        )

    # 遍历所有 execute 调用，找到含 UPDATE 的 SQL
    update_calls = [
        c for c in conn.execute.call_args_list
        if "update" in str(c[0][0]).lower()
    ]
    assert update_calls, "update_message 必须执行至少一条 UPDATE 语句"
    params = update_calls[0][0][1]
    # SQL 参数必须包含 conversation_id 和 message_id
    assert "conv-001" in params
    assert "msg-001" in params


def test_update_message_raises_lookup_error_for_missing_message():
    """update_message 找不到消息时必须抛出 LookupError（与 update_title 一致）。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    # 模拟 UPDATE 影响 0 行：fetchone 返回 None
    conn.execute.return_value.fetchone.return_value = None

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        try:
            ConversationRepository.update_message(
                conversation_id="conv-001",
                message_id="nonexistent",
                report_snapshot={"k": "v"},
            )
        except LookupError:
            pass
        else:
            raise AssertionError("update_message 找不到消息时必须抛出 LookupError")


def test_update_message_closes_connection():
    """update_message 执行后必须关闭连接（与其他 repository 方法一致）。"""
    from app.persistence.chat_repository import ConversationRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchone.return_value = {
        "id": "msg-001", "conversation_id": "conv-001",
        "role": "assistant", "content": "",
    }

    with patch(
        "app.persistence.chat_repository.postgres.get_connection", return_value=conn
    ):
        ConversationRepository.update_message(
            conversation_id="conv-001",
            message_id="msg-001",
            report_snapshot={"k": "v"},
        )

    conn.close.assert_called_once()
