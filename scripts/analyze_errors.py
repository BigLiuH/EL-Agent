"""
分析错误类型，区分全简称问题 vs 跨领域问题 vs 其他。
"""
import json
from collections import Counter

with open("data/all_errors.json", "r", encoding="utf-8") as f:
    errors = json.load(f)

print(f"总错误数: {len(errors)}\n")

# =============================================
# 1. 全简称问题：预期名和预测名存在包含关系
# =============================================
containment_errors = []
cross_sport_errors = []
year_variant_errors = []
other_errors = []

for e in errors:
    expected = e["expected_name"]
    predicted = e["predicted_name"]
    mention = e["mention"]

    # 名称包含关系（核心全简称信号）
    expected_in_predicted = expected in predicted or predicted in expected

    # 检查是否有共同"根"词（去除年份数字后比对）
    import re
    expected_clean = re.sub(r'\d{4}[年]?', '', expected).strip()
    predicted_clean = re.sub(r'\d{4}[年]?', '', predicted).strip()

    # 去年后是否有包含关系（年份前缀/后缀变体）
    year_variant = (expected_clean in predicted_clean or predicted_clean in expected_clean) \
                   and expected_clean != predicted_clean

    # 完全不同的实体名（无包含关系）→ 跨领域/跨项目
    completely_different = not expected_in_predicted and not year_variant

    if expected_in_predicted:
        # 纯全简称：一个名是另一个的子串
        if len(expected) < len(predicted):
            containment_errors.append({**e, "type": "简称→全称(预期短选长)"})
        else:
            containment_errors.append({**e, "type": "全称→简称(预期长选短)"})
    elif year_variant:
        # 年份变体
        year_variant_errors.append({**e, "type": "年份变体"})
    else:
        # 跨领域/跨项目
        cross_sport_errors.append({**e, "type": "跨项目混淆"})


print(f"=== 错误分类 ===")
print(f"全简称问题（名称包含关系）: {len(containment_errors)} ({len(containment_errors)/len(errors)*100:.1f}%)")
print(f"年份变体:                    {len(year_variant_errors)} ({len(year_variant_errors)/len(errors)*100:.1f}%)")
print(f"跨项目混淆:                  {len(cross_sport_errors)} ({len(cross_sport_errors)/len(errors)*100:.1f}%)")
print(f"其他:                        {len(other_errors)}")

# =============================================
# 2. 全简称问题细分
# =============================================
print(f"\n=== 全简称问题 Top 20 ===")
mention_counts = Counter(e["mention"] for e in containment_errors)
for mention, count in mention_counts.most_common(20):
    samples = [e for e in containment_errors if e["mention"] == mention]
    expected_names = set(e["expected_name"] for e in samples)
    predicted_names = set(e["predicted_name"] for e in samples)
    subtype = samples[0]["type"]
    print(f"  {mention} ({count}次) [{subtype}]")
    print(f"    预期: {expected_names}")
    print(f"    预测: {predicted_names}")

# =============================================
# 3. 跨项目混淆 Top 20
# =============================================
print(f"\n=== 跨项目混淆 Top 20 ===")
mention_counts = Counter(e["mention"] for e in cross_sport_errors)
for mention, count in mention_counts.most_common(20):
    samples = [e for e in cross_sport_errors if e["mention"] == mention]
    expected_names = set(e["expected_name"] for e in samples)
    predicted_names = set(e["predicted_name"] for e in samples)
    print(f"  {mention} ({count}次)")
    print(f"    预期: {expected_names}")
    print(f"    预测: {predicted_names}")

# =============================================
# 4. 年份变体 Top 20
# =============================================
print(f"\n=== 年份变体 Top 20 ===")
mention_counts = Counter(e["mention"] for e in year_variant_errors)
for mention, count in mention_counts.most_common(20):
    samples = [e for e in year_variant_errors if e["mention"] == mention]
    expected_names = set(e["expected_name"] for e in samples)
    predicted_names = set(e["predicted_name"] for e in samples)
    print(f"  {mention} ({count}次)")
    print(f"    预期: {expected_names}")
    print(f"    预测: {predicted_names}")

# =============================================
# 5. 总结
# =============================================
print(f"\n=== 总结 ===")
print(f"可通过实体合并修复的全简称: {len(containment_errors)} ({len(containment_errors)/len(errors)*100:.1f}%)")
print(f"可通过实体合并修复的年份变体: {len(year_variant_errors)} ({len(year_variant_errors)/len(errors)*100:.1f}%)")
print(f"合并可修复合计: {len(containment_errors) + len(year_variant_errors)} ({(len(containment_errors)+len(year_variant_errors))/len(errors)*100:.1f}%)")
print(f"需要其他手段的跨项目混淆: {len(cross_sport_errors)} ({len(cross_sport_errors)/len(errors)*100:.1f}%)")
