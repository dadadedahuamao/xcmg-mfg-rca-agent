"""RCA 工作流进度事件测试 — 适配 LangGraph stream/get_state 执行模型。

测试覆盖：
- task_started / node_started / node_completed / task_done 正常流程
- task_error 异常流程（新模型不发射 node_error）
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
    """使用 mock compiled graph 运行工作流。

    新执行模型：workflow.run() 调用 compiled.stream() 和 compiled.get_state()，
    不再使用旧的回调/ invoke 模型。
    """
    from app.agent.workflow import RCAWorkflow
    from app.agent.state import rca_state_to_graph_state

    event, state = _make_state()
    workflow = RCAWorkflow()
    events = []

    def capture_event(**kwargs):
        events.append(kwargs)

    with patch("app.agent.workflow.StepEventRepository.append_event",
               side_effect=capture_event), \
         patch.object(workflow, "_build_graph") as mock_build, \
         patch.object(workflow.checkpointer, "save"):

        mock_compiled = Mock()

        if raise_error:
            mock_compiled.stream.side_effect = RuntimeError("模拟节点执行失败")
        else:
            nodes = [
                "analyze_symptom", "generate_hypotheses", "select_tool",
                "execute_tool", "observe_evidence", "draft_rca",
                "reflect", "generate_report",
            ]
            mock_compiled.stream.return_value = iter([
                {node_name: {}} for node_name in nodes
            ])

        # Mock get_state 返回 graph state 快照
        graph_state = rca_state_to_graph_state(state)
        mock_snapshot = Mock()
        mock_snapshot.values = graph_state
        mock_compiled.get_state.return_value = mock_snapshot

        # _build_graph 直接返回 mock compiled graph
        mock_build.return_value = mock_compiled

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


def test_workflow_does_not_emit_node_error():
    """新 LangGraph stream 模型不发射 node_error 事件。

    异常通过 compiled.stream() 抛出，workflow 只发射 task_error。
    """
    events = []
    try:
        _, events = _run_with_mocked_graph(raise_error=True)
    except RuntimeError:
        pass
    node_error = [e for e in events if e["event_type"] == "node_error"]
    assert len(node_error) == 0, (
        f"新模型不应发射 node_error 事件，实际收到 {len(node_error)} 个"
    )


def test_task_error_includes_exception_message_in_summary():
    """task_error 事件的 summary 应包含异常消息。"""
    events = []
    try:
        _, events = _run_with_mocked_graph(raise_error=True)
    except RuntimeError:
        pass
    task_error = [e for e in events if e["event_type"] == "task_error"]
    assert len(task_error) == 1
    e = task_error[0]
    assert "模拟节点执行失败" in e["summary"], (
        f"summary 应包含异常消息，实际: {e['summary']}"
    )


def test_task_error_detail_json_includes_error():
    """task_error 的 detail_json 应包含 error 字段。"""
    events = []
    try:
        _, events = _run_with_mocked_graph(raise_error=True)
    except RuntimeError:
        pass
    task_error = [e for e in events if e["event_type"] == "task_error"]
    assert len(task_error) == 1
    e = task_error[0]
    assert e.get("detail_json") is not None, "task_error 应有 detail_json"
    assert "error" in e["detail_json"], (
        f"detail_json 应包含 error 字段: {e['detail_json']}"
    )
    assert e["detail_json"]["error"] == "模拟节点执行失败"


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
    """模拟 reflect 回退到 select_tool 的循环场景。

    新模型通过 compiled.stream() 产生包含重复节点的 chunks 来模拟循环。
    """
    from app.agent.workflow import RCAWorkflow
    from app.agent.state import rca_state_to_graph_state

    event, state = _make_state()
    workflow = RCAWorkflow()
    events = []

    def capture_event(**kwargs):
        events.append(kwargs)

    with patch("app.agent.workflow.StepEventRepository.append_event",
               side_effect=capture_event), \
         patch.object(workflow, "_build_graph") as mock_build, \
         patch.object(workflow.checkpointer, "save"):

        mock_compiled = Mock()

        # 模拟循环：第一次遍历全部节点，reflect 触发 NEED_MORE_EVIDENCE 回退
        loop_nodes = [
            "analyze_symptom", "generate_hypotheses",
            "select_tool", "execute_tool", "observe_evidence",
            "draft_rca", "reflect",
            # 回退到 select_tool
            "select_tool", "execute_tool", "observe_evidence",
            "draft_rca", "reflect",
            # 最终 PROCEED → generate_report
            "generate_report",
        ]
        mock_compiled.stream.return_value = iter([
            {node_name: {}} for node_name in loop_nodes
        ])

        graph_state = rca_state_to_graph_state(state)
        mock_snapshot = Mock()
        mock_snapshot.values = graph_state
        mock_compiled.get_state.return_value = mock_snapshot

        mock_build.return_value = mock_compiled

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
    """验证新 stream 模型下检查点保存仍然正常触发。"""
    from app.agent.workflow import RCAWorkflow
    from app.agent.state import rca_state_to_graph_state

    event, state = _make_state()
    workflow = RCAWorkflow()

    with patch.object(workflow, "_build_graph") as mock_build, \
         patch("app.agent.workflow.StepEventRepository.append_event"), \
         patch.object(workflow.checkpointer, "save") as mock_save:

        mock_compiled = Mock()

        nodes = [
            "analyze_symptom", "generate_hypotheses", "select_tool",
            "execute_tool", "observe_evidence", "draft_rca",
            "reflect", "generate_report",
        ]
        mock_compiled.stream.return_value = iter([
            {node_name: {}} for node_name in nodes
        ])

        graph_state = rca_state_to_graph_state(state)
        mock_snapshot = Mock()
        mock_snapshot.values = graph_state
        mock_compiled.get_state.return_value = mock_snapshot

        mock_build.return_value = mock_compiled

        workflow.run(event=event, task_id="test-ckpt", skip_persistence=True)

    assert mock_save.call_count == 8


# ============================================================================
# 安全错误消息测试
# ============================================================================

def test_safe_error_message_masks_password():
    """_safe_error_message 应掩码 password=xxx 形式的敏感信息。"""
    from app.agent.workflow import _safe_error_message

    error = Exception("连接失败: password=mysecret123, host=localhost")
    safe = _safe_error_message(error)
    assert "mysecret123" not in safe
    assert "password=***" in safe
    assert "host=localhost" in safe


def test_safe_error_message_masks_api_key():
    """_safe_error_message 应掩码 api_key=xxx 形式的敏感信息。"""
    from app.agent.workflow import _safe_error_message

    error = Exception("认证失败: api_key=sk-abc123def456, user=admin")
    safe = _safe_error_message(error)
    assert "sk-abc123def456" not in safe
    assert "api_key=***" in safe
    assert "user=admin" in safe


def test_safe_error_message_masks_token():
    """_safe_error_message 应掩码 token=xxx 形式的敏感信息。"""
    from app.agent.workflow import _safe_error_message

    error = Exception("token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0 invalid")
    safe = _safe_error_message(error)
    assert "eyJhbGciOiJIUzI1NiJ9" not in safe
    assert "token=***" in safe


def test_safe_error_message_masks_sk_prefix():
    """_safe_error_message 应掩码 sk- 前缀的长密钥。"""
    from app.agent.workflow import _safe_error_message

    error = Exception("密钥 sk-proj-abcdefghijklmnopqrstuvwxyz 无效")
    safe = _safe_error_message(error)
    assert "sk-proj-abcdefghijklmnopqrstuvwxyz" not in safe
    assert "sk-***" in safe


def test_safe_error_message_truncates_long_messages():
    """_safe_error_message 应截断超过 500 字符的消息。"""
    from app.agent.workflow import _safe_error_message

    long_msg = "x" * 600
    error = Exception(long_msg)
    safe = _safe_error_message(error)
    assert len(safe) <= 503  # 500 + "..."
    assert safe.endswith("...")


def test_safe_error_message_preserves_safe_content():
    """_safe_error_message 不应修改不含敏感信息的普通消息。"""
    from app.agent.workflow import _safe_error_message

    error = Exception("模拟节点执行失败")
    safe = _safe_error_message(error)
    assert safe == "模拟节点执行失败"
