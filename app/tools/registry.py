"""工具注册中心 - 管理所有 MCP 风格工具的注册和查找。"""

from typing import Any, Optional

from app.tools.base import BaseTool
from app.tools.workorder_tool import WorkOrderTool
from app.tools.resource_tool import ResourceTool
from app.tools.material_tool import MaterialTool
from app.tools.interface_log_tool import InterfaceLogTool
from app.tools.quality_tool import QualityTool
from app.tools.knowledge_tool import KnowledgeTool
from app.tools.text2sql_tool import Text2SQLTool


class ToolRegistry:
    """工具注册中心（单例模式）。"""

    _instance: Optional["ToolRegistry"] = None
    _tools: dict[str, BaseTool] = {}

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """注册所有工具。"""
        self._tools = {
            "workorder": WorkOrderTool(),
            "resource": ResourceTool(),
            "material": MaterialTool(),
            "interface_log": InterfaceLogTool(),
            "quality": QualityTool(),
            "equipment_maintenance": EquipmentMaintenanceTool(),
            "knowledge": KnowledgeTool(),
            "text2sql": Text2SQLTool(),
        }

    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具实例。"""
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        """列出所有已注册工具（含 input/output schema）。"""
        return [t.to_dict() for t in self._tools.values()]

    def execute(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        """执行指定工具。"""
        tool = self.get(name)
        if tool is None:
            return {"success": False, "error": f"工具未注册: {name}"}
        return tool.execute(params)


# 延迟导入避免循环依赖
from app.tools.equipment_maintenance_tool import EquipmentMaintenanceTool  # noqa: E402
