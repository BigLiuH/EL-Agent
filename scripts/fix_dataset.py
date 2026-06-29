"""
数据集修复脚本

修复内容：
1. 恢复缺失的实体
2. 修复不匹配的名称
3. 清理无效别名
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

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


def fix_missing_entities(kb_data, articles):
    """
    修复缺失的实体

    从标注数据中提取缺失的entity_id，创建实体
    """
    kb_entities = {e['entity_id']: e for e in kb_data['entities']}

    # 找出缺失的entity_id
    missing_entities = {}
    for article in articles:
        for mention in article.get('mentions', []):
            entity_id = mention.get('entity_id')
            if entity_id and entity_id not in kb_entities:
                if entity_id not in missing_entities:
                    missing_entities[entity_id] = {
                        'entity_id': entity_id,
                        'standard_name': mention.get('standard_name', ''),
                        'entity_type': mention.get('entity_type', ''),
                        'aliases': [],
                        'description': '',
                        'source': 'restored_from_annotations'
                    }
                # 添加mention文本作为别名
                mention_text = mention.get('text', '')
                if mention_text and mention_text not in missing_entities[entity_id]['aliases']:
                    missing_entities[entity_id]['aliases'].append(mention_text)

    # 添加到知识库
    for entity_id, entity_info in missing_entities.items():
        kb_data['entities'].append(entity_info)

    print(f'恢复了 {len(missing_entities)} 个缺失实体')
    return kb_data, missing_entities


def fix_name_mismatches(kb_data, articles):
    """
    修复名称不匹配

    以标注数据为准，更新知识库中的标准名称
    """
    kb_entities = {e['entity_id']: e for e in kb_data['entities']}

    # 从标注数据中提取entity_id和standard_name的映射
    annotation_names = {}
    for article in articles:
        for mention in article.get('mentions', []):
            entity_id = mention.get('entity_id')
            standard_name = mention.get('standard_name', '')
            if entity_id and standard_name:
                if entity_id not in annotation_names:
                    annotation_names[entity_id] = standard_name

    # 修复不匹配的名称
    fixed_count = 0
    for entity_id, annotation_name in annotation_names.items():
        if entity_id in kb_entities:
            kb_name = kb_entities[entity_id]['standard_name']
            if kb_name != annotation_name:
                # 以标注数据为准
                kb_entities[entity_id]['standard_name'] = annotation_name
                fixed_count += 1

    print(f'修复了 {fixed_count} 个不匹配的名称')
    return kb_data


def fix_invalid_aliases(alias_data, kb_data):
    """
    修复无效别名

    删除指向不存在实体的别名
    """
    kb_entity_ids = {e['entity_id'] for e in kb_data['entities']}

    # 找出无效别名
    invalid_aliases = []
    for alias, info in alias_data.items():
        entity_id = info.get('entity_id')
        if entity_id not in kb_entity_ids:
            invalid_aliases.append(alias)

    # 删除无效别名
    for alias in invalid_aliases:
        del alias_data[alias]

    print(f'删除了 {len(invalid_aliases)} 个无效别名')
    return alias_data


def save_data(kb_data, alias_data, articles):
    """保存数据"""
    with open('Dataset/knowledge_base_merged.json', 'w', encoding='utf-8') as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)

    with open('Dataset/aliases_merged.json', 'w', encoding='utf-8') as f:
        json.dump(alias_data, f, ensure_ascii=False, indent=2)

    print('数据已保存')


def main():
    """主函数"""
    print('=' * 70)
    print('数据集修复')
    print('=' * 70)

    # 加载数据
    print('\n[1/5] 加载数据...')
    kb_data, articles, alias_data = load_data()
    kb_count = len(kb_data['entities'])
    alias_count = len(alias_data)
    print(f'  知识库实体数: {kb_count}')
    print(f'  文章数: {len(articles)}')
    print(f'  别名数: {alias_count}')

    # 修复缺失的实体
    print('\n[2/5] 修复缺失的实体...')
    kb_data, missing_entities = fix_missing_entities(kb_data, articles)

    # 修复不匹配的名称
    print('\n[3/5] 修复不匹配的名称...')
    kb_data = fix_name_mismatches(kb_data, articles)

    # 修复无效别名
    print('\n[4/5] 修复无效别名...')
    alias_data = fix_invalid_aliases(alias_data, kb_data)

    # 保存数据
    print('\n[5/5] 保存数据...')
    save_data(kb_data, alias_data, articles)

    # 统计
    kb_count_new = len(kb_data['entities'])
    alias_count_new = len(alias_data)
    missing_count = len(missing_entities)

    print('\n' + '=' * 70)
    print('修复完成')
    print('=' * 70)
    print(f'知识库实体数: {kb_count} -> {kb_count_new}')
    print(f'别名数: {alias_count} -> {alias_count_new}')
    print(f'恢复的实体数: {missing_count}')


if __name__ == "__main__":
    main()
