"""
实体指称(Mention)数据模型

定义文本中实体指称的数据结构。
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import uuid


@dataclass
class Mention:
    """
    实体指称

    表示文本中需要链接的实体名称。

    Attributes:
        id: 唯一标识符
        text: 指称文本，如"国网"
        start_pos: 在原文中的起始位置
        end_pos: 在原文中的结束位置
        context: 上下文（可选，系统可自动提取）
        entity_type: NER识别的实体类型：PER/ORG/LOC/EVENT
        doc_id: 所属文档ID（可选）
        metadata: 其他元数据
    """

    text: str
    start_pos: int
    end_pos: int
    entity_type: Optional[str] = None
    context: Optional[str] = None
    doc_id: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: dict = field(default_factory=dict)

    def get_context_from_text(self, full_text: str, window_size: int = 100) -> str:
        """
        从完整文本中提取上下文

        Args:
            full_text: 完整文本
            window_size: 上下文窗口大小（前后各取的字符数）

        Returns:
            提取的上下文文本
        """
        start = max(0, self.start_pos - window_size)
        end = min(len(full_text), self.end_pos + window_size)
        return full_text[start:end]

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "text": self.text,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "entity_type": self.entity_type,
            "context": self.context,
            "doc_id": self.doc_id,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Mention":
        """从字典创建Mention实例"""
        return cls(
            text=data["text"],
            start_pos=data["start_pos"],
            end_pos=data["end_pos"],
            entity_type=data.get("entity_type"),
            context=data.get("context"),
            doc_id=data.get("doc_id"),
            id=data.get("id", str(uuid.uuid4())),
            metadata=data.get("metadata", {}),
        )
