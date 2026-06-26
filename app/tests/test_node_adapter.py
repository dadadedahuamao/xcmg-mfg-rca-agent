"""单元测试 - node_adapter 模块。

测试适配器模块的导入、增量 diff 逻辑和导出完整性。
不调用真实业务节点，仅验证适配层逻辑。
"""

import sys
import uuid
from pathlib import Path
from typing import Any, cast

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest

from app.agent.state import RCAState, RCAGraphState


# ═══════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════

def _make_minimal_graph_state(**overrides) -> RCAGraphState:
    """创建最小可用的 RCAGraphState 用于测试。"""
    state: RCAGraphState = {
        "task_id": f"test-{uuid.uuid4().hex[:8]}",
        "status": "pending",
        "current_node": None,
        "event": None,
        "hypotheses": [],
        "evidence": [],
        "selected_tools": [],
        "tool_call_history": [],
        "reflection_round": 0,
        "draft_rca": None,
        "reflection_result": None,
        "confidence": 0.0,
        "final_report": None,
        "prompt_history": [],
        "anomaly_type": "test_type",
        "description": "test description",
        "source_system": "MES",
        "metadata": {},
        "created_at": "",
        "completed_at": None,
    }
    cast("dict[str, Any]", state).update(overrides)
    return state


def _fake_node_append_evidence(state: RCAState) -> RCAState:
    """假节点函数：追加一条证据到已有列表。"""
    state.evidence.append({"id": "new_ev", "content": "new evidence"})
    return state


def _fake_node_change_scalar(state: RCAState) -> RCAState:
    """假节点函数：修改标量字段 description。"""
    state.description = "modified"
    return state


def _fake_node_change_scalar_and_append(state: RCAState) -> RCAState:
    """假节点函数：同时修改标量和追加列表。"""
    state.description = "modified"
    state.evidence.append({"id": "ev2", "content": "more evidence"})
    return state


def _fake_node_replace_list(state: RCAState) -> RCAState:
    """假节点函数：替换整个列表（非追加）。"""
    state.evidence = [{"id": "replaced", "content": "replaced list"}]
    return state


def _identity_node(state: RCAState) -> RCAState:
    """恒等假节点函数：原样返回。"""
    return state


# ═══════════════════════════════════════════════════════════════
# 测试: _compute_diff 函数
# ═══════════════════════════════════════════════════════════════

class TestComputeDiff:
    """测试 _compute_diff 增量计算逻辑。"""

    def test_reducer_list_append_returns_only_suffix(self):
        """验证 reducer 列表追加只返回新增项。"""
        from app.agent.node_adapter import _compute_diff

        before: RCAGraphState = {
            "evidence": [{"id": "ev1"}],
        }
        after: RCAGraphState = {
            "evidence": [{"id": "ev1"}, {"id": "ev2"}, {"id": "ev3"}],
        }

        diff: dict[str, Any] = cast("dict[str, Any]", _compute_diff(before, after))

        assert "evidence" in diff
        assert diff["evidence"] == [{"id": "ev2"}, {"id": "ev3"}]

    def test_reducer_list_no_change_returns_empty(self):
        """验证 reducer 列表无变更时不返回。"""
        from app.agent.node_adapter import _compute_diff

        before: RCAGraphState = {"evidence": [{"id": "ev1"}]}
        after: RCAGraphState = {"evidence": [{"id": "ev1"}]}

        diff: dict[str, Any] = cast("dict[str, Any]", _compute_diff(before, after))

        assert "evidence" not in diff

    def test_reducer_list_replace_returns_full_list(self):
        """验证 reducer 列表被替换时返回完整列表。"""
        from app.agent.node_adapter import _compute_diff

        before: RCAGraphState = {"evidence": [{"id": "ev1"}]}
        after: RCAGraphState = {"evidence": [{"id": "replaced"}]}

        diff: dict[str, Any] = cast("dict[str, Any]", _compute_diff(before, after))

        assert "evidence" in diff
        assert diff["evidence"] == [{"id": "replaced"}]

    def test_scalar_change_returns_only_changed_field(self):
        """验证标量变更只返回该字段。"""
        from app.agent.node_adapter import _compute_diff

        before: RCAGraphState = {"description": "old", "status": "pending"}
        after: RCAGraphState = {"description": "new", "status": "pending"}

        diff: dict[str, Any] = cast("dict[str, Any]", _compute_diff(before, after))

        assert diff == {"description": "new"}

    def test_no_changes_returns_empty_dict(self):
        """验证无变更时返回空字典。"""
        from app.agent.node_adapter import _compute_diff

        before: RCAGraphState = {"description": "same", "confidence": 0.5}
        after: RCAGraphState = {"description": "same", "confidence": 0.5}

        diff: dict[str, Any] = cast("dict[str, Any]", _compute_diff(before, after))

        assert diff == {}

    def test_multiple_reducer_lists_append(self):
        """验证多个 reducer 列表同时追加。"""
        from app.agent.node_adapter import _compute_diff

        before: RCAGraphState = {
            "hypotheses": [{"h": 1}],
            "evidence": [{"e": 1}],
            "selected_tools": ["tool_a"],
        }
        after: RCAGraphState = {
            "hypotheses": [{"h": 1}, {"h": 2}],
            "evidence": [{"e": 1}, {"e": 2}],
            "selected_tools": ["tool_a", "tool_b"],
        }

        diff: dict[str, Any] = cast("dict[str, Any]", _compute_diff(before, after))

        assert diff["hypotheses"] == [{"h": 2}]
        assert diff["evidence"] == [{"e": 2}]
        assert diff["selected_tools"] == ["tool_b"]

    def test_optional_field_from_none_to_value(self):
        """验证可选字段从 None 变为有值。"""
        from app.agent.node_adapter import _compute_diff

        before: RCAGraphState = {"draft_rca": None}
        after: RCAGraphState = {"draft_rca": "some draft"}

        diff = _compute_diff(before, after)

        assert diff == {"draft_rca": "some draft"}

    def test_optional_field_from_value_to_none(self):
        """验证可选字段从有值变为 None。"""
        from app.agent.node_adapter import _compute_diff

        before: RCAGraphState = {"draft_rca": "old draft"}
        after: RCAGraphState = {"draft_rca": None}

        diff = _compute_diff(before, after)

        assert diff == {"draft_rca": None}


