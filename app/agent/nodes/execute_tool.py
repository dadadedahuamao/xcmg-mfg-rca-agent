"""节点 4: 执行工具 - 调用选中的 MCP 工具并收集结果。"""

import logging
import time
from datetime import datetime

from app.agent.state import RCAState
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def execute_tool_node(state: RCAState) -> RCAState:
    """执行选中的工具调用。

    对每个选中的工具：
    1. 构建输入参数
    2. 调用工具
    3. 记录调用历史
    """
    tools = state.selected_tools
    registry = ToolRegistry()

    for tool_name in tools:
        tool = registry.get(tool_name)
        if tool is None:
            logger.warning(f"[execute_tool] 工具未注册: {tool_name}")
            continue

        # 构建输入参数
        params = _build_params(tool_name, state)

        # 调用工具
        start = time.time()
        try:
            result = tool.execute(params)
            success = True
            error = None
        except Exception as e:
            result = {"error": str(e)}
            success = False
            error = str(e)
            logger.error(f"[execute_tool] 工具 {tool_name} 执行失败: {e}")

        duration_ms = int((time.time() - start) * 1000)

        # 记录调用历史（含 schema 信息）
        record = {
            "tool_name": tool_name,
            "input_params": params,
            "input_schema": tool.input_schema if tool else {},
            "output_schema": tool.output_schema if tool else {},
            "output": result,
            "success": success,
            "error": error,
            "duration_ms": duration_ms,
            "timestamp": datetime.now().isoformat(),
        }
        state.add_tool_call(record)

        logger.info(
            f"[execute_tool] task={state.task_id} tool={tool_name} "
            f"success={success} duration={duration_ms}ms"
        )

    return state


def _build_params(tool_name: str, state: RCAState) -> dict:
    """根据工具类型和状态构建参数。"""
    base_params = {
        "task_id": state.task_id,
        "anomaly_type": state.anomaly_type,
        "description": state.description,
    }

    tool_specific = {
        "workorder": {
            "status_filter": ["pending", "in_progress", "delayed"],
            "limit": 20,
        },
        "resource": {
            "resource_type": "equipment",
            "limit": 20,
        },
        "material": {
            "check_safety_stock": True,
            "limit": 20,
        },
        "interface_log": {
            "hours_back": 24,
            "limit": 50,
        },
        "quality": {
            "defect_types": ["all"],
            "limit": 20,
        },
        "equipment_maintenance": {
            "status_filter": ["planned", "in_progress", "overdue"],
            "limit": 20,
        },
        "knowledge": {
            "query": state.description,
            "anomaly_type": state.anomaly_type,
            "top_k": 5,
        },
        "text2sql": {
            "query": state.description,
            "anomaly_type": state.anomaly_type,
        },
    }

    params = {**base_params, **tool_specific.get(tool_name, {})}
    return params
