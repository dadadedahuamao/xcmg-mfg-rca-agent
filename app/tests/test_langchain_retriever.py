"""LangChain Retriever 包装测试。"""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.rag.hybrid_retriever import HybridRetriever  # noqa: E402


def _mock_search_results() -> list[dict]:
    return [
        {
            "id": "doc_1",
            "content": "超站处理方案：检查工单节拍和设备状态",
            "title": "超站检查 - 处理流程",
            "anomaly_type": "overstation_check",
            "source": "overstation_knowledge",
            "keyword_score": 0.8,
            "vector_score": 0.9,
            "type_score": 1.0,
            "hybrid_score": 0.88,
            "rerank_score": 0.92,
            "rerank_source": "model",
        },
        {
            "id": "doc_2",
            "content": "物料短缺应急流程",
            "title": "物料短缺 - 应急",
            "anomaly_type": "material_shortage",
            "source": "material_knowledge",
            "hybrid_score": 0.6,
        },
    ]


def test_langchain_retriever_returns_documents():
    """LangChainHybridRetriever 应返回 Document 对象列表。"""
    from langchain_core.documents import Document

    from app.rag.langchain_retriever import LangChainHybridRetriever

    mock_hybrid = Mock(spec=HybridRetriever)
    mock_hybrid.search.return_value = _mock_search_results()

    retriever = LangChainHybridRetriever(
        hybrid_retriever=mock_hybrid,
        anomaly_type="overstation_check",
        top_k=5,
    )
    docs = retriever.invoke("超站处理")

    assert len(docs) == 2
    assert all(isinstance(d, Document) for d in docs)
    assert docs[0].page_content == "超站处理方案：检查工单节拍和设备状态"
    mock_hybrid.search.assert_called_once_with(
        query="超站处理",
        anomaly_type="overstation_check",
        top_k=5,
    )


def test_langchain_retriever_metadata_includes_scores():
    """Document metadata 应包含检索分数。"""
    from app.rag.langchain_retriever import LangChainHybridRetriever

    mock_hybrid = Mock(spec=HybridRetriever)
    mock_hybrid.search.return_value = _mock_search_results()

    retriever = LangChainHybridRetriever(hybrid_retriever=mock_hybrid)
    docs = retriever.invoke("测试")

    meta = docs[0].metadata
    assert meta["id"] == "doc_1"
    assert meta["title"] == "超站检查 - 处理流程"
    assert meta["anomaly_type"] == "overstation_check"
    assert meta["rerank_score"] == 0.92
    assert meta["rerank_source"] == "model"
    assert meta["hybrid_score"] == 0.88


def test_langchain_retriever_omits_none_scores():
    """缺失的分数字段不应出现在 metadata 中。"""
    from app.rag.langchain_retriever import LangChainHybridRetriever

    mock_hybrid = Mock(spec=HybridRetriever)
    mock_hybrid.search.return_value = _mock_search_results()

    retriever = LangChainHybridRetriever(hybrid_retriever=mock_hybrid)
    docs = retriever.invoke("测试")

    # doc_2 没有 rerank_score / rerank_source
    meta2 = docs[1].metadata
    assert "rerank_score" not in meta2
    assert "rerank_source" not in meta2
    assert meta2["hybrid_score"] == 0.6


def test_create_retriever_factory():
    """create_retriever 工厂函数应返回可用的 retriever 实例。"""
    from app.rag.langchain_retriever import LangChainHybridRetriever, create_retriever

    retriever = create_retriever(anomaly_type="quality_abnormal", top_k=3)

    assert isinstance(retriever, LangChainHybridRetriever)
    assert retriever.anomaly_type == "quality_abnormal"
    assert retriever.top_k == 3
