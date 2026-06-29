"""诊断文章词投票为什么没生效"""
import json, sys, jieba
from pathlib import Path
from collections import Counter
sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.knowledge_base import knowledge_base
from elagent.core.disambiguator import disambiguator
from elagent.models.mention import Mention
from elagent.models.entity import Candidate

knowledge_base.load()

with open("data/all_errors.json", "r", encoding="utf-8") as f:
    errors = json.load(f)

# 找实际错误文章
with open("Dataset/llm_extracted_merged.json", "r", encoding="utf-8") as f:
    articles = json.load(f)

error_mentions = set(e["mention"] for e in errors[:10])
checked = set()
for art in articles[:800]:
    text = art.get("text", "")
    for m in art.get("mentions", []):
        key = (m["text"], m.get("standard_name", ""))
        if m["text"] in error_mentions and key not in checked:
            checked.add(key)
            mention = Mention(text=m["text"], start_pos=m["start"], end_pos=m["end"],
                             entity_type=m.get("entity_type"), context=text)
            expected = m.get("standard_name", "")

            # 召回
            alias_entities = knowledge_base.search_by_alias(mention.text)
            if not alias_entities:
                continue
            if len(alias_entities) < 2:
                continue

            candidates = [Candidate(entity=e, score=0.95, match_source="alias") for e in alias_entities]
            ranked = disambiguator.disambiguate(mention, candidates, top_k=5, full_text=text)
            if len(ranked) < 2:
                continue

            top1 = ranked[0]
            gap = ranked[0].score - ranked[1].score
            is_error = top1.entity.standard_name != expected

            if is_error:
                print(f"\n{'='*60}")
                print(f"Mention: {m['text']}  预期: {expected}")
                print(f"Top-1: {top1.entity.standard_name} ({top1.score:.4f})")
                print(f"Top-2: {ranked[1].entity.standard_name} ({ranked[1].score:.4f})")
                print(f"Gap: {gap:.4f}  {'触发投票' if gap < 0.03 else '未触发'}")
                print(f"文章长度: {len(text)}")

                # 文章关键词
                article_words = [w for w in jieba.cut(text) if len(w) >= 2]
                word_counts = Counter(article_words)

                # 各候选的特有词命中
                mention_words = set(w for w in jieba.cut(mention.text) if len(w) >= 2)
                for i, c in enumerate(ranked[:3]):
                    entity_words = set()
                    for name in [c.entity.standard_name] + list(c.entity.aliases):
                        entity_words.update(w for w in jieba.cut(name) if len(w) >= 2)
                    unique = entity_words - mention_words
                    hits = {w: word_counts.get(w, 0) for w in unique}
                    total = sum(hits.values())
                    tag = " ← 预期" if c.entity.standard_name == expected else ""
                    print(f"  #{i+1} {c.entity.standard_name}")
                    print(f"     特有词: {unique}  命中: {hits}  总计:{total}{tag}")

            if len(checked) >= 5:
                break
    if len(checked) >= 5:
        break
