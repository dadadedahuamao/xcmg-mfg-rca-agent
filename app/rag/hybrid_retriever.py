"""混合检索器 - 结合关键词匹配、真实 Embedding 向量检索和重排序。"""

import logging
import re

from app.rag.embedding_client import embedding_client
from app.rag.knowledge_loader import KnowledgeLoader
from app.rag.reranker import Reranker
from app.rag.vector_store import vector_store

logger = logging.getLogger(__name__)


class HybridRetriever:
    """混合检索器。

    检索策略：
    1. 关键词匹配评分 (BM25-like)
    2. 真实 Embedding 向量检索 (pgvector)
    3. 重排序 (基于异常类型相关性)
    """

    def __init__(self):
        self.loader = KnowledgeLoader()
        self.reranker = Reranker()
        self._documents: list[dict] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """延迟加载文档。"""
        if not self._loaded:
            self._documents = self.loader.load_all()
            self._loaded = True

    def search(
        self,
        query: str,
        anomaly_type: str = "",
        top_k: int = 5,
    ) -> list[dict]:
        """混合检索。

        Args:
            query: 查询文本
            anomaly_type: 异常类型过滤
            top_k: 返回结果数

        Returns:
            排序后的文档块列表
        """
        self._ensure_loaded()

        if not self._documents:
            return []

        # 按异常类型预过滤
        if anomaly_type:
            candidates = [
                d for d in self._documents
                if d.get("anomaly_type") in (anomaly_type, "general")
            ]
        else:
            candidates = list(self._documents)

        if not candidates:
            return []

        vector_scores = self._vector_scores(query, anomaly_type, top_k * 4)

        # 计算混合分数
        scored = []
        for doc in candidates:
            keyword_score = self._keyword_score(query, doc["content"])
            vector_score = vector_scores.get(doc.get("id", ""), 0.0)
            type_score = self._type_match_score(anomaly_type, doc.get("anomaly_type", ""))

            # 加权混合
            hybrid_score = (
                keyword_score * 0.3
                + vector_score * 0.5
                + type_score * 0.2
            )

            scored.append({
                **doc,
                "keyword_score": keyword_score,
                "vector_score": vector_score,
                "type_score": type_score,
                "hybrid_score": hybrid_score,
            })

        # 排序
        scored.sort(key=lambda x: x["hybrid_score"], reverse=True)

        # 重排序
        top_candidates = scored[:top_k * 2]
        reranked = self.reranker.rerank(query, top_candidates)

        return reranked[:top_k]

    def _keyword_score(self, query: str, content: str) -> float:
        """基于关键词匹配的评分 (BM25-like)。"""
        query_lower = query.lower()
        content_lower = content.lower()

        # 分词（简单空格+中文单字）
        query_terms = set(re.findall(r"[\u4e00-\u9fff]|\w+", query_lower))
        content_terms = re.findall(r"[\u4e00-\u9fff]|\w+", content_lower)

        if not query_terms:
            return 0.0

        # 计算匹配度
        matches = sum(1 for t in query_terms if t in content_terms)
        match_ratio = matches / len(query_terms)

        # TF 因子
        tf = sum(content_terms.count(t) for t in query_terms) / max(len(content_terms), 1)

        return match_ratio * 0.7 + min(tf * 10, 1.0) * 0.3

    def _vector_scores(self, query: str, anomaly_type: str, limit: int) -> dict[str, float]:
        """通过真实 Embedding + pgvector 获取向量相似度。"""
        if not embedding_client.enabled:
            logger.warning("EMBEDDING_API_KEY 未配置，跳过真实向量检索")
            return {}
        try:
            query_embedding = embedding_client.embed_query(query)
            rows = vector_store.search(query_embedding, anomaly_type=anomaly_type, limit=limit)
            return {str(row.get("id")): float(row.get("vector_score") or 0.0) for row in rows}
        except Exception as exc:
            logger.warning("真实向量检索失败，回退关键词检索: %s", exc)
            return {}

    def _type_match_score(self, query_type: str, doc_type: str) -> float:
        """异常类型匹配评分。"""
        if not query_type:
            return 0.5
        if query_type == doc_type:
            return 1.0
        if doc_type == "general":
            return 0.6
        return 0.1
