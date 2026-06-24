"""知识库查询工具 - 基于 RAG 检索 SOP 和知识文档。"""

from typing import Any

from app.rag.hybrid_retriever import HybridRetriever
from app.tools.base import BaseTool


class KnowledgeTool(BaseTool):
    name = "knowledge"
    description = "基于 RAG 检索制造领域的 SOP、最佳实践和知识文档"

    # ── MCP 风格 Schema ──────────────────────────────────────
    input_schema = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "关联的 RCA 任务 ID",
            },
            "anomaly_type": {
                "type": "string",
                "description": "异常类型",
            },
            "description": {
                "type": "string",
                "description": "异常描述",
            },
            "query": {
                "type": "string",
                "description": "检索查询文本",
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数",
                "default": 5,
                "minimum": 1,
                "maximum": 20,
            },
        },
        "required": ["task_id", "query"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "success": {
                "type": "boolean",
                "description": "执行是否成功",
            },
            "results": {
                "type": "array",
                "description": "检索结果列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string", "description": "文档内容"},
                        "score": {"type": "number", "description": "相关性评分"},
                        "source": {"type": "string", "description": "文档来源"},
                    },
                },
            },
            "count": {
                "type": "integer",
                "description": "返回结果数",
            },
            "query": {
                "type": "string",
                "description": "原始查询文本",
            },
        },
    }

    def __init__(self):
        super().__init__()
        self._retriever: HybridRetriever | None = None

    @property
    def retriever(self) -> HybridRetriever:
        if self._retriever is None:
            self._retriever = HybridRetriever()
        return self._retriever

    def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        query = params.get("query", "")
        anomaly_type = params.get("anomaly_type", "")
        top_k = params.get("top_k", 5)

        results = self.retriever.search(
            query=query,
            anomaly_type=anomaly_type,
            top_k=top_k,
        )

        return {
            "success": True,
            "results": results,
            "count": len(results),
            "query": query,
        }
