"""
实体链接与知识对齐智能体 - 主控流水线

编排原子 Skill 协同完成实体链接+消歧+NIL+共指。
默认评测全部三个数据集，输出统一报告。

用法:
  python elagent/agent_pipeline.py               # 全量评测
  python elagent/agent_pipeline.py --skills       # 列出Skill
  python -m elagent.agent_pipeline               # 同上（全量）
"""
import argparse
import json
import logging
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import List, Optional

if __name__ == "__main__" and __package__ is None:
    __package__ = "elagent"
    sys.path.insert(0, str(Path(__file__).parent.parent))

from .core.knowledge_base import knowledge_base
from .core.disambiguator import disambiguator
from .core.bm25_index import bm25_index
from .core.nil_detector import nil_detector
from .core.coref_resolver import evaluate_coref, is_coreference_mention, resolve_coreference
from .models.mention import Mention
from .models.entity import Entity, Candidate

logger = logging.getLogger(__name__)

# ============================================================
# Skill 注册表
# ============================================================
SKILL_REGISTRY = {}
SKILL_CALL_LOG = []

def register_skill(name, impl_type, desc, cost, no_llm_reason):
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

def call_skill(name, *args, **kwargs):
    info = SKILL_REGISTRY[name]
    start = time.time()
    result = info["func"](*args, **kwargs)
    elapsed = (time.time() - start) * 1000
    SKILL_CALL_LOG.append({"skill": name, "type": info["implementation"], "cost_ms": round(elapsed, 2)})
    return result

# ============================================================
# Skill 实现
# ============================================================
@register_skill("候选实体生成/检索", "规则(别名+模糊+BM25)", "别名匹配→模糊→BM25，召回候选列表", "<50ms",
    "三步召回（哈希表+子串遍历+BM25），全部确定性规则。")
def skill_candidate_retrieval(mention_text, mention_type, full_text):
    """返回候选实体列表，供上下文消歧Skill使用"""
    candidates = []
    seen = set()

    # 1. 别名匹配
    alias_entities = knowledge_base.search_by_alias(mention_text)
    for e in alias_entities:
        if e.id not in seen:
            candidates.append(e)
            seen.add(e.id)

    # 2. 模糊匹配（名称包含）
    for entity in knowledge_base.entities.values():
        if mention_text in entity.standard_name and len(entity.standard_name) - len(mention_text) <= 8:
            if entity.id not in seen:
                candidates.append(entity)
                seen.add(entity.id)
        elif entity.standard_name in mention_text and len(mention_text) - len(entity.standard_name) <= 8:
            if entity.id not in seen:
                candidates.append(entity)
                seen.add(entity.id)

    # 2. BM25
    if bm25_index.built:
        results = bm25_index.search(mention_text, top_k=10)
        for eid, score in results:
            if eid not in seen:
                entity = knowledge_base.get_entity(eid)
                if entity:
                    candidates.append(entity)
                    seen.add(eid)

    if mention_type:
        tm = [e for e in candidates if e.entity_type == mention_type]
        if tm:
            candidates = tm

    return candidates

@register_skill("nil_detect", "规则(候选检索+多信号)", "知识库不存在实体的识别", "<0.5ms",
    "候选检索+分数阈值+类型一致性判定，哈希表解决。")
def skill_nil_detect(mention_text, mention_type, candidates=None):
    result = nil_detector.detect(
        mention_text=mention_text, mention_type=mention_type,
        candidates=candidates or [],
        best_candidate=candidates[0] if candidates else None)
    return {"is_nil": result.is_nil, "confidence": result.confidence, "reason": result.reason}

@register_skill("实体标准化", "纯规则(哈希表)", "标准名称精确匹配→标准全称+ID", "<0.1ms",
    "仅查 name_index，O(1)精确匹配。别名匹配由候选检索处理（可能需消歧）。")
def skill_standardize(mention_text):
    e = knowledge_base.get_entity_by_name(mention_text)
    if e:
        return {"matched": True, "standard_name": e.standard_name, "entity_id": e.id, "entity_type": e.entity_type}
    return {"matched": False}

@register_skill("上下文消歧", "规则(5信号加权评分)", "多候选结合上下文区分同名异指", "<1ms",
    "5信号评分已达90.85%，gap<0.01可选LLM。")
def skill_disambiguate(mention, full_text, entities):
    """entities: 可以是 Entity 或 Candidate 列表"""
    if len(entities) <= 1:
        return entities[0] if entities else None
    # 统一转为Candidate
    cs = []
    for e in entities:
        if hasattr(e, 'entity'):  # 已经是Candidate
            cs.append(e)
        else:  # Entity对象
            cs.append(Candidate(entity=e, score=0.95))
    if mention.entity_type:
        tm = [c for c in cs if c.entity.entity_type == mention.entity_type]
        if tm:
            cs = tm
    ranked = disambiguator.disambiguate(mention, cs, top_k=1, full_text=full_text)
    return ranked[0] if ranked else None


