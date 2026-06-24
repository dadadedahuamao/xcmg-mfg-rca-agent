"""RCA 步骤事件持久化测试 — Task 1: rca_step_events 基础。"""

import json
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
    assert re.match(TIMESTAMP_PATTERN, value), (
        f"时间戳格式不符合预期: {value}"
    )


# ═══════════════════════════════════════════════════════════════
# append_event 测试
# ═══════════════════════════════════════════════════════════════


def test_append_event_inserts_with_correct_fields():
    """append_event 必须写入所有必需字段。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        StepEventRepository.append_event(
            task_id="task-001",
            node_name="analyze_symptom",
            event_type="node_started",
            status="running",
            title="分析异常症状",
            summary="正在分析工位 WS-03 超站异常",
            detail="详细分析过程...",
            detail_json={"tool": "workorder", "params": {"a": 1}},
            checkpoint_id=None,
        )

    # call_args_list[0] = SELECT seq, call_args_list[1] = INSERT
    insert_sql = conn.execute.call_args_list[1][0][0]
    insert_params = conn.execute.call_args_list[1][0][1]

    assert "INSERT INTO rca_step_events" in insert_sql
    assert insert_params[0] == "task-001"
    assert insert_params[2] == "analyze_symptom"
    assert insert_params[3] == "node_started"
    assert insert_params[4] == "running"
    assert insert_params[5] == "分析异常症状"
    assert insert_params[6] == "正在分析工位 WS-03 超站异常"
    assert insert_params[7] == "详细分析过程..."
    assert json.loads(insert_params[8]) == {"tool": "workorder", "params": {"a": 1}}
    assert insert_params[9] is None  # checkpoint_id
    _assert_database_timestamp(insert_params[10])  # created_at


def test_append_event_auto_increments_seq_per_task():
    """同一 task_id 的事件 seq 从 1 开始自动递增。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    # 模拟 COALESCE(MAX(seq), 0) + 1 返回 1
    conn.execute.return_value.fetchone.return_value = {"seq": 1}

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        StepEventRepository.append_event(
            task_id="task-001",
            node_name="analyze_symptom",
            event_type="node_started",
            status="running",
            title="步骤 1",
        )

    # 第一次调用是 SELECT COALESCE(MAX(seq), 0) + 1
    select_sql = conn.execute.call_args_list[0][0][0]
    assert "COALESCE(MAX(seq)" in select_sql
    assert conn.execute.call_args_list[0][0][1] == ("task-001",)

    # 第二次调用是 INSERT，seq 应为 1
    insert_params = conn.execute.call_args_list[1][0][1]
    assert insert_params[1] == 1  # seq


def test_append_event_seq_increments_across_calls():
    """多次 append_event 时 seq 应递增。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    # 第一次返回 1，第二次返回 2
    conn.execute.return_value.fetchone.side_effect = [{"seq": 1}, {"seq": 2}]

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        StepEventRepository.append_event(
            task_id="task-001",
            node_name="analyze_symptom",
            event_type="node_started",
            status="running",
            title="步骤 1",
        )
        StepEventRepository.append_event(
            task_id="task-001",
            node_name="generate_hypotheses",
            event_type="node_started",
            status="running",
            title="步骤 2",
        )

    # 两次 INSERT 的 seq 分别为 1 和 2
    seq1 = conn.execute.call_args_list[1][0][1][1]
    seq2 = conn.execute.call_args_list[3][0][1][1]
    assert seq1 == 1
    assert seq2 == 2


def test_append_event_different_tasks_independent_seq():
    """不同 task_id 的 seq 应独立计数。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchone.side_effect = [{"seq": 1}, {"seq": 1}]

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        StepEventRepository.append_event(
            task_id="task-A",
            node_name="analyze_symptom",
            event_type="node_started",
            status="running",
            title="任务A步骤1",
        )
        StepEventRepository.append_event(
            task_id="task-B",
            node_name="analyze_symptom",
            event_type="node_started",
            status="running",
            title="任务B步骤1",
        )

    # 两个不同任务的 seq 都应该是 1
    seq_a = conn.execute.call_args_list[1][0][1][1]
    seq_b = conn.execute.call_args_list[3][0][1][1]
    assert seq_a == 1
    assert seq_b == 1


