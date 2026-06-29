"""
知识库管理模块

提供知识库的加载、查询和管理功能。
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from ..models.entity import Entity
from ..config import config

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """
    知识库管理器

    负责加载知识库数据，提供实体查询功能。
    """

    def __init__(self):
        """初始化知识库管理器"""
        self.entities: Dict[str, Entity] = {}  # id -> Entity
        self.alias_dict: Dict[str, List[str]] = defaultdict(list)  # alias -> [entity_id]
        self.type_index: Dict[str, List[str]] = defaultdict(list)  # type -> [entity_id]
        self.name_index: Dict[str, str] = {}  # standard_name -> entity_id
        self._loaded = False

    @property
    def loaded(self) -> bool:
        """知识库是否已加载"""
        return self._loaded

    @property
    def entity_count(self) -> int:
        """实体数量"""
        return len(self.entities)

    @property
    def alias_count(self) -> int:
        """别名数量"""
        return len(self.alias_dict)

    def load(self,
             knowledge_base_path: Optional[str] = None,
             aliases_path: Optional[str] = None) -> None:
        """
        加载知识库数据

        Args:
            knowledge_base_path: 知识库文件路径
            aliases_path: 别名文件路径
        """
        kb_path = Path(knowledge_base_path) if knowledge_base_path else config.knowledge_base_path
        alias_path = Path(aliases_path) if aliases_path else config.aliases_path

        logger.info(f"开始加载知识库: {kb_path}")

        # 加载知识库
        self._load_entities(kb_path)

        # 加载别名
        if alias_path.exists():
            self._load_aliases(alias_path)

        # 构建索引
        self._build_indexes()

        self._loaded = True
        logger.info(f"知识库加载完成: {self.entity_count}个实体, {self.alias_count}个别名")

    def _load_entities(self, path: Path) -> None:
        """加载实体数据"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 根据数据格式解析
        if isinstance(data, list):
            # 列表格式
            for item in data:
                entity = self._parse_entity(item)
                if entity:
                    self.entities[entity.id] = entity
        elif isinstance(data, dict):
            # 字典格式（可能是按类型或ID组织的）
            if "entities" in data:
                # 有entities字段
                for item in data["entities"]:
                    entity = self._parse_entity(item)
                    if entity:
                        self.entities[entity.id] = entity
            else:
                # 直接是id->entity的映射
                for entity_id, item in data.items():
                    entity = self._parse_entity(item, entity_id)
                    if entity:
                        self.entities[entity.id] = entity

        logger.info(f"从 {path} 加载了 {len(self.entities)} 个实体")

    def _parse_entity(self, data: dict, default_id: str = None) -> Optional[Entity]:
        """解析实体数据"""
        try:
            # 尝试不同的字段名映射
            entity_id = (data.get("id") or
                        data.get("entity_id") or
                        data.get("ID") or
                        default_id)

            standard_name = (data.get("standard_name") or
                           data.get("name") or
                           data.get("title") or
                           data.get("entity_name"))

            if not standard_name:
                return None

            # 提取实体类型
            entity_type = (data.get("entity_type") or
                          data.get("type") or
                          data.get("category") or
                          "UNKNOWN")

            # 提取别名
            aliases = data.get("aliases", [])
            if isinstance(aliases, str):
                aliases = [aliases]

            # 提取描述
            description = (data.get("description") or
                          data.get("desc") or
                          data.get("summary") or
                          "")

            # 提取其他属性
            attributes = {}
            for key in ["attributes", "properties", "info", "details"]:
                if key in data and isinstance(data[key], dict):
                    attributes = data[key]
                    break

            return Entity(
                id=str(entity_id) if entity_id else str(len(self.entities)),
                standard_name=standard_name,
                entity_type=entity_type.upper() if entity_type else "UNKNOWN",
                aliases=aliases,
                description=description,
                attributes=attributes,
                popularity=data.get("popularity", 0.0),
                source=data.get("source", ""),
            )
        except Exception as e:
            logger.warning(f"解析实体数据失败: {e}, data={data}")
            return None

    def _load_aliases(self, path: Path) -> None:
        """加载别名数据"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 解析别名数据
        # 格式: {"alias_name": {"entity_id": "xxx", "standard_name": "xxx"}}
        if isinstance(data, dict):
            for alias, value in data.items():
                if isinstance(value, dict):
                    # 格式: {"entity_id": "xxx", "standard_name": "xxx"}
                    entity_id = value.get("entity_id")
                    if entity_id:
                        self.alias_dict[alias].append(str(entity_id))
                elif isinstance(value, list):
                    # 格式: ["entity_id1", "entity_id2"]
                    for eid in value:
                        self.alias_dict[alias].append(str(eid))
                elif isinstance(value, str):
                    # 格式: "entity_id"
                    self.alias_dict[alias].append(value)

        logger.info(f"从 {path} 加载了 {len(self.alias_dict)} 个别名")

    def _build_indexes(self) -> None:
        """构建索引"""
        # 第一步：构建名称索引和类型索引
        for entity_id, entity in self.entities.items():
            # 名称索引
            self.name_index[entity.standard_name] = entity_id

            # 类型索引
            self.type_index[entity.entity_type].append(entity_id)

        # 第二步：清理别名索引，确保entity_id在知识库中存在
        # 优先使用知识库实体自身的别名
        cleaned_alias_dict = defaultdict(list)

        # 先添加知识库实体自身的别名
        for entity_id, entity in self.entities.items():
            for alias in entity.aliases:
                if entity_id not in cleaned_alias_dict[alias]:
                    cleaned_alias_dict[alias].append(entity_id)

        # 再添加外部别名文件中的别名（仅当entity_id存在于知识库中）
        for alias, entity_ids in self.alias_dict.items():
            for eid in entity_ids:
                if eid in self.entities and eid not in cleaned_alias_dict[alias]:
                    cleaned_alias_dict[alias].append(eid)

        self.alias_dict = cleaned_alias_dict

        logger.info(f"索引构建完成: {len(self.name_index)}个名称, {len(self.type_index)}个类型")

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """根据ID获取实体"""
        return self.entities.get(entity_id)

    def get_entity_by_name(self, name: str) -> Optional[Entity]:
        """根据名称获取实体"""
        entity_id = self.name_index.get(name)
        if entity_id:
            return self.entities.get(entity_id)
        return None

    def search_by_alias(self, alias: str) -> List[Entity]:
        """
        根据别名搜索实体

        Args:
            alias: 别名文本

        Returns:
            匹配的实体列表
        """
        entity_ids = self.alias_dict.get(alias, [])
        return [self.entities[eid] for eid in entity_ids if eid in self.entities]

    def search_by_type(self, entity_type: str) -> List[Entity]:
        """
        根据类型搜索实体

        Args:
            entity_type: 实体类型

        Returns:
            该类型的所有实体
        """
        entity_ids = self.type_index.get(entity_type.upper(), [])
        return [self.entities[eid] for eid in entity_ids if eid in self.entities]

    def get_statistics(self) -> dict:
        """获取知识库统计信息"""
        type_counts = {}
        for entity_type, entity_ids in self.type_index.items():
            type_counts[entity_type] = len(entity_ids)

        return {
            "total_entities": self.entity_count,
            "total_aliases": self.alias_count,
            "entity_types": type_counts,
            "loaded": self._loaded,
        }


# 全局知识库实例
knowledge_base = KnowledgeBase()
