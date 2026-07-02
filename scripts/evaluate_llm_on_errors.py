"""
LLM消歧能力评测

对规则消歧失败的 194 个样本，用 LLM 重新判断。
对比 LLM 准确率 vs 规则准确率。

用法:
  python scripts/evaluate_llm_on_errors.py                      # 不调LLM，只看样本
  python scripts/evaluate_llm_on_errors.py --enable-llm          # 调LLM评测
  python scripts/evaluate_llm_on_errors.py --enable-llm --max 50 # 跑50条
"""
import json
import sys
import time
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.llm_disambiguator import llm_disambiguator


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-llm", action="store_true", help="调用LLM评测")
    parser.add_argument("--max", type=int, default=0, help="最多跑N条")
    args = parser.parse_args()

    with open("data/llm_test_samples.json", "r", encoding="utf-8") as f:
        samples = json.load(f)

    if args.max:
        samples = samples[:args.max]

    print(f"=== LLM消歧能力评测 ===")
    print(f"样本数: {len(samples)}")
    print(f"规则消歧准确率: 0% (全部是规则错题)\n")

    # 按gap分组
    from collections import Counter
    gaps = Counter()
    for s in samples:
        g = s["gap"]
        if g < 0.005: gaps["<0.005"] += 1
        elif g < 0.01: gaps["0.005-0.01"] += 1
        elif g < 0.02: gaps["0.01-0.02"] += 1
        elif g < 0.03: gaps["0.02-0.03"] += 1
        else: gaps[">=0.03"] += 1

    print("gap分布:")
    for k, v in gaps.most_common():
        print(f"  {k}: {v}")
    print()

    # 展示样本
    print("=== 样本预览(前10) ===")
    for s in samples[:10]:
        print(f"  mention='{s['mention']}'")
        print(f"    预期: {s['expected_name']} ({s['expected_id']})")
        print(f"    预测: {s['predicted_name']} ({s['predicted_id']})")
        print(f"    gap: {s['gap']}")
        for c in s['candidates']:
            tag = " ← 预期" if c['id'] == s['expected_id'] else " ← 错" if c['id'] == s['predicted_id'] else ""
            print(f"       {c['name']} ({c['id']}) score={c['score']}{tag}")
        print()

    # LLM评测
    if args.enable_llm:
        if not llm_disambiguator.available:
            print("LLM不可用，跳过")
            return

        print(f"\n=== LLM消歧评测 ===")
        correct = 0
        total = 0
        for i, s in enumerate(samples):
            mention_text = s['mention']
            context = s['context']

            # 构造候选
            prompt = f"根据文章语境，\"{mention_text}\"最可能是以下哪个实体？只回复entity_id。\n\n文章：{context}\n\n候选：\n"
            for j, c in enumerate(s['candidates']):
                prompt += f"{j+1}. ID={c['id']} 名称={c['name']}\n"

            total += 1
            try:
                response = llm_disambiguator._call_with_retry(
                    [{"role": "user", "content": prompt}], max_tokens=20)
                if response:
                    result = llm_disambiguator._parse_response(
                        response.choices[0].message.content)
                    predicted = result.get("entity_id") if result else None
                else:
                    predicted = None

                if predicted == s['expected_id']:
                    correct += 1
                    status = "✓"
                else:
                    status = f"✗ (pred={predicted})"
            except Exception as e:
                status = f"✗ (err={e})"

            if i < 5:
                print(f"  {i+1}. {mention_text} -> {status}")

            time.sleep(0.5)

        print(f"\nLLM准确率: {correct}/{total} = {correct/max(total,1)*100:.1f}%")
        print(f"规则准确率: 0% (全部是规则错题)")


if __name__ == "__main__":
    main()