def test_append_event_detail_json_defaults_to_none():
    """detail_json 不传时应默认为 None（JSON null）。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        StepEventRepository.append_event(
            task_id="task-001",
            node_name="analyze_symptom",
            event_type="node_started",
            status="running",
            title="步骤",
        )

    insert_params = conn.execute.call_args_list[1][0][1]
    assert insert_params[8] is None  # detail_json 默认 None


def test_append_event_detail_json_stores_complex_structure():
    """detail_json 应能存储嵌套的 dict/list 结构。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    complex_data = {
        "tool_calls": [
            {"tool": "workorder", "params": {"wo_id": "WO-001"}, "result": {"status": "delayed"}},
            {"tool": "material", "params": {"mat_code": "MAT-001"}},
        ],
        "llm_usage": {"model": "gpt-4o-mini", "tokens": 1500},
    }

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        StepEventRepository.append_event(
            task_id="task-001",
            node_name="execute_tool",
            event_type="node_completed",
            status="completed",
            title="执行工具",
            detail_json=complex_data,
        )

    insert_params = conn.execute.call_args_list[1][0][1]
    stored = json.loads(insert_params[8])
    assert stored == complex_data
    assert stored["tool_calls"][0]["tool"] == "workorder"
    assert stored["llm_usage"]["tokens"] == 1500


def test_append_event_uses_database_timestamp_format():
    """append_event 写入 created_at 必须使用数据库时间戳格式。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        StepEventRepository.append_event(
            task_id="task-001",
            node_name="analyze_symptom",
            event_type="node_started",
            status="running",
            title="步骤",
        )

    insert_params = conn.execute.call_args_list[1][0][1]
    _assert_database_timestamp(insert_params[10])


# ═══════════════════════════════════════════════════════════════
# list_events 测试
# ═══════════════════════════════════════════════════════════════


def test_list_events_returns_events_ordered_by_seq():
    """list_events 应按 seq 升序返回事件。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchall.return_value = [
        {"id": 1, "task_id": "task-001", "seq": 1, "node_name": "analyze_symptom",
         "event_type": "node_started", "status": "running", "title": "步骤1",
         "summary": None, "detail": None, "detail_json": None, "checkpoint_id": None,
         "created_at": "2026-06-23 10:00:00.000"},
        {"id": 2, "task_id": "task-001", "seq": 2, "node_name": "generate_hypotheses",
         "event_type": "node_started", "status": "running", "title": "步骤2",
         "summary": None, "detail": None, "detail_json": None, "checkpoint_id": None,
         "created_at": "2026-06-23 10:00:01.000"},
    ]

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        events = StepEventRepository.list_events("task-001")

    assert len(events) == 2
    assert events[0]["seq"] == 1
    assert events[1]["seq"] == 2


def test_list_events_default_after_seq_zero():
    """list_events 默认 after_seq=0 应返回所有事件。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchall.return_value = [
        {"id": 1, "task_id": "task-001", "seq": 1, "node_name": "analyze_symptom",
         "event_type": "node_started", "status": "running", "title": "步骤1",
         "summary": None, "detail": None, "detail_json": None, "checkpoint_id": None,
         "created_at": "2026-06-23 10:00:00.000"},
    ]

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        events = StepEventRepository.list_events("task-001")

    select_sql = conn.execute.call_args_list[0][0][0]
    # 默认 after_seq=0，应使用 seq > ? 条件
    assert "seq > ?" in select_sql or "seq > %s" in select_sql
    assert conn.execute.call_args_list[0][0][1] == ("task-001", 0)


def test_list_events_with_after_seq_filters():
    """list_events(after_seq=N) 应只返回 seq > N 的事件。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchall.return_value = [
        {"id": 3, "task_id": "task-001", "seq": 3, "node_name": "select_tool",
         "event_type": "node_started", "status": "running", "title": "步骤3",
         "summary": None, "detail": None, "detail_json": None, "checkpoint_id": None,
         "created_at": "2026-06-23 10:00:02.000"},
    ]

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        events = StepEventRepository.list_events("task-001", after_seq=2)

    assert len(events) == 1
    assert events[0]["seq"] == 3
    assert conn.execute.call_args_list[0][0][1] == ("task-001", 2)


def test_list_events_empty_result():
    """list_events 无匹配事件时应返回空列表。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchall.return_value = []

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        events = StepEventRepository.list_events("task-001")

    assert events == []


def test_list_events_deserializes_detail_json():
    """list_events 应将 detail_json 从 JSON 字符串反序列化为 Python 对象。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchall.return_value = [
        {"id": 1, "task_id": "task-001", "seq": 1, "node_name": "execute_tool",
         "event_type": "node_completed", "status": "completed", "title": "执行工具",
         "summary": None, "detail": None,
         "detail_json": '{"tool": "workorder", "result": {"status": "ok"}}',
         "checkpoint_id": None, "created_at": "2026-06-23 10:00:00.000"},
    ]

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        events = StepEventRepository.list_events("task-001")

    assert isinstance(events[0]["detail_json"], dict)
    assert events[0]["detail_json"]["tool"] == "workorder"
    assert events[0]["detail_json"]["result"]["status"] == "ok"


