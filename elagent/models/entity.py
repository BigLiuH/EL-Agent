"""
实体(Entity)数据模型

定义知识库实体和候选实体的数据结构。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
import uuid


@dataclass
class Entity:
    """
    知识库实体

    表示知识库中的一个标准实体。

    Attributes:
        id: 唯一ID，如"Q12345"
        standard_name: 标准全称，如"国家电网有限公司"
        aliases: 别名列表
        entity_type: 实体类型：PER/ORG/LOC/EVENT
        description: 实体描述
        attributes: 其他属性
        popularity: 流行度分数（0-1）
        source: 数据来源
    """

    id: str
    standard_name: str
    entity_type: str
    aliases: List[str] = field(default_factory=list)
    description: str = ""
    attributes: Dict = field(default_factory=dict)
    popularity: float = 0.0
    source: str = ""

    def all_names(self) -> List[str]:
        """获取所有名称（标准名 + 别名）"""
        return [self.standard_name] + self.aliases

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "standard_name": self.standard_name,
            "entity_type": self.entity_type,
            "aliases": self.aliases,
            "description": self.description,
            "attributes": self.attributes,
            "popularity": self.popularity,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Entity":
        """从字典创建Entity实例"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            standard_name=data["standard_name"],
            entity_type=data.get("entity_type", "UNKNOWN"),
            aliases=data.get("aliases", []),
            description=data.get("description", ""),
            attributes=data.get("attributes", {}),
            popularity=data.get("popularity", 0.0),
            source=data.get("source", ""),
        )


@dataclass
class Candidate:
    """
    候选实体

    表示一个候选链接实体及其匹配得分。

    Attributes:
        entity: 候选实体
        score: 综合得分（0-1）
        match_source: 匹配来源：bm25/alias/vector
        match_details: 各路得分详情
    """

    entity: Entity
    score: float
    match_source: str = ""
    match_details: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "entity": self.entity.to_dict(),
            "score": self.score,
            "match_source": self.match_source,
            "match_details": self.match_details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Candidate":
        """从字典创建Candidate实例"""
        return cls(
            entity=Entity.from_dict(data["entity"]),
            score=data["score"],
            match_source=data.get("match_source", ""),
            match_details=data.get("match_details", {}),
        )
