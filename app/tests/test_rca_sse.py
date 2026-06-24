"""RCA SSE 步骤事件流端点测试 — Task 4: 新增 SSE 步骤事件流端点。

测试覆盖:
- SSE 响应头（Content-Type, Cache-Control, Connection）
- 事件重放（replay DB events）
- after 参数过滤
- Last-Event-ID 头回退
- SSE 帧格式（id, event, data）
- 心跳格式
- 终端关闭行为（done/error）
- 404 不存在的任务
- 现有端点不受影响
"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ============================================================================
# 辅助工具
# ============================================================================

def _mock_task(status="running", task_id="rca-sse-001"):
    return {
        "task_id": task_id,
        "status": status,
        "anomaly_type": "overstation_check",
        "description": "测试",
        "source_system": "MES",
        "metadata": "{}",
        "confidence": 0.0,
        "reflection_rounds": 0,
        "created_at": "2026-06-23 10:00:00.000",
        "updated_at": "2026-06-23 10:00:00.000",
        "completed_at": None,
    }


def _mock_event(seq=1, event_type="node_started", status="running",
                node_name="analyze_symptom", title="分析异常症状",
                summary=None, detail=None, detail_json=None):
    return {
        "id": seq,
        "task_id": "rca-sse-001",
        "seq": seq,
        "node_name": node_name,
        "event_type": event_type,
        "status": status,
        "title": title,
        "summary": summary,
        "detail": detail,
        "detail_json": detail_json,
        "checkpoint_id": None,
        "created_at": f"2026-06-23 10:00:0{seq}.000",
    }


# ============================================================================
# SSE 格式化辅助函数测试
# ============================================================================

def test_format_sse_helper_exists():
    """_format_sse 辅助函数必须存在于 routes 模块中。"""
    from app.api.routes import _format_sse

    assert callable(_format_sse), "_format_sse 必须是可调用对象"


def test_format_sse_basic_frame():
    """_format_sse 应生成符合 SSE 规范的帧。"""
    from app.api.routes import _format_sse

    frame = _format_sse("step", {"key": "value"}, event_id=1)

    assert "event: step" in frame
    assert "data: " in frame
    assert frame.endswith("\n\n"), f"SSE 帧应以双换行结尾: {repr(frame)}"


def test_format_sse_includes_id_when_provided():
    """提供 event_id 时帧应包含 id 行。"""
    from app.api.routes import _format_sse

    frame = _format_sse("step", {"key": "value"}, event_id=42)

    assert "id: 42" in frame, f"帧应包含 id: 42: {repr(frame)}"


def test_format_sse_omits_id_when_none():
    """event_id 为 None 时帧不应包含 id 行。"""
    from app.api.routes import _format_sse

    frame = _format_sse("heartbeat", {})

    assert "id:" not in frame, f"无 id 的帧不应包含 id 行: {repr(frame)}"


def test_format_sse_data_is_json():
    """data 字段必须是 JSON 字符串。"""
    from app.api.routes import _format_sse

    data = {"task_id": "rca-001", "status": "running", "title": "测试"}
    frame = _format_sse("step", data, event_id=1)

    # 提取 data 行内容
    for line in frame.split("\n"):
        if line.startswith("data: "):
            payload = line[len("data: "):]
            parsed = json.loads(payload)
            assert parsed == data
            return

    pytest.fail(f"帧中未找到 data 行: {repr(frame)}")


def test_format_sse_event_types():
    """_format_sse 应支持 step/done/error/heartbeat 四种事件类型。"""
    from app.api.routes import _format_sse

    for event_type in ("step", "done", "error", "heartbeat"):
        frame = _format_sse(event_type, {"msg": "test"})
        assert f"event: {event_type}" in frame, (
            f"事件类型 {event_type} 未出现在帧中: {repr(frame)}"
        )


# ============================================================================
# 事件流生成器测试
# ============================================================================

def test_event_stream_generator_exists():
    """_event_stream 异步生成器必须存在于 routes 模块中。"""
    import inspect
    from app.api.routes import _event_stream

    assert inspect.isasyncgenfunction(_event_stream), (
        "_event_stream 必须是 async generator function"
    )


def test_event_stream_replays_existing_events():
    """_event_stream 应先重放数据库中已有的事件。"""
    import asyncio
    from app.api.routes import _event_stream

    events = [
        _mock_event(seq=1, title="步骤1"),
        _mock_event(seq=2, title="步骤2"),
    ]

    with patch("app.api.routes.StepEventRepository.list_events",
               side_effect=[events, []]) as mock_list, \
         patch("app.api.routes.RCATaskRepository.get", return_value=_mock_task(status="running")):
        async def collect():
            results = []
            gen = _event_stream("rca-sse-001", after=0)
            try:
                async for frame in gen:
                    results.append(frame)
                    if len(results) >= 2:
                        break
            finally:
                await gen.aclose()
            return results

        results = asyncio.run(asyncio.wait_for(collect(), timeout=5))

    assert len(results) == 2
    for i, frame in enumerate(results):
        assert f"id: {i + 1}" in frame, f"帧 {i} 缺少 id: {repr(frame)}"
        assert "event: step" in frame, f"帧 {i} 缺少 event: step: {repr(frame)}"


def test_event_stream_respects_after_param():
    """_event_stream 应使用 after 参数过滤已重放事件。"""
    import asyncio
    from app.api.routes import _event_stream

    events = [
        _mock_event(seq=3, title="步骤3"),
    ]

    with patch("app.api.routes.StepEventRepository.list_events",
               side_effect=[events, []]) as mock_list, \
         patch("app.api.routes.RCATaskRepository.get", return_value=_mock_task(status="running")):
        async def collect():
            results = []
            gen = _event_stream("rca-sse-001", after=2)
            try:
                async for frame in gen:
                    results.append(frame)
                    if len(results) >= 1:
                        break
            finally:
                await gen.aclose()
            return results

        results = asyncio.run(asyncio.wait_for(collect(), timeout=5))

    assert len(results) >= 1
    # 应只包含 seq=3 的事件
    assert "id: 3" in results[0], f"应重放 seq=3 的事件: {repr(results[0])}"


def test_event_stream_sends_done_on_completed():
    """任务状态为 completed 且无新事件时应发送 done 事件。"""
    import asyncio
    from app.api.routes import _event_stream

    events = [
        _mock_event(seq=1, title="完成"),
    ]

    with patch("app.api.routes.StepEventRepository.list_events",
               side_effect=[events, []]) as mock_list, \
         patch("app.api.routes.RCATaskRepository.get", return_value=_mock_task(status="completed")):
        async def collect():
            results = []
            gen = _event_stream("rca-sse-001", after=0)
            try:
                async for frame in gen:
                    results.append(frame)
            finally:
                await gen.aclose()
            return results

        results = asyncio.run(asyncio.wait_for(collect(), timeout=5))

    # 至少应有 step + done
    assert len(results) >= 2
    # 最后一帧应为 done
    last_frame = results[-1]
    assert "event: done" in last_frame, f"最后一帧应为 done: {repr(last_frame)}"


def test_event_stream_sends_error_on_failed():
    """任务状态为 failed 且无新事件时应发送 error 事件。"""
    import asyncio
    from app.api.routes import _event_stream

    events = [
        _mock_event(seq=1, title="失败步骤"),
    ]

    with patch("app.api.routes.StepEventRepository.list_events",
               side_effect=[events, []]) as mock_list, \
         patch("app.api.routes.RCATaskRepository.get", return_value=_mock_task(status="failed")):
        async def collect():
            results = []
            gen = _event_stream("rca-sse-001", after=0)
            try:
                async for frame in gen:
                    results.append(frame)
            finally:
                await gen.aclose()
            return results

        results = asyncio.run(asyncio.wait_for(collect(), timeout=5))

    assert len(results) >= 2
    last_frame = results[-1]
    assert "event: error" in last_frame, f"最后一帧应为 error: {repr(last_frame)}"


def test_event_stream_sends_heartbeat_format():
    """心跳帧格式应正确：event: heartbeat, data: {...}。"""
    from app.api.routes import _format_sse

    frame = _format_sse("heartbeat", {"task_id": "rca-sse-001"})

    assert "event: heartbeat" in frame
    assert "data: " in frame
    data_line = [l for l in frame.split("\n") if l.startswith("data: ")][0]
    payload = json.loads(data_line[len("data: "):])
    assert "task_id" in payload


# ============================================================================
# HTTP 端点测试
# ============================================================================

def test_sse_endpoint_returns_text_event_stream():
    """GET /tasks/{task_id}/events 必须返回 Content-Type: text/event-stream。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.get", return_value=_mock_task(status="completed")), \
         patch("app.api.routes.StepEventRepository.list_events", return_value=[]):
        response = client.get("/api/v1/rca/tasks/rca-sse-001/events")

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "text/event-stream" in content_type, (
        f"Content-Type 应为 text/event-stream: {content_type}"
    )


