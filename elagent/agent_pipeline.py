"""
实体链接与知识对齐智能体 - 主控流水线

按任务书要求，智能体内部编排若干原子能力（Skill）协同完成。
每个 Skill 可独立调用（按需启用），也可通过主流水线组合执行。

用法:
  python -m elagent.agent_pipeline                      # 启动服务
  python -m elagent.agent_pipeline --skills             # 列出所有Skill
  python -m elagent.agent_pipeline --run standardize --input "国羽"  # 单独调用某个Skill
"""
import argparse
import json
import logging
from typing import List, Dict, Optional

from .core.knowledge_base import knowledge_base
from .core.disambiguator import disambiguator
from .core.bm25_index import bm25_index
from .core.nil_detector import nil_detector
from .core.coref_resolver import is_coreference_mention, resolve_coreference
from .models.mention import Mention
from .models.entity import Entity, Candidate
from .models.result import LinkResult
from .config import config

logger = logging.getLogger(__name__)


# ============================================================
# Skill 注册表
# ============================================================

SKILL_REGISTRY = {}


def register_skill(name: str, impl_type: str, desc: str, cost: str, no_llm_reason: str):
    """注册 Skill 到注册表"""
    def decorator(func):
        SKILL_REGISTRY[name] = {
            "name": name,
            "description": desc,
            "implementation": impl_type,
            "cost": cost,
            "why_no_llm": no_llm_reason,
            "func": func,
        }
        return func
    return decorator


def list_skills():
    """列出所有注册的 Skill"""
    print(f"{'Skill名称':<20} {'实现类型':<12} {'成本':<12} {'说明'}")
    print("-" * 80)
    for name, info in sorted(SKILL_REGISTRY.items()):
        print(f"{name:<20} {info['implementation']:<12} {info['cost']:<12} {info['description']}")
    return SKILL_REGISTRY


# ============================================================
# Skill 实现
# ============================================================

@register_skill(
    "standardize",
    "纯规则",
    "别名/简称/曾用名 → 标准全称 + 唯一ID",
    "O(1)",
    "别名映射是确定的键值对查找，哈希表即可解决。"
)
def skill_standardize(mention_text: str) -> dict:
    """Skill: 实体标准化"""
    # 标准名匹配
    entity = knowledge_base.get_entity_by_name(mention_text)
    if entity:
        return {
            "matched": True,
            "standard_name": entity.standard_name,
            "entity_id": entity.id,
            "entity_type": entity.entity_type,
        }
    # 别名匹配
    aliases = knowledge_base.search_by_alias(mention_text)
    if aliases:
        best = aliases[0]
        return {
            "matched": True,
            "standard_name": best.standard_name,
            "entity_id": best.id,
            "entity_type": best.entity_type,
        }
    return {"matched": False}


@register_skill(
    "disambiguate",
    "规则（5信号评分）",
    "多候选实体结合上下文选择最佳",
    "<1ms",
    "5信号规则消歧器已达到90.85%准确率。LLM仅作为gap<0.01的可选兜底。"
)
def skill_disambiguate(mention: Mention, candidates: list) -> list:
    """Skill: 上下文消歧"""
    if len(candidates) <= 1:
        return candidates
    # 类型过滤
    if mention.entity_type:
        type_matched = [c for c in candidates if c.entity.entity_type == mention.entity_type]
        if type_matched:
            candidates = type_matched
    if len(candidates) <= 1:
        return candidates

    all_entities = [c.entity for c in candidates]
    scored = []
    for c in candidates:
        score = disambiguator._compute_score(mention, c.entity, "", all_entities)
        c.score = score
        scored.append(c)
    scored.sort(key=lambda x: x.score, reverse=True)
    return scored[:3]


