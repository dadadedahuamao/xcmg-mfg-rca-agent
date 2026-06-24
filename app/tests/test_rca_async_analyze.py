"""RCA 异步分析端点契约测试 — Task 2: 将 /api/v1/rca/analyze 改为异步任务创建。

所有测试验证 POST /api/v1/rca/analyze 的异步契约：
- 返回 HTTP 202（非 200）
- 响应包含 task_id, status, message, events_url
- 任务记录在返回前已创建（status=pending）
- 后台任务被调度执行
"""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ============================================================================
# 路由前缀
# ============================================================================

def test_analyze_router_prefix_is_api_v1_rca():
    """RCA 路由前缀必须为 /api/v1/rca。"""
    from app.api.routes import router

    assert router.prefix == "/api/v1/rca"


# ============================================================================
# POST /api/v1/rca/analyze — 异步契约
# ============================================================================

_MOCK_TASK = {
    "task_id": "rca-test001",
    "status": "pending",
    "anomaly_type": "overstation_check",
    "description": "测试超站",
    "source_system": "MES",
    "metadata": "{}",
    "confidence": 0.0,
    "reflection_rounds": 0,
    "created_at": "2026-06-23 10:00:00.000",
    "updated_at": "2026-06-23 10:00:00.000",
    "completed_at": None,
}


def _make_request(client, task_id=None):
    """发送 POST /analyze 请求的辅助函数。"""
    body = {
        "event": {
            "anomaly_type": "overstation_check",
            "description": "测试超站",
            "source_system": "MES",
        },
    }
    if task_id:
        body["task_id"] = task_id
    return client.post("/api/v1/rca/analyze", json=body)


def test_analyze_returns_202_accepted():
    """POST /analyze 必须返回 HTTP 202 Accepted。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.create") as mock_create, \
         patch("app.api.routes.RCATaskRepository.update_status"), \
         patch("app.api.routes.RCAWorkflow"):
        mock_create.return_value = _MOCK_TASK
        response = _make_request(client)

    assert response.status_code == 202, (
        f"期望 HTTP 202，实际: {response.status_code}"
    )


def test_analyze_response_includes_task_id():
    """响应必须包含 task_id 字段。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.create") as mock_create, \
         patch("app.api.routes.RCATaskRepository.update_status"), \
         patch("app.api.routes.RCAWorkflow"):
        mock_create.return_value = _MOCK_TASK
        response = _make_request(client)

    data = response.json()
    assert "task_id" in data, f"响应缺少 task_id: {data}"
    assert data["task_id"].startswith("rca-"), (
        f"task_id 应以 'rca-' 开头: {data['task_id']}"
    )


def test_analyze_response_includes_status():
    """响应必须包含 status 字段。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.create") as mock_create, \
         patch("app.api.routes.RCATaskRepository.update_status"), \
         patch("app.api.routes.RCAWorkflow"):
        mock_create.return_value = _MOCK_TASK
        response = _make_request(client)

    data = response.json()
    assert "status" in data, f"响应缺少 status: {data}"
    assert data["status"] == "pending"


def test_analyze_response_includes_message():
    """响应必须包含 message 字段。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.create") as mock_create, \
         patch("app.api.routes.RCATaskRepository.update_status"), \
         patch("app.api.routes.RCAWorkflow"):
        mock_create.return_value = _MOCK_TASK
        response = _make_request(client)

    data = response.json()
    assert "message" in data, f"响应缺少 message: {data}"
    assert len(data["message"]) > 0


def test_analyze_response_includes_events_url():
    """响应必须包含 events_url 字段，指向任务事件端点。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.create") as mock_create, \
         patch("app.api.routes.RCATaskRepository.update_status"), \
         patch("app.api.routes.RCAWorkflow"):
        mock_create.return_value = _MOCK_TASK
        response = _make_request(client)

    data = response.json()
    assert "events_url" in data, f"响应缺少 events_url: {data}"
    # events_url 格式: /api/v1/rca/tasks/{task_id}/events
    assert "/api/v1/rca/tasks/" in data["events_url"]
    assert data["events_url"].endswith("/events")


def test_analyze_creates_task_before_returning():
    """任务记录必须在返回响应前创建（status=pending）。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.create") as mock_create, \
         patch("app.api.routes.RCATaskRepository.update_status"), \
         patch("app.api.routes.RCAWorkflow"):
        mock_create.return_value = _MOCK_TASK
        _make_request(client)

    mock_create.assert_called_once()
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["anomaly_type"] == "overstation_check"
    assert call_kwargs["description"] == "测试超站"


def test_analyze_schedules_background_task():
    """后台任务必须被调度执行（TestClient 中同步执行）。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.create") as mock_create, \
         patch("app.api.routes.RCATaskRepository.update_status"), \
         patch("app.api.routes.RCAWorkflow"):
        mock_create.return_value = _MOCK_TASK
        response = _make_request(client)

    assert response.status_code == 202


def test_analyze_auto_generates_task_id():
    """不传 task_id 时自动生成。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.create") as mock_create, \
         patch("app.api.routes.RCATaskRepository.update_status"), \
         patch("app.api.routes.RCAWorkflow"):
        mock_create.return_value = _MOCK_TASK
        response = _make_request(client)

    data = response.json()
    assert data["task_id"].startswith("rca-"), (
        f"自动生成的 task_id 应以 'rca-' 开头: {data['task_id']}"
    )


