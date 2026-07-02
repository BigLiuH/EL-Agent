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
        # ('2026年全国游泳冠军赛', '全国游泳冠军赛'),('中国台北','中国台湾地区'),
        # ('全运会', '全国运动会'),('长三角','长江三角洲地区'),('台湾','中国台湾地区'),('香港','中国香港特别行政区'),('澳门','中国澳门特别行政区'),
        # ("Chou Tien-chen","周天成"),
        # ('中国残奥委员会', '中国残疾人奥林匹克委员会'),
        # ('温布尔登网球锦标赛', '2024年温布尔登网球锦标赛'),
        # ('东京', '东京都'),
        # ('北京国家奥林匹克体育中心体育馆', '国家奥林匹克体育中心体育馆'),
        # ('首钢花滑馆', '首钢花样滑冰馆'),
        # ('2026年澳门羽毛球公开赛', '澳门羽毛球公开赛'),
        # ('中国羽毛球协会（中国羽毛球队）', '中国国家羽毛球队'),
        # ('萨格勒布常规赛', 'WTT萨格勒布常规赛'),
        # ('WTT中国大满贯2025', '2025年中国大满贯'),
        # ('新加坡大满贯', 'WTT新加坡大满贯'),
        # ('World Table Tennis（世界乒乓球职业大联盟）', '世界乒乓球职业大联盟'),
        # ('名古屋亚运会', '2026年名古屋亚运会'),
        # ('李宁体育用品有限公司', '李宁（中国）体育用品有限公司'),
        # ('World Table Tennis', '世界乒乓球职业大联盟'),
        # ('澳门羽毛球公开赛', '2026澳门羽毛球公开赛'),
        # ('2026年爱知·名古屋亚运会', '2026年名古屋亚运会'),
        # ('澳大利亚羽毛球公开赛', '2026年澳大利亚羽毛球公开赛'),
        # ('2026澳大利亚羽毛球公开赛', '2026年澳大利亚羽毛球公开赛'),
        # ('2026 Australian Badminton Open', '2026年澳大利亚羽毛球公开赛'),
        # ('小波波夫', '波波夫'),
        # ('意大利', '意大利共和国'),
        # ('2026年澳大利亚公开赛', '2026年澳大利亚羽毛球公开赛'),
        # ('超级500赛', 'BWF世界巡回赛超级500'),
        # ('世界羽联巡回赛超级500赛事', 'BWF世界巡回赛超级500'),
        # ('世界羽联超级500赛', 'BWF世界巡回赛超级500'),
        # ('BWF', '国际羽毛球联合会'),
        # ('羽毛球超级300赛', '羽毛球世界巡回赛超级300赛'),
        # ('中国澳门羽毛球公开赛', '澳门羽毛球公开赛'),
        # ('天祝县', '天祝藏族自治县'),
        # ("Ja'Kobe Tharp", '贾科比·萨普'),
        # ('Adaejah Hodge', '阿达贾·霍奇'),
        # ('University of Florida', '佛罗里达大学'),
        # ('Louisiana State University', '路易斯安那州立大学'),
        # ('香港100', '香港100越野赛'),
        # ('UTMB', '环勃朗峰超级越野赛'),
        # ('NCAA', '美国大学体育协会'),
        # ('中国台北地区', '中国台湾地区'),
        # ('中国台湾省', '中国台湾地区'),
        # ('中国台湾（中国台北）', '中国台湾地区'),
        # ('台湾省', '中国台湾地区'),
        # ('中国台湾', '中国台湾地区'),
        # ('成都大运会', '2021年成都世界大学生夏季运动会'),
        # ('博捷体育', '四川博捷体育文化传播有限公司'),
        # ('乐刻', '乐刻运动'),
        # ('浙江绍兴', '绍兴市'),
        # ('绍兴上虞', '绍兴市上虞区'),
        # ('罗马钻石联赛', '2026年罗马钻石联赛'),
        # ('广西', '广西壮族自治区'),
        # ('世界泳联', '国际游泳联合会'),
        # ('世界游泳联合会', '国际游泳联合会'),
        # ('里约奥运会', '2016年里约奥运会'),
        # ('2016年里约热内卢奥运会', '2016年里约奥运会'),
        # ('2016年里约热内卢夏季奥运会', '2016年里约奥运会'),
        # ('凯特-道格拉斯', '凯特·道格拉斯'),
        # ('杭州亚运会', '2022年杭州亚运会'),
        # ('2023年杭州亚运会', '2022年杭州亚运会'),
        # ('杭州亚洲运动会', '2022年杭州亚运会'),
        # ('洛杉矶奥运会', '2028年洛杉矶夏季奥运会'),
        # ('伦敦奥运会', '2012年伦敦奥运会'),
        # ('2012年伦敦夏季奥运会', '2012年伦敦奥运会'),
        # ('2012年伦敦夏季奥林匹克运动会', '2012年伦敦奥运会'),
        # ('全国冠军赛', '全国游泳冠军赛'),
        # ('名古屋亚运会', '2026年名古屋亚运会'),
        # ('2026年名古屋亚洲运动会', '2026年名古屋亚运会'),
        # ('2026年爱知-名古屋亚洲运动会', '2026年名古屋亚运会'),
        # ('2026年爱知-名古屋亚运会', '2026年名古屋亚运会'),
        # ('银川站', '银川高铁站'),('澳门羽毛球公开赛', '2026年中国澳门羽毛球公开赛'),
        # ('泰国羽毛球公开赛', '2026年泰国羽毛球公开赛'),('', ''),
        # ('2026中国澳门羽毛球公开赛', '2026年中国澳门羽毛球公开赛'),('Fubo', 'Fubo TV'),
        #('斯诺克冠中冠','斯诺克冠中冠赛'),('冠中冠','斯诺克冠中冠赛'),
        # ('田口真彩（Taguchi Maya）','田口真彩'),('渡边勇大（Watanabe Yuta）','渡边勇大'),
        # ('蒂亚布迪（Setiadi 或类似拼写，文中未明确）','塞蒂亚布迪'),
        # ('世界乒乓球职业大联盟 (WTT)','世界乒乓球职业大联盟'),
        # ('多哈世界乒乓球锦标赛','多哈世乒赛'),
        # ('斯诺克冠军联赛（排名赛版）','2026年斯诺克排名赛版冠军联赛'),
        # ('China Open','中国斯诺克公开赛'),
        # ('萨格勒布常规挑战赛','WTT萨格勒布常规挑战赛'),
        # ('杨雅婷（Yeung Nga Ting）','杨雅婷'),
        # ('塞蒂亚布迪（Setiadi 或类似拼写，文中未明确）','塞蒂亚布迪'),
        
        ('2026年亚洲运动会','2026年名古屋亚运会'),
        ('美国女子篮球协会','美国女子职业篮球联赛'),
        ('WNBA','浙江省游美国女子职业篮球联赛泳队'),
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