@register_skill(
    "nil_check",
    "规则（候选检索）",
    "判断实体是否在知识库中不存在",
    "<0.5ms",
    "NIL判定本质是'KB中是否存在此mention'，哈希表直接解决。"
)
def skill_nil_check(mention_text: str) -> dict:
    """Skill: NIL检测"""
    candidates = knowledge_base.search_by_alias(mention_text)
    if not candidates:
        name_entity = knowledge_base.get_entity_by_name(mention_text)
        if name_entity:
            candidates = [name_entity]
    result = nil_detector.detect(
        mention_text=mention_text,
        mention_type="",
        candidates=[Candidate(entity=c, score=0.95) for c in candidates] if candidates else [],
    )
    return {"is_nil": result.is_nil, "confidence": result.confidence, "reason": result.reason}


@register_skill(
    "coref",
    "规则（最近前序回链）",
    "代词/指代词回链到具体实体",
    "<0.5ms",
    "结构化文本中代词回链通过'最近前序同类型实体'即可达到94.3%。"
)
def skill_coref(full_text: str) -> list:
    """Skill: 共指消解"""
    mentions = []
    for i in range(len(full_text)):
        for size in range(1, 5):
            chunk = full_text[i:i + size]
            etype = is_coreference_mention(chunk)
            if etype:
                mentions.append({"text": chunk, "start": i, "end": i + size, "entity_type": etype, "entity_id": None})
                break
    if not mentions:
        return []
    all_mentions = sorted(mentions, key=lambda m: m["start"])
    results = []
    for idx, m in enumerate(all_mentions):
        target = resolve_coreference(idx, all_mentions)
        results.append({
            "mention": m["text"],
            "entity_type": m["entity_type"],
            "coref_target": target["text"] if target else None,
            "entity_id": target.get("entity_id") if target else None,
        })
    return results


# ============================================================
# 主流水线（组合 Skill）
# ============================================================

def link_pipeline(mention: Mention, full_text: str = "", trace: list = None) -> LinkResult:
    """
    实体链接主流水线。

    按优先级依次尝试 5 级瀑布，返回链接结果。
    每一步均记录追溯（原值→新值→依据）。
    """
    result = LinkResult(mention=mention)
    if trace is None:
        trace = []

    # Step 1: 标准名称匹配
    step_trace(trace, "标准名称匹配", mention.text)
    name_entity = knowledge_base.get_entity_by_name(mention.text)
    if name_entity:
        result.linked_entity = name_entity
        result.is_nil = False
        result.confidence = 1.0
        step_trace(trace, "标准名称匹配", mention.text, f"{name_entity.standard_name} ({name_entity.id})", "标准名称完全匹配")
        return result

    # Step 2: 别名匹配 + 消歧
    step_trace(trace, "别名精确匹配", mention.text)
    alias_entities = knowledge_base.search_by_alias(mention.text)
    if alias_entities:
        if len(alias_entities) == 1:
            result.linked_entity = alias_entities[0]
            result.is_nil = False
            result.confidence = 0.95
            step_trace(trace, "别名精确匹配", mention.text, f"{alias_entities[0].standard_name} ({alias_entities[0].id})", "别名匹配成功")
            return result

        # 多候选消歧
        candidates = [Candidate(entity=e, score=0.95, match_source="alias") for e in alias_entities]
        ranked = skill_disambiguate(mention, candidates)
        if ranked:
            best = ranked[0]
            result.linked_entity = best.entity
            result.is_nil = False
            result.confidence = best.score
            step_trace(trace, "别名匹配+消歧", mention.text, f"{best.entity.standard_name} ({best.entity.id})",
                       f"从{len(alias_entities)}个候选中选择，得分={best.score:.2f}")
            return result

    # Step 3: 模糊匹配
    step_trace(trace, "模糊匹配", mention.text)
    fuzzy_candidates = []
    for entity in knowledge_base.entities.values():
        if mention.text in entity.standard_name and len(entity.standard_name) - len(mention.text) <= 8:
            fuzzy_candidates.append(entity)
        elif entity.standard_name in mention.text and len(mention.text) - len(entity.standard_name) <= 8:
            fuzzy_candidates.append(entity)
    if fuzzy_candidates:
        if mention.entity_type:
            type_matched = [e for e in fuzzy_candidates if e.entity_type == mention.entity_type]
            if type_matched:
                fuzzy_candidates = type_matched
        if len(fuzzy_candidates) == 1:
            result.linked_entity = fuzzy_candidates[0]
            result.is_nil = False
            result.confidence = 0.8
            step_trace(trace, "模糊匹配", mention.text, f"{fuzzy_candidates[0].standard_name} ({fuzzy_candidates[0].id})", "名称包含关系匹配")
            return result
        candidates = [Candidate(entity=e, score=0.75, match_source="fuzzy") for e in fuzzy_candidates]
        ranked = skill_disambiguate(mention, candidates)
        if ranked:
            best = ranked[0]
            result.linked_entity = best.entity
            result.is_nil = False
            result.confidence = best.score
            step_trace(trace, "模糊匹配消歧", mention.text, f"{best.entity.standard_name} ({best.entity.id})",
                       f"从{len(fuzzy_candidates)}个候选中消歧选择，得分={best.score:.2f}")
            return result

    # Step 4: BM25 检索
    step_trace(trace, "BM25检索", mention.text)
    if bm25_index.built:
        bm25_results = bm25_index.search(mention.text, top_k=10)
        if bm25_results:
            best_entity_id, best_score = bm25_results[0]
            entity = knowledge_base.get_entity(best_entity_id)
            if entity:
                result.linked_entity = entity
                result.is_nil = False
                result.confidence = min(best_score / 10.0, 0.7)
                step_trace(trace, "BM25检索", mention.text, f"{entity.standard_name} ({entity.id})", f"BM25相似度={best_score:.2f}")
                return result

    # Step 5: NIL
    nil_result = nil_detector.detect(mention_text=mention.text, mention_type=mention.entity_type or "", candidates=[], best_candidate=None)
    result.is_nil = True
    result.confidence = nil_result.confidence
    result.nil_reason = nil_result.reason if nil_result.is_nil else f"知识库中未找到与'{mention.text}'匹配的实体"
    step_trace(trace, "NIL判定", mention.text, "NIL", result.nil_reason)
    return result


