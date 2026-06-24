"""证据 Schema。"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EvidenceSource(str, Enum):
    TOOL = "tool"
    RAG = "rag"
    TEXT2SQL = "text2sql"
    KNOWLEDGE = "knowledge"
    USER = "user"


class Evidence(BaseModel):
    """单条证据。"""

    id: str = Field(..., description="证据唯一 ID")
    source: EvidenceSource = Field(..., description="证据来源")
    tool_name: Optional[str] = Field(default=None, description="工具名称")
    content: str = Field(..., description="证据内容")
    relevance_score: float = Field(default=0.0, description="相关性评分 0-1")
    confidence: float = Field(default=0.5, description="置信度 0-1")
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)


class EvidenceCollection(BaseModel):
    """证据集合。"""

    items: list[Evidence] = Field(default_factory=list)
    total: int = 0

    def add(self, evidence: Evidence) -> None:
        self.items.append(evidence)
        self.total = len(self.items)

    def top_k(self, k: int = 5) -> list[Evidence]:
        return sorted(self.items, key=lambda e: e.relevance_score, reverse=True)[:k]