# ═══════════════════════════════════════════════════════════════
# 测试: adapt_node 函数
# ═══════════════════════════════════════════════════════════════

class TestAdaptNode:
    """测试 adapt_node 核心包装逻辑。"""

    def test_append_to_reducer_list_returns_only_new_items(self):
        """验证节点追加列表时只返回新增项，不返回已有项。"""
        from app.agent.node_adapter import adapt_node

        adapted = adapt_node(_fake_node_append_evidence, node_name="append_ev")
        graph_state = _make_minimal_graph_state(
            evidence=[{"id": "existing", "content": "original"}],
        )

        result: dict[str, Any] = cast("dict[str, Any]", adapted(graph_state))

        # 必须只返回新增项，不能包含已有项
        assert "evidence" in result
        assert result["evidence"] == [{"id": "new_ev", "content": "new evidence"}]
        assert len(result["evidence"]) == 1

    def test_identity_node_returns_empty_dict(self):
        """验证恒等节点（无变更）返回空字典。"""
        from app.agent.node_adapter import adapt_node

        adapted = adapt_node(_identity_node, node_name="identity")
        graph_state = _make_minimal_graph_state()

        result: dict[str, Any] = cast("dict[str, Any]", adapted(graph_state))

        assert result == {}

    def test_scalar_change_returns_only_changed_field(self):
        """验证标量变更只返回该字段。"""
        from app.agent.node_adapter import adapt_node

        adapted = adapt_node(_fake_node_change_scalar, node_name="change_scalar")
        graph_state = _make_minimal_graph_state(description="original")

        result: dict[str, Any] = cast("dict[str, Any]", adapted(graph_state))

        assert result == {"description": "modified"}

    def test_mixed_changes_returns_only_deltas(self):
        """验证同时修改标量和追加列表时只返回增量。"""
        from app.agent.node_adapter import adapt_node

        adapted = adapt_node(
            _fake_node_change_scalar_and_append, node_name="mixed"
        )
        graph_state = _make_minimal_graph_state(
            description="original",
            evidence=[{"id": "existing", "content": "original"}],
        )

        result: dict[str, Any] = cast("dict[str, Any]", adapted(graph_state))

        # 标量变更
        assert result["description"] == "modified"
        # 列表只返回新增项
        assert result["evidence"] == [{"id": "ev2", "content": "more evidence"}]
        assert len(result["evidence"]) == 1

    def test_replace_list_returns_full_list(self):
        """验证节点替换整个列表时返回完整列表。"""
        from app.agent.node_adapter import adapt_node

        adapted = adapt_node(_fake_node_replace_list, node_name="replace_list")
        graph_state = _make_minimal_graph_state(
            evidence=[{"id": "existing", "content": "original"}],
        )

        result: dict[str, Any] = cast("dict[str, Any]", adapted(graph_state))

        # 非追加模式，返回完整列表
        assert "evidence" in result
        assert result["evidence"] == [{"id": "replaced", "content": "replaced list"}]

    def test_adapted_function_metadata(self):
        """验证适配后函数保留正确的元数据。"""
        from app.agent.node_adapter import adapt_node

        adapted = adapt_node(_identity_node, node_name="meta_test")

        assert adapted.__name__ == "adapted_meta_test"
        assert "RCAGraphState" in (adapted.__doc__ or "")


