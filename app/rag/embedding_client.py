"""OpenAI-compatible Embedding 客户端。"""

from openai import OpenAI

from app.config import settings


class EmbeddingConfigurationError(RuntimeError):
    """Embedding 配置不可用。"""


class EmbeddingClient:
    def __init__(self) -> None:
        self.provider = settings.embedding_provider
        self.model = settings.embedding_model
        self.base_url = settings.embedding_base_url
        self.api_key = settings.embedding_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.api_key != "sk-your-key-here")

    def _client(self) -> OpenAI:
        if not self.enabled:
            raise EmbeddingConfigurationError("EMBEDDING_API_KEY 未配置，无法调用真实 Embedding 模型")
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    def embed_query(self, text: str) -> list[float]:
        response = self._client().embeddings.create(
            model=self.model,
            input=text,
            dimensions=settings.embedding_dimension,
        )
        return list(response.data[0].embedding)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client().embeddings.create(
            model=self.model,
            input=texts,
            dimensions=settings.embedding_dimension,
        )
        return [list(item.embedding) for item in response.data]


embedding_client = EmbeddingClient()
