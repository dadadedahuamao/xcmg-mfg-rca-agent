"""RCA 工作流进度事件测试 — Task 3: 为 RCAWorkflow 注入结构化节点事件。

测试覆盖：
- task_started / node_started / node_completed / task_done 正常流程
- task_error / node_error 异常流程
- 中文 title/summary
- detail_json 包含 node_name, round, duration_ms
- reflect 循环追加新 seq 事件
- skip_persistence 仍能发出事件
- 事件顺序正确
"""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


# ============================================================================
# 测试辅助
# ============================================================================

def _make_state():
    from app.schemas.api import AnomalyEvent, TaskStatus
    from app.agent.state import RCAState

    event = AnomalyEvent(anomaly_type="overstation_check", description="测试超站")
    state = RCAState(task_id="test-001", event=event)
    state.status = TaskStatus.COMPLETED
    state.confidence = 0.85
    state.reflection_round = 1
    state.current_node = "generate_report"
    return event, state


def _run_with_mocked_graph(task_id="test-001", skip_persistence=True, raise_error=False):
    from app.agent.workflow import RCAWorkflow

    event, state = _make_state()
    workflow = RCAWorkflow()
    events = []

    def capture_event(**kwargs):
        events.append(kwargs)

    with patch("app.agent.workflow.StepEventRepository.append_event",
               side_effect=capture_event), \
         patch.object(workflow, "_build_graph") as mock_build, \
         patch.object(workflow.checkpointer, "save"):

        mock_graph = Mock()
        mock_compiled = Mock()
        captured_callbacks = {}

        def mock_set_callback(cb):
            captured_callbacks["complete"] = cb

        def mock_set_start_callback(cb):
            captured_callbacks["start"] = cb

        def mock_set_error_callback(cb):
            captured_callbacks["error"] = cb

        mock_compiled.set_callback = mock_set_callback
        mock_compiled.set_start_callback = mock_set_start_callback
        mock_compiled.set_error_callback = mock_set_error_callback

        def mock_invoke(initial_state, resume_from=None):
            if raise_error:
                # 模拟节点执行异常：先触发 start，再触发 error（传入 exception）
                cb_start = captured_callbacks.get("start")
                cb_error = captured_callbacks.get("error")
                exc = RuntimeError("模拟节点执行失败")
                if cb_start:
                    cb_start("analyze_symptom", initial_state)
                if cb_error:
                    cb_error("analyze_symptom", initial_state, exc)
                raise exc

            cb_start = captured_callbacks.get("start")
            cb_complete = captured_callbacks.get("complete")

            nodes = [
                "analyze_symptom", "generate_hypotheses", "select_tool",
                "execute_tool", "observe_evidence", "draft_rca",
                "reflect", "generate_report",
            ]

            for node_name in nodes:
                if cb_start:
                    cb_start(node_name, initial_state)
                if cb_complete:
                    cb_complete(node_name, initial_state)

            return state

        mock_compiled.invoke = mock_invoke
        mock_graph.compile.return_value = mock_compiled
        mock_build.return_value = mock_graph

        try:
            result = workflow.run(event=event, task_id=task_id,
                                  skip_persistence=skip_persistence)
        except RuntimeError:
            result = None

    return result, events


# ============================================================================
# 正常流程事件测试
# ============================================================================

def test_workflow_emits_task_started():
    _, events = _run_with_mocked_graph()
    task_started = [e for e in events if e["event_type"] == "task_started"]
    assert len(task_started) == 1
    e = task_started[0]
    assert e["task_id"] == "test-001"
    assert e["status"] == "running"
    assert len(e["title"]) > 0


def test_workflow_emits_node_started_for_each_node():
    _, events = _run_with_mocked_graph()
    node_started = [e for e in events if e["event_type"] == "node_started"]
    assert len(node_started) == 8
    node_names = [e["node_name"] for e in node_started]
    assert "analyze_symptom" in node_names
    assert "generate_report" in node_names


def test_workflow_emits_node_completed_for_each_node():
    _, events = _run_with_mocked_graph()
    node_completed = [e for e in events if e["event_type"] == "node_completed"]
    assert len(node_completed) == 8


def test_workflow_emits_task_done():
    _, events = _run_with_mocked_graph()
    task_done = [e for e in events if e["event_type"] == "task_done"]
    assert len(task_done) == 1
    e = task_done[0]
    assert e["task_id"] == "test-001"
    assert e["status"] == "completed"


def test_workflow_event_order():
    _, events = _run_with_mocked_graph()
    types = [e["event_type"] for e in events]
    assert types[0] == "task_started"
    assert types[-1] == "task_done"
    for i in range(1, len(types) - 1, 2):
        assert types[i] == "node_started"
        assert types[i + 1] == "node_completed"


# ============================================================================
# 异常流程事件测试
# ============================================================================

