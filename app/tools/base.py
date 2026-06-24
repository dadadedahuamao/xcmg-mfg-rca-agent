"""MCP 风格工具基类。"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from pydantic import BaseModel, Field


class ToolInput(BaseModel):
    """工具输入基类。"""

    task_id: str = Field(..., description="关联的 RCA 任务 ID")
    anomaly_type: str = Field(default="", description="异常类型")
    description: str = Field(default="", description="异常描述")


class ToolResult(BaseModel):
    """工具执行结果。"""

    success: bool = True
    data: Any = None
    count: int = 0
    error: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseTool(ABC):
    """MCP 风格工具基类。

    所有工具必须实现：
    - name: 工具名称
    - description: 工具描述
    - input_schema: 输入参数 JSON Schema
    - output_schema: 输出结果 JSON Schema
    - execute: 执行方法
    """

    name: str = "base_tool"
    description: str = "基础工具"

    # ── MCP 风格 Schema ──────────────────────────────────────
    input_schema: dict = {}
    """输入参数 JSON Schema，定义工具接受的参数结构。

    格式遵循 JSON Schema 规范：
    {
        "type": "object",
        "properties": {
            "param_name": {
                "type": "string",
                "description": "参数描述",
            }
        },
        "required": ["param_name"]
    }
    """

    output_schema: dict = {}
    """输出结果 JSON Schema，定义工具返回的数据结构。

    格式遵循 JSON Schema 规范：
    {
        "type": "object",
        "properties": {
            "field_name": {
                "type": "string",
                "description": "字段描述",
            }
        }
    }
    """

    @abstractmethod
    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        """执行工具调用。

        Args:
            params: 工具参数

        Returns:
            执行结果字典
        """
        ...

    def to_dict(self) -> dict:
        """导出工具元信息（含 schema）。"""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
        }