def step_trace(trace: list, step: str, original: str, new_value: str = "", reason: str = ""):
    """记录追溯步骤"""
    trace.append({
        "step": step,
        "original_value": original,
        "new_value": new_value or original,
        "reason": reason,
    })


# ============================================================
# CLI 入口（用于独立测试）
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="实体链接与知识对齐智能体")
    parser.add_argument("--skills", action="store_true", help="列出所有Skill")
    parser.add_argument("--run", choices=list(SKILL_REGISTRY.keys()), help="单独运行某个Skill")
    parser.add_argument("--input", type=str, help="Skill的输入参数")

    args = parser.parse_args()

    # 初始化
    print("加载知识库...")
    knowledge_base.load()
    print(f"  实体: {knowledge_base.entity_count}")
    bm25_index.build(knowledge_base.entities)

    if args.skills:
        print(f"\n注册了 {len(SKILL_REGISTRY)} 个 Skill:")
        print()
        list_skills()
        return

    if args.run:
        skill = SKILL_REGISTRY.get(args.run)
        if not skill:
            print(f"Skill '{args.run}' 不存在")
            return
        print(f"\n运行 Skill: {args.run}")
        print(f"  实现: {skill['implementation']}")
        print(f"  说明: {skill['description']}")
        print(f"  成本: {skill['cost']}")
        print(f"  不用LLM: {skill['why_no_llm']}")
        print(f"\n  输入: {args.input}")
        result = skill["func"](args.input)
        print(f"  输出: {json.dumps(result, ensure_ascii=False, indent=4)}")
        return

    # 默认：列出Skill
    print(f"\n实体链接与知识对齐智能体")
    print(f"注册了 {len(SKILL_REGISTRY)} 个 Skill，全部按需启用")
    print()
    list_skills()


if __name__ == "__main__":
    main()
