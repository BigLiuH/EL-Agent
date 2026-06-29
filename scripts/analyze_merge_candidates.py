"""
分析合并候选

基于标注数据，找出指向同一mention的不同entity_id。
"""

import json
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_data():
    """加载数据"""
    with open('data/fixed_chinese/knowledge_base_merged.json', 'r', encoding='utf-8') as f:
        kb_data = json.load(f)

    with open('data/fixed_chinese/llm_extracted_merged.json', 'r', encoding='utf-8') as f:
        articles = json.load(f)

    return kb_data, articles


def analyze_mentions(articles):
    """
    分析标注数据，找出指向同一mention的不同entity_id

    返回：{mention_text: set(entity_id1, entity_id2, ...)}
    """
    mention_to_entities = defaultdict(set)

    for article in articles:
        for mention in article.get('mentions', []):
            mention_text = mention.get('text', '')
            entity_id = mention.get('entity_id', '')

            if mention_text and entity_id:
                mention_to_entities[mention_text].add(entity_id)

    return mention_to_entities


def find_merge_candidates(mention_to_entities, kb_data):
    """
    找出合并候选

    条件：
    1. 同一个mention指向多个不同entity_id
    2. 这些entity_id在知识库中存在
    3. 这些实体类型相同
    """
    id_to_entity = {e['entity_id']: e for e in kb_data['entities']}

    merge_candidates = []

    for mention_text, entity_ids in mention_to_entities.items():
        # 只处理指向多个实体的情况
        if len(entity_ids) < 2:
            continue

        # 检查这些实体是否都在知识库中
        valid_entities = []
        for eid in entity_ids:
            if eid in id_to_entity:
                valid_entities.append(id_to_entity[eid])

        # 检查类型是否相同
        types = set(e['entity_type'] for e in valid_entities)
        if len(types) > 1:
            continue  # 类型不同，跳过

        # 记录候选
        merge_candidates.append({
            'mention': mention_text,
            'entity_ids': list(entity_ids),
            'entities': valid_entities,
            'entity_type': list(types)[0] if types else 'UNKNOWN'
        })

    return merge_candidates


def save_candidates(candidates, output_path='data/merge_candidates.json'):
    """保存合并候选"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2)

    print(f"\n合并候选已保存到: {output_path}")
    return output_path


def main():
    """主函数"""
    print("=" * 70)
    print("分析合并候选")
    print("=" * 70)

    # 加载数据
    print("\n[1/3] 加载数据...")
    kb_data, articles = load_data()
    print(f"  知识库实体数: {len(kb_data['entities'])}")
    print(f"  文章数: {len(articles)}")

    # 分析mention
    print("\n[2/3] 分析mention...")
    mention_to_entities = analyze_mentions(articles)
    print(f"  不同mention数: {len(mention_to_entities)}")

    # 统计指向多个实体的mention
    multi_entity_mentions = {k: v for k, v in mention_to_entities.items() if len(v) >= 2}
    print(f"  指向多个实体的mention数: {len(multi_entity_mentions)}")

    # 找出合并候选
    print("\n[3/3] 找出合并候选...")
    candidates = find_merge_candidates(mention_to_entities, kb_data)
    print(f"  合并候选数: {len(candidates)}")

    # 按类型统计
    type_counter = defaultdict(int)
    for c in candidates:
        type_counter[c['entity_type']] += 1

    print("\n按类型统计:")
    for etype, count in sorted(type_counter.items(), key=lambda x: -x[1]):
        print(f"  {etype}: {count}")

    # 显示示例
    print("\n合并候选示例 (前20个):")
    for i, c in enumerate(candidates[:20]):
        print(f"  {i+1}. {c['mention']} ({c['entity_type']})")
        for e in c['entities']:
            print(f"     - {e['entity_id']}: {e['standard_name']}")

    # 保存
    output_path = save_candidates(candidates)

    return output_path


if __name__ == "__main__":
    main()
