"""Prompt 模板管理器。

负责加载 YAML 格式的 Prompt 模板，支持按节点名称加载和渲染。
模板使用 {variable} 占位符，渲染时替换为实际值。

使用方式:
    manager = PromptManager()
    template = manager.load("analyze_symptom")
    prompt = manager.render("analyze_symptom", anomaly_type="xxx", description="xxx")
"""

import logging
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# 模板定义目录（相对于本文件）
_DEFINITIONS_DIR = Path(__file__).parent / "definitions"


class PromptTemplate:
    """单个 Prompt 模板的数据结构。

    封装 YAML 模板中的所有字段，提供便捷的属性访问。
    """

    def __init__(self, data: dict[str, Any]):
        self._data = data

    @property
    def node_name(self) -> str:
        """节点名称。"""
        return self._data.get("node_name", "")

    @property
    def description(self) -> str:
        """模板描述。"""
        return self._data.get("description", "")

    @property
    def system_prompt(self) -> str:
        """系统提示词。"""
        return self._data.get("system_prompt", "")

    @property
    def user_prompt_template(self) -> str:
        """用户提示词模板（含 {variable} 占位符）。"""
        return self._data.get("user_prompt_template", "")

    @property
    def variables(self) -> list[dict[str, Any]]:
        """模板变量定义列表。"""
        return self._data.get("variables", [])

    @property
    def temperature(self) -> float:
        """推荐的 LLM temperature。"""
        return self._data.get("temperature", 0.3)

    @property
    def max_tokens(self) -> int:
        """推荐的最大 token 数。"""
        return self._data.get("max_tokens", 1000)

    def get_required_variables(self) -> list[str]:
        """获取所有必填变量名。"""
        return [v["name"] for v in self.variables if v.get("required", False)]

    def to_dict(self) -> dict[str, Any]:
        """导出为字典。"""
        return dict(self._data)


class PromptManager:
    """Prompt 模板管理器。

    功能：
    - 从 YAML 文件加载模板
    - 缓存已加载的模板
    - 渲染模板（替换变量占位符）
    - 验证必填变量

    使用方式:
        manager = PromptManager()
        prompt = manager.render("analyze_symptom",
                                anomaly_type="overstation_check",
                                description="工位超站",
                                source_system="MES")
    """

    def __init__(self, definitions_dir: Optional[Path] = None):
        """初始化 Prompt 管理器。

        Args:
            definitions_dir: 模板定义目录，默认为本文件同级的 definitions/
        """
        self._definitions_dir = definitions_dir or _DEFINITIONS_DIR
        self._cache: dict[str, PromptTemplate] = {}

    # ── 加载 ──────────────────────────────────────────────────

    def load(self, node_name: str) -> PromptTemplate:
        """加载指定节点的 Prompt 模板。

        优先从缓存读取，缓存未命中时从 YAML 文件加载。

        Args:
            node_name: 节点名称（对应 YAML 文件名，不含 .yaml 后缀）

        Returns:
            PromptTemplate 实例

        Raises:
            FileNotFoundError: 模板文件不存在
            ValueError: YAML 解析失败
        """
        if node_name in self._cache:
            return self._cache[node_name]

        template_path = self._definitions_dir / f"{node_name}.yaml"
        if not template_path.exists():
            raise FileNotFoundError(
                f"Prompt 模板文件不存在: {template_path}"
            )

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"YAML 解析失败 ({template_path}): {e}") from e

        if not isinstance(data, dict):
            raise ValueError(f"模板文件内容不是有效的字典: {template_path}")

        template = PromptTemplate(data)
        self._cache[node_name] = template

        logger.debug(f"已加载 Prompt 模板: {node_name}")
        return template

    # ── 渲染 ──────────────────────────────────────────────────

    def render(self, node_name: str, **kwargs: Any) -> str:
        """加载并渲染 Prompt 模板。

        将 user_prompt_template 中的 {variable} 占位符替换为实际值，
        返回完整的 prompt 字符串（system_prompt + 渲染后的 user_prompt）。

        Args:
            node_name: 节点名称
            **kwargs: 模板变量值

        Returns:
            渲染后的完整 prompt 字符串

        Raises:
            FileNotFoundError: 模板文件不存在
            ValueError: 缺少必填变量
        """
        template = self.load(node_name)

        # 验证必填变量
        required = template.get_required_variables()
        missing = [v for v in required if v not in kwargs]
        if missing:
            raise ValueError(
                f"模板 '{node_name}' 缺少必填变量: {missing}"
            )

        # 渲染 user_prompt_template
        try:
            user_prompt = template.user_prompt_template.format(**kwargs)
        except KeyError as e:
            raise ValueError(
                f"模板 '{node_name}' 渲染失败，变量 {e} 未提供"
            ) from e

        # 组装完整 prompt
        full_prompt = (
            f"[System Prompt]\n{template.system_prompt.strip()}\n\n"
            f"[User Prompt]\n{user_prompt.strip()}"
        )

        logger.debug(
            f"已渲染 Prompt: node={node_name}, "
            f"variables={list(kwargs.keys())}"
        )
        return full_prompt

    def render_user_prompt(self, node_name: str, **kwargs: Any) -> str:
        """只渲染用户提示词，用于 chat completions 的 user message。"""
        template = self.load(node_name)
        required = template.get_required_variables()
        missing = [v for v in required if v not in kwargs]
        if missing:
            raise ValueError(f"模板 '{node_name}' 缺少必填变量: {missing}")
        try:
            return template.user_prompt_template.format(**kwargs).strip()
        except KeyError as e:
            raise ValueError(f"模板 '{node_name}' 渲染失败，变量 {e} 未提供") from e

    # ── 查询 ──────────────────────────────────────────────────

    def list_templates(self) -> list[str]:
        """列出所有可用的模板名称。"""
        if not self._definitions_dir.exists():
            return []
        return sorted(
            p.stem
            for p in self._definitions_dir.glob("*.yaml")
            if p.stem != "__init__"
        )

    def get_template_info(self, node_name: str) -> dict[str, Any]:
        """获取模板的元信息（不渲染）。"""
        template = self.load(node_name)
        return {
            "node_name": template.node_name,
            "description": template.description,
            "variables": template.variables,
            "temperature": template.temperature,
            "max_tokens": template.max_tokens,
        }

    def clear_cache(self) -> None:
        """清空模板缓存。"""
        self._cache.clear()
