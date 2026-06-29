"""
知识库数据治理脚本

解决以下问题：
1. 别名指向不一致（别名文件中的ID与知识库中的ID不匹配）
2. 相似实体合并（名称包含关系的实体）
3. 数据去重
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_data():
    """加载数据"""
    with open('Dataset/knowledge_base_merged.json', 'r', encoding='utf-8') as f:
        kb_data = json.load(f)

    with open('Dataset/aliases_merged.json', 'r', encoding='utf-8') as f:
        alias_data = json.load(f)

    return kb_data, alias_data


def build_entity_index(kb_data):
    """构建实体索引"""
    entities = {}
    name_to_id = {}

    for entity in kb_data['entities']:
        eid = entity['entity_id']
        entities[eid] = entity
        name_to_id[entity['standard_name']] = eid

    return entities, name_to_id


def fix_alias_mapping(alias_data, entities, name_to_id):
    """
    修复别名映射

    确保别名指向的entity_id在知识库中存在。
    如果不存在，尝试通过standard_name查找正确的ID。
    """
    fixed_aliases = {}
    fixed_count = 0
    removed_count = 0

    for alias, info in alias_data.items():
        target_id = info['entity_id']
        target_name = info['standard_name']

        # 检查目标实体是否存在
        if target_id in entities:
            # 存在，保留
            fixed_aliases[alias] = info
        else:
            # 不存在，尝试通过名称查找
            if target_name in name_to_id:
                new_id = name_to_id[target_name]
                fixed_aliases[alias] = {
                    'entity_id': new_id,
                    'standard_name': target_name
                }
                fixed_count += 1
            else:
                # 找不到，移除
                removed_count += 1

    print(f"修复别名映射: {fixed_count} 个, 移除: {removed_count} 个")
    return fixed_aliases


def merge_similar_entities(entities, name_to_id):
    """
    合并相似实体

    策略：
    1. 名称完全相同的实体，保留ID最小的
    2. 名称包含关系的实体，保留更完整的名称
    3. 必须类型相同才能合并
    """
    # 找出需要合并的实体组
    merge_groups = []
    processed = set()

    for eid, entity in entities.items():
        if eid in processed:
            continue

        name = entity['standard_name']
        entity_type = entity['entity_type']
        group = [eid]

        # 查找名称包含关系的实体
        for other_id, other_entity in entities.items():
            if other_id == eid or other_id in processed:
                continue

            other_name = other_entity['standard_name']
            other_type = other_entity['entity_type']

            # 名称完全相同
            if name == other_name:
                group.append(other_id)
                processed.add(other_id)
            # 名称包含关系（如"宁夏"和"宁夏回族自治区"）
            elif name in other_name or other_name in name:
                # 必须类型相同才能合并
                if entity_type != other_type:
                    continue
                # 只合并长度差异较小的
                if abs(len(name) - len(other_name)) <= 4:
                    group.append(other_id)
                    processed.add(other_id)

        if len(group) > 1:
            merge_groups.append(group)
        processed.add(eid)

    print(f"找到 {len(merge_groups)} 组需要合并的实体")

    # 执行合并
    merge_map = {}  # old_id -> new_id
    merged_entities = {}

    for group in merge_groups:
        # 选择ID最小的作为主实体
        group.sort()
        main_id = group[0]
        main_entity = entities[main_id].copy()

        # 收集所有别名
        all_aliases = set(main_entity.get('aliases', []))

        for old_id in group[1:]:
            old_entity = entities[old_id]
            all_aliases.update(old_entity.get('aliases', []))
            merge_map[old_id] = main_id

            # 如果主实体名称较短，用更完整的名称
            if len(old_entity['standard_name']) > len(main_entity['standard_name']):
                main_entity['standard_name'] = old_entity['standard_name']

        main_entity['aliases'] = list(all_aliases)
        merged_entities[main_id] = main_entity

    return merge_groups, merge_map, merged_entities


def apply_merge_to_aliases(alias_data, merge_map):
    """应用合并到别名数据"""
    updated_aliases = {}
    updated_count = 0

    for alias, info in alias_data.items():
        old_id = info['entity_id']
        if old_id in merge_map:
            new_id = merge_map[old_id]
            updated_aliases[alias] = {
                'entity_id': new_id,
                'standard_name': info['standard_name']
            }
            updated_count += 1
        else:
            updated_aliases[alias] = info

    print(f"更新别名映射: {updated_count} 个")
    return updated_aliases


def apply_merge_to_kb(kb_data, merge_map, merged_entities):
    """应用合并到知识库数据"""
    new_entities = []

    for entity in kb_data['entities']:
        eid = entity['entity_id']
        if eid in merge_map:
            # 被合并的实体，跳过
            continue
        elif eid in merged_entities:
            # 使用合并后的实体
            new_entities.append(merged_entities[eid])
        else:
            # 保持不变
            new_entities.append(entity)

    print(f"知识库实体数: {len(kb_data['entities'])} -> {len(new_entities)}")

    return {'entities': new_entities}


def validate_fixes(kb_data, alias_data):
    """验证修复结果"""
    entities, name_to_id = build_entity_index(kb_data)

    # 检查别名指向
    valid_count = 0
    invalid_count = 0

    for alias, info in alias_data.items():
        if info['entity_id'] in entities:
            valid_count += 1
        else:
            invalid_count += 1

    print(f"\n验证结果:")
    print(f"  有效别名: {valid_count}")
    print(f"  无效别名: {invalid_count}")

    return invalid_count == 0


def save_cleaned_data(kb_data, alias_data, output_dir='data/cleaned'):
    """保存清理后的数据"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    kb_path = output_path / 'knowledge_base_cleaned.json'
    alias_path = output_path / 'aliases_cleaned.json'

    with open(kb_path, 'w', encoding='utf-8') as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)

    with open(alias_path, 'w', encoding='utf-8') as f:
        json.dump(alias_data, f, ensure_ascii=False, indent=2)

    print(f"\n清理后的数据已保存到:")
    print(f"  {kb_path}")
    print(f"  {alias_path}")

    return str(kb_path), str(alias_path)


def main():
    """主函数"""
    print("=" * 70)
    print("知识库数据治理")
    print("=" * 70)

    # 1. 加载数据
    print("\n[1/5] 加载数据...")
    kb_data, alias_data = load_data()
    entities, name_to_id = build_entity_index(kb_data)
    print(f"  知识库实体数: {len(entities)}")
    print(f"  别名数: {len(alias_data)}")

    # 2. 修复别名映射
    print("\n[2/5] 修复别名映射...")
    alias_data = fix_alias_mapping(alias_data, entities, name_to_id)

    # 3. 合并相似实体
    print("\n[3/5] 合并相似实体...")
    merge_groups, merge_map, merged_entities = merge_similar_entities(entities, name_to_id)

    # 4. 应用合并
    print("\n[4/5] 应用合并...")
    alias_data = apply_merge_to_aliases(alias_data, merge_map)
    kb_data = apply_merge_to_kb(kb_data, merge_map, merged_entities)

    # 5. 验证
    print("\n[5/5] 验证修复结果...")
    is_valid = validate_fixes(kb_data, alias_data)

    # 保存结果
    kb_path, alias_path = save_cleaned_data(kb_data, alias_data)

    # 显示合并详情
    if merge_groups:
        print(f"\n合并详情 (前10组):")
        for i, group in enumerate(merge_groups[:10]):
            print(f"  组{i+1}:")
            for eid in group:
                entity = entities[eid]
                print(f"    {eid}: {entity['standard_name']}")

    return kb_path, alias_path


if __name__ == "__main__":
    main()
