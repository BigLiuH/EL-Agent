"""
LLM判断合并候选

使用LLM判断哪些实体应该合并。
"""

import json
import sys
import time
import requests
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_candidates():
    """加载合并候选"""
    with open('data/merge_candidates.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_prompt(candidate):
    """生成LLM提示"""
    mention = candidate['mention']
    entities = candidate['entities']

    # 构建实体描述
    entity_descriptions = []
    for i, entity in enumerate(entities[:3]):  # 最多3个实体
        desc = f"实体{i+1}: {entity['standard_name']} ({entity['entity_id']})"
        desc += f"\n  类型: {entity['entity_type']}"
        if entity.get('description'):
            desc += f"\n  描述: {entity['description'][:100]}"
        entity_descriptions.append(desc)

    prompt = f"""请判断以下实体是否应该合并为同一个实体：

提及: {mention}

{chr(10).join(entity_descriptions)}

判断标准：
1. 如果这些实体指的是同一事物（如"宁夏"和"宁夏回族自治区"），应该合并
2. 如果这些实体是同一事物的不同方面（如"李宁公司"和"李宁品牌"），需要具体分析
3. 如果这些实体是不同的事物，不应该合并

请用JSON格式回答，不要有其他内容：
{{"should_merge": true/false, "keep_id": "保留哪个实体的ID", "reason": "判断理由"}}"""

    return prompt


def call_llm_api(prompt, api_base, api_key, model):
    """调用LLM API"""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key
    }

    prompt_with_instruction = prompt + "\n\n注意：不要思考过程，直接给出JSON结果。"

    data = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt_with_instruction}
        ],
        "temperature": 0.1,
        "max_tokens": 200
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


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="LLM判断合并候选")
    parser.add_argument("--api-base", default="https://token-plan-cn.xiaomimimo.com/anthropic", help="API地址")
    parser.add_argument("--api-key", default="tp-cf14mbl352izebb9pig1jk1wubevaxp35mfqnoy18kdzjf9n", help="API密钥")
    parser.add_argument("--model", default="mimo-v2.5", help="模型名称")
    parser.add_argument("--max-candidates", type=int, default=100, help="最大处理数量")

    args = parser.parse_args()

    print("=" * 70)
    print("LLM判断合并候选")
    print("=" * 70)

    # 加载候选
    print("\n[1/3] 加载合并候选...")
    candidates = load_candidates()
    candidates = candidates[:args.max_candidates]
    print(f"  处理 {len(candidates)} 个候选")

    # 逐个判断
    print("\n[2/3] 调用LLM判断...")
    decisions = []

    for i, candidate in enumerate(candidates):
        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{len(candidates)}")

        # 生成提示
        prompt = generate_prompt(candidate)

        # 调用LLM
        response = call_llm_api(prompt, args.api_base, args.api_key, args.model)

        if response:
            # 解析响应
            decision = parse_response(response)
            decision['candidate'] = candidate
            decisions.append(decision)

        # 避免API限流
        time.sleep(0.5)

    # 统计结果
    merge_count = sum(1 for d in decisions if d.get('should_merge', False))
    print(f"\n[3/3] 统计结果:")
    print(f"  处理总数: {len(decisions)}")
    print(f"  应该合并: {merge_count}")
    print(f"  不应该合并: {len(decisions) - merge_count}")

    # 保存结果
    output_path = 'data/merge_decisions.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(decisions, f, ensure_ascii=False, indent=2)

    print(f"\n判断结果已保存到: {output_path}")

    # 显示应该合并的示例
    print("\n应该合并的示例:")
    for d in decisions:
        if d.get('should_merge', False):
            candidate = d['candidate']
            print(f"  {candidate['mention']} -> {d['keep_id']}")
            print(f"    理由: {d['reason']}")
            if len([x for x in decisions if x.get('should_merge', False)]) > 5:
                break

    return decisions


if __name__ == "__main__":
    main()