# ═══════════════════════════════════════════════════════════════
# 测试: 导出完整性
# ═══════════════════════════════════════════════════════════════

class TestExports:
    """验证 node_adapter 模块的导出内容。"""

    def test_all_adapted_nodes_importable(self):
        """验证所有 8 个适配节点函数可导入且可调用。"""
        from app.agent.node_adapter import (
            adapted_analyze_symptom,
            adapted_generate_hypotheses,
            adapted_select_tool,
            adapted_execute_tool,
            adapted_observe_evidence,
            adapted_draft_rca,
            adapted_reflect,
            adapted_generate_report,
        )

        for name, func in [
            ("adapted_analyze_symptom", adapted_analyze_symptom),
            ("adapted_generate_hypotheses", adapted_generate_hypotheses),
            ("adapted_select_tool", adapted_select_tool),
            ("adapted_execute_tool", adapted_execute_tool),
            ("adapted_observe_evidence", adapted_observe_evidence),
            ("adapted_draft_rca", adapted_draft_rca),
            ("adapted_reflect", adapted_reflect),
            ("adapted_generate_report", adapted_generate_report),
        ]:
            assert callable(func), f"{name} 应该可调用"
            assert func.__name__.startswith("adapted_"), (
                f"{name} 的 __name__ 应以 adapted_ 开头"
            )

    def test_adapted_nodes_dict(self):
        """验证 ADAPTED_NODES 字典包含全部 8 个节点。"""
        from app.agent.node_adapter import ADAPTED_NODES

        expected_keys = [
            "analyze_symptom",
            "generate_hypotheses",
            "select_tool",
            "execute_tool",
            "observe_evidence",
            "draft_rca",
            "reflect",
            "generate_report",
        ]

        assert isinstance(ADAPTED_NODES, dict)
        assert len(ADAPTED_NODES) == 8
        for key in expected_keys:
            assert key in ADAPTED_NODES, f"ADAPTED_NODES 缺少键: {key}"
            assert callable(ADAPTED_NODES[key]), (
                f"ADAPTED_NODES[{key!r}] 应该可调用"
            )

    def test_adapted_nodes_dict_values_match_exports(self):
        """验证 ADAPTED_NODES 字典值与独立导出一致。"""
        from app.agent.node_adapter import (
            ADAPTED_NODES,
            adapted_analyze_symptom,
            adapted_generate_hypotheses,
            adapted_select_tool,
            adapted_execute_tool,
            adapted_observe_evidence,
            adapted_draft_rca,
            adapted_reflect,
            adapted_generate_report,
        )

        assert ADAPTED_NODES["analyze_symptom"] is adapted_analyze_symptom
        assert ADAPTED_NODES["generate_hypotheses"] is adapted_generate_hypotheses
        assert ADAPTED_NODES["select_tool"] is adapted_select_tool
        assert ADAPTED_NODES["execute_tool"] is adapted_execute_tool
        assert ADAPTED_NODES["observe_evidence"] is adapted_observe_evidence
        assert ADAPTED_NODES["draft_rca"] is adapted_draft_rca
        assert ADAPTED_NODES["reflect"] is adapted_reflect
        assert ADAPTED_NODES["generate_report"] is adapted_generate_report


# ═══════════════════════════════════════════════════════════════
# 测试: 导入无副作用
# ═══════════════════════════════════════════════════════════════

class TestImportSafety:
    """验证模块导入不会触发副作用。"""

    def test_adapter_does_not_call_node_on_import(self):
        """验证导入模块时不会触发任何节点函数调用。"""
        import importlib
        import sys

        mod = importlib.import_module("app.agent.node_adapter")
        assert mod is not None
        assert callable(mod.adapt_node)