def test_workflow_emits_task_error_on_exception():
    events = []
    try:
        _, events = _run_with_mocked_graph(raise_error=True)
    except RuntimeError:
        pass
    task_error = [e for e in events if e["event_type"] == "task_error"]
    assert len(task_error) == 1
    e = task_error[0]
    assert e["task_id"] == "test-001"
    assert e["status"] == "failed"


def test_workflow_emits_node_error_on_exception():
    events = []
    try:
        _, events = _run_with_mocked_graph(raise_error=True)
    except RuntimeError:
        pass
    node_error = [e for e in events if e["event_type"] == "node_error"]
    assert len(node_error) >= 1


def test_node_error_includes_exception_message_in_summary():
    """node_error 事件的 summary 应包含异常消息。"""
    events = []
    try:
        _, events = _run_with_mocked_graph(raise_error=True)
    except RuntimeError:
        pass
    node_error = [e for e in events if e["event_type"] == "node_error"]
    assert len(node_error) >= 1
    e = node_error[0]
    assert "模拟节点执行失败" in e["summary"], (
        f"summary 应包含异常消息，实际: {e['summary']}"
    )


def test_node_error_detail_json_includes_error_and_error_type():
    """node_error 的 detail_json 应包含 error 和 error_type 字段。"""
    events = []
    try:
        _, events = _run_with_mocked_graph(raise_error=True)
    except RuntimeError:
        pass
    node_error = [e for e in events if e["event_type"] == "node_error"]
    assert len(node_error) >= 1
    e = node_error[0]
    assert e.get("detail_json") is not None, "node_error 应有 detail_json"
    assert "error" in e["detail_json"], (
        f"detail_json 应包含 error 字段: {e['detail_json']}"
    )
    assert "error_type" in e["detail_json"], (
        f"detail_json 应包含 error_type 字段: {e['detail_json']}"
    )
    assert e["detail_json"]["error"] == "模拟节点执行失败"
    assert e["detail_json"]["error_type"] == "RuntimeError"


# ============================================================================
# 中文 title / summary 测试
# ============================================================================

def test_node_started_has_chinese_title():
    _, events = _run_with_mocked_graph()
    node_started = [e for e in events if e["event_type"] == "node_started"]
    for e in node_started:
        assert len(e["title"]) > 0
        assert any('\u4e00' <= c <= '\u9fff' for c in e["title"])


def test_node_completed_has_chinese_title():
    _, events = _run_with_mocked_graph()
    node_completed = [e for e in events if e["event_type"] == "node_completed"]
    for e in node_completed:
        assert len(e["title"]) > 0
        assert any('\u4e00' <= c <= '\u9fff' for c in e["title"])


def test_task_started_has_chinese_title():
    _, events = _run_with_mocked_graph()
    task_started = [e for e in events if e["event_type"] == "task_started"]
    e = task_started[0]
    assert any('\u4e00' <= c <= '\u9fff' for c in e["title"])


def test_task_done_has_chinese_title():
    _, events = _run_with_mocked_graph()
    task_done = [e for e in events if e["event_type"] == "task_done"]
    e = task_done[0]
    assert any('\u4e00' <= c <= '\u9fff' for c in e["title"])


# ============================================================================
# detail_json 测试
# ============================================================================

def test_node_started_detail_json_has_node_name():
    _, events = _run_with_mocked_graph()
    node_started = [e for e in events if e["event_type"] == "node_started"]
    for e in node_started:
        assert e.get("detail_json") is not None
        assert "node_name" in e["detail_json"]


def test_node_completed_detail_json_has_node_name_and_round():
    _, events = _run_with_mocked_graph()
    node_completed = [e for e in events if e["event_type"] == "node_completed"]
    for e in node_completed:
        assert e.get("detail_json") is not None
        assert "node_name" in e["detail_json"]
        assert "round" in e["detail_json"]


def test_node_completed_detail_json_has_duration_ms():
    _, events = _run_with_mocked_graph()
    node_completed = [e for e in events if e["event_type"] == "node_completed"]
    for e in node_completed:
        assert "duration_ms" in e["detail_json"]
        assert isinstance(e["detail_json"]["duration_ms"], (int, float))


def test_task_done_detail_json_has_confidence():
    _, events = _run_with_mocked_graph()
    task_done = [e for e in events if e["event_type"] == "task_done"]
    e = task_done[0]
    assert e.get("detail_json") is not None
    assert "confidence" in e["detail_json"]
    assert "reflection_rounds" in e["detail_json"]


# ============================================================================
# skip_persistence 测试
# ============================================================================

def test_skip_persistence_still_emits_events():
    _, events = _run_with_mocked_graph(skip_persistence=True)
    assert len(events) > 0
    event_types = {e["event_type"] for e in events}
    assert "task_started" in event_types
    assert "task_done" in event_types


