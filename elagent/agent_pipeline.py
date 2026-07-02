"""
实体链接与知识对齐智能体 - 主控流水线

编排原子 Skill 协同完成实体链接，每个 Skill 复用最终优化策略。
按需启用，全程可追溯。

用法:
  python -m elagent.agent_pipeline --skills
  python -m elagent.agent_pipeline --article Dataset/llm_extracted_merged.json
  python -m elagent.agent_pipeline --run standardize --input "国羽"
"""
import argparse
import json
import logging
import sys
import time
from collections import Counter
from pathlib import Path
from typing import List, Optional

# 支持直接运行（python agent_pipeline.py）
if __name__ == "__main__" and __package__ is None:
    __package__ = "elagent"
    sys.path.insert(0, str(Path(__file__).parent.parent))

from .core.knowledge_base import knowledge_base
from .core.disambiguator import disambiguator
from .core.bm25_index import bm25_index
from .core.nil_detector import nil_detector
from .core.coref_resolver import is_coreference_mention, resolve_coreference
from .models.mention import Mention
from .models.entity import Entity, Candidate
from .config import config

logger = logging.getLogger(__name__)


# ============================================================
# Skill 注册表
# ============================================================

SKILL_REGISTRY = {}
SKILL_CALL_LOG = []


def register_skill(name: str, impl_type: str, desc: str, cost: str, no_llm_reason: str):
    def decorator(func):
        SKILL_REGISTRY[name] = {"name": name, "description": desc,
            "implementation": impl_type, "cost": cost, "why_no_llm": no_llm_reason, "func": func}
        return func
    return decorator


def list_skills():
    print(f"\n{'Skill':<22} {'实现':<16} {'成本':<10} {'不用大模型的原因'}")
    print("=" * 90)
    for name, info in sorted(SKILL_REGISTRY.items()):
        print(f"{name:<22} {info['implementation']:<16} {info['cost']:<10} {info['why_no_llm']}")
    print(f"\n共 {len(SKILL_REGISTRY)} 个 Skill")


def call_skill(name: str, *args, **kwargs) -> any:
    info = SKILL_REGISTRY[name]
    start = time.time()
    result = info["func"](*args, **kwargs)
    elapsed = (time.time() - start) * 1000
    SKILL_CALL_LOG.append({"skill": name, "type": info["implementation"], "cost_ms": round(elapsed, 2)})
    if elapsed > 0.5:
        print(f"  ├─ [{name}] ({elapsed:.1f}ms, {info['implementation']})")
    return result


# ============================================================
# Skill 实现（复用最终策略）
# ============================================================

@register_skill(
    "standard_name_match", "纯规则(哈希表)",
    "标准名称精确匹配 → 置信度1.0", "<0.1ms",
    "哈希表查 name_index，O(1) 精确匹配。")
def skill_standard_name_match(mention_text: str) -> Optional[Entity]:
    return knowledge_base.get_entity_by_name(mention_text)


@register_skill(
    "alias_match", "纯规则(哈希表)",
    "别名精确匹配 + 消歧器（5信号评分）", "<1ms",
    "哈希表查 alias_dict，多候选时用5信号规则消歧，已达90.85%。")
def skill_alias_match(mention: Mention, full_text: str) -> Optional[Candidate]:
    entities = knowledge_base.search_by_alias(mention.text)
    if not entities:
        return None
    if len(entities) == 1:
        return Candidate(entity=entities[0], score=0.95, match_source="alias")
    candidates = [Candidate(entity=e, score=0.95, match_source="alias") for e in entities]
    # 类型过滤
    if mention.entity_type:
        tm = [c for c in candidates if c.entity.entity_type == mention.entity_type]
        if tm:
            candidates = tm
    ranked = disambiguator.disambiguate(mention, candidates, top_k=1, full_text=full_text)
    return ranked[0] if ranked else None


@register_skill(
    "fuzzy_match", "规则(名称包含)",
    "名称包含关系匹配 + 消歧器", "<30ms(遍历KB)",
    "遍历KB做子串匹配，多候选时复用5信号消歧器。")
def skill_fuzzy_match(mention: Mention, full_text: str) -> Optional[Candidate]:
    candidates = []
    for entity in knowledge_base.entities.values():
        if mention.text in entity.standard_name and len(entity.standard_name) - len(mention.text) <= 8:
            candidates.append(entity)
        elif entity.standard_name in mention.text and len(mention.text) - len(entity.standard_name) <= 8:
            candidates.append(entity)
    if not candidates:
        return None
    if mention.entity_type:
        tm = [e for e in candidates if e.entity_type == mention.entity_type]
        if tm:
            candidates = tm
    if len(candidates) == 1:
        return Candidate(entity=candidates[0], score=0.8, match_source="fuzzy")
    cs = [Candidate(entity=e, score=0.75, match_source="fuzzy") for e in candidates]
    ranked = disambiguator.disambiguate(mention, cs, top_k=1, full_text=full_text)
    return ranked[0] if ranked else None


