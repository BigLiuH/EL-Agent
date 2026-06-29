"""
使用LLM判断实体关系

找出可能重复的实体对，让LLM判断是否应该合并。
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_kb():
    """加载知识库"""
    with open('Dataset/knowledge_base_merged.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def find_similar_entity_pairs(kb_data, max_pairs=100):
    """
    找出可能重复的实体对

    策略：
    1. 名称包含关系
    2. 名称相似度高
    """
    entities = kb_data['entities']
    pairs = []
    processed = set()

    for i, e1 in enumerate(entities):
        name1 = e1['standard_name']
        type1 = e1['entity_type']

        for j, e2 in enumerate(entities[i+1:], i+1):
            if j in processed:
                continue

            name2 = e2['standard_name']
            type2 = e2['entity_type']

            # 只处理同类型实体
            if type1 != type2:
                continue

            # 名称包含关系
            if name1 in name2 or name2 in name1:
                # 长度差异不超过6个字符
                if abs(len(name1) - len(name2)) <= 6:
                    pairs.append({
                        'entity1': {
                            'id': e1['entity_id'],
                            'name': name1,
                            'type': type1,
                            'description': e1.get('description', '')[:200]
                        },
                        'entity2': {
                            'id': e2['entity_id'],
                            'name': name2,
                            'type': type2,
                            'description': e2.get('description', '')[:200]
                        }
                    })
                    processed.add(j)

                    if len(pairs) >= max_pairs:
                        return pairs

    return pairs


def generate_llm_prompt(entity_pair):
    """生成LLM提示"""
    e1 = entity_pair['entity1']
    e2 = entity_pair['entity2']

    prompt = f"""请判断以下两个实体是否应该合并为同一个实体：

实体1:
- ID: {e1['id']}
- 名称: {e1['name']}
- 类型: {e1['type']}
- 描述: {e1['description']}

实体2:
- ID: {e2['id']}
- 名称: {e2['name']}
- 类型: {e2['type']}
- 描述: {e2['description']}

请根据以下标准判断：
1. 如果两个实体指的是同一个事物（如"美国"和"美利坚合众国"），应该合并
2. 如果两个实体是包含关系但指不同事物（如"浙江省"和"浙江省羽毛球队"），不应该合并
3. 如果两个实体是同一事物的不同方面（如"李宁公司"和"李宁品牌"），需要具体分析

请用JSON格式回答：
{{
    "should_merge": true/false,
    "reason": "判断理由",
    "preferred_entity": "entity1的ID或entity2的ID，表示应该保留哪个实体"
}}"""

    return prompt


def parse_llm_response(response):
    """解析LLM响应"""
    try:
        # 尝试提取JSON
        import re
        json_match = re.search(r'\{[^{}]*\}', response)
        if json_match:
            result = json.loads(json_match.group())
            return {
                'should_merge': result.get('should_merge', False),
                'reason': result.get('reason', ''),
                'preferred_entity': result.get('preferred_entity', '')
            }
    except:
        pass

    # 默认返回
    return {
        'should_merge': False,
        'reason': '无法解析LLM响应',
        'preferred_entity': ''
    }


def save_pairs_for_review(pairs, output_path='data/entity_pairs_for_review.json'):
    """保存实体对供审核"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(pairs, f, ensure_ascii=False, indent=2)

    print(f"实体对已保存到: {output_path}")
    print(f"共 {len(pairs)} 对实体需要审核")
    return output_path


def main():
    """主函数"""
    print("=" * 70)
    print("使用LLM判断实体关系")
    print("=" * 70)

    # 加载知识库
    print("\n[1/3] 加载知识库...")
    kb_data = load_kb()
    print(f"  实体数: {len(kb_data['entities'])}")

    # 找出可能重复的实体对
    print("\n[2/3] 找出可能重复的实体对...")
    pairs = find_similar_entity_pairs(kb_data, max_pairs=100)
    print(f"  找到 {len(pairs)} 对可能重复的实体")

    # 显示前10对
    print("\n前10对实体:")
    for i, pair in enumerate(pairs[:10]):
        e1 = pair['entity1']
        e2 = pair['entity2']
        print(f"  {i+1}. {e1['name']} ({e1['id']}) <-> {e2['name']} ({e2['id']})")

    # 保存供审核
    print("\n[3/3] 保存实体对...")
    output_path = save_pairs_for_review(pairs)

    # 生成示例提示
    print("\n示例LLM提示:")
    print("-" * 70)
    print(generate_llm_prompt(pairs[0]))
    print("-" * 70)

    return output_path


if __name__ == "__main__":
    main()
