"""
使用LLM API自动判断实体对

自动调用大模型API判断实体是否应该合并。
"""

import json
import sys
import time
import requests
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_pairs():
    """加载实体对"""
    with open('data/entity_pairs_for_review.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def generate_prompt(entity_pair):
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

判断标准：
1. 如果两个实体指的是同一个事物（如"美国"和"美利坚合众国"），应该合并
2. 如果两个实体是包含关系但指不同事物（如"浙江省"和"浙江省羽毛球队"），不应该合并
3. 如果两个实体是同一事物的不同方面（如"李宁公司"和"李宁品牌"），需要具体分析

请用JSON格式回答，不要思考过程，直接给出结果：
{{"should_merge": true/false, "reason": "判断理由", "preferred_entity": "entity1的ID或entity2的ID"}}"""

    return prompt


def call_llm_api(prompt, api_base, api_key, model):
    """调用LLM API"""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key
    }

    data = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,  # 低温度，确保结果稳定
        "max_tokens": 500
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
            # 处理Anthropic响应格式
            if 'content' in result:
                for content in result['content']:
                    if content.get('type') == 'text':
                        return content['text']
            return None
        else:
            print(f"API错误: {response.status_code}")
            return None
    except Exception as e:
        print(f"API调用失败: {e}")
        return None


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


def save_decisions(decisions, output_path='data/entity_merge_decisions.json'):
    """保存判断结果"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(decisions, f, ensure_ascii=False, indent=2)

    print(f"\n判断结果已保存到: {output_path}")
    return output_path


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="使用LLM判断实体对")
    parser.add_argument("--api-base", default="https://token-plan-cn.xiaomimimo.com/anthropic", help="API地址")
    parser.add_argument("--api-key", default="tp-cf14mbl352izebb9pig1jk1wubevaxp35mfqnoy18kdzjf9n", help="API密钥")
    parser.add_argument("--model", default="mimo-v2.5", help="模型名称")
    parser.add_argument("--max-pairs", type=int, default=50, help="最大处理对数")

    args = parser.parse_args()

    print("=" * 70)
    print("使用LLM自动判断实体对")
    print("=" * 70)

    # 加载实体对
    print("\n[1/3] 加载实体对...")
    pairs = load_pairs()
    pairs = pairs[:args.max_pairs]  # 限制数量
    print(f"  处理 {len(pairs)} 对实体")

    # 逐个判断
    print("\n[2/3] 调用LLM判断...")
    decisions = []

    for i, pair in enumerate(pairs):
        print(f"\n处理 {i+1}/{len(pairs)}: {pair['entity1']['name']} <-> {pair['entity2']['name']}")

        # 生成提示
        prompt = generate_prompt(pair)

        # 调用API
        response = call_llm_api(prompt, args.api_base, args.api_key, args.model)

        if response:
            # 解析响应
            decision = parse_llm_response(response)
            decision['pair_index'] = i
            decision['entity1'] = pair['entity1']
            decision['entity2'] = pair['entity2']

            if decision['should_merge']:
                decision['action'] = 'merge'
                decision['keep_entity'] = decision['preferred_entity']
            else:
                decision['action'] = 'keep_both'
                decision['keep_entity'] = None

            decisions.append(decision)

            print(f"  结果: {'合并' if decision['should_merge'] else '保留'}")
            print(f"  理由: {decision['reason']}")

        # 避免API限流
        time.sleep(1)

    # 保存结果
    print("\n[3/3] 保存结果...")
    if decisions:
        output_path = save_decisions(decisions)

        # 统计
        merge_count = sum(1 for d in decisions if d.get('should_merge', False))
        keep_count = sum(1 for d in decisions if not d.get('should_merge', False))

        print(f"\n统计:")
        print(f"  处理总数: {len(decisions)}")
        print(f"  合并: {merge_count}")
        print(f"  保留: {keep_count}")

    return decisions


if __name__ == "__main__":
    main()