def test_list_events_detail_json_null_returns_none():
    """detail_json 为 NULL 时应返回 None。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchall.return_value = [
        {"id": 1, "task_id": "task-001", "seq": 1, "node_name": "analyze_symptom",
         "event_type": "node_started", "status": "running", "title": "步骤",
         "summary": None, "detail": None, "detail_json": None, "checkpoint_id": None,
         "created_at": "2026-06-23 10:00:00.000"},
    ]

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        events = StepEventRepository.list_events("task-001")

    assert events[0]["detail_json"] is None


# ═══════════════════════════════════════════════════════════════
# 集成式测试：append + list 往返
# ═══════════════════════════════════════════════════════════════


def test_append_and_list_roundtrip():
    """append_event 后 list_events 应能返回写入的事件。"""
    from app.persistence.repositories import StepEventRepository

    conn = _mock_connection()
    conn.execute.return_value.fetchone.return_value = {"seq": 1}
    conn.execute.return_value.fetchall.return_value = [
        {"id": 1, "task_id": "task-001", "seq": 1, "node_name": "analyze_symptom",
         "event_type": "node_started", "status": "running", "title": "分析异常症状",
         "summary": "摘要", "detail": "详情",
         "detail_json": '{"key": "value"}', "checkpoint_id": None,
         "created_at": "2026-06-23 10:00:00.000"},
    ]

    with patch("app.persistence.repositories.postgres.get_connection", return_value=conn):
        StepEventRepository.append_event(
            task_id="task-001",
            node_name="analyze_symptom",
            event_type="node_started",
            status="running",
            title="分析异常症状",
            summary="摘要",
            detail="详情",
            detail_json={"key": "value"},
        )
        events = StepEventRepository.list_events("task-001")

    assert len(events) == 1
    assert events[0]["task_id"] == "task-001"
    assert events[0]["seq"] == 1
    assert events[0]["node_name"] == "analyze_symptom"
    assert events[0]["event_type"] == "node_started"
    assert events[0]["status"] == "running"
    assert events[0]["title"] == "分析异常症状"
    assert events[0]["summary"] == "摘要"
    assert events[0]["detail"] == "详情"
    assert events[0]["detail_json"] == {"key": "value"}


# ═══════════════════════════════════════════════════════════════
# Schema 契约测试：唯一约束
# ═══════════════════════════════════════════════════════════════


def test_schema_enforces_unique_task_id_seq():
    """db/001_init_app_schema.sql 必须对 rca_step_events 的 (task_id, seq) 施加唯一约束。"""
    import re

    schema_path = Path(__file__).resolve().parent.parent.parent / "db" / "001_init_app_schema.sql"
    sql = schema_path.read_text(encoding="utf-8")

    # 1. 表定义内必须有 CONSTRAINT ... UNIQUE (task_id, seq) 或 UNIQUE (task_id, seq)
    table_block = re.search(
        r"CREATE TABLE IF NOT EXISTS rca_step_events\s*\(([\s\S]*?)\);",
        sql,
    )
    assert table_block is not None, "未找到 rca_step_events 表定义"
    table_body = table_block.group(1)

    has_table_constraint = bool(re.search(
        r"CONSTRAINT\s+\w+\s+UNIQUE\s*\(\s*task_id\s*,\s*seq\s*\)",
        table_body,
        re.IGNORECASE,
    ))

    # 2. 索引区必须有 CREATE UNIQUE INDEX ... ON rca_step_events (task_id, seq)
    has_unique_index = bool(re.search(
        r"CREATE\s+UNIQUE\s+INDEX\s+\S+\s+ON\s+rca_step_events\s*\(\s*task_id\s*,\s*seq\s*\)",
        sql,
        re.IGNORECASE,
    ))

    assert has_table_constraint or has_unique_index, (
        "rca_step_events 缺少 (task_id, seq) 唯一约束。"
        " 需要在表定义中添加 CONSTRAINT ... UNIQUE (task_id, seq)"
        " 或创建 CREATE UNIQUE INDEX ... ON rca_step_events (task_id, seq)"
    )
