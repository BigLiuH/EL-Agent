"""
知识库数据治理脚本 V2

增强版：处理更多相似实体合并场景
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
    with open('data/cleaned/knowledge_base_cleaned.json', 'r', encoding='utf-8') as f:
        kb_data = json.load(f)

    with open('data/cleaned/aliases_cleaned.json', 'r', encoding='utf-8') as f:
        alias_data = json.load(f)

    return kb_data, alias_data


def find_similar_entities(entities):
    """
    查找相似实体

    策略：
    1. 名称包含关系（长度差异<=6）
    2. 名称相似度高的实体
    """
    merge_groups = []
    processed = set()
    entity_list = list(entities.values())

    for i, e1 in enumerate(entity_list):
        if e1['entity_id'] in processed:
            continue

        name1 = e1['standard_name']
        group = [e1['entity_id']]

        for e2 in entity_list[i+1:]:
            if e2['entity_id'] in processed:
                continue

            name2 = e2['standard_name']

            # 名称完全相同
            if name1 == name2:
                group.append(e2['entity_id'])
                processed.add(e2['entity_id'])
                continue

            # 名称包含关系
            if name1 in name2 or name2 in name1:
                # 长度差异不超过6个字符
                if abs(len(name1) - len(name2)) <= 6:
                    # 必须类型相同才能合并
                    if e1['entity_type'] == e2['entity_type']:
                        group.append(e2['entity_id'])
                        processed.add(e2['entity_id'])

        if len(group) > 1:
            merge_groups.append(group)
        processed.add(e1['entity_id'])

    return merge_groups


def merge_entities(entities, merge_groups):
    """合并实体"""
    merge_map = {}  # old_id -> new_id
    merged_entities = {}

    for group in merge_groups:
        # 选择名称最长的作为主实体（通常是更完整的名称）
        group_entities = [(eid, entities[eid]) for eid in group]
        group_entities.sort(key=lambda x: len(x[1]['standard_name']), reverse=True)

        main_id = group_entities[0][0]
        main_entity = group_entities[0][1].copy()

        # 收集所有别名
        all_aliases = set(main_entity.get('aliases', []))

        for old_id, old_entity in group_entities[1:]:
            merge_map[old_id] = main_id
            all_aliases.update(old_entity.get('aliases', []))
            # 添加旧名称作为别名
            all_aliases.add(old_entity['standard_name'])

        main_entity['aliases'] = list(all_aliases)
        merged_entities[main_id] = main_entity

    return merge_map, merged_entities


def apply_merge(kb_data, alias_data, merge_map, merged_entities):
    """应用合并"""
    # 更新知识库
    new_entities = []
    for entity in kb_data['entities']:
        eid = entity['entity_id']
        if eid in merge_map:
            continue  # 被合并的实体，跳过
        elif eid in merged_entities:
            new_entities.append(merged_entities[eid])
        else:
            new_entities.append(entity)

    # 更新别名
    new_aliases = {}
    for alias, info in alias_data.items():
        old_id = info['entity_id']
        if old_id in merge_map:
            new_id = merge_map[old_id]
            new_aliases[alias] = {
                'entity_id': new_id,
                'standard_name': info['standard_name']
            }
        else:
            new_aliases[alias] = info

    return {'entities': new_entities}, new_aliases


def save_data(kb_data, alias_data):
    """保存数据"""
    output_dir = Path('data/cleaned_v2')
    output_dir.mkdir(parents=True, exist_ok=True)

    kb_path = output_dir / 'knowledge_base_cleaned.json'
    alias_path = output_dir / 'aliases_cleaned.json'

    with open(kb_path, 'w', encoding='utf-8') as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)

    with open(alias_path, 'w', encoding='utf-8') as f:
        json.dump(alias_data, f, ensure_ascii=False, indent=2)

    return str(kb_path), str(alias_path)


def main():
    """主函数"""
    print("=" * 70)
    print("知识库数据治理 V2")
    print("=" * 70)

    # 加载数据
    print("\n[1/4] 加载数据...")
    kb_data, alias_data = load_data()
    entities = {e['entity_id']: e for e in kb_data['entities']}
    print(f"  实体数: {len(entities)}")
    print(f"  别名数: {len(alias_data)}")

    # 查找相似实体
    print("\n[2/4] 查找相似实体...")
    merge_groups = find_similar_entities(entities)
    print(f"  找到 {len(merge_groups)} 组需要合并的实体")

    # 合并实体
    print("\n[3/4] 合并实体...")
    merge_map, merged_entities = merge_entities(entities, merge_groups)
    print(f"  合并了 {len(merge_map)} 个实体")

    # 应用合并
    print("\n[4/4] 应用合并...")
    kb_data, alias_data = apply_merge(kb_data, alias_data, merge_map, merged_entities)
    print(f"  最终实体数: {len(kb_data['entities'])}")

    # 保存数据
    kb_path, alias_path = save_data(kb_data, alias_data)
    print(f"\n数据已保存到:")
    print(f"  {kb_path}")
    print(f"  {alias_path}")

    # 显示合并详情
    if merge_groups:
        print(f"\n合并详情 (前20组):")
        for i, group in enumerate(merge_groups[:20]):
            print(f"  组{i+1}:")
            for eid in group:
                entity = entities[eid]
                print(f"    {eid}: {entity['standard_name']} ({entity['entity_type']})")

    return kb_path, alias_path


if __name__ == "__main__":
    main()
