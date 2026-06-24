"""EmbeddingClient 配置透传测试。"""

from unittest.mock import Mock


def test_embed_query_passes_configured_dimensions(monkeypatch):
    """查询 embedding 请求必须透传 EMBEDDING_DIMENSION。"""
    from app.rag.embedding_client import EmbeddingClient

    client = EmbeddingClient()
    client.api_key = "test-key"
    client.model = "doubao-embedding-vision"

    embeddings = Mock()
    embeddings.create.return_value.data = [Mock(embedding=[0.1, 0.2])]
    openai_client = Mock()
    openai_client.embeddings = embeddings
    monkeypatch.setattr(client, "_client", Mock(return_value=openai_client))

    client.embed_query("液压系统异响")

    embeddings.create.assert_called_once_with(
        model="doubao-embedding-vision",
        input="液压系统异响",
        dimensions=1024,
    )


def test_embed_documents_passes_configured_dimensions(monkeypatch):
    """批量文档 embedding 请求必须透传 EMBEDDING_DIMENSION。"""
    from app.rag.embedding_client import EmbeddingClient

    client = EmbeddingClient()
    client.api_key = "test-key"
    client.model = "doubao-embedding-vision"

    embeddings = Mock()
    embeddings.create.return_value.data = [
        Mock(embedding=[0.1, 0.2]),
        Mock(embedding=[0.3, 0.4]),
    ]
    openai_client = Mock()
    openai_client.embeddings = embeddings
    monkeypatch.setattr(client, "_client", Mock(return_value=openai_client))

    client.embed_documents(["文档1", "文档2"])

    embeddings.create.assert_called_once_with(
        model="doubao-embedding-vision",
        input=["文档1", "文档2"],
        dimensions=1024,
    )
