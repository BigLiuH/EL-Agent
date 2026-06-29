"""
修复标注数据中的中文实体指向

如果文章中的实体是中文，但指向英文标准名称的实体，
则修改为指向中文标准名称的实体。
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

    return kb_data, articles


def is_chinese(text):
    """检查文本是否主要是中文"""
    # 包含至少2个中文字符
    chinese_chars = re.findall(r'[一-鿿]', text)
    return len(chinese_chars) >= 2


def is_english(text):
    """检查文本是否主要是英文"""
    # 包含至少3个英文字母，且没有中文
    english_chars = re.findall(r'[a-zA-Z]', text)
    chinese_chars = re.findall(r'[一-鿿]', text)
    return len(english_chars) >= 3 and len(chinese_chars) == 0


def build_chinese_name_map(kb_data):
    """
    构建中文名称到实体的映射

    找出所有标准名称是中文的实体
    """
    chinese_map = {}  # 中文名称 -> entity_id

    for entity in kb_data['entities']:
        name = entity['standard_name']
        if is_chinese(name):
            chinese_map[name] = entity['entity_id']

    return chinese_map


def build_entity_id_to_name(kb_data):
    """构建entity_id到标准名称的映射"""
    id_to_name = {}

    for entity in kb_data['entities']:
        id_to_name[entity['entity_id']] = entity['standard_name']

    return id_to_name


def fix_annotations(articles, chinese_map, id_to_name):
    """
    修复标注数据

    策略：
    如果 mention 是中文，但 entity_id 指向英文标准名称实体，
    则在中文实体映射中查找，修改 entity_id
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

            mention_text = mention.get('text', '')
            entity_id = mention.get('entity_id', '')
            standard_name = mention.get('standard_name', '')

            # 检查是否需要修复
            if is_chinese(mention_text) and entity_id in id_to_name:
                entity_name = id_to_name[entity_id]

                # 如果实体标准名称是英文，但mention是中文
                if is_english(entity_name):
                    # 在中文映射中查找
                    if mention_text in chinese_map:
                        new_entity_id = chinese_map[mention_text]
                        if new_entity_id != entity_id:
                            fixed_mention['entity_id'] = new_entity_id
                            fixed_mention['standard_name'] = mention_text
                            fixed_count += 1

            fixed_mentions.append(fixed_mention)

        fixed_article['mentions'] = fixed_mentions
        fixed_articles.append(fixed_article)

    print(f"修复结果:")
    print(f"  总mention数: {total_mentions}")
    print(f"  修复数: {fixed_count}")
    print(f"  修复率: {fixed_count/total_mentions*100:.2f}%")

    return fixed_articles


def save_fixed_articles(articles, output_path='data/annotations_fixed_chinese.json'):
    """保存修复后的标注数据"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n修复后的标注数据已保存到: {output_path}")
    return output_path


def main():
    """主函数"""
    print("=" * 70)
    print("修复标注数据中的中文实体指向")
    print("=" * 70)

    # 加载数据
    print("\n[1/4] 加载数据...")
    kb_data, articles = load_data()
    chinese_map = build_chinese_name_map(kb_data)
    id_to_name = build_entity_id_to_name(kb_data)
    print(f"  知识库实体数: {len(kb_data['entities'])}")
    print(f"  中文标准名称实体数: {len(chinese_map)}")
    print(f"  文章数: {len(articles)}")

    # 显示中文映射示例
    print("\n中文名称映射示例:")
    for name, eid in list(chinese_map.items())[:10]:
        print(f"  {name} -> {eid}")

    # 修复标注数据
    print("\n[2/4] 修复标注数据...")
    fixed_articles = fix_annotations(articles, chinese_map, id_to_name)

    # 保存
    print("\n[3/4] 保存修复结果...")
    output_path = save_fixed_articles(fixed_articles)

    # 验证
    print("\n[4/4] 验证修复结果...")
    # 检查修复后的数据
    fixed_count = 0
    for article in fixed_articles:
        for mention in article.get('mentions', []):
            entity_id = mention.get('entity_id', '')
            if entity_id in id_to_name:
                entity_name = id_to_name[entity_id]
                mention_text = mention.get('text', '')
                if is_chinese(mention_text) and is_english(entity_name):
                    fixed_count += 1

    print(f"  剩余需要修复的mention数: {fixed_count}")

    return output_path


if __name__ == "__main__":
    main()