# ============================================================================
# reflect 循环测试
# ============================================================================

def test_reflect_loop_appends_new_events():
    from app.agent.workflow import RCAWorkflow

    event, state = _make_state()
    workflow = RCAWorkflow()
    events = []

    def capture_event(**kwargs):
        events.append(kwargs)

    with patch("app.agent.workflow.StepEventRepository.append_event",
               side_effect=capture_event), \
         patch.object(workflow, "_build_graph") as mock_build, \
         patch.object(workflow.checkpointer, "save"):

        mock_graph = Mock()
        mock_compiled = Mock()
        captured_callbacks = {}

        def mock_set_callback(cb):
            captured_callbacks["complete"] = cb

        def mock_set_start_callback(cb):
            captured_callbacks["start"] = cb

        def mock_set_error_callback(cb):
            captured_callbacks["error"] = cb

        mock_compiled.set_callback = mock_set_callback
        mock_compiled.set_start_callback = mock_set_start_callback
        mock_compiled.set_error_callback = mock_set_error_callback

        def mock_invoke(initial_state, resume_from=None):
            cb_start = captured_callbacks.get("start")
            cb_complete = captured_callbacks.get("complete")

            # 第一次循环
            for node_name in ["analyze_symptom", "generate_hypotheses",
                              "select_tool", "execute_tool", "observe_evidence",
                              "draft_rca", "reflect"]:
                if cb_start:
                    cb_start(node_name, initial_state)
                if cb_complete:
                    cb_complete(node_name, initial_state)

            # reflect 决定 NEED_MORE_EVIDENCE，回退到 select_tool
            for node_name in ["select_tool", "execute_tool", "observe_evidence",
                              "draft_rca", "reflect"]:
                if cb_start:
                    cb_start(node_name, initial_state)
                if cb_complete:
                    cb_complete(node_name, initial_state)

            # 最终 PROCEED -> generate_report
            for node_name in ["generate_report"]:
                if cb_start:
                    cb_start(node_name, initial_state)
                if cb_complete:
                    cb_complete(node_name, initial_state)

            return state

        mock_compiled.invoke = mock_invoke
        mock_graph.compile.return_value = mock_compiled
        mock_build.return_value = mock_graph

        workflow.run(event=event, task_id="test-loop", skip_persistence=True)

    select_tool_events = [
        e for e in events
        if e["node_name"] == "select_tool" and e["event_type"] == "node_started"
    ]
    assert len(select_tool_events) == 2


# ============================================================================
# 节点标题映射测试
# ============================================================================

def test_all_eight_nodes_have_chinese_titles():
    from app.agent.workflow import RCAWorkflow

    workflow = RCAWorkflow()
    expected_nodes = [
        "analyze_symptom", "generate_hypotheses", "select_tool",
        "execute_tool", "observe_evidence", "draft_rca",
        "reflect", "generate_report",
    ]
    node_titles = getattr(workflow, "_NODE_TITLES", None)
    if node_titles is None:
        node_titles = getattr(RCAWorkflow, "_NODE_TITLES", None)
    assert node_titles is not None
    for node_name in expected_nodes:
        assert node_name in node_titles
        title = node_titles[node_name]
        assert len(title) > 0
        assert any('\u4e00' <= c <= '\u9fff' for c in title)


# ============================================================================
# 检查点保存不受影响
# ============================================================================

def test_checkpoint_save_still_occurs():
    from app.agent.workflow import RCAWorkflow

    event, state = _make_state()
    workflow = RCAWorkflow()

    with patch.object(workflow, "_build_graph") as mock_build,          patch("app.agent.workflow.StepEventRepository.append_event"),          patch.object(workflow.checkpointer, "save") as mock_save:

        mock_graph = Mock()
        mock_compiled = Mock()
        captured_callbacks = {}

        def mock_set_callback(cb):
            captured_callbacks["complete"] = cb

        def mock_set_start_callback(cb):
            captured_callbacks["start"] = cb

        def mock_set_error_callback(cb):
            captured_callbacks["error"] = cb

        mock_compiled.set_callback = mock_set_callback
        mock_compiled.set_start_callback = mock_set_start_callback
        mock_compiled.set_error_callback = mock_set_error_callback

        def mock_invoke(initial_state, resume_from=None):
            for node_name in ["analyze_symptom", "generate_hypotheses",
                              "select_tool", "execute_tool", "observe_evidence",
                              "draft_rca", "reflect", "generate_report"]:
                if captured_callbacks:
                    captured_callbacks["complete"](node_name, initial_state)
            return state

        mock_compiled.invoke = mock_invoke
        mock_graph.compile.return_value = mock_compiled
        mock_build.return_value = mock_graph

        workflow.run(event=event, task_id="test-ckpt", skip_persistence=True)

    assert mock_save.call_count == 8
