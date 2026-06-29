"""
合并地名简称/全称实体脚本

将地名简称合并到全称，如：安徽 -> 安徽省
"""

import json
import shutil
import os
from datetime import datetime


def backup():
    """备份三个数据文件"""
    backup_dir = f'Dataset/backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    os.makedirs(backup_dir, exist_ok=True)
    shutil.copy('Dataset/knowledge_base_merged.json', f'{backup_dir}/knowledge_base_merged.json')
    shutil.copy('Dataset/aliases_merged.json', f'{backup_dir}/aliases_merged.json')
    shutil.copy('Dataset/llm_extracted_merged.json', f'{backup_dir}/llm_extracted_merged.json')
    print(f'备份完成: {backup_dir}')
    return backup_dir


def merge():
    """执行合并"""
    # 加载数据
    with open('Dataset/knowledge_base_merged.json', 'r', encoding='utf-8') as f:
        kb_data = json.load(f)
    with open('Dataset/aliases_merged.json', 'r', encoding='utf-8') as f:
        alias_data = json.load(f)
    with open('Dataset/llm_extracted_merged.json', 'r', encoding='utf-8') as f:
        articles = json.load(f)

    name_to_entity = {e['standard_name']: e for e in kb_data['entities']}

    # 要合并的实体对
    merge_pairs = [
        ('安徽', '安徽省'), ('东莞', '东莞市'), ('广州', '广州市'),
        ('吉林', '吉林省'), ('山西', '山西省'), ('海南', '海南省'),
        ('贵州', '贵州省'), ('黑龙江', '黑龙江省'), ('沈阳', '沈阳市'),
        ('郑州', '郑州市'), ('长沙', '长沙市'), ('长春', '长春市'),
        ('青岛', '青岛市'), ('苏州', '苏州市'), ('贵阳', '贵阳市'),
        ('哈尔滨', '哈尔滨市'), ('厦门', '厦门市'), ('日照', '日照市'),
        ('武威', '武威市'), ('马鞍山', '马鞍山市'),
        ('宝山', '宝山区'), ('静安', '静安区'), ('黄浦', '黄浦区'),
        ('东营', '东营市'), ('兰州', '兰州市'),
        ('纽约', '纽约市'), ('新昌', '新昌县'),
        ('香格里拉', '香格里拉镇'),
    ]

    total_fixed = 0
    for short_name, full_name in merge_pairs:
        remove_entity = name_to_entity.get(short_name)
        keep_entity = name_to_entity.get(full_name)

        if remove_entity and keep_entity:
            if remove_entity['entity_type'] == keep_entity['entity_type']:
                # 1. 更新知识库
                if short_name not in keep_entity.get('aliases', []):
                    keep_entity.setdefault('aliases', []).append(short_name)
                for alias in remove_entity.get('aliases', []):
                    if alias not in keep_entity.get('aliases', []):
                        keep_entity['aliases'].append(alias)

                kb_data['entities'] = [e for e in kb_data['entities'] if e['entity_id'] != remove_entity['entity_id']]

                # 2. 更新别名文件
                for alias, info in alias_data.items():
                    if info['entity_id'] == remove_entity['entity_id']:
                        info['entity_id'] = keep_entity['entity_id']
                        info['standard_name'] = full_name

                # 3. 更新标注数据
                fixed = 0
                for article in articles:
                    for mention in article.get('mentions', []):
                        if mention.get('entity_id') == remove_entity['entity_id']:
                            mention['entity_id'] = keep_entity['entity_id']
                            mention['standard_name'] = full_name
                            fixed += 1

                total_fixed += fixed
                print(f'合并: {short_name} -> {full_name}, 修复标注: {fixed}')

    # 保存三个文件
    with open('Dataset/knowledge_base_merged.json', 'w', encoding='utf-8') as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)
    with open('Dataset/aliases_merged.json', 'w', encoding='utf-8') as f:
        json.dump(alias_data, f, ensure_ascii=False, indent=2)
    with open('Dataset/llm_extracted_merged.json', 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f'\n合并完成:')
    print(f'  合并实体对: {len(merge_pairs)}')
    print(f'  修复标注总数: {total_fixed}')
    print(f'  实体总数: {len(kb_data["entities"])}')


if __name__ == '__main__':
    backup()
    merge()
