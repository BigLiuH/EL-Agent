"""
修复知识库中的英文标准名称

将英文标准名称改为中文，英文名称作为别名。
"""

import json
import sys
import re
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

    with open('Dataset/aliases_merged.json', 'r', encoding='utf-8') as f:
        alias_data = json.load(f)

    return kb_data, articles, alias_data


def is_chinese(text):
    """检查文本是否主要是中文"""
    chinese_chars = re.findall(r'[一-鿿]', text)
    return len(chinese_chars) >= 2


def is_english(text):
    """检查文本是否主要是英文"""
    english_chars = re.findall(r'[a-zA-Z]', text)
    chinese_chars = re.findall(r'[一-鿿]', text)
    return len(english_chars) >= 3 and len(chinese_chars) == 0


def find_chinese_mentions_for_english_entities(articles, kb_data):
    """
    找出中文mention指向英文实体的情况

    返回：{entity_id: [中文mention列表]}
    """
    id_to_entity = {e['entity_id']: e for e in kb_data['entities']}

    # 收集每个entity_id对应的中文mention
    entity_chinese_mentions = {}

    for article in articles:
        for mention in article.get('mentions', []):
            entity_id = mention.get('entity_id', '')
            mention_text = mention.get('text', '')

            if entity_id in id_to_entity:
                entity = id_to_entity[entity_id]
                entity_name = entity['standard_name']

                # 如果实体是英文名，但mention是中文
                if is_english(entity_name) and is_chinese(mention_text):
                    if entity_id not in entity_chinese_mentions:
                        entity_chinese_mentions[entity_id] = set()
                    entity_chinese_mentions[entity_id].add(mention_text)

    return entity_chinese_mentions


def fix_kb_entities(kb_data, entity_chinese_mentions):
    """
    修复知识库中的实体

    将英文标准名称改为中文，英文名称作为别名
    """
    fixed_count = 0

    for entity in kb_data['entities']:
        entity_id = entity['entity_id']

        if entity_id in entity_chinese_mentions:
            chinese_mentions = list(entity_chinese_mentions[entity_id])

            # 选择最常见的中文名称作为标准名称
            # 这里简单选择第一个
            new_standard_name = chinese_mentions[0]

            # 将原英文名称添加到别名
            old_name = entity['standard_name']
            aliases = entity.get('aliases', [])
            if old_name not in aliases:
                aliases.append(old_name)

            # 添加其他中文名称到别名
            for name in chinese_mentions[1:]:
                if name not in aliases:
                    aliases.append(name)

            # 更新实体
            entity['standard_name'] = new_standard_name
            entity['aliases'] = aliases
            fixed_count += 1

    print(f"修复结果:")
    print(f"  修复的实体数: {fixed_count}")

    return kb_data


def fix_alias_data(alias_data, kb_data):
    """
    修复别名数据

    更新别名映射，使其与知识库一致
    """
    id_to_entity = {e['entity_id']: e for e in kb_data['entities']}

    # 重新构建别名映射
    new_aliases = {}

    for entity in kb_data['entities']:
        entity_id = entity['entity_id']
        standard_name = entity['standard_name']

        # 标准名称作为别名
        new_aliases[standard_name] = {
            'entity_id': entity_id,
            'standard_name': standard_name
        }

        # 实体的别名
        for alias in entity.get('aliases', []):
            if alias not in new_aliases:
                new_aliases[alias] = {
                    'entity_id': entity_id,
                    'standard_name': standard_name
                }

    print(f"别名数据修复结果:")
    print(f"  原别名数: {len(alias_data)}")
    print(f"  新别名数: {len(new_aliases)}")

    return new_aliases


def fix_annotations(articles, kb_data):
    """
    修复标注数据

    更新standard_name和entity_id
    """
    id_to_entity = {e['entity_id']: e for e in kb_data['entities']}

    fixed_count = 0
    total_mentions = 0
    fixed_articles = []

    for article in articles:
        fixed_article = article.copy()
        fixed_mentions = []

        for mention in article.get('mentions', []):
            total_mentions += 1
            fixed_mention = mention.copy()

            entity_id = mention.get('entity_id', '')

            # 如果entity_id在知识库中，更新standard_name
            if entity_id in id_to_entity:
                entity = id_to_entity[entity_id]
                old_name = mention.get('standard_name', '')
                new_name = entity['standard_name']

                if old_name != new_name:
                    fixed_mention['standard_name'] = new_name
                    fixed_count += 1

            fixed_mentions.append(fixed_mention)

        fixed_article['mentions'] = fixed_mentions
        fixed_articles.append(fixed_article)

    print(f"标注数据修复结果:")
    print(f"  总mention数: {total_mentions}")
    print(f"  修复数: {fixed_count}")

    return fixed_articles


def save_fixed_data(kb_data, alias_data, articles, output_dir='data/fixed_chinese'):
    """保存修复后的数据"""
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
    print("修复知识库中的英文标准名称")
    print("=" * 70)

    # 加载数据
    print("\n[1/5] 加载数据...")
    kb_data, articles, alias_data = load_data()
    print(f"  知识库实体数: {len(kb_data['entities'])}")
    print(f"  文章数: {len(articles)}")
    print(f"  别名数: {len(alias_data)}")

    # 找出需要修复的实体
    print("\n[2/5] 找出需要修复的实体...")
    entity_chinese_mentions = find_chinese_mentions_for_english_entities(articles, kb_data)
    print(f"  需要修复的实体数: {len(entity_chinese_mentions)}")

    # 显示示例
    print("\n需要修复的实体示例:")
    for i, (entity_id, mentions) in enumerate(list(entity_chinese_mentions.items())[:10]):
        entity = next(e for e in kb_data['entities'] if e['entity_id'] == entity_id)
        print(f"  {entity_id}: {entity['standard_name']} -> {list(mentions)[0]}")

    # 修复知识库
    print("\n[3/5] 修复知识库...")
    kb_data = fix_kb_entities(kb_data, entity_chinese_mentions)

    # 修复别名数据
    print("\n[4/5] 修复别名数据...")
    alias_data = fix_alias_data(alias_data, kb_data)

    # 修复标注数据
    print("\n[5/5] 修复标注数据...")
    articles = fix_annotations(articles, kb_data)

    # 保存数据
    kb_path, alias_path, articles_path = save_fixed_data(kb_data, alias_data, articles)

    return kb_path, alias_path, articles_path


if __name__ == "__main__":
    main()
