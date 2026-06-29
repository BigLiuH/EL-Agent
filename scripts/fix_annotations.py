"""
修复标注数据脚本

基于标准名称重新映射entity_id，解决标注数据与知识库不一致的问题。
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

    with open('Dataset/llm_extracted_merged.json', 'r', encoding='utf-8') as f:
        articles = json.load(f)

    return kb_data, articles


def build_name_to_id(kb_data):
    """构建标准名称到entity_id的映射"""
    name_to_id = {}

    for entity in kb_data['entities']:
        name = entity['standard_name']
        eid = entity['entity_id']

        # 如果有多个同名实体，保留第一个
        if name not in name_to_id:
            name_to_id[name] = eid

    return name_to_id


def fix_annotations(articles, name_to_id, kb_entities):
    """
    修复标注数据

    策略：
    1. 检查标注数据中的entity_id是否存在于知识库中
    2. 如果不存在，通过standard_name查找正确的entity_id
    3. 如果存在但standard_name不匹配，保留原始entity_id（因为可能是同名实体）
    """
    fixed_count = 0
    total_mentions = 0
    fixed_articles = []

    for article in articles:
        fixed_article = article.copy()
        fixed_mentions = []

        for mention in article.get('mentions', []):
            total_mentions += 1
            fixed_mention = mention.copy()

            standard_name = mention.get('standard_name', '')
            old_entity_id = mention.get('entity_id', '')

            # 检查entity_id是否存在于知识库中
            if old_entity_id not in kb_entities:
                # 不存在，通过standard_name查找
                if standard_name in name_to_id:
                    new_entity_id = name_to_id[standard_name]
                    fixed_mention['entity_id'] = new_entity_id
                    fixed_count += 1
            # 如果存在，保留原始entity_id（不修改）

            fixed_mentions.append(fixed_mention)

        fixed_article['mentions'] = fixed_mentions
        fixed_articles.append(fixed_article)

    print(f"修复结果:")
    print(f"  总mention数: {total_mentions}")
    print(f"  修复数: {fixed_count}")
    print(f"  修复率: {fixed_count/total_mentions*100:.2f}%")

    return fixed_articles


def save_fixed_articles(articles, output_path='data/annotations_fixed.json'):
    """保存修复后的标注数据"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n修复后的标注数据已保存到: {output_path}")
    return output_path


def validate_fixes(articles, kb_entities):
    """验证修复结果"""
    valid_count = 0
    invalid_count = 0
    invalid_examples = []

    for article in articles:
        for mention in article.get('mentions', []):
            entity_id = mention.get('entity_id', '')
            if entity_id in kb_entities:
                valid_count += 1
            else:
                invalid_count += 1
                if len(invalid_examples) < 10:
                    invalid_examples.append({
                        'mention': mention.get('text', ''),
                        'entity_id': entity_id,
                        'standard_name': mention.get('standard_name', '')
                    })

    print(f"\n验证结果:")
    print(f"  有效: {valid_count}")
    print(f"  无效: {invalid_count}")

    if invalid_examples:
        print(f"\n无效示例:")
        for ex in invalid_examples:
            print(f"  {ex['mention']} -> {ex['entity_id']} ({ex['standard_name']})")

    return invalid_count == 0


def main():
    """主函数"""
    print("=" * 70)
    print("修复标注数据")
    print("=" * 70)

    # 加载数据
    print("\n[1/4] 加载数据...")
    kb_data, articles = load_data()
    kb_entities = {e['entity_id']: e for e in kb_data['entities']}
    name_to_id = build_name_to_id(kb_data)
    print(f"  知识库实体数: {len(kb_entities)}")
    print(f"  文章数: {len(articles)}")
    print(f"  名称映射数: {len(name_to_id)}")

    # 修复标注数据
    print("\n[2/4] 修复标注数据...")
    fixed_articles = fix_annotations(articles, name_to_id, kb_entities)

    # 验证
    print("\n[3/4] 验证修复结果...")
    is_valid = validate_fixes(fixed_articles, kb_entities)

    # 保存
    print("\n[4/4] 保存修复结果...")
    output_path = save_fixed_articles(fixed_articles)

    # 显示修复示例
    print("\n修复示例:")
    examples = [
        ('周天成', 'PER', 'Chou Tien-chen'),
        ('陈雨菲', 'PER', 'Chen Yufei'),
        ('美国', 'LOC', '美利坚合众国'),
        ('中国台北', 'LOC', '中国台北地区'),
    ]

    for mention, etype, expected_name in examples:
        if expected_name in name_to_id:
            print(f"  {mention} ({etype}) -> {name_to_id[expected_name]} ({expected_name})")

    return output_path


if __name__ == "__main__":
    main()
