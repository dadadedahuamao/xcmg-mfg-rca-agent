"""重排序器 - 对检索结果进行二次排序。"""

import json
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class Reranker:
    """模型优先、规则回退的重排序器。"""

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """对候选文档重排序。

        Args:
            query: 原始查询
            candidates: 候选文档列表（已含 hybrid_score）

        Returns:
            重排序后的文档列表
        """
        if not candidates:
            return []

        if self._model_enabled:
            try:
                return self._rerank_with_model(query, candidates)
            except Exception as exc:
                logger.warning("Reranker 模型调用失败，回退规则重排: %s", exc)

        return self._rerank_with_rules(candidates, query)

    @property
    def _model_enabled(self) -> bool:
        return bool(
            settings.reranker_provider == "ollama"
            and settings.reranker_model
            and settings.reranker_base_url
        )

    def _rerank_with_model(self, query: str, candidates: list[dict]) -> list[dict]:
        ranked_items = []
        for index, doc in enumerate(candidates):
            response = httpx.post(
                f"{settings.reranker_base_url.rstrip('/')}/api/generate",
                json={
                    "model": settings.reranker_model,
                    "prompt": self._build_pair_prompt(query, doc),
                    "stream": False,
                    "options": {
                        "temperature": 0,
                        "num_predict": 8,
                    },
                },
                timeout=settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            score = self._score_yes_no_response(str(response.json().get("response", "")))
            ranked_items.append({
                "id": str(doc.get("id", index)),
                "score": score,
                "reason": self._build_yes_no_reason(score),
            })
        return self._merge_model_scores(candidates, ranked_items)

    def _build_pair_prompt(self, query: str, doc: dict) -> str:
        return f"""Judge whether the Document meets the requirements based on the Query.
Note that the answer can only be yes or no.

Query:
{query}

Document title:
{str(doc.get("title", ""))}

Document:
{str(doc.get("content", ""))[:1200]}
"""

    def _score_yes_no_response(self, text: str) -> float:
        normalized = text.strip().lower()
        if normalized.startswith("yes") or "\nyes" in normalized:
            return 0.9
        if normalized.startswith("no") or "\nno" in normalized:
            return 0.1
        return 0.5

    def _build_yes_no_reason(self, score: float) -> str:
        if score >= 0.75:
            return "模型判断候选与查询相关"
        if score <= 0.25:
            return "模型判断候选与查询不相关"
        return "模型判断候选与查询相关性不确定"

    def _parse_ranked_items(self, text: str) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = self._extract_first_json_array(text)

        if not isinstance(parsed, list):
            raise ValueError("Reranker 模型输出不是列表")

        ranked_items: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            doc_id = str(item.get("id", ""))
            if not doc_id:
                continue
            score = self._normalize_score(item.get("score", 0.0))
            ranked_items.append({
                "id": doc_id,
                "score": score,
                "reason": str(item.get("reason", "")),
            })

        if not ranked_items:
            raise ValueError("Reranker 模型未返回有效候选")
        return ranked_items

    def _extract_first_json_array(self, text: str) -> Any:
        decoder = json.JSONDecoder()
        start = text.find("[")
        while start != -1:
            try:
                parsed, _ = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                start = text.find("[", start + 1)
                continue
            if isinstance(parsed, list):
                return parsed
            start = text.find("[", start + 1)
        raise ValueError("Reranker 模型输出不是 JSON 数组")

    def _merge_model_scores(self, candidates: list[dict], ranked_items: list[dict[str, Any]]) -> list[dict]:
        by_id = {str(doc.get("id", index)): doc for index, doc in enumerate(candidates)}
        seen_ids: set[str] = set()
        reranked: list[dict] = []

        for item in ranked_items:
            doc_id = str(item["id"])
            doc = by_id.get(doc_id)
            if doc is None or doc_id in seen_ids:
                continue
            seen_ids.add(doc_id)
            reranked.append({
                **doc,
                "rerank_score": item["score"],
                "rerank_reason": item["reason"],
                "rerank_source": "model",
            })

        if not reranked:
            raise ValueError("Reranker 模型返回的候选 id 与输入不匹配")

        for doc_id, doc in by_id.items():
            if doc_id not in seen_ids:
                reranked.append({
                    **doc,
                    "rerank_score": float(doc.get("hybrid_score", 0.0) or 0.0),
                    "rerank_reason": "模型未返回该候选，保留混合检索分数",
                    "rerank_source": "hybrid_fallback",
                })

        reranked.sort(key=lambda item: item.get("rerank_score", 0.0), reverse=True)
        return reranked

    def _normalize_score(self, value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        return min(1.0, max(0.0, score))

    def _rerank_with_rules(self, candidates: list[dict], query: str) -> list[dict]:
        query_lower = query.lower()
        reranked: list[dict] = []

        for doc in candidates:
            content_len = len(doc.get("content", ""))
            if 200 <= content_len <= 1000:
                length_score = 1.0
            elif 100 <= content_len < 200:
                length_score = 0.8
            elif content_len > 1000:
                length_score = 0.7
            else:
                length_score = 0.4

            title = doc.get("title", "").lower()
            title_match = sum(
                1 for word in query_lower.split()
                if word in title
            )
            title_score = min(1.0, title_match * 0.3)

            reranked.append({
                **doc,
                "rerank_score": (
                    float(doc.get("hybrid_score", 0.0) or 0.0) * 0.6
                    + length_score * 0.25
                    + title_score * 0.15
                ),
                "rerank_source": "rules",
            })

        reranked.sort(key=lambda item: item.get("rerank_score", 0.0), reverse=True)
        return reranked
