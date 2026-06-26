"""LangChain Retriever 包装器 - 将 HybridRetriever 适配为 LangChain BaseRetriever。"""

import logging
from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from app.rag.hybrid_retriever import HybridRetriever

logger = logging.getLogger(__name__)


class LangChainHybridRetriever(BaseRetriever):
    """将项目 HybridRetriever 包装为 LangChain BaseRetriever。

    使用方式::

        from app.rag.langchain_retriever import LangChainHybridRetriever

        retriever = LangChainHybridRetriever()
        docs = retriever.invoke("超站处理方案")

    内部委托给 HybridRetriever 完成关键词/向量/重排序检索，
    然后将结果转换为 LangChain Document 格式。
    """

    hybrid_retriever: HybridRetriever
    anomaly_type: str = ""
    top_k: int = 5

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        """执行检索并返回 LangChain Document 列表。"""
        results = self.hybrid_retriever.search(
            query=query,
            anomaly_type=self.anomaly_type,
            top_k=self.top_k,
        )

        documents: list[Document] = []
        for item in results:
            metadata: dict[str, Any] = {
                "id": str(item.get("id", "")),
                "title": str(item.get("title", "")),
                "anomaly_type": str(item.get("anomaly_type", "")),
                "source": str(item.get("source", "")),
            }
            # 附加检索分数元数据
            for score_key in ("keyword_score", "vector_score", "type_score",
                              "hybrid_score", "rerank_score", "rerank_source"):
                value = item.get(score_key)
                if value is not None:
                    metadata[score_key] = value

            documents.append(
                Document(
                    page_content=str(item.get("content", "")),
                    metadata=metadata,
                )
            )

        return documents


def create_retriever(
    anomaly_type: str = "",
    top_k: int = 5,
) -> LangChainHybridRetriever:
    """工厂函数：创建 LangChain HybridRetriever 实例。"""
    return LangChainHybridRetriever(
        hybrid_retriever=HybridRetriever(),
        anomaly_type=anomaly_type,
        top_k=top_k,
    )
