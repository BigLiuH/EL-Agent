"""
评测集生成脚本

基于知识库自动生成实体链接评测集。
"""

import json
import random
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.knowledge_base import KnowledgeBase


def generate_positive_samples(kb: KnowledgeBase, n: int = 200) -> list:
    """
    生成正例样本（应该成功链接的）

    策略：
    1. 使用实体的标准名称
    2. 使用实体的别名
    """
    samples = []
    entities = list(kb.entities.values())
    random.shuffle(entities)

    for entity in entities[:n]:
        # 使用标准名称
        samples.append({
            "mention_text": entity.standard_name,
            "expected_entity_id": entity.id,
            "expected_standard_name": entity.standard_name,
            "entity_type": entity.entity_type,
            "is_nil": False,
            "source": "standard_name"
        })

        # 使用别名（如果有）
        if entity.aliases:
            alias = random.choice(entity.aliases)
            samples.append({
                "mention_text": alias,
                "expected_entity_id": entity.id,
                "expected_standard_name": entity.standard_name,
                "entity_type": entity.entity_type,
                "is_nil": False,
                "source": "alias"
            })

    return samples


def generate_negative_samples(kb: KnowledgeBase, n: int = 100) -> list:
    """
    生成负例样本（应该返回NIL的）

    策略：
    1. 随机生成不存在的名称
    2. 对现有名称做微小修改
    """
    samples = []
    entities = list(kb.entities.values())

    # 策略1：随机组合生成不存在的名称
    prefixes = ["新", "旧", "大", "小", "超级", "全球", "国际"]
    suffixes = ["公司", "集团", "协会", "联盟", "组织", "机构"]

    for i in range(n // 2):
        # 生成随机名称
        if random.random() < 0.5:
            # 使用前缀+后缀组合
            name = random.choice(prefixes) + random.choice(suffixes)
        else:
            # 从实体名称中取部分并修改
            entity = random.choice(entities)
            name = entity.standard_name[:2] + "测试" + entity.standard_name[-2:] if len(entity.standard_name) > 4 else "测试实体"

        # 确保不在知识库中
        if not kb.search_by_alias(name) and not kb.get_entity_by_name(name):
            samples.append({
                "mention_text": name,
                "expected_entity_id": None,
                "expected_standard_name": None,
                "entity_type": "UNKNOWN",
                "is_nil": True,
                "source": "generated"
            })

    # 策略2：对现有名称做微小修改
    for i in range(n // 2):
        entity = random.choice(entities)
        original = entity.standard_name

        # 随机修改一个字符
        if len(original) > 2:
            pos = random.randint(0, len(original) - 1)
            modified = original[:pos] + "X" + original[pos+1:]

            # 确保修改后不在知识库中
            if not kb.search_by_alias(modified) and not kb.get_entity_by_name(modified):
                samples.append({
                    "mention_text": modified,
                    "expected_entity_id": None,
                    "expected_standard_name": None,
                    "entity_type": "UNKNOWN",
                    "is_nil": True,
                    "source": "modified"
                })

    return samples


def generate_testset(output_path: str = "data/testset.json"):
    """生成评测集"""
    print("正在加载知识库...")
    kb = KnowledgeBase()
    kb.load()

    print(f"知识库加载完成: {kb.entity_count}个实体")

    # 生成样本
    print("\n正在生成正例样本...")
    positive = generate_positive_samples(kb, n=200)
    print(f"生成了 {len(positive)} 个正例样本")

    print("\n正在生成负例样本...")
    negative = generate_negative_samples(kb, n=100)
    print(f"生成了 {len(negative)} 个负例样本")

    # 合并并打乱
    testset = positive + negative
    random.shuffle(testset)

    # 统计
    stats = {
        "total": len(testset),
        "positive": len(positive),
        "negative": len(negative),
        "type_distribution": {}
    }

    for sample in testset:
        t = sample.get("entity_type", "UNKNOWN")
        stats["type_distribution"][t] = stats["type_distribution"].get(t, 0) + 1

    # 保存
    output = {
        "metadata": {
            "description": "实体链接评测集",
            "generated_from": "knowledge_base_merged.json",
            "statistics": stats
        },
        "samples": testset
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n评测集已保存到: {output_path}")
    print(f"统计信息:")
    print(f"  总样本数: {stats['total']}")
    print(f"  正例数: {stats['positive']}")
    print(f"  负例数: {stats['negative']}")
    print(f"  类型分布: {stats['type_distribution']}")

    return output


if __name__ == "__main__":
    generate_testset()
