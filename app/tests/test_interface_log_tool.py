"""接口日志工具 SQL 契约测试。"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _mock_connection() -> Mock:
    conn = Mock()
    cursor = Mock()
    cursor.fetchall.return_value = []
    conn.execute.return_value = cursor
    return conn


def test_interface_log_tool_uses_postgresql_interval_filter():
    """接口日志时间过滤必须使用 PostgreSQL interval 语法。"""
    from app.tools.interface_log_tool import InterfaceLogTool

    conn = _mock_connection()

    with patch("app.tools.interface_log_tool.get_connection", return_value=conn):
        result = InterfaceLogTool().execute({"task_id": "task-001", "hours_back": 24, "limit": 50})

    sql, params = conn.execute.call_args.args

    assert result["success"] is True
    assert "datetime(" not in sql.lower()
    assert "now() - interval '1 hour' * ?" in sql.lower()
    assert params == (24, 50)
    conn.close.assert_called_once()