def test_analyze_accepts_custom_task_id():
    """传入自定义 task_id 时使用自定义值。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.create") as mock_create, \
         patch("app.api.routes.RCATaskRepository.update_status"), \
         patch("app.api.routes.RCAWorkflow"):
        mock_create.return_value = {**_MOCK_TASK, "task_id": "my-custom-task-123"}
        response = _make_request(client, task_id="my-custom-task-123")

    data = response.json()
    assert data["task_id"] == "my-custom-task-123"


def test_analyze_events_url_matches_task_id():
    """events_url 必须包含正确的 task_id。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    with patch("app.api.routes.RCATaskRepository.create") as mock_create, \
         patch("app.api.routes.RCATaskRepository.update_status"), \
         patch("app.api.routes.RCAWorkflow"):
        mock_create.return_value = {**_MOCK_TASK, "task_id": "rca-url-test"}
        response = _make_request(client, task_id="rca-url-test")

    data = response.json()
    expected_url = "/api/v1/rca/tasks/rca-url-test/events"
    assert data["events_url"] == expected_url, (
        f"events_url 不匹配: 期望 {expected_url}, 实际 {data['events_url']}"
    )


# ============================================================================
# 后台执行包装器测试
# ============================================================================

def test_background_wrapper_updates_status_on_success():
    """后台执行成功后应更新任务状态为 completed。"""
    from app.api.routes import _run_rca_background

    mock_workflow = Mock()
    mock_state = Mock()
    mock_state.task_id = "rca-bg-001"
    mock_state.status.value = "completed"
    mock_state.confidence = 0.85
    mock_state.reflection_round = 1
    mock_workflow.run.return_value = mock_state

    with patch("app.api.routes.RCATaskRepository.update_status") as mock_update:
        _run_rca_background(
            task_id="rca-bg-001",
            event_dict={
                "anomaly_type": "overstation_check",
                "description": "测试",
                "source_system": "MES",
                "metadata": {},
            },
            _workflow=mock_workflow,
        )

    assert mock_update.call_count == 2
    assert mock_update.call_args_list[0][0][0] == "rca-bg-001"
    assert mock_update.call_args_list[0][0][1] == "running"
    assert mock_update.call_args_list[1][0][0] == "rca-bg-001"
    assert mock_update.call_args_list[1][0][1] == "completed"


def test_background_wrapper_updates_status_on_failure():
    """后台执行失败时应更新任务状态为 failed。"""
    from app.api.routes import _run_rca_background

    mock_workflow = Mock()
    mock_workflow.run.side_effect = RuntimeError("模拟执行失败")

    with patch("app.api.routes.RCATaskRepository.update_status") as mock_update:
        _run_rca_background(
            task_id="rca-bg-002",
            event_dict={
                "anomaly_type": "overstation_check",
                "description": "测试",
                "source_system": "MES",
                "metadata": {},
            },
            _workflow=mock_workflow,
        )

    assert mock_update.call_count == 2
    assert mock_update.call_args_list[0][0][1] == "running"
    assert mock_update.call_args_list[1][0][1] == "failed"


# ============================================================================
# 现有端点不受影响
# ============================================================================

def test_get_reports_still_works():
    """GET /reports/{task_id} 端点不应被破坏。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    mock_task = {
        "task_id": "rca-existing",
        "status": "completed",
        "anomaly_type": "overstation_check",
        "description": "已有任务",
        "source_system": "MES",
        "metadata": "{}",
        "confidence": 0.85,
        "reflection_rounds": 1,
        "created_at": "2026-06-23 10:00:00.000",
        "updated_at": "2026-06-23 10:01:00.000",
        "completed_at": "2026-06-23 10:01:00.000",
    }

    with patch("app.api.routes.RCATaskRepository.get", return_value=mock_task), \
         patch("app.api.routes.RCAReportRepository.get", return_value=None):
        response = client.get("/api/v1/rca/reports/rca-existing")

    assert response.status_code == 200


def test_get_tasks_still_works():
    """GET /tasks/{task_id} 端点不应被破坏。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    mock_task = {
        "task_id": "rca-existing",
        "status": "completed",
        "anomaly_type": "overstation_check",
        "description": "已有任务",
        "source_system": "MES",
        "metadata": "{}",
        "confidence": 0.85,
        "reflection_rounds": 1,
        "created_at": "2026-06-23 10:00:00.000",
        "updated_at": "2026-06-23 10:01:00.000",
        "completed_at": "2026-06-23 10:01:00.000",
    }

    with patch("app.api.routes.RCATaskRepository.get", return_value=mock_task):
        response = client.get("/api/v1/rca/tasks/rca-existing")

    assert response.status_code == 200


def test_health_still_works():
    """GET /health 端点不应被破坏。"""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/v1/rca/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
