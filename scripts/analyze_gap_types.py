"""
分析消歧错误中 top-1 vs top-2 的得分差异模式
"""
import json, sys
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.knowledge_base import knowledge_base
from elagent.core.disambiguator import disambiguator
from elagent.models.mention import Mention
from elagent.models.entity import Candidate

knowledge_base.load()

with open("Dataset/llm_extracted_merged.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

# 分析多候选 case 的得分模式
gap_types = Counter()
examples = {k: [] for k in ["name_tie_prior_wrong", "short_beats_long", "long_beats_short",
                              "year_prefix", "cross_sport", "other"]}

for art in articles[:500]:  # 采样500篇
    text = art.get("text", "")
    for m in art.get("mentions", []):
        mention = Mention(text=m["text"], start_pos=m["start"], end_pos=m["end"],
                         entity_type=m.get("entity_type"), context=text)
        expected = m.get("standard_name", "")

        # 召回
        alias_entities = knowledge_base.search_by_alias(mention.text)
        if not alias_entities:
            e = knowledge_base.get_entity_by_name(mention.text)
            alias_entities = [e] if e else []
        if len(alias_entities) < 2:
            continue

        candidates = [Candidate(entity=e, score=0.95, match_source="alias") for e in alias_entities]
        ranked = disambiguator.disambiguate(mention, candidates, top_k=2, full_text=text)
        if len(ranked) < 2:
            continue

        top1, top2 = ranked[0], ranked[1]
        gap = top1.score - top2.score
        top1_name = disambiguator._name_match_score(mention, top1.entity)
        top2_name = disambiguator._name_match_score(mention, top2.entity)
        top1_prior = disambiguator._prior_probability_score(top1.entity)
        top2_prior = disambiguator._prior_probability_score(top2.entity)
        top1_comp = disambiguator._name_completeness_score(mention, top1.entity)
        top2_comp = disambiguator._name_completeness_score(mention, top2.entity)

        top1_correct = (top1.entity.standard_name == expected)
        top2_correct = (top2.entity.standard_name == expected)
        error = not top1_correct

        # 分类
        name_tie = abs(top1_name - top2_name) < 0.02
        prior_reversed = (top1_prior > top2_prior and top2_correct) or (top2_prior > top1_prior and top1_correct)
        short_wins = len(top1.entity.standard_name) < len(top2.entity.standard_name) and top2_correct
        long_wins = len(top1.entity.standard_name) > len(top2.entity.standard_name) and top2_correct
        year_diff = (top1.entity.standard_name[:4].isdigit() != top2.entity.standard_name[:4].isdigit())

        if error and name_tie and prior_reversed:
            gap_types["name平_prior错判"] += 1
        elif error and short_wins:
            gap_types["短名胜长名(错)"] += 1
        elif error and long_wins:
            gap_types["长名胜短名(错)"] += 1
        elif error and year_diff:
            gap_types["年份变体混淆"] += 1
        elif error and name_tie:
            gap_types["name平_其他信号错"] += 1
        elif error:
            gap_types["name不平_其他信号错"] += 1
        else:
            gap_types["正确"] += 1

total = sum(gap_types.values())
print(f"总多候选样本: {total}\n")
print(f"{'类型':<25} {'数量':>6} {'占比':>8}")
print("-" * 40)
for k in ["正确", "name平_prior错判", "短名胜长名(错)", "长名胜短名(错)", "年份变体混淆", "name平_其他信号错", "name不平_其他信号错"]:
    c = gap_types.get(k, 0)
    print(f"{k:<25} {c:>6} {c/total*100:>7.1f}%")

print(f"\n=== 前两类详解 ===")
print(f"\n'name平_prior错判': mention的别名命中多个实体，name_match相同")
print(f"  先验概率高的实体胜出，但标注指向先验低的实体")
print(f"\n'name不平_其他信号错': name_match有明显差距")
print(f"  但标注指向name_match低的实体（可能是全称/简称问题）")
