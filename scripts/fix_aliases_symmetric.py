"""
修复别名映射的双向对称性

如果A的别名包含B的标准名称，那么B的别名也应该包含A的标准名称。
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Set

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_data():
    """加载数据"""
    with open('Dataset/knowledge_base_merged.json', 'r', encoding='utf-8') as f:
        kb_data = json.load(f)

    return kb_data


def build_name_to_entity(kb_data):
    """构建名称到实体的映射"""
    name_to_entity = {}

    for entity in kb_data['entities']:
        name = entity['standard_name']
        name_to_entity[name] = entity

    return name_to_entity


def fix_aliases_symmetric(kb_data):
    """
    修复别名的双向对称性

    策略：
    1. 遍历所有实体
    2. 如果实体A的别名中包含实体B的标准名称
    3. 那么实体B的别名中应该包含实体A的标准名称
    """
    name_to_entity = build_name_to_entity(kb_data)

    # 统计
    fixed_count = 0
    total_additions = 0

    # 创建实体ID到实体的映射
    id_to_entity = {e['entity_id']: e for e in kb_data['entities']}

    # 遍历所有实体
    for entity in kb_data['entities']:
        entity_id = entity['entity_id']
        standard_name = entity['standard_name']
        aliases = entity.get('aliases', [])

        # 检查每个别名
        for alias in aliases:
            # 如果别名是另一个实体的标准名称
            if alias in name_to_entity:
                other_entity = name_to_entity[alias]
                other_id = other_entity['entity_id']

                # 如果另一个实体不是自己
                if other_id != entity_id:
                    # 检查另一个实体的别名中是否包含当前实体的标准名称
                    other_aliases = set(other_entity.get('aliases', []))

                    if standard_name not in other_aliases:
                        # 添加到另一个实体的别名中
                        other_aliases.add(standard_name)
                        other_entity['aliases'] = list(other_aliases)
                        total_additions += 1

    # 统计修复的实体数
    fixed_count = sum(1 for e in kb_data['entities'] if len(e.get('aliases', [])) > 0)

    print(f"修复结果:")
    print(f"  添加的别名数: {total_additions}")
    print(f"  有别名的实体数: {fixed_count}")

    return kb_data


def save_fixed_kb(kb_data, output_path='data/kb_fixed_symmetric.json'):
    """保存修复后的知识库"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)

    print(f"\n修复后的知识库已保存到: {output_path}")
    return output_path


def validate_fixes(kb_data):
    """验证修复结果"""
    name_to_entity = build_name_to_entity(kb_data)

    # 检查是否还有不对称的情况
    asymmetric_count = 0
    asymmetric_examples = []

    for entity in kb_data['entities']:
        entity_id = entity['entity_id']
        standard_name = entity['standard_name']
        aliases = entity.get('aliases', [])

        for alias in aliases:
            if alias in name_to_entity:
                other_entity = name_to_entity[alias]
                other_id = other_entity['entity_id']

                if other_id != entity_id:
                    other_aliases = other_entity.get('aliases', [])
                    if standard_name not in other_aliases:
                        asymmetric_count += 1
                        if len(asymmetric_examples) < 5:
                            asymmetric_examples.append({
                                'entity1': standard_name,
                                'entity2': alias,
                                'issue': f'{standard_name} 的别名包含 {alias}, 但 {alias} 的别名不包含 {standard_name}'
                            })

    print(f"\n验证结果:")
    print(f"  不对称的别名数: {asymmetric_count}")

    if asymmetric_examples:
        print(f"\n不对称示例:")
        for ex in asymmetric_examples:
            print(f"  {ex['issue']}")

    return asymmetric_count == 0


def main():
    """主函数"""
    print("=" * 70)
    print("修复别名映射的双向对称性")
    print("=" * 70)

    # 加载数据
    print("\n[1/4] 加载知识库...")
    kb_data = load_data()
    print(f"  实体数: {len(kb_data['entities'])}")

    # 修复别名
    print("\n[2/4] 修复别名...")
    kb_data = fix_aliases_symmetric(kb_data)

    # 验证
    print("\n[3/4] 验证修复结果...")
    is_valid = validate_fixes(kb_data)

    # 保存
    print("\n[4/4] 保存修复结果...")
    output_path = save_fixed_kb(kb_data)

    # 显示修复示例
    print("\n修复示例:")
    test_entities = ['周天成', '陈雨菲', '美国', '中国台北']
    name_to_entity = build_name_to_entity(kb_data)

    for name in test_entities:
        if name in name_to_entity:
            entity = name_to_entity[name]
            aliases = entity.get('aliases', [])
            print(f"  {name}: {aliases[:5]}")

    return output_path


if __name__ == "__main__":
    main()