@register_skill(
    "bm25_search", "算法(BM25+jieba)",
    "全文检索兜底", "<100ms",
    "BM25是确定性检索算法，无参数学习。")
def skill_bm25_search(mention_text: str) -> Optional[Candidate]:
    if not bm25_index.built:
        return None
    results = bm25_index.search(mention_text, top_k=10)
    if not results:
        return None
    eid, score = results[0]
    entity = knowledge_base.get_entity(eid)
    if not entity:
        return None
    return Candidate(entity=entity, score=min(score / 10.0, 0.7), match_source="bm25")


@register_skill(
    "nil_detect", "规则(多信号融合)",
    "知识库不存在实体的正确识别", "<0.5ms",
    "候选检索+分数阈值+类型一致性判定，哈希表即可解决。")
def skill_nil_detect(mention_text: str, mention_type: str, candidates: list = None) -> dict:
    result = nil_detector.detect(
        mention_text=mention_text, mention_type=mention_type,
        candidates=candidates or [],
        best_candidate=candidates[0] if candidates else None)
    return {"is_nil": result.is_nil, "confidence": result.confidence, "reason": result.reason}


@register_skill(
    "coref", "规则(最近前序回链)",
    "代词/指代词回链到前序实体", "<1ms",
    "最近前序同类型实体规则已达94.3%。")
def skill_coref(full_text: str) -> list:
    mentions = []
    for i in range(len(full_text)):
        for size in range(1, 5):
            chunk = full_text[i:i + size]
            etype = is_coreference_mention(chunk)
            if etype:
                mentions.append({"text": chunk, "start": i, "end": i + size, "entity_type": etype})
                break
    if not mentions:
        return []
    all_m = sorted(mentions, key=lambda m: m["start"])
    results = []
    for idx, m in enumerate(all_m):
        target = resolve_coreference(idx, all_m)
        results.append({"mention": m["text"], "entity_type": m["entity_type"],
                        "coref_target": target["text"] if target else None,
                        "entity_id": target.get("entity_id") if target else None})
    return results


# ============================================================
# 主流水线（5级瀑布，复用最终策略）
# ============================================================

def process_mention(mention_text: str, start_pos: int, end_pos: int,
                    entity_type: str, full_text: str, enable_coref: bool = False) -> dict:
    """
    5 级瀑布流水线：
    标准名匹配 → 别名匹配+消歧 → 模糊匹配+消歧 → BM25 → NIL
    """
    trace = []
    mention = Mention(text=mention_text, start_pos=start_pos, end_pos=end_pos,
                      entity_type=entity_type, context=full_text)
    result_info = {"mention": mention_text, "entity_type": entity_type}
    best = None
    source = ""

    # ── Step 1: 标准名称匹配 ──
    entity = call_skill("standard_name_match", mention_text)
    if entity:
        best = Candidate(entity=entity, score=1.0, match_source="standard_name")
        source = "标准名匹配"
        trace.append(f"标准名精确匹配 → {entity.standard_name}")

    # ── Step 2: 别名匹配 + 消歧 ──
    if not best:
        best = call_skill("alias_match", mention, full_text)
        if best:
            source = "别名+消歧"
            trace.append(f"别名匹配+消歧 → {best.entity.standard_name} ({best.score:.2f})")

    # ── Step 3: 模糊匹配 + 消歧 ──
    if not best:
        best = call_skill("fuzzy_match", mention, full_text)
        if best:
            source = "模糊+消歧"
            trace.append(f"模糊匹配+消歧 → {best.entity.standard_name} ({best.score:.2f})")

    # ── Step 4: BM25 ──
    if not best:
        best = call_skill("bm25_search", mention_text)
        if best:
            source = "BM25"
            trace.append(f"BM25检索 → {best.entity.standard_name} ({best.score:.2f})")

    # ── Step 5: NIL ──
    if not best:
        nil = call_skill("nil_detect", mention_text, entity_type or "")
        result_info["is_nil"] = nil["is_nil"]
        result_info["confidence"] = nil["confidence"]
        result_info["nil_reason"] = nil["reason"]
        trace.append(f"NIL判定 → {nil['reason']}")

    if best:
        result_info["linked_entity_id"] = best.entity.id
        result_info["linked_entity_name"] = best.entity.standard_name
        result_info["linked_type"] = best.entity.entity_type
        result_info["confidence"] = best.score
        result_info["is_nil"] = False

    result_info["trace"] = trace
    result_info["source"] = source

    if enable_coref:
        result_info["coref_results"] = call_skill("coref", full_text)

    return result_info


