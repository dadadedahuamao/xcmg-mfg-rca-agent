"""RCA 工作流节点适配器。

将接收/返回 RCAState (Pydantic) 的业务节点函数，
适配为接收/返回 RCAGraphState (TypedDict) 的 LangGraph 兼容节点。

关键设计：增量返回（diff）。
由于 RCAGraphState 列表字段使用 Annotated[list, operator.add] 作为 reducer，
返回全量列表会导致 LangGraph 重复追加已有数据。
适配器通过快照对比，只返回变更的字段；对于 reducer 列表字段，
如果节点只做了追加操作，只返回新增项。

用法:
    from app.agent.node_adapter import adapted_analyze_symptom, ADAPTED_NODES
    graph_state = adapted_analyze_symptom(graph_state)  # 输入/输出都是 RCAGraphState
"""

import copy
import logging
from typing import Any, Callable, Optional

from app.agent.state import (
    RCAState,
    RCAGraphState,
    graph_state_to_rca_state,
    rca_state_to_graph_state,
)
from app.agent.nodes.analyze_symptom import analyze_symptom_node
from app.agent.nodes.generate_hypotheses import generate_hypotheses_node
from app.agent.nodes.select_tool import select_tool_node
from app.agent.nodes.execute_tool import execute_tool_node
from app.agent.nodes.observe_evidence import observe_evidence_node
from app.agent.nodes.draft_rca import draft_rca_node
from app.agent.nodes.reflect import reflect_node
from app.agent.nodes.generate_report import generate_report_node

logger = logging.getLogger(__name__)

# 节点函数签名: (RCAGraphState) -> RCAGraphState
AdaptedNodeFunc = Callable[[RCAGraphState], RCAGraphState]

# 使用 operator.add reducer 的列表字段
# 对于这些字段，如果 after 以 before 为前缀，只返回新增项
_REDUCER_LIST_FIELDS: set[str] = {
    "hypotheses",
    "evidence",
    "selected_tools",
    "tool_call_history",
    "prompt_history",
}


def _compute_diff(before: RCAGraphState, after: RCAGraphState) -> RCAGraphState:
    """计算 before → after 的增量变更。

    对于 reducer 列表字段，如果 after 以 before 为前缀，只返回新增项。
    对于标量/字典/可选字段，只返回变更的值。
    无变更时返回空字典。
    """
    diff: RCAGraphState = {}

    for key, after_value in after.items():
        before_value = before.get(key)

        if key in _REDUCER_LIST_FIELDS:
            # reducer 列表字段：尝试提取后缀
            before_list = before_value if isinstance(before_value, list) else []
            after_list = after_value if isinstance(after_value, list) else []

            if len(after_list) >= len(before_list) and after_list[: len(before_list)] == before_list:
                # 追加模式：仅返回新增项
                suffix = after_list[len(before_list) :]
                if suffix:
                    diff[key] = suffix
            else:
                # 非追加变更（替换/重排），返回完整列表
                # 注意：与 operator.add reducer 配合使用时可能导致重复
                # 调用方应确保此类场景使用覆盖式写入策略
                diff[key] = list(after_list)
        else:
            # 标量/字典/可选字段：仅返回变更值
            if after_value != before_value:
                diff[key] = copy.deepcopy(after_value)

    return diff


def adapt_node(
    node_func: Callable[[RCAState], RCAState],
    node_name: Optional[str] = None,
) -> AdaptedNodeFunc:
    """将接收/返回 RCAState 的节点函数适配为接收/返回 RCAGraphState。

    通过快照对比实现增量返回，避免 reducer 列表字段重复。

    Args:
        node_func: 原始业务节点函数，签名为 (RCAState) -> RCAState
        node_name: 节点名称（仅用于日志）

    Returns:
        适配后的节点函数，签名为 (RCAGraphState) -> RCAGraphState
    """
    name = node_name or getattr(node_func, "__name__", "unknown")

    def adapted(graph_state: RCAGraphState) -> RCAGraphState:
        # 1. 将 RCAGraphState (TypedDict) 转换为 RCAState (Pydantic)
        rca_state = graph_state_to_rca_state(graph_state)

        # 2. 快照：调用前的 graph state（用于后续 diff）
        before_gs = rca_state_to_graph_state(rca_state)

        # 3. 调用原始业务节点
        logger.debug(f"[Adapter] 调用节点: {name}")
        result_rca = node_func(rca_state)

        # 4. 将 RCAState 转换回 RCAGraphState
        after_gs = rca_state_to_graph_state(result_rca)

        # 5. 计算增量变更并返回
        return _compute_diff(before_gs, after_gs)

    adapted.__name__ = f"adapted_{name}"
    adapted.__qualname__ = adapted.__name__
    adapted.__doc__ = f"适配后的 {name} 节点（输入/输出: RCAGraphState，增量返回）"

    return adapted


# ── 适配后的节点函数 ──────────────────────────────────────────

adapted_analyze_symptom: AdaptedNodeFunc = adapt_node(
    analyze_symptom_node, node_name="analyze_symptom"
)
adapted_generate_hypotheses: AdaptedNodeFunc = adapt_node(
    generate_hypotheses_node, node_name="generate_hypotheses"
)
adapted_select_tool: AdaptedNodeFunc = adapt_node(
    select_tool_node, node_name="select_tool"
)
adapted_execute_tool: AdaptedNodeFunc = adapt_node(
    execute_tool_node, node_name="execute_tool"
)
adapted_observe_evidence: AdaptedNodeFunc = adapt_node(
    observe_evidence_node, node_name="observe_evidence"
)
adapted_draft_rca: AdaptedNodeFunc = adapt_node(
    draft_rca_node, node_name="draft_rca"
)
adapted_reflect: AdaptedNodeFunc = adapt_node(
    reflect_node, node_name="reflect"
)
adapted_generate_report: AdaptedNodeFunc = adapt_node(
    generate_report_node, node_name="generate_report"
)

# ── 适配节点字典 ──────────────────────────────────────────────

ADAPTED_NODES: dict[str, AdaptedNodeFunc] = {
    "analyze_symptom": adapted_analyze_symptom,
    "generate_hypotheses": adapted_generate_hypotheses,
    "select_tool": adapted_select_tool,
    "execute_tool": adapted_execute_tool,
    "observe_evidence": adapted_observe_evidence,
    "draft_rca": adapted_draft_rca,
    "reflect": adapted_reflect,
    "generate_report": adapted_generate_report,
}