def test_sse_endpoint_sets_cache_control_no_cache():
    """SSE 端点应设置 Cache-Control: no-cache。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.get", return_value=_mock_task(status="completed")), \
         patch("app.api.routes.StepEventRepository.list_events", return_value=[]):
        response = client.get("/api/v1/rca/tasks/rca-sse-001/events")

    cache_control = response.headers.get("cache-control", "")
    assert "no-cache" in cache_control, (
        f"Cache-Control 应包含 no-cache: {cache_control}"
    )


def test_sse_endpoint_sets_connection_keep_alive():
    """SSE 端点应设置 Connection: keep-alive。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.get", return_value=_mock_task(status="completed")), \
         patch("app.api.routes.StepEventRepository.list_events", return_value=[]):
        response = client.get("/api/v1/rca/tasks/rca-sse-001/events")

    connection = response.headers.get("connection", "")
    assert "keep-alive" in connection.lower(), (
        f"Connection 应包含 keep-alive: {connection}"
    )


def test_sse_endpoint_404_for_nonexistent_task():
    """不存在的任务应返回 404。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.get", return_value=None):
        response = client.get("/api/v1/rca/tasks/nonexistent/events")

    assert response.status_code == 404


def test_sse_endpoint_passes_after_query_param():
    """after 查询参数应传递给 list_events。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.get", return_value=_mock_task(status="completed")), \
         patch("app.api.routes.StepEventRepository.list_events", return_value=[]) as mock_list:
        client.get("/api/v1/rca/tasks/rca-sse-001/events?after=5")

    mock_list.assert_called_once_with("rca-sse-001", after_seq=5)


