"""
实体合并脚本

使用三层漏斗策略合并冗余实体：
1. 规则筛选（快速，粗筛）
2. 相似度计算（中速，精筛）
3. LLM判断（慢速，精确）
"""

import json
import sys
import time
import requests
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_kb():
    """加载知识库"""
    with open('Dataset/knowledge_base_merged.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def layer1_rule_filter(entities):
    """
    第1层：规则筛选

    筛选条件：
    1. 必须是同一类型
    2. 名称有包含关系
    3. 长度差异不超过4个字符
    """
    print("第1层：规则筛选...")

    # 按类型分组
    type_groups = defaultdict(list)
    for entity in entities:
        type_groups[entity['entity_type']].append(entity)

    pairs = []

    for etype, group in type_groups.items():
        for i, e1 in enumerate(group):
            name1 = e1['standard_name']

            for e2 in group[i+1:]:
                name2 = e2['standard_name']

                # 名称包含关系
                if name1 in name2 or name2 in name1:
                    # 长度差异不超过4个字符
                    if abs(len(name1) - len(name2)) <= 4:
                        pairs.append({
                            'entity1': e1,
                            'entity2': e2,
                            'match_type': 'containment'
                        })

    print(f"  筛选前: {len(entities)} 个实体")
    print(f"  筛选后: {len(pairs)} 对可能重复")
    return pairs


def layer2_similarity_filter(pairs):
    """
    第2层：相似度计算

    使用编辑距离计算名称相似度
    """
    print("第2层：相似度计算...")

    filtered_pairs = []

    for pair in pairs:
        name1 = pair['entity1']['standard_name']
        name2 = pair['entity2']['standard_name']

        # 计算编辑距离相似度
        similarity = calculate_similarity(name1, name2)

        pair['similarity'] = similarity

        # 只保留相似度大于0.6的
        if similarity >= 0.6:
            filtered_pairs.append(pair)

    print(f"  筛选前: {len(pairs)} 对")
    print(f"  筛选后: {len(filtered_pairs)} 对 (相似度 >= 0.6)")
    return filtered_pairs


def calculate_similarity(s1, s2):
    """
    计算两个字符串的相似度

    使用编辑距离
    """
    if len(s1) == 0 or len(s2) == 0:
        return 0.0

    # 计算编辑距离
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i-1] == s2[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1]) + 1

    edit_distance = dp[m][n]
    max_len = max(m, n)

    return 1 - edit_distance / max_len


def layer3_llm_judge(pairs, api_base, api_key, model, max_pairs=200):
    """
    第3层：LLM判断

    使用LLM判断是否应该合并
    """
    print("第3层：LLM判断...")

    # 限制处理数量
    pairs = pairs[:max_pairs]
    print(f"  处理 {len(pairs)} 对实体")

    decisions = []

    for i, pair in enumerate(pairs):
        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{len(pairs)}")

        # 生成提示
        prompt = generate_prompt(pair)

        # 调用LLM
        response = call_llm_api(prompt, api_base, api_key, model)

        if response:
            # 解析响应
            decision = parse_response(response)
            decision['pair'] = pair

            decisions.append(decision)

            # 避免API限流
            time.sleep(0.5)

    # 统计结果
    merge_count = sum(1 for d in decisions if d.get('should_merge', False))
    print(f"  判断结果: {merge_count} 对应该合并, {len(decisions) - merge_count} 对保留")

    return decisions


def generate_prompt(pair):
    """生成LLM提示"""
    e1 = pair['entity1']
    e2 = pair['entity2']

    # 提取别名
    aliases1 = e1.get('aliases', [])
    aliases2 = e2.get('aliases', [])

    prompt = f"""请判断以下两个实体是否应该合并为同一个实体：

实体1:
- ID: {e1['entity_id']}
- 名称: {e1['standard_name']}
- 类型: {e1['entity_type']}
- 描述: {e1.get('description', '无')[:200]}
- 别名: {', '.join(aliases1[:5]) if aliases1 else '无'}

实体2:
- ID: {e2['entity_id']}
- 名称: {e2['standard_name']}
- 类型: {e2['entity_type']}
- 描述: {e2.get('description', '无')[:200]}
- 别名: {', '.join(aliases2[:5]) if aliases2 else '无'}

判断标准：
1. 如果两个实体指的是同一事物（如"美国"和"美利坚合众国"），应该合并
2. 如果两个实体是同一人名的中英文（如"周天成"和"Chou Tien-chen"），应该合并
3. 如果两个实体是包含关系但指不同事物（如"浙江省"和"浙江省羽毛球队"），不应该合并
4. 如果两个实体是同一事物的不同方面（如"李宁公司"和"李宁品牌"），需要具体分析

请用JSON格式回答，不要有其他内容：
{{"should_merge": true/false, "keep_id": "保留哪个实体的ID", "reason": "判断理由"}}"""

    return prompt


