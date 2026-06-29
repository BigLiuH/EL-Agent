"""
执行实体合并

基于合并候选，执行实体合并。
"""

import json
import sys
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_data():
    """加载数据"""
    with open('data/merge_candidates.json', 'r', encoding='utf-8') as f:
        candidates = json.load(f)

    with open('data/fixed_chinese/knowledge_base_merged.json', 'r', encoding='utf-8') as f:
        kb_data = json.load(f)

    with open('data/fixed_chinese/aliases_merged.json', 'r', encoding='utf-8') as f:
        alias_data = json.load(f)

    with open('data/fixed_chinese/llm_extracted_merged.json', 'r', encoding='utf-8') as f:
        articles = json.load(f)

    return candidates, kb_data, alias_data, articles


def select_merge_target(candidates, kb_data):
    """
    选择合并目标

    策略：
    1. 对于全称/简称，保留全称
    2. 对于其他情况，保留名称较长的
    """
    id_to_entity = {e['entity_id']: e for e in kb_data['entities']}

    merge_map = {}  # old_id -> new_id

    for candidate in candidates:
        entity_ids = candidate['entity_ids']
        entities = [id_to_entity[eid] for eid in entity_ids if eid in id_to_entity]

        if len(entities) < 2:
            continue

        # 选择名称最长的作为保留实体
        keep_entity = max(entities, key=lambda e: len(e['standard_name']))
        keep_id = keep_entity['entity_id']

        # 其他实体合并到保留实体
        for entity in entities:
            if entity['entity_id'] != keep_id:
                merge_map[entity['entity_id']] = keep_id

    return merge_map


def execute_merge(kb_data, alias_data, articles, merge_map):
    """
    执行合并

    同步修改知识库、别名文件、标注数据
    """
    id_to_entity = {e['entity_id']: e for e in kb_data['entities']}

    # 1. 修改知识库
    print("  修改知识库...")
    new_entities = []
    removed_ids = set(merge_map.keys())

    for entity in kb_data['entities']:
        if entity['entity_id'] in removed_ids:
            continue

        # 如果是保留的实体，添加被合并实体的别名
        if entity['entity_id'] in merge_map.values():
            for old_id, new_id in merge_map.items():
                if new_id == entity['entity_id']:
                    old_entity = id_to_entity.get(old_id)
                    if old_entity:
                        # 添加被合并实体的标准名称作为别名
                        aliases = entity.get('aliases', [])
                        if old_entity['standard_name'] not in aliases:
                            aliases.append(old_entity['standard_name'])
                        # 添加被合并实体的别名
                        for alias in old_entity.get('aliases', []):
                            if alias not in aliases:
                                aliases.append(alias)
                        entity['aliases'] = aliases

        new_entities.append(entity)

    # 2. 修改别名文件
    print("  修改别名文件...")
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

    # 3. 修改标注数据
    print("  修改标注数据...")
    fixed_articles = []
    fixed_count = 0

    for article in articles:
        fixed_article = article.copy()
        fixed_mentions = []

        for mention in article.get('mentions', []):
            fixed_mention = mention.copy()
            entity_id = mention.get('entity_id', '')

            if entity_id in merge_map:
                new_id = merge_map[entity_id]
                fixed_mention['entity_id'] = new_id
                # 更新standard_name
                if new_id in id_to_entity:
                    fixed_mention['standard_name'] = id_to_entity[new_id]['standard_name']
                fixed_count += 1

            fixed_mentions.append(fixed_mention)

        fixed_article['mentions'] = fixed_mentions
        fixed_articles.append(fixed_article)

    print(f"  合并实体数: {len(merge_map)}")
    print(f"  修改标注数: {fixed_count}")

    return {'entities': new_entities}, new_aliases, fixed_articles


def save_merged_data(kb_data, alias_data, articles, output_dir='data/merged'):
    """保存合并后的数据"""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 保存知识库
    kb_path = output_path / 'knowledge_base_merged.json'
    with open(kb_path, 'w', encoding='utf-8') as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)

    # 保存别名
    alias_path = output_path / 'aliases_merged.json'
    with open(alias_path, 'w', encoding='utf-8') as f:
        json.dump(alias_data, f, ensure_ascii=False, indent=2)

    # 保存标注数据
    articles_path = output_path / 'llm_extracted_merged.json'
    with open(articles_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n数据已保存到:")
    print(f"  {kb_path}")
    print(f"  {alias_path}")
    print(f"  {articles_path}")

    return str(kb_path), str(alias_path), str(articles_path)


def main():
    """主函数"""
    print("=" * 70)
    print("执行实体合并")
    print("=" * 70)

    # 加载数据
    print("\n[1/4] 加载数据...")
    candidates, kb_data, alias_data, articles = load_data()
    print(f"  合并候选数: {len(candidates)}")
    print(f"  知识库实体数: {len(kb_data['entities'])}")

    # 选择合并目标
    print("\n[2/4] 选择合并目标...")
    merge_map = select_merge_target(candidates, kb_data)
    print(f"  需要合并的实体数: {len(merge_map)}")

    # 执行合并
    print("\n[3/4] 执行合并...")
    kb_data, alias_data, articles = execute_merge(kb_data, alias_data, articles, merge_map)

    # 保存数据
    print("\n[4/4] 保存数据...")
    kb_path, alias_path, articles_path = save_merged_data(kb_data, alias_data, articles)

    print(f"\n合并完成！")
    print(f"请更新配置使用合并后的数据，然后重新评测。")

    return kb_path, alias_path, articles_path


if __name__ == "__main__":
    main()
