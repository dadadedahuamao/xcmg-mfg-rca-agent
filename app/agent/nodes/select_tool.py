"""节点 3: 选择工具 - 根据假设和异常类型选择需要调用的工具。"""

import logging

from app.agent.state import RCAState

logger = logging.getLogger(__name__)

# 异常类型 → 默认工具映射
DEFAULT_TOOLS = {
    "overstation_check": ["workorder", "resource", "material", "equipment_maintenance", "knowledge"],
    "equipment_conflict": ["workorder", "resource", "equipment_maintenance", "knowledge"],
    "material_shortage": ["material", "workorder", "interface_log", "quality", "knowledge"],
    "quality_abnormal": ["quality", "equipment_maintenance", "material", "knowledge"],
    "interface_timeout": ["interface_log", "resource", "text2sql", "knowledge"],
    "schedule_risk": ["workorder", "resource", "equipment_maintenance", "material", "knowledge"],
}


def select_tool_node(state: RCAState) -> RCAState:
    """选择需要调用的工具。

    策略：
    1. 第一轮：使用默认工具集
    2. 后续轮次：根据反思结果中的 missing_evidence 调整
    """
    anomaly_type = state.anomaly_type
    reflection_round = state.reflection_round

    if reflection_round == 0:
        # 第一轮：使用默认工具集
        tools = DEFAULT_TOOLS.get(anomaly_type, ["knowledge"])
    else:
        # 后续轮次：根据反思结果补充
        tools = list(state.selected_tools)  # 保留之前的工具
        if state.reflection_result:
            missing = state.reflection_result.get("missing_evidence", [])
            for m in missing:
                tool_name = _map_evidence_to_tool(m)
                if tool_name and tool_name not in tools:
                    tools.append(tool_name)

    state.selected_tools = tools

    logger.info(
        f"[select_tool] task={state.task_id} round={reflection_round} "
        f"tools={tools}"
    )

    return state


def _map_evidence_to_tool(evidence_type: str) -> str:
    """将缺失证据类型映射到工具名称。"""
    mapping = {
        "工单数据": "workorder",
        "设备数据": "equipment_maintenance",
        "资源数据": "resource",
        "物料数据": "material",
        "质量数据": "quality",
        "接口日志": "interface_log",
        "知识文档": "knowledge",
        "SQL查询": "text2sql",
    }
    return mapping.get(evidence_type, "")