@register_skill("coref_resolve", "规则(最近前序回链)", "代词/指代词回链到前序实体", "<1ms",
    "最近前序同类型实体规则已达94.3%，无需大模型。")
def skill_coref_resolve(full_text):
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
# 主流水线（5级瀑布 + NIL + 共指）
# ============================================================
def process_mention(mention_text, start_pos, end_pos, entity_type, full_text):
    result_info = {"mention": mention_text, "entity_type": entity_type}
    mention = Mention(text=mention_text, start_pos=0, end_pos=len(mention_text),
                      entity_type=entity_type, context=full_text)

    # Step 1: 实体标准化（return early if 1 candidate）
    std = call_skill("实体标准化", mention_text)
    if std["matched"]:
        result_info["linked_entity_id"] = std["entity_id"]
        result_info["linked_entity_name"] = std["standard_name"]
        result_info["linked_type"] = std["entity_type"]
        result_info["confidence"] = 1.0
        result_info["is_nil"] = False
        result_info["source"] = "standardize"
        return result_info

    # Step 2: 候选检索（fuzzy + BM25）
    candidates = call_skill("候选实体生成/检索", mention_text, entity_type, full_text)
    if not candidates:
        nil = call_skill("nil_detect", mention_text, entity_type or "")
        result_info["is_nil"] = nil["is_nil"]
        result_info["confidence"] = nil["confidence"]
        result_info["nil_reason"] = nil["reason"]
        return result_info

    # Step 3: 上下文消歧（多候选时）
    if len(candidates) == 1:
        best_entity = candidates[0]
        result_info["linked_entity_id"] = best_entity.id
        result_info["linked_entity_name"] = best_entity.standard_name
        result_info["linked_type"] = best_entity.entity_type
        result_info["confidence"] = 0.8
        result_info["is_nil"] = False
        result_info["source"] = "fuzzy"
        return result_info
    else:
        best = call_skill("上下文消歧", mention, full_text, candidates)
        result_info["source"] = "disambiguate"
        result_info["multi_candidate"] = True

    if best:
        result_info["linked_entity_id"] = best.entity.id
        result_info["linked_entity_name"] = best.entity.standard_name
        result_info["linked_type"] = best.entity.entity_type
        result_info["confidence"] = best.score
        result_info["is_nil"] = False
    else:
        nil = call_skill("nil_detect", mention_text, entity_type or "")
        result_info["is_nil"] = nil["is_nil"]
        result_info["confidence"] = nil["confidence"]
        result_info["nil_reason"] = nil["reason"]

    return result_info


def process_article(article):
    """处理文章全部mention，返回评测结果"""
    text = article.get("text", "")
    raw = article.get("mentions", [])
    results = []
    for m in raw:
        # 跳过共指标注中的指代词（留待共指评测处理）
        if m.get("is_coref") or is_coreference_mention(m.get("text", "")):
            continue
        r = process_mention(m["text"], m["start"], m["end"],
                           m.get("entity_type", ""), text)
        r["expected_id"] = m.get("entity_id")
        r["expected_name"] = m.get("standard_name", "")
        r["is_correct"] = r.get("linked_entity_id") == m.get("entity_id")
        results.append(r)
    stats = {"total": len(results), "correct": sum(1 for r in results if r["is_correct"])}
    stats["accuracy"] = stats["correct"] / max(stats["total"], 1)
    multi_total = sum(1 for r in results if r.get("multi_candidate"))
    multi_correct = sum(1 for r in results if r["is_correct"] and r.get("multi_candidate"))
    stats["multi_total"] = multi_total
    stats["multi_correct"] = multi_correct
    stats["disambiguation_accuracy"] = multi_correct / max(multi_total, 1) if multi_total > 0 else None
    return {"mentions": results, "stats": stats}