def test_sse_endpoint_uses_last_event_id_header():
    """当 after 为 0 且存在 Last-Event-ID 头时，应使用其值。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.get", return_value=_mock_task(status="completed")), \
         patch("app.api.routes.StepEventRepository.list_events", return_value=[]) as mock_list:
        client.get(
            "/api/v1/rca/tasks/rca-sse-001/events",
            headers={"Last-Event-ID": "3"},
        )

    mock_list.assert_called_once_with("rca-sse-001", after_seq=3)


def test_sse_endpoint_after_param_overrides_last_event_id():
    """after 参数非零时应覆盖 Last-Event-ID 头。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.get", return_value=_mock_task(status="completed")), \
         patch("app.api.routes.StepEventRepository.list_events", return_value=[]) as mock_list:
        client.get(
            "/api/v1/rca/tasks/rca-sse-001/events?after=10",
            headers={"Last-Event-ID": "3"},
        )

    mock_list.assert_called_once_with("rca-sse-001", after_seq=10)


# ============================================================================
# 现有端点不受影响
# ============================================================================

def test_existing_endpoints_not_broken_by_sse():
    """SSE 端点不应破坏现有端点。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    # Health
    response = client.get("/api/v1/rca/health")
    assert response.status_code == 200

    # Tasks (需要 mock)
    mock_task = _mock_task(status="completed")
    with patch("app.api.routes.RCATaskRepository.get", return_value=mock_task):
        response = client.get("/api/v1/rca/tasks/rca-sse-001")
        assert response.status_code == 200

    # Reports (需要 mock)
    with patch("app.api.routes.RCATaskRepository.get", return_value=mock_task), \
         patch("app.api.routes.RCAReportRepository.get", return_value=None):
        response = client.get("/api/v1/rca/reports/rca-sse-001")
        assert response.status_code == 200
