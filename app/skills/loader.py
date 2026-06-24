"""Skills 加载器 - 加载 YAML 定义的 SOP 技能配置。"""

from pathlib import Path
from typing import Optional

import yaml


class SkillsLoader:
    """技能加载器。

    从 definitions/ 目录加载 YAML 技能定义，
    按 anomaly_type 索引。
    """

    def __init__(self, definitions_dir: Optional[Path] = None):
        if definitions_dir is None:
            definitions_dir = Path(__file__).parent / "definitions"
        self.definitions_dir = definitions_dir
        self._skills: dict[str, dict] = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """延迟加载所有技能定义。"""
        if self._loaded:
            return

        if not self.definitions_dir.exists():
            self._loaded = True
            return

        for yaml_file in self.definitions_dir.glob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    skill = yaml.safe_load(f)
                if skill and "anomaly_type" in skill:
                    self._skills[skill["anomaly_type"]] = skill
            except Exception:
                continue

        self._loaded = True

    def get_skill(self, anomaly_type: str) -> Optional[dict]:
        """根据异常类型获取技能定义。"""
        self._ensure_loaded()
        return self._skills.get(anomaly_type)

    def list_skills(self) -> list[str]:
        """列出所有已加载的技能类型。"""
        self._ensure_loaded()
        return list(self._skills.keys())

    def get_tools_for_type(self, anomaly_type: str) -> list[str]:
        """获取指定异常类型需要调用的工具列表。"""
        skill = self.get_skill(anomaly_type)
        if skill:
            return skill.get("tools", [])
        return []

    def get_evidence_rules(self, anomaly_type: str) -> list[dict]:
        """获取指定异常类型的证据规则。"""
        skill = self.get_skill(anomaly_type)
        if skill:
            return skill.get("evidence_rules", [])
        return []
