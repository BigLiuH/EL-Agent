"""
知识库模块测试
"""

import pytest
import json
import tempfile
from pathlib import Path

from elagent.core.knowledge_base import KnowledgeBase


@pytest.fixture
def sample_kb_data():
    """创建测试用的知识库数据"""
    return [
        {
            "id": "1",
            "standard_name": "国家电网有限公司",
            "entity_type": "ORG",
            "aliases": ["国网", "国家电网", "State Grid"],
            "description": "中国最大的电力公司"
        },
        {
            "id": "2",
            "standard_name": "中国银行",
            "entity_type": "ORG",
            "aliases": ["中行", "BOC"],
            "description": "中国四大国有银行之一"
        },
        {
            "id": "3",
            "standard_name": "张三",
            "entity_type": "PER",
            "aliases": ["老张", "Zhang San"],
            "description": "测试人物"
        }
    ]


@pytest.fixture
def sample_alias_data():
    """创建测试用的别名数据"""
    return {
        "国网": ["1"],
        "国家电网": ["1"],
        "中行": ["2"],
        "中国银行": ["2"],
        "老张": ["3"]
    }


@pytest.fixture
def kb_with_data(sample_kb_data, sample_alias_data, tmp_path):
    """创建带有测试数据的知识库"""
    # 写入临时文件
    kb_file = tmp_path / "kb.json"
    alias_file = tmp_path / "aliases.json"

    with open(kb_file, 'w', encoding='utf-8') as f:
        json.dump(sample_kb_data, f, ensure_ascii=False)

    with open(alias_file, 'w', encoding='utf-8') as f:
        json.dump(sample_alias_data, f, ensure_ascii=False)

    # 加载知识库
    kb = KnowledgeBase()
    kb.load(str(kb_file), str(alias_file))

    return kb


class TestKnowledgeBase:
    """知识库测试类"""

    def test_load_entities(self, kb_with_data):
        """测试加载实体"""
        kb = kb_with_data
        assert kb.loaded == True
        assert kb.entity_count == 3

    def test_get_entity(self, kb_with_data):
        """测试获取实体"""
        kb = kb_with_data
        entity = kb.get_entity("1")
        assert entity is not None
        assert entity.standard_name == "国家电网有限公司"
        assert entity.entity_type == "ORG"

    def test_get_entity_by_name(self, kb_with_data):
        """测试根据名称获取实体"""
        kb = kb_with_data
        entity = kb.get_entity_by_name("国家电网有限公司")
        assert entity is not None
        assert entity.id == "1"

    def test_search_by_alias(self, kb_with_data):
        """测试别名搜索"""
        kb = kb_with_data

        # 测试精确别名
        entities = kb.search_by_alias("国网")
        assert len(entities) == 1
        assert entities[0].standard_name == "国家电网有限公司"

        # 测试另一个别名
        entities = kb.search_by_alias("中行")
        assert len(entities) == 1
        assert entities[0].standard_name == "中国银行"

    def test_search_by_type(self, kb_with_data):
        """测试类型搜索"""
        kb = kb_with_data

        # 搜索ORG类型
        org_entities = kb.search_by_type("ORG")
        assert len(org_entities) == 2

        # 搜索PER类型
        per_entities = kb.search_by_type("PER")
        assert len(per_entities) == 1

    def test_get_statistics(self, kb_with_data):
        """测试获取统计信息"""
        kb = kb_with_data
        stats = kb.get_statistics()

        assert stats["total_entities"] == 3
        assert stats["loaded"] == True
        assert "ORG" in stats["entity_types"]
        assert stats["entity_types"]["ORG"] == 2
        assert stats["entity_types"]["PER"] == 1

    def test_entity_all_names(self, kb_with_data):
        """测试获取实体所有名称"""
        kb = kb_with_data
        entity = kb.get_entity("1")

        all_names = entity.all_names()
        assert "国家电网有限公司" in all_names
        assert "国网" in all_names
        assert "State Grid" in all_names

    def test_empty_search(self, kb_with_data):
        """测试空搜索结果"""
        kb = kb_with_data

        # 搜索不存在的别名
        entities = kb.search_by_alias("不存在的实体")
        assert len(entities) == 0

        # 搜索不存在的类型
        entities = kb.search_by_type("UNKNOWN")
        assert len(entities) == 0