def process_article(article: dict, enable_coref: bool = False) -> dict:
    text = article.get("text", "")
    raw = article.get("mentions", [])
    results = []
    for m in raw:
        r = process_mention(m["text"], m["start"], m["end"],
                           m.get("entity_type", ""), text, enable_coref)
        r["expected_id"] = m.get("entity_id")
        r["expected_name"] = m.get("standard_name", "")
        r["is_correct"] = r.get("linked_entity_id") == m.get("entity_id")
        results.append(r)
    multi_total = sum(1 for r in results if r.get("source") in ("别名+消歧", "模糊+消歧"))
    multi_correct = sum(1 for r in results if r["is_correct"] and r.get("source") in ("别名+消歧", "模糊+消歧"))
    stats = {"total": len(results), "correct": sum(1 for r in results if r["is_correct"]),
             "multi_total": multi_total, "multi_correct": multi_correct}
    stats["accuracy"] = stats["correct"] / max(stats["total"], 1)
    stats["disambiguation_accuracy"] = multi_correct / max(multi_total, 1)
    return {"mentions": results, "stats": stats}


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="实体链接与知识对齐智能体 - 主控流水线")
    parser.add_argument("--skills", action="store_true", help="列出所有Skill")
    parser.add_argument("--run", choices=list(SKILL_REGISTRY.keys()), help="单独运行某个Skill")
    parser.add_argument("--input", type=str, help="Skill输入")
    parser.add_argument("--article", type=str, help="文章数据集路径")
    parser.add_argument("--max-articles", type=int, default=99999, help="最多N篇")
    parser.add_argument("--enable-coref", action="store_true", help="启用共指消解")
    args = parser.parse_args()

    print("加载知识库...")
    knowledge_base.load()
    print(f"  实体: {knowledge_base.entity_count}")
    bm25_index.build(knowledge_base.entities)
    print(f"  Skill: {len(SKILL_REGISTRY)} 个")

    if args.skills:
        list_skills()
        return

    # 默认：全量评测
    if not args.run and not args.article:
        args.article = "Dataset/llm_extracted_merged.json"

    if args.run:
        if args.run not in SKILL_REGISTRY:
            print(f"未知 Skill: {args.run}")
            return
        info = SKILL_REGISTRY[args.run]
        print(f"\n运行: {args.run} ({info['description']})")
        print(f"  实现: {info['implementation']} | 成本: {info['cost']}")
        print(f"  不用LLM: {info['why_no_llm']}")
        result = info["func"](args.input if args.input else "")
        print(f"  结果: {json.dumps(result, ensure_ascii=False, indent=2)}")
        return

    if args.article:
        path = Path(args.article)
        if not path.exists():
            print(f"文件不存在: {args.article}")
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            data = data[:args.max_articles]

        print(f"\n处理 {len(data)} 篇文章...")
        total = {"total": 0, "correct": 0, "multi_total": 0, "multi_correct": 0}
        for i, art in enumerate(data):
            result = process_article(art, enable_coref=args.enable_coref)
            s = result["stats"]
            total["total"] += s["total"]
            total["correct"] += s["correct"]
            total["multi_total"] += s["multi_total"]
            total["multi_correct"] += s["multi_correct"]
            acc = total["correct"] / max(total["total"], 1)
            if i < 3:
                for mr in result["mentions"][:3]:
                    mark = "OK" if mr["is_correct"] else "XX"
                    linked = mr.get("linked_entity_name") or "NIL"
                    print(f"  [{mark}] {mr['mention']} -> {linked}")
            print(f"  进度: {i+1}/{len(data)}, 当前准确率: {acc:.2%}")

        final_acc = total["correct"] / max(total["total"], 1)
        multi_total = total.get("multi_total", 0)
        multi_correct = total.get("multi_correct", 0)
        disambig_acc = multi_correct / max(multi_total, 1)
        print(f"\n=== 处理完成 ===")
        print(f"总mention: {total['total']}")
        print(f"正确: {total['correct']}")
        print(f"链接准确率: {final_acc:.2%}")
        if multi_total > 0:
            print(f"消歧准确率: {disambig_acc:.2%} (多候选{multi_total}个)")
        print(f"别名召回率: {total['correct']}/{total['total']} = {final_acc:.2%}")

        skill_stats = Counter(log["skill"] for log in SKILL_CALL_LOG)
        print(f"\nSkill调用统计:")
        for name, cnt in skill_stats.most_common():
            cost = sum(log["cost_ms"] for log in SKILL_CALL_LOG if log["skill"] == name)
            print(f"  {name}: {cnt}次, 总{cost:.0f}ms")


if __name__ == "__main__":
    main()
