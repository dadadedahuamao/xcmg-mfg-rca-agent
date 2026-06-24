"""OpenAI-compatible LLM 客户端。"""

import json
import logging
import re
from typing import Any, Optional

from openai import OpenAI

from app.config import settings
from app.prompts.templates import PromptTemplate

logger = logging.getLogger(__name__)


class LLMConfigurationError(RuntimeError):
    """LLM 配置不可用。"""


class LLMClient:
    """封装 OpenAI-compatible Chat Completions 调用。"""

    def __init__(self) -> None:
        self.provider = settings.llm_provider
        self.model = settings.llm_model
        self.base_url = settings.llm_base_url
        self.api_key = settings.llm_api_key

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.api_key != "sk-your-key-here")

    def _client(self) -> OpenAI:
        if not self.enabled:
            raise LLMConfigurationError("LLM_API_KEY 未配置，无法调用真实大模型")
        return OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )

    def complete(
        self,
        template: PromptTemplate,
        user_prompt: str,
        response_format: Optional[dict[str, Any]] = None,
    ) -> str:
        """调用 LLM 并返回文本结果。"""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": template.system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            "temperature": template.temperature,
            "max_tokens": template.max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format
        logger.info("调用 LLM: provider=%s model=%s", self.provider, self.model)
        response = self._client().chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM 返回空内容")
        return content

    def complete_json(self, template: PromptTemplate, user_prompt: str) -> dict[str, Any]:
        """调用 LLM 并解析 JSON 对象。
        
        不依赖 OpenAI 特有的 response_format 参数，而是通过提示词约束
        要求模型输出 JSON，配合容忍解析器提高兼容性。
        """
        content = self.complete(template, user_prompt)
        return _parse_json_object(content)


def _parse_json_object(content: str) -> dict[str, Any]:
    """从 LLM 文本中解析 JSON 对象，兼容 Markdown 代码块。"""
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if not match:
            match = re.search(r"(\{.*\})", content, re.DOTALL)
        if not match:
            raise
        parsed = json.loads(match.group(1))
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON 响应不是对象")
    return parsed


llm_client = LLMClient()
