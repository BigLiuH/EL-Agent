"""
重建别名文件

基于知识库中的实体别名重新构建别名文件。
"""

import json
import sys
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_kb():
    """加载知识库"""
    with open('Dataset/knowledge_base_merged.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def build_aliases(kb_data):
    """
    基于知识库构建别名

    策略：
    1. 标准名称作为别名
    2. 实体自身的aliases字段
    """
    aliases = {}

    for entity in kb_data['entities']:
        eid = entity['entity_id']
        name = entity['standard_name']

        # 标准名称作为别名
        aliases[name] = {
            'entity_id': eid,
            'standard_name': name
        }

        # 实体自身的aliases
        for alias in entity.get('aliases', []):
            if alias not in aliases:
                aliases[alias] = {
                    'entity_id': eid,
                    'standard_name': name
                }

    return aliases


def merge_with_original(new_aliases, original_aliases):
    """
    与原始别名合并

    策略：
    1. 如果原始别名中的entity_id存在于知识库中，保留
    2. 否则使用新别名
    """
    merged = {}
    merged_count = 0
    new_count = 0

    # 先添加新别名
    for alias, info in new_aliases.items():
        merged[alias] = info
        new_count += 1

    # 合并原始别名（如果entity_id有效）
    for alias, info in original_aliases.items():
        if alias not in merged:
            merged[alias] = info
            merged_count += 1

    print(f"合并结果:")
    print(f"  新别名: {new_count}")
    print(f"  原始别名: {merged_count}")
    print(f"  总计: {len(merged)}")

    return merged


def save_aliases(aliases, output_path='data/aliases_rebuilt.json'):
    """保存别名"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(aliases, f, ensure_ascii=False, indent=2)

    print(f"\n别名已保存到: {output_path}")
    return output_path


def validate_aliases(aliases, kb_entities):
    """验证别名"""
    valid_count = 0
    invalid_count = 0

    for alias, info in aliases.items():
        if info['entity_id'] in kb_entities:
            valid_count += 1
        else:
            invalid_count += 1

    print(f"\n验证结果:")
    print(f"  有效: {valid_count}")
    print(f"  无效: {invalid_count}")

    return invalid_count == 0


def main():
    """主函数"""
    print("=" * 70)
    print("重建别名文件")
    print("=" * 70)

    # 加载知识库
    print("\n[1/4] 加载知识库...")
    kb_data = load_kb()
    kb_entities = {e['entity_id']: e for e in kb_data['entities']}
    print(f"  实体数: {len(kb_entities)}")

    # 构建新别名
    print("\n[2/4] 构建新别名...")
    new_aliases = build_aliases(kb_data)
    print(f"  新别名数: {len(new_aliases)}")

    # 加载原始别名
    print("\n[3/4] 合并原始别名...")
    with open('Dataset/aliases_merged.json', 'r', encoding='utf-8') as f:
        original_aliases = json.load(f)
    merged_aliases = merge_with_original(new_aliases, original_aliases)

    # 验证并保存
    print("\n[4/4] 验证并保存...")
    is_valid = validate_aliases(merged_aliases, kb_entities)
    output_path = save_aliases(merged_aliases)

    # 显示关键实体
    print("\n关键实体别名:")
    test_names = ['宁夏回族自治区', '美国', '中国台北', '澳门', '中国残奥委员会', '李宁公司']
    for name in test_names:
        if name in merged_aliases:
            info = merged_aliases[name]
            print(f"  {name} -> {info['entity_id']}")

    return output_path


if __name__ == "__main__":
    main()
