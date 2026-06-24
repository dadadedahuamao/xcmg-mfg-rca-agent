"""聊天持久化 Repository — ConversationRepository 纯静态方法。"""

import json
import uuid
from typing import Any, Optional

from app.persistence import postgres

ADMIN_USER_ID = "admin"


def _now() -> str:
    """返回数据库文本时间戳格式：YYYY-MM-DD HH:MM:SS.mmm。"""
    return postgres.database_timestamp()


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row.items())


class ConversationRepository:
    """聊天会话与消息仓库。"""

    @staticmethod
    def create(title: str = "新会话") -> dict:
        conn = postgres.get_connection()
        try:
            conv_id = f"conv-{uuid.uuid4().hex[:12]}"
            now = _now()
            conn.execute(
                """INSERT INTO chat_conversations (id, user_id, title, pinned, archived, metadata, created_at, updated_at)
                   VALUES (?, ?, ?, 0, 0, '{}', ?, ?)""",
                (conv_id, ADMIN_USER_ID, title, now, now),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM chat_conversations WHERE id = ? AND user_id = ?",
                (conv_id, ADMIN_USER_ID),
            ).fetchone()
            return _row_to_dict(row)
        finally:
            conn.close()

    @staticmethod
    def list_all() -> list[dict]:
        conn = postgres.get_connection()
        try:
            rows = conn.execute(
                """SELECT * FROM chat_conversations
                   WHERE user_id = ? AND archived = 0
                   ORDER BY pinned DESC, updated_at DESC""",
                (ADMIN_USER_ID,),
            ).fetchall()
            return [_row_to_dict(row) for row in rows]
        finally:
            conn.close()

    @staticmethod
    def update_title(conversation_id: str, title: str) -> None:
        """更新会话标题（用于 LLM 摘要后持久化）。"""
        conn = postgres.get_connection()
        try:
            now = _now()
            conn.execute(
                "UPDATE chat_conversations SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (title, now, conversation_id, ADMIN_USER_ID),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def rename(conversation_id: str, title: str) -> None:
        conn = postgres.get_connection()
        try:
            now = _now()
            conn.execute(
                "UPDATE chat_conversations SET title = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (title, now, conversation_id, ADMIN_USER_ID),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def set_pinned(conversation_id: str, pinned: bool) -> None:
        conn = postgres.get_connection()
        try:
            conn.execute(
                "UPDATE chat_conversations SET pinned = ? WHERE id = ? AND user_id = ?",
                (1 if pinned else 0, conversation_id, ADMIN_USER_ID),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def archive(conversation_id: str) -> None:
        conn = postgres.get_connection()
        try:
            conn.execute(
                "UPDATE chat_conversations SET archived = 1 WHERE id = ? AND user_id = ?",
                (conversation_id, ADMIN_USER_ID),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def delete(conversation_id: str) -> None:
        conn = postgres.get_connection()
        try:
            conn.execute(
                "DELETE FROM chat_messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            conn.execute(
                "DELETE FROM chat_conversations WHERE id = ? AND user_id = ?",
                (conversation_id, ADMIN_USER_ID),
            )
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def append_message(
        conversation_id: str,
        role: str,
        content: str,
        anomaly_type: Optional[str] = None,
        task_id: Optional[str] = None,
        report_snapshot: Optional[dict] = None,
        error: bool = False,
        metadata: Optional[dict] = None,
    ) -> dict:
        conn = postgres.get_connection()
        try:
            msg_id = f"msg-{uuid.uuid4().hex[:12]}"
            now = _now()
            conn.execute(
                """INSERT INTO chat_messages (id, conversation_id, role, content, anomaly_type, task_id,
                   report_snapshot, error, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    msg_id,
                    conversation_id,
                    role,
                    content,
                    anomaly_type,
                    task_id,
                    json.dumps(report_snapshot, ensure_ascii=False) if report_snapshot else None,
                    1 if error else 0,
                    json.dumps(metadata, ensure_ascii=False) if metadata else "{}",
                    now,
                ),
            )
            conn.execute(
                """UPDATE chat_conversations
                   SET updated_at = ?, last_message_at = ?
                   WHERE id = ? AND user_id = ?""",
                (now, now, conversation_id, ADMIN_USER_ID),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM chat_messages WHERE id = ?",
                (msg_id,),
            ).fetchone()
            result = _row_to_dict(row)
            # 将 JSON 字符串字段转回 dict
            if result.get("report_snapshot") and isinstance(result["report_snapshot"], str):
                try:
                    result["report_snapshot"] = json.loads(result["report_snapshot"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if result.get("metadata") and isinstance(result["metadata"], str):
                try:
                    result["metadata"] = json.loads(result["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            return result
        finally:
            conn.close()

    @staticmethod
    def list_messages(conversation_id: str) -> list[dict]:
        conn = postgres.get_connection()
        try:
            rows = conn.execute(
                """SELECT * FROM chat_messages
                   WHERE conversation_id = ?
                   ORDER BY created_at ASC""",
                (conversation_id,),
            ).fetchall()
            results = []
            for row in rows:
                d = _row_to_dict(row)
                if d.get("report_snapshot") and isinstance(d["report_snapshot"], str):
                    try:
                        d["report_snapshot"] = json.loads(d["report_snapshot"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                if d.get("metadata") and isinstance(d["metadata"], str):
                    try:
                        d["metadata"] = json.loads(d["metadata"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                results.append(d)
            return results
        finally:
            conn.close()

    @staticmethod
    def update_message(
        conversation_id: str,
        message_id: str,
        content: Optional[str] = None,
        report_snapshot: Optional[dict] = None,
        error: Optional[bool] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """更新已存在的 chat_messages 记录（Task 8 QA：同消息报告持久化）。

        Args:
            conversation_id: 所属会话 ID
            message_id: 目标消息 ID
            content: 可选，替换消息文本
            report_snapshot: 可选，RCA 报告快照（dict 会被 JSON 序列化）
            error: 可选，更新错误标记
            metadata: 可选，更新元数据

        Returns:
            更新后的完整消息记录（dict）

        Raises:
            LookupError: 消息不存在或不属于指定会话
        """
        # 动态构建 SET 子句；空调用应直接报 LookupError，避免误用为"无操作"
        set_clauses: list[str] = []
        params: list[Any] = []
        if content is not None:
            set_clauses.append("content = ?")
            params.append(content)
        if report_snapshot is not None:
            set_clauses.append("report_snapshot = ?")
            params.append(
                json.dumps(report_snapshot, ensure_ascii=False)
            )
        if error is not None:
            set_clauses.append("error = ?")
            params.append(1 if error else 0)
        if metadata is not None:
            set_clauses.append("metadata = ?")
            params.append(json.dumps(metadata, ensure_ascii=False))

        if not set_clauses:
            raise ValueError("update_message 至少需要一个待更新字段")

        conn = postgres.get_connection()
        try:
            sql = (
                "UPDATE chat_messages SET " + ", ".join(set_clauses) +
                " WHERE id = ? AND conversation_id = ?"
            )
            params.extend([message_id, conversation_id])
            conn.execute(sql, tuple(params))
            conn.commit()
            # 读取更新后的完整记录
            row = conn.execute(
                "SELECT * FROM chat_messages WHERE id = ? AND conversation_id = ?",
                (message_id, conversation_id),
            ).fetchone()
            if row is None:
                raise LookupError(
                    f"消息不存在或不属于会话: conversation_id={conversation_id}, "
                    f"message_id={message_id}"
                )
            result = _row_to_dict(row)
            if result.get("report_snapshot") and isinstance(result["report_snapshot"], str):
                try:
                    result["report_snapshot"] = json.loads(result["report_snapshot"])
                except (json.JSONDecodeError, TypeError):
                    pass
            if result.get("metadata") and isinstance(result["metadata"], str):
                try:
                    result["metadata"] = json.loads(result["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass
            return result
        finally:
            conn.close()
