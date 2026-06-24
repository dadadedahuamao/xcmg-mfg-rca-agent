"""知识文档加载器 - 加载 Markdown 知识文档并分块。"""

import re
from pathlib import Path
from typing import Optional

from app.config import settings


class KnowledgeLoader:
    """知识文档加载器。

    加载 knowledge/ 目录下的 Markdown 文档，
    按标题分块，构建文档索引。
    """

    def __init__(self, knowledge_dir: Optional[Path] = None):
        self.knowledge_dir = knowledge_dir or settings.knowledge_dir
        if not self.knowledge_dir.is_absolute():
            # 基于项目根目录（app 包的父目录）解析相对路径
            project_root = Path(__file__).resolve().parent.parent.parent
            self.knowledge_dir = (project_root / self.knowledge_dir).resolve()

    def load_all(self) -> list[dict]:
        """加载所有知识文档。

        Returns:
            文档块列表，每个块包含 content, source, title, anomaly_type
        """
        documents = []

        if not self.knowledge_dir.exists():
            return documents

        for md_file in self.knowledge_dir.glob("*.md"):
            docs = self._load_file(md_file)
            documents.extend(docs)

        return documents

    def _load_file(self, file_path: Path) -> list[dict]:
        """加载单个 Markdown 文件并分块。"""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            return []

        # 按 ## 标题分块
        chunks = self._split_by_headers(content, file_path.stem)

        return chunks

    def _split_by_headers(self, content: str, source: str) -> list[dict]:
        """按二级标题分块。"""
        chunks = []

        # 提取文档标题（第一个 # 标题）
        title_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        doc_title = title_match.group(1).strip() if title_match else source

        # 按 ## 分割
        sections = re.split(r"\n(?=##\s)", content)

        for i, section in enumerate(sections):
            # 提取小节标题
            header_match = re.match(r"^##\s+(.+)$", section, re.MULTILINE)
            section_title = header_match.group(1).strip() if header_match else doc_title

            # 清理内容
            clean_content = re.sub(r"^#+\s+.*$", "", section, flags=re.MULTILINE).strip()

            if not clean_content:
                continue

            # 推断异常类型
            anomaly_type = self._infer_anomaly_type(source, section_title, clean_content)

            chunks.append({
                "id": f"{source}_{i}",
                "content": clean_content,
                "source": source,
                "title": f"{doc_title} - {section_title}",
                "anomaly_type": anomaly_type,
                "chunk_index": i,
            })

        return chunks

    def _infer_anomaly_type(self, source: str, title: str, content: str) -> str:
        """推断文档块关联的异常类型。"""
        text = f"{source} {title} {content}".lower()

        type_keywords = {
            "overstation_check": ["超站", "overstation", "工序超时", "节拍"],
            "equipment_conflict": ["设备冲突", "equipment conflict", "资源争用"],
            "material_shortage": ["物料短缺", "material shortage", "缺料", "库存不足"],
            "quality_abnormal": ["质量异常", "quality abnormal", "不良", "缺陷"],
            "interface_timeout": ["接口超时", "interface timeout", "系统集成"],
            "schedule_risk": ["排程风险", "schedule risk", "交付延期"],
        }

        for atype, keywords in type_keywords.items():
            if any(kw in text for kw in keywords):
                return atype

        return "general"
