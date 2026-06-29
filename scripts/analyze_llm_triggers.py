"""
分析有多少 mention 会触发 LLM 消歧（top-2 得分差 < 0.1）
"""
import json
import sys
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.knowledge_base import knowledge_base
from elagent.core.bm25_index import bm25_index
from elagent.core.disambiguator import disambiguator
from elagent.models.mention import Mention
from elagent.models.entity import Candidate
from elagent.api.routes import _enhanced_link

# 加载知识库
print("加载知识库...")
knowledge_base.load()
bm25_index.build(knowledge_base.entities)

# 加载文章
articles_path = "Dataset/llm_extracted_merged.json"
with open(articles_path, "r", encoding="utf-8") as f:
    articles = json.load(f)

print(f"分析 {len(articles)} 篇文章...")

total_mentions = 0
multi_cand_count = 0
llm_trigger_count = 0
gap_distribution = Counter()
trigger_examples = []

for art_idx, article in enumerate(articles):
    text = article.get("text", "")
    if art_idx % 200 == 0:
        print(f"  进度: {art_idx}/{len(articles)}")

    for mention_data in article.get("mentions", []):
        total_mentions += 1

        mention = Mention(
            text=mention_data["text"],
            start_pos=mention_data["start"],
            end_pos=mention_data["end"],
            entity_type=mention_data.get("entity_type"),
            context=text,
        )

        # 别名匹配获取候选
        alias_entities = knowledge_base.search_by_alias(mention.text)
        if not alias_entities:
            # 也尝试标准名称
            e = knowledge_base.get_entity_by_name(mention.text)
            if e:
                alias_entities = [e]

        if len(alias_entities) < 2:
            # 也检查模糊匹配
            fuzzy = []
            for e in knowledge_base.entities.values():
                if mention.text in e.standard_name and len(e.standard_name) - len(mention.text) <= 8:
                    fuzzy.append(e)
                elif e.standard_name in mention.text and len(mention.text) - len(e.standard_name) <= 8:
                    fuzzy.append(e)
            seen = {e.id for e in alias_entities}
            for e in fuzzy:
                if e.id not in seen:
                    alias_entities.append(e)
                    seen.add(e.id)

        if len(alias_entities) >= 2:
            multi_cand_count += 1
            candidates = [Candidate(entity=e, score=0.95, match_source="alias") for e in alias_entities]
            ranked = disambiguator.disambiguate(mention, candidates, top_k=5, full_text=text)

            if len(ranked) >= 2:
                gap = ranked[0].score - ranked[1].score
                # 分桶: <0.05, 0.05-0.1, 0.1-0.15, 0.15-0.2, >=0.2
                if gap < 0.05:
                    bucket = "<0.05"
                elif gap < 0.1:
                    bucket = "0.05-0.1"
                elif gap < 0.15:
                    bucket = "0.1-0.15"
                elif gap < 0.2:
                    bucket = "0.15-0.2"
                else:
                    bucket = ">=0.2"
                gap_distribution[bucket] += 1

                if gap < 0.1:
                    llm_trigger_count += 1
                    if len(trigger_examples) < 5:
                        trigger_examples.append({
                            "mention": mention.text,
                            "top1": f"{ranked[0].entity.standard_name} ({ranked[0].score:.3f})",
                            "top2": f"{ranked[1].entity.standard_name} ({ranked[1].score:.3f})",
                            "gap": f"{gap:.3f}",
                        })

print(f"\n=== 统计 ===")
print(f"总 mention 数: {total_mentions}")
print(f"多候选 case 数: {multi_cand_count}")
print(f"score gap < 0.1 (触发LLM): {llm_trigger_count} ({llm_trigger_count/max(multi_cand_count,1)*100:.1f}%)")

print(f"\n=== 得分差分布 ===")
for bucket in ["<0.05", "0.05-0.1", "0.1-0.15", "0.15-0.2", ">=0.2"]:
    count = gap_distribution.get(bucket, 0)
    pct = count / max(multi_cand_count, 1) * 100
    bar = "#" * int(pct / 2)
    print(f"  {bucket}: {count:5d} ({pct:5.1f}%) {bar}")

print(f"\n=== 触发示例 ===")
for ex in trigger_examples:
    print(f"  mention='{ex['mention']}' top1={ex['top1']} top2={ex['top2']} gap={ex['gap']}")

print(f"\n=== 结论 ===")
print(f"LLM 最多调用 {llm_trigger_count} 次 (当前 max_calls=500)")
if llm_trigger_count > 500:
    print(f"建议: 增加 max_calls 到 {llm_trigger_count}")