# ============================================================
# 评测函数
# ============================================================
def evaluate_entity_linking():
    """实体链接评测（链接+消歧+别名）"""
    print(f"\n{'='*60}")
    print("一、实体链接评测")
    print(f"{'='*60}")
    path = "Dataset/llm_extracted_merged.json"
    with open(path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    total = {"total": 0, "correct": 0, "multi_total": 0, "multi_correct": 0}
    for i, art in enumerate(articles):
        r = process_article(art)
        s = r["stats"]
        total["total"] += s["total"]
        total["correct"] += s["correct"]
        total["multi_total"] += s["multi_total"]
        total["multi_correct"] += s["multi_correct"]
        if i > 0 and i % 200 == 0:
            print(f"  进度: {i}/{len(articles)}")

    link_acc = total["correct"] / max(total["total"], 1)
    disambig_acc = total["multi_correct"] / max(total["multi_total"], 1)
    print(f"  总样本: {total['total']}, 正确: {total['correct']}")
    print(f"  链接准确率: {link_acc:.2%}")
    print(f"  消歧准确率: {disambig_acc:.2%} (多候选{total['multi_total']}个)")
    print(f"  目标: ≥85%  {'PASS' if link_acc >= 0.85 else 'FAIL'}")
    return {"link_accuracy": link_acc, "disambiguation_accuracy": disambig_acc,
            "total": total["total"], "correct": total["correct"],
            "multi_total": total["multi_total"], "multi_correct": total["multi_correct"]}


def evaluate_nil():
    """NIL检测评测"""
    print(f"\n{'='*60}")
    print("二、NIL检测评测")
    print(f"{'='*60}")
    path = "Dataset/NIL.json"
    if not Path(path).exists():
        print("  NIL数据集不存在，跳过")
        return None
    with open(path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    total_nil = 0
    nil_correct = 0
    false_hits = []
    for art in articles:
        text = art.get("text", "")
        for m in art.get("mentions", []):
            annotation_nil = m.get("is_nil", True)
            if annotation_nil:
                total_nil += 1
                # NIL检测直接调用 nil_detect Skill，不走全链路
                nil_result = call_skill("nil_detect", m["text"], m.get("entity_type", ""))
                if nil_result["is_nil"]:
                    nil_correct += 1
                else:
                    false_hits.append({"mention": m["text"]})

    nil_acc = nil_correct / max(total_nil, 1)
    print(f"  标注NIL: {total_nil}, 正确检测NIL: {nil_correct}, 漏检: {len(false_hits)}")
    print(f"  NIL准确率: {nil_acc:.2%}")
    print(f"  目标: ≥80%  {'PASS' if nil_acc >= 0.80 else 'FAIL'}")
    return {"nil_accuracy": nil_acc, "total_nil": total_nil, "nil_correct": nil_correct}


def evaluate_coref_task():
    """共指消解评测"""
    print(f"\n{'='*60}")
    print("三、共指消解评测")
    print(f"{'='*60}")
    path = "Dataset/llm_extracted_with_coref.json"
    if not Path(path).exists():
        print("  共指数据集不存在，跳过")
        return None
    with open(path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    result = evaluate_coref(articles)
    acc = result["accuracy"]
    print(f"  指代词: {result['total']}, 正确回链: {result['correct']}")
    print(f"  共指准确率: {acc:.2%}")
    print(f"  目标: ≥80%  {'PASS' if acc >= 0.80 else 'FAIL'}")
    return {"coref_accuracy": acc, "total": result["total"], "correct": result["correct"]}


# ============================================================
# CLI
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="实体链接与知识对齐智能体 - 全流水线评测")
    parser.add_argument("--skills", action="store_true", help="列出所有Skill")
    parser.add_argument("--run", choices=list(SKILL_REGISTRY.keys()), help="单独运行某个Skill")
    parser.add_argument("--input", type=str, help="Skill输入")
    parser.add_argument("--max-articles", type=int, default=99999, help="最多文章数")
    args = parser.parse_args()

    print("加载知识库...")
    knowledge_base.load()
    print(f"  实体: {knowledge_base.entity_count}")
    bm25_index.build(knowledge_base.entities)
    print(f"  Skill: {len(SKILL_REGISTRY)} 个")

    if args.skills:
        list_skills()
        return

    if args.run:
        if args.run not in SKILL_REGISTRY:
            print(f"未知 Skill: {args.run}")
            return
        info = SKILL_REGISTRY[args.run]
        result = info["func"](args.input or "")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    # 全量评测
    el_result = evaluate_entity_linking()
    nil_result = evaluate_nil()
    coref_result = evaluate_coref_task()

    print(f"\n{'='*60}")
    print("评测结果汇总")
    print(f"{'='*60}")
    print(f"{'指标':<30} {'数值':<10} {'目标':<10} {'状态':<10}")
    print("-" * 60)
    if el_result:
        link = el_result["link_accuracy"]
        disambig = el_result["disambiguation_accuracy"]
        print(f"{'链接准确率':<30} {link*100:<8.2f}% {'≥85%':<10} {'PASS' if link>=0.85 else 'FAIL':<10}")
        print(f"{'消歧准确率':<30} {disambig*100:<8.2f}% {'≥85%':<10} {'PASS' if disambig>=0.85 else 'FAIL':<10}")
    if nil_result:
        nil = nil_result["nil_accuracy"]
        print(f"{'NIL检测':<30} {nil*100:<8.2f}% {'≥80%':<10} {'PASS' if nil>=0.80 else 'FAIL':<10}")
    if coref_result:
        coref = coref_result["coref_accuracy"]
        print(f"{'共指消解':<30} {coref*100:<8.2f}% {'≥80%':<10} {'PASS' if coref>=0.80 else 'FAIL':<10}")

    print(f"\nSkill调用统计:")
    skill_stats = Counter(log["skill"] for log in SKILL_CALL_LOG)
    for name, cnt in skill_stats.most_common():
        cost = sum(log["cost_ms"] for log in SKILL_CALL_LOG if log["skill"] == name)
        print(f"  {name}: {cnt}次, 累计{cost:.0f}ms")


if __name__ == "__main__":
    main()
