"""
诊断：为什么上下文信号在具体错误上不生效
追踪完整链路：召回→候选→得分→最终选择
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.knowledge_base import knowledge_base
from elagent.core.disambiguator import disambiguator
from elagent.models.mention import Mention
from elagent.models.entity import Candidate

knowledge_base.load()

# 找3个典型错误文章
with open("Dataset/llm_extracted_merged.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

target_mentions = {"浙江队": 0, "日本队": 0, "亚锦赛": 0}
found = 0

for art in articles:
    text = art.get("text", "")
    for m in art.get("mentions", []):
        if m["text"] in target_mentions and target_mentions[m["text"]] < 1:
            target_mentions[m["text"]] += 1
            mention_text = m["text"]
            expected = m.get("standard_name", "")

            print(f"\n{'='*60}")
            print(f"Mention: {mention_text}  预期: {expected}")
            print(f"文章长度: {len(text)} 字")

            # 关键词检查
            for kw in ["羽毛", "乒乓", "斯诺", "游泳", "田径"]:
                c = text.count(kw)
                if c > 0:
                    print(f"  文章含 '{kw}': {c} 次")

            mention = Mention(
                text=mention_text, start_pos=m["start"], end_pos=m["end"],
                entity_type=m.get("entity_type"), context=text
            )

            # Step 1: 别名召回
            alias_entities = knowledge_base.search_by_alias(mention_text)
            print(f"\n[召回] 别名匹配: {len(alias_entities)} 个")
            for e in alias_entities:
                print(f"  {e.id}: {e.standard_name} (aliases={e.aliases[:5]})")

            # Step 2: 模糊匹配
            fuzzy = []
            for e in knowledge_base.entities.values():
                if mention_text in e.standard_name and len(e.standard_name) - len(mention_text) <= 8:
                    fuzzy.append(e)
                elif e.standard_name in mention_text and len(mention_text) - len(e.standard_name) <= 8:
                    fuzzy.append(e)
            if fuzzy:
                print(f"[召回] 模糊匹配: {len(fuzzy)} 个")
                for e in fuzzy:
                    if e.id not in {x.id for x in alias_entities}:
                        print(f"  {e.id}: {e.standard_name}")

            # Step 3: 消歧评分
            all_entities = alias_entities.copy()
            seen_ids = {e.id for e in all_entities}
            for e in fuzzy:
                if e.id not in seen_ids:
                    all_entities.append(e)
                    seen_ids.add(e.id)

            candidates = [Candidate(entity=e, score=0.95, match_source="alias") for e in all_entities]
            ranked = disambiguator.disambiguate(mention, candidates, top_k=5, full_text=text)

            print(f"\n[消歧结果] Top-5:")
            for i, c in enumerate(ranked):
                name_score = disambiguator._name_match_score(mention, c.entity)
                prior_score = disambiguator._prior_probability_score(c.entity)
                complete_score = disambiguator._name_completeness_score(mention, c.entity)
                context_boost = disambiguator._context_boost(mention, c.entity, text)
                correct = " ← 预期" if c.entity.standard_name == expected else ""
                print(f"  {i+1}. {c.entity.id} {c.entity.standard_name} "
                      f"final={c.score:.4f} "
                      f"name={name_score:.3f} prior={prior_score:.3f} "
                      f"complete={complete_score:.3f} boost={context_boost:.3f}{correct}")

                # 区分词分析
                all_names = [c.entity.standard_name] + list(c.entity.aliases)
                entity_bigrams = set()
                for name in all_names:
                    name_l = name.lower()
                    for j in range(len(name_l)-1):
                        entity_bigrams.add(name_l[j:j+2])
                mention_bigrams = set()
                for j in range(len(mention_text)-1):
                    mention_bigrams.add(mention_text[j:j+2])
                diff = entity_bigrams - mention_bigrams
                if diff:
                    hits = {bg: text.lower().count(bg) for bg in diff if text.lower().count(bg) > 0}
                    print(f"     区分2-gram命中: {hits}")

            found += 1
            if found >= 3:
                break
    if found >= 3:
        break

print(f"\n{'='*60}")
print("诊断完成")
