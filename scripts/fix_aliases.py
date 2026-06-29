"""
修复别名映射脚本

修复别名文件中entity_id与知识库不匹配的问题。
"""

import json
import sys
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_data():
    """加载数据"""
    with open('Dataset/knowledge_base_merged.json', 'r', encoding='utf-8') as f:
        kb_data = json.load(f)

    with open('Dataset/aliases_merged.json', 'r', encoding='utf-8') as f:
        alias_data = json.load(f)

    return kb_data, alias_data


def build_name_index(kb_data):
    """构建名称索引"""
    name_to_entities = {}  # name -> [entity_id, ...]

    for entity in kb_data['entities']:
        name = entity['standard_name']
        if name not in name_to_entities:
            name_to_entities[name] = []
        name_to_entities[name].append(entity['entity_id'])

    return name_to_entities


def fix_aliases(alias_data, kb_entities, name_to_entities):
    """
    修复别名映射

    策略：
    1. 如果entity_id存在于知识库中，保留
    2. 如果entity_id不存在，通过standard_name查找正确的ID
    3. 如果找不到，移除该别名
    """
    fixed_aliases = {}
    fixed_count = 0
    removed_count = 0
    unchanged_count = 0

    for alias, info in alias_data.items():
        target_id = info['entity_id']
        target_name = info['standard_name']

        # 检查目标实体是否存在
        if target_id in kb_entities:
            # 存在，保留
            fixed_aliases[alias] = info
            unchanged_count += 1
        else:
            # 不存在，尝试通过名称查找
            if target_name in name_to_entities:
                # 找到同名实体，使用第一个
                new_id = name_to_entities[target_name][0]
                fixed_aliases[alias] = {
                    'entity_id': new_id,
                    'standard_name': target_name
                }
                fixed_count += 1
            else:
                # 找不到，移除
                removed_count += 1

    print(f"修复结果:")
    print(f"  不变: {unchanged_count}")
    print(f"  修复: {fixed_count}")
    print(f"  移除: {removed_count}")

    return fixed_aliases


def save_fixed_aliases(alias_data, output_path='data/aliases_fixed.json'):
    """保存修复后的别名"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(alias_data, f, ensure_ascii=False, indent=2)

    print(f"\n修复后的别名已保存到: {output_path}")
    return output_path


def validate_fixes(alias_data, kb_entities):
    """验证修复结果"""
    valid_count = 0
    invalid_count = 0

    for alias, info in alias_data.items():
        if info['entity_id'] in kb_entities:
            valid_count += 1
        else:
            invalid_count += 1

    print(f"\n验证结果:")
    print(f"  有效: {valid_count}")
    print(f"  无效: {invalid_count}")

    return invalid_count == 0


def main():
    """主函数"""
    print("=" * 70)
    print("修复别名映射")
    print("=" * 70)

    # 加载数据
    print("\n[1/4] 加载数据...")
    kb_data, alias_data = load_data()
    kb_entities = {e['entity_id']: e for e in kb_data['entities']}
    name_to_entities = build_name_index(kb_data)
    print(f"  知识库实体数: {len(kb_entities)}")
    print(f"  别名数: {len(alias_data)}")

    # 修复别名
    print("\n[2/4] 修复别名映射...")
    fixed_aliases = fix_aliases(alias_data, kb_entities, name_to_entities)

    # 验证
    print("\n[3/4] 验证修复结果...")
    is_valid = validate_fixes(fixed_aliases, kb_entities)

    # 保存
    print("\n[4/4] 保存修复结果...")
    output_path = save_fixed_aliases(fixed_aliases)

    # 显示修复示例
    print("\n修复示例:")
    test_aliases = ['宁夏', '美国', '中国台北', '澳门']
    for alias in test_aliases:
        if alias in fixed_aliases:
            info = fixed_aliases[alias]
            print(f"  {alias} -> {info['entity_id']} ({info['standard_name']})")

    return output_path


if __name__ == "__main__":
    main()
