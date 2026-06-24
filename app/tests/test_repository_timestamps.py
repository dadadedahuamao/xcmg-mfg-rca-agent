"""业务仓储时间戳格式契约测试。"""

import re
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


TIMESTAMP_PATTERN = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}$"


def _mock_connection() -> Mock:
    conn = Mock()
    cursor = Mock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    conn.execute.return_value = cursor
    return conn


def _assert_database_timestamp(value: str) -> None:
    assert re.match(TIMESTAMP_PATTERN, value)


def test_rca_task_create_uses_database_timestamp_format():
    """创建 RCA 任务写入 created_at/updated_at 必须使用数据库时间戳格式。"""
    from app.persistence.repositories import RCATaskRepository

    conn = _mock_connection()

    with (
        patch("app.persistence.repositories.postgres.get_connection", return_value=conn),
        patch.object(RCATaskRepository, "get", return_value={"task_id": "task-001"}),
    ):
        RCATaskRepository.create(
            task_id="task-001",
            anomaly_type="overstation_check",
            description="测试",
        )

    insert_params = conn.execute.call_args_list[0][0][1]
    _assert_database_timestamp(insert_params[5])
    _assert_database_timestamp(insert_params[6])


def test_rca_task_update_status_uses_database_timestamp_format():
    """更新 RCA 任务状态写入 updated_at/completed_at 必须使用数据库时间戳格式。"""
    from app.persistence.repositories import RCATaskRepository

    conn = _mock_connection()

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        RCATaskRepository.update_status("task-001", "completed")

    update_params = conn.execute.call_args_list[0][0][1]
    _assert_database_timestamp(update_params[1])
    _assert_database_timestamp(update_params[2])


def test_rca_report_save_uses_database_timestamp_format():
    """保存 RCA 报告写入 generated_at 必须使用数据库时间戳格式。"""
    from app.persistence.repositories import RCAReportRepository

    conn = _mock_connection()

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        RCAReportRepository.save("task-001", {"root_cause": "测试根因"})

    insert_params = conn.execute.call_args_list[0][0][1]
    _assert_database_timestamp(insert_params[10])


def test_checkpoint_save_uses_database_timestamp_format():
    """保存检查点写入 created_at 必须使用数据库时间戳格式。"""
    from app.persistence.repositories import CheckpointRepository

    conn = _mock_connection()
    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        CheckpointRepository.save("task-001", "analyze_symptom", "{}")

    insert_params = conn.execute.call_args_list[0][0][1]
    _assert_database_timestamp(insert_params[3])


def test_tool_dedup_record_uses_database_timestamp_format():
    """记录工具去重写入 created_at 必须使用数据库时间戳格式。"""
    from app.persistence.repositories import ToolDedupRepository

    conn = _mock_connection()
    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        ToolDedupRepository.check_and_record("task-001", "workorder", {"a": 1})

    insert_params = conn.execute.call_args_list[1][0][1]
    _assert_database_timestamp(insert_params[3])


def test_sample_data_uses_database_timestamp_format():
    """示例数据脚本写入业务表的时间字段必须使用数据库时间戳格式。"""
    from app.scripts.init_sample_db import insert_sample_data

    conn = _mock_connection()
    with patch("app.scripts.init_sample_db.postgres.get_connection", return_value=conn):
        insert_sample_data()

    work_orders = conn.executemany.call_args_list[0][0][1]
    maintenance = conn.executemany.call_args_list[1][0][1]
    materials = conn.executemany.call_args_list[2][0][1]
    quality = conn.executemany.call_args_list[3][0][1]
    interface_logs = conn.executemany.call_args_list[4][0][1]

    for row in work_orders:
        for value in (row[3], row[4], row[5], row[6], row[9]):
            if value is not None:
                _assert_database_timestamp(value)
    for row in maintenance:
        for value in (row[4], row[5], row[9]):
            if value is not None:
                _assert_database_timestamp(value)
    for row in materials:
        _assert_database_timestamp(row[6])
    for row in quality:
        _assert_database_timestamp(row[7])
    for row in interface_logs:
        for value in (row[3], row[4]):
            if value is not None:
                _assert_database_timestamp(value)
