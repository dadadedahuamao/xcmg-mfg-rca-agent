"""Prompt Engineering 模板系统。

提供制造业 RCA 场景下的 Prompt 模板管理，
支持按节点名称加载和渲染 YAML 模板。
"""

from app.prompts.templates import PromptManager

__all__ = ["PromptManager"]