def call_llm_api(prompt, api_base, api_key, model):
    """调用LLM API"""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key
    }

    # 在prompt末尾添加"不要思考，直接给出JSON结果"
    prompt_with_instruction = prompt + "\n\n注意：不要思考过程，直接给出JSON结果。"

    data = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt_with_instruction}
        ],
        "temperature": 0.1,
        "max_tokens": 200  # 减小token数，强制直接输出
    }

    try:
        endpoint = f"{api_base}/v1/messages"
        response = requests.post(
            endpoint,
            headers=headers,
            json=data,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            if 'content' in result:
                for content in result['content']:
                    if content.get('type') == 'text':
                        return content['text']
        return None
    except Exception as e:
        return None


def parse_response(response):
    """解析LLM响应"""
    import re

    try:
        # 尝试提取JSON
        json_match = re.search(r'\{[^{}]*\}', response)
        if json_match:
            result = json.loads(json_match.group())
            return {
                'should_merge': result.get('should_merge', False),
                'keep_id': result.get('keep_id', ''),
                'reason': result.get('reason', '')
            }
    except:
        pass

    return {
        'should_merge': False,
        'keep_id': '',
        'reason': '无法解析响应'
    }


def execute_merge(decisions, kb_data, alias_data):
    """
    执行合并

    根据LLM判断结果合并实体
    """
    print("执行合并...")

    entities = {e['entity_id']: e for e in kb_data['entities']}
    merge_map = {}  # old_id -> new_id
    merged_count = 0

    for decision in decisions:
        if not decision.get('should_merge', False):
            continue

        pair = decision['pair']
        keep_id = decision.get('keep_id', '')

        # 确定保留哪个实体
        e1_id = pair['entity1']['entity_id']
        e2_id = pair['entity2']['entity_id']

        if keep_id == e1_id:
            remove_id = e2_id
        elif keep_id == e2_id:
            remove_id = e1_id
        else:
            # 默认保留第一个
            keep_id = e1_id
            remove_id = e2_id

        # 记录合并映射
        merge_map[remove_id] = keep_id
        merged_count += 1

    print(f"  合并映射: {merged_count} 对")

    # 应用合并
    new_entities = []
    removed_ids = set(merge_map.keys())

    for entity in kb_data['entities']:
        if entity['entity_id'] not in removed_ids:
            # 更新别名
            if entity['entity_id'] in merge_map.values():
                # 这是保留的实体，添加被合并实体的别名
                for old_id, new_id in merge_map.items():
                    if new_id == entity['entity_id']:
                        old_entity = entities.get(old_id)
                        if old_entity:
                            old_aliases = set(entity.get('aliases', []))
                            old_aliases.update(old_entity.get('aliases', []))
                            old_aliases.add(old_entity['standard_name'])
                            entity['aliases'] = list(old_aliases)

            new_entities.append(entity)

    # 更新别名数据
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

    print(f"  实体数: {len(kb_data['entities'])} -> {len(new_entities)}")
    print(f"  别名数: {len(alias_data)} -> {len(new_aliases)}")

    return {'entities': new_entities}, new_aliases, merge_map


def save_merged_data(kb_data, alias_data, merge_map, output_dir='data/merged'):
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

    # 保存合并映射
    map_path = output_path / 'merge_map.json'
    with open(map_path, 'w', encoding='utf-8') as f:
        json.dump(merge_map, f, ensure_ascii=False, indent=2)

    print(f"\n数据已保存到:")
    print(f"  {kb_path}")
    print(f"  {alias_path}")
    print(f"  {map_path}")

    return str(kb_path), str(alias_path)


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="合并冗余实体")
    parser.add_argument("--api-base", default="https://token-plan-cn.xiaomimimo.com/anthropic", help="API地址")
    parser.add_argument("--api-key", default="tp-cf14mbl352izebb9pig1jk1wubevaxp35mfqnoy18kdzjf9n", help="API密钥")
    parser.add_argument("--model", default="mimo-v2.5", help="模型名称")
    parser.add_argument("--max-pairs", type=int, default=200, help="最大处理对数")
    parser.add_argument("--dry-run", action="store_true", help="只分析不执行")

    args = parser.parse_args()

    print("=" * 70)
    print("实体合并脚本")
    print("=" * 70)

    # 加载知识库
    print("\n[1/5] 加载知识库...")
    kb_data = load_kb()

    with open('Dataset/aliases_merged.json', 'r', encoding='utf-8') as f:
        alias_data = json.load(f)

    print(f"  实体数: {len(kb_data['entities'])}")
    print(f"  别名数: {len(alias_data)}")

    # 第1层：规则筛选
    print("\n[2/5] 第1层：规则筛选...")
    pairs = layer1_rule_filter(kb_data['entities'])

    # 第2层：相似度计算
    print("\n[3/5] 第2层：相似度计算...")
    pairs = layer2_similarity_filter(pairs)

    # 第3层：LLM判断
    print("\n[4/5] 第3层：LLM判断...")
    decisions = layer3_llm_judge(
        pairs,
        args.api_base,
        args.api_key,
        args.model,
        args.max_pairs
    )

    # 执行合并
    if not args.dry_run:
        print("\n[5/5] 执行合并...")
        kb_data, alias_data, merge_map = execute_merge(decisions, kb_data, alias_data)

        # 保存数据
        kb_path, alias_path = save_merged_data(kb_data, alias_data, merge_map)

        print("\n合并完成！")
        print(f"请更新配置使用合并后的数据，然后重新评测。")
    else:
        print("\n[5/5] 干运行模式，不执行合并")

        # 显示应该合并的实体对
        merge_decisions = [d for d in decisions if d.get('should_merge', False)]
        print(f"\n应该合并的实体对 ({len(merge_decisions)} 对):")
        for d in merge_decisions[:20]:
            pair = d['pair']
            print(f"  {pair['entity1']['standard_name']} <-> {pair['entity2']['standard_name']}")
            print(f"    理由: {d.get('reason', '')}")

    return decisions


if __name__ == "__main__":
    main()
