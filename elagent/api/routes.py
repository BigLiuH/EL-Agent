"""
API路由模块

定义实体链接系统的RESTful API接口。
"""

import time
import logging
from fastapi import APIRouter, HTTPException

from .schemas import (
    LinkRequest, LinkResponse,
    BatchLinkRequest, BatchLinkResponse,
    KBStatsResponse, TraceResponse, HealthResponse,
    EntityResponse,
    NILRequest, NILResponse,
    CorefRequest, CorefResponse, CorefResult,
)
from ..core.knowledge_base import knowledge_base
from ..core.bm25_index import bm25_index
from ..core.disambiguator import disambiguator
from ..core.llm_disambiguator import llm_disambiguator
from ..core.trace_logger import trace_logger
from ..core.nil_detector import nil_detector
from ..core.coref_resolver import is_coreference_mention, resolve_coreference
from ..config import config
from ..models.mention import Mention
from ..models.entity import Candidate
from ..models.result import LinkResult

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["系统"])
async def health_check():
    """服务健康检查。返回服务状态、版本号和知识库加载情况。"""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        kb_loaded=knowledge_base.loaded,
        kb_entity_count=knowledge_base.entity_count,
    )


@router.get("/kb/stats", response_model=KBStatsResponse, tags=["知识库"])
async def get_kb_stats():
    """知识库统计。查看当前知识库的实体数、别名数、各类型分布。"""
    stats = knowledge_base.get_statistics()
    return KBStatsResponse(**stats)


@router.post("/link", response_model=LinkResponse, tags=["实体链接"])
async def link_entity(request: LinkRequest):
    """
    实体链接（核心接口）

    将文本中的实体指称链接到知识库中的标准实体。
    支持消歧、别名标准化、NIL检测。

    测试示例:
    ```
    {"text": "2024年世界羽联世界羽毛球锦标赛在哥本哈根举行，中国羽毛球队在世锦赛上表现出色。",
     "mention": {"text": "世锦赛", "start_pos": 44, "end_pos": 47, "entity_type": "EVENT"}}
    ```
    """
    if not knowledge_base.loaded:
        raise HTTPException(status_code=503, detail="知识库未加载")

    start_time = time.time()

    try:
        # 构建Mention对象
        # 窗口上下文（±200字符）用于局部关键词匹配
        # 全文单独传入用于文档级区分词命中统计
        text = request.text
        win_start = max(0, request.mention.start_pos - 200)
        win_end = min(len(text), request.mention.end_pos + 200)
        window_context = text[win_start:win_end]

        mention = Mention(
            text=request.mention.text,
            start_pos=request.mention.start_pos,
            end_pos=request.mention.end_pos,
            entity_type=request.mention.entity_type,
            context=window_context,
        )

        # 创建追溯日志（含原始输入，用于回放）
        trace = trace_logger.create_trace(
            mention_id=mention.id,
            mention_text=mention.text,
            entity_type=mention.entity_type or "UNKNOWN",
            input_data={
                "full_text": text,
                "mention_text": mention.text,
                "start_pos": mention.start_pos,
                "end_pos": mention.end_pos,
                "entity_type": mention.entity_type,
            }
        )

        # Phase 2: 增强链接（BM25 + 消歧 + 上下文）
        result = _enhanced_link(mention, trace, full_text=text)

        # 计算处理时间
        processing_time = (time.time() - start_time) * 1000
        result.processing_time_ms = processing_time
        result.trace_id = trace.trace_id

        # 完成追溯日志
        trace.finalize({
            "linked_entity_id": result.linked_entity.id if result.linked_entity else None,
            "linked_entity_name": result.linked_entity.standard_name if result.linked_entity else None,
            "is_nil": result.is_nil,
            "confidence": result.confidence,
            "nil_reason": result.nil_reason
        })

        # 保存追溯日志
        trace_logger.save_trace(trace)

        # 转换为响应
        return _to_response(result)

    except Exception as e:
        logger.error(f"实体链接失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"链接失败: {str(e)}")


@router.post("/batch_link", response_model=BatchLinkResponse, tags=["实体链接"])
async def batch_link(request: BatchLinkRequest):
    """批量实体链接。一次处理多条链接请求，推荐用于同一篇文章的多个mention。"""
    if not knowledge_base.loaded:
        raise HTTPException(status_code=503, detail="知识库未加载")

    results = []
    success_count = 0
    nil_count = 0

    for item in request.items:
        try:
            # 逐个处理
            link_request = LinkRequest(text=item.text, mention=item.mention)
            response = await link_entity(link_request)
            results.append(response)

            if not response.is_nil:
                success_count += 1
            else:
                nil_count += 1

        except Exception as e:
            logger.error(f"批量链接中某项失败: {e}")
            results.append(LinkResponse(
                is_nil=True,
                nil_reason=f"处理失败: {str(e)}",
            ))
            nil_count += 1

    return BatchLinkResponse(
        results=results,
        total=len(results),
        success_count=success_count,
        nil_count=nil_count,
    )


@router.get("/trace/{trace_id}", response_model=TraceResponse, tags=["追溯"])
async def get_trace(trace_id: str):
    """查询追溯日志。查看实体链接的完整处理过程，包括每一步的输入、输出和决策依据。"""
    trace = trace_logger.get_trace(trace_id)
    if trace is None:
        # 尝试从文件加载
        trace = trace_logger.load_trace(trace_id)

    if trace is None:
        raise HTTPException(status_code=404, detail=f"追溯日志不存在: {trace_id}")

    return TraceResponse(
        trace_id=trace.trace_id,
        mention_id=trace.mention_id,
        skill_name="entity_linking",
        input_data={"mention_text": trace.mention_text, "entity_type": trace.entity_type},
        output_data=trace.final_result,
        timestamp=trace.start_time,
        duration_ms=trace.total_duration_ms,
        decision_reason=trace.steps[-1].reason if trace.steps else ""
    )


@router.get("/traces", tags=["追溯"])
async def list_traces(limit: int = 100):
    """列出最近的追溯日志。- limit: 返回数量上限"""
    traces = trace_logger.list_traces(limit)
    return {"traces": traces, "total": len(traces)}


@router.post("/trace/{trace_id}/replay", tags=["追溯"])
async def replay_trace(trace_id: str):
    """追溯回放。用原始输入重新执行一次链接，对比结果是否一致，用于审计验证。"""
    trace = trace_logger.get_trace(trace_id)
    if trace is None:
        trace = trace_logger.load_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"追溯日志不存在: {trace_id}")

    input_data = getattr(trace, "input_data", {})
    if not input_data or not input_data.get("full_text"):
        return {"trace_id": trace_id, "error": "该追溯日志未保存原始输入，无法回放"}

    mention = Mention(
        text=input_data["mention_text"],
        start_pos=input_data.get("start_pos", 0),
        end_pos=input_data.get("end_pos", len(input_data["mention_text"])),
        entity_type=input_data.get("entity_type", ""),
        context=input_data["full_text"],
    )
    result = _enhanced_link(mention, full_text=input_data["full_text"])

    return {
        "trace_id": trace_id,
        "replay": {
            "linked_entity": result.linked_entity.standard_name if result.linked_entity else None,
            "linked_id": result.linked_entity.id if result.linked_entity else None,
            "is_nil": result.is_nil,
            "confidence": result.confidence,
        },
        "original": {
            "linked_entity": trace.final_result.get("linked_entity_name"),
            "linked_id": trace.final_result.get("linked_entity_id"),
            "is_nil": trace.final_result.get("is_nil"),
        },
    }


@router.post("/trace/{trace_id}/rollback", tags=["追溯"])
async def rollback_trace(trace_id: str):
    """追溯回滚。返回链接前的原始mention状态，用于回退变更。"""
    trace = trace_logger.get_trace(trace_id)
    if trace is None:
        trace = trace_logger.load_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"追溯日志不存在: {trace_id}")

    input_data = getattr(trace, "input_data", {})
    return {
        "trace_id": trace_id,
        "original_mention": {
            "text": input_data.get("mention_text") or trace.mention_text,
            "entity_type": input_data.get("entity_type") or trace.entity_type,
        },
        "rollback_success": True,
    }


@router.post("/nil_check", response_model=NILResponse, tags=["NIL检测"])
async def nil_check(request: NILRequest):
    """NIL检测。判断指称文本在知识库中是否存在对应实体（不执行完整链接流程）。"""
    knowledge_base.search_by_alias(request.text)
    candidates = knowledge_base.search_by_alias(request.text)

    if not candidates:
        name_entity = knowledge_base.get_entity_by_name(request.text)
        if name_entity:
            candidates = [name_entity]

    nil_result = nil_detector.detect(
        mention_text=request.text,
        mention_type=request.entity_type or "",
        candidates=[] if not candidates else [Candidate(entity=c, score=0.95) for c in candidates],
    )

    return NILResponse(
        is_nil=nil_result.is_nil,
        confidence=nil_result.confidence,
        reason=nil_result.reason,
    )


@router.post("/coref", response_model=CorefResponse, tags=["共指消解"])
async def coref_resolve(request: CorefRequest):
    """共指消解。找出文本中的代词(她/他/它)和指代词(本次赛事/该队)，回链到前序实体。"""
    text = request.text
    mentions = []

    # 第一步：找出所有指代词
    for i, ch in enumerate(text):
        for size in range(1, 5):
            chunk = text[i:i + size]
            etype = is_coreference_mention(chunk)
            if etype:
                mentions.append({
                    "text": chunk, "start": i, "end": i + size,
                    "entity_type": etype, "entity_id": None,
                })

    if not mentions:
        return CorefResponse(results=[])

    # 第二步：回链
    import copy
    all_mentions = sorted(mentions, key=lambda m: m["start"])
    results = []
    for idx, m in enumerate(all_mentions):
        target = resolve_coreference(idx, all_mentions)
        results.append(CorefResult(
            index=m["start"],
            mention=m["text"],
            entity_type=m["entity_type"],
            coref_target=target["text"] if target else None,
            entity_id=target.get("entity_id") if target else None,
        ))

    return CorefResponse(results=results)


# ============ 辅助函数 ============

def _simple_link(mention: Mention) -> LinkResult:
    """
    简单的实体链接（Phase 1实现）

    仅使用别名精确匹配。
    """
    result = LinkResult(mention=mention)

    # 1. 别名精确匹配
    entities = knowledge_base.search_by_alias(mention.text)

    if not entities:
        # 也尝试标准名称匹配
        entity = knowledge_base.get_entity_by_name(mention.text)
        if entity:
            entities = [entity]

    if entities:
        # 如果有多个匹配，选择第一个（Phase 2会加入消歧）
        linked_entity = entities[0]
        result.linked_entity = linked_entity
        result.is_nil = False
        result.confidence = 0.95  # 精确匹配置信度高
        result.nil_reason = ""
    else:
        # NIL: 知识库中无对应实体
        result.linked_entity = None
        result.is_nil = True
        result.confidence = 0.0
        result.nil_reason = f"知识库中未找到与'{mention.text}'匹配的实体"

    return result


def _enhanced_link(mention: Mention, trace=None, full_text: str = "", article_domain: str = "") -> LinkResult:
    """
    增强的实体链接（Phase 2实现）

    多路召回 + 消歧：
    1. 标准名称匹配（最高优先级）
    2. 别名精确匹配
    3. BM25全文检索（仅在无精确匹配时使用）
    4. 消歧选择最佳候选
    """
    result = LinkResult(mention=mention)

    # 1. 标准名称匹配（最高优先级）
    # 如果标准名称完全匹配，直接返回
    name_entity = knowledge_base.get_entity_by_name(mention.text)
    if name_entity:
        result.linked_entity = name_entity
        result.is_nil = False
        result.confidence = 1.0
        result.nil_reason = ""
        # 记录追溯
        if trace:
            trace.add_step(
                step_name="标准名称匹配",
                original_value=mention.text,
                new_value=f"{name_entity.standard_name} ({name_entity.id})",
                reason=f"标准名称完全匹配"
            )
        return result

    # 2. 别名精确匹配
    alias_entities = knowledge_base.search_by_alias(mention.text)
    if alias_entities:
        if len(alias_entities) == 1:
            result.linked_entity = alias_entities[0]
            result.is_nil = False
            result.confidence = 0.95
            result.nil_reason = ""
            if trace:
                trace.add_step(step_name="别名精确匹配", original_value=mention.text,
                    new_value=f"{alias_entities[0].standard_name} ({alias_entities[0].id})",
                    reason="别名匹配成功")
            return result

        candidates = [Candidate(entity=e, score=0.95, match_source="alias") for e in alias_entities]
        ranked = disambiguator.disambiguate(mention, candidates, top_k=5, full_text=full_text, article_domain=article_domain)
        if ranked:
            ranked = _llm_fallback(mention, ranked, full_text, trace)
            best = ranked[0]
            result.linked_entity = best.entity
            result.is_nil = False
            result.confidence = best.score
            result.nil_reason = ""
            if trace:
                trace.add_step(step_name="别名匹配+消歧", original_value=mention.text,
                    new_value=f"{best.entity.standard_name} ({best.entity.id})",
                    reason=f"从{len(alias_entities)}个候选中选择，得分={best.score:.2f}")
            return result

    # 3. 模糊匹配（名称包含关系）
    fuzzy_candidates = []
    for entity in knowledge_base.entities.values():
        if mention.text in entity.standard_name:
            if len(entity.standard_name) - len(mention.text) <= 8:
                fuzzy_candidates.append(entity)
        elif entity.standard_name in mention.text:
            if len(mention.text) - len(entity.standard_name) <= 8:
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
            result.nil_reason = ""
            if trace:
                trace.add_step(step_name="模糊匹配", original_value=mention.text,
                    new_value=f"{fuzzy_candidates[0].standard_name} ({fuzzy_candidates[0].id})",
                    reason="名称包含关系匹配")
            return result

        candidates = [Candidate(entity=e, score=0.75, match_source="fuzzy") for e in fuzzy_candidates]
        ranked = disambiguator.disambiguate(mention, candidates, top_k=5, full_text=full_text, article_domain=article_domain)
        if ranked:
            ranked = _llm_fallback(mention, ranked, full_text, trace)
            best = ranked[0]
            result.linked_entity = best.entity
            result.is_nil = False
            result.confidence = best.score
            result.nil_reason = ""
            if trace:
                trace.add_step(step_name="模糊匹配消歧", original_value=mention.text,
                    new_value=f"{best.entity.standard_name} ({best.entity.id})",
                    reason=f"从{len(fuzzy_candidates)}个候选中消歧选择，得分={best.score:.2f}")
            return result

    # 4. BM25检索（仅在前面都没有匹配时使用）
    if bm25_index.built:
        bm25_results = bm25_index.search(mention.text, top_k=10)
        if bm25_results:
            if len(bm25_results) == 1:
                # 唯一候选直接使用
                best_entity_id, best_score = bm25_results[0]
                entity = knowledge_base.get_entity(best_entity_id)
                if entity:
                    normalized_score = min(best_score / 10.0, 0.7)
                    result.linked_entity = entity
                    result.is_nil = False
                    result.confidence = normalized_score
                    result.nil_reason = ""
                    if trace:
                        trace.add_step(
                            step_name="BM25检索",
                            original_value=mention.text,
                            new_value=f"{entity.standard_name} ({entity.id})",
                            reason=f"BM25唯一候选，相似度={best_score:.2f}"
                        )
                    return result
            else:
                # 多候选但BERT不可用，使用规则消歧器
                bm25_entities = []
                for entity_id, score in bm25_results:
                    entity = knowledge_base.get_entity(entity_id)
                    if entity:
                        bm25_entities.append(entity)

                if bm25_entities:
                    # 先按实体类型过滤
                    if mention.entity_type:
                        type_matched = [e for e in bm25_entities if e.entity_type == mention.entity_type]
                        if type_matched:
                            bm25_entities = type_matched

                    if len(bm25_entities) == 1:
                        result.linked_entity = bm25_entities[0]
                        result.is_nil = False
                        result.confidence = 0.65
                        result.nil_reason = ""
                        if trace:
                            trace.add_step(
                                step_name="BM25+类型过滤",
                                original_value=mention.text,
                                new_value=f"{bm25_entities[0].standard_name} ({bm25_entities[0].id})",
                                reason="BM25多候选经类型过滤后唯一"
                            )
                        return result

                    # 多候选使用消歧器
                    candidates = [Candidate(entity=e, score=0.5, match_source="bm25")
                                  for e in bm25_entities]
                    ranked = disambiguator.disambiguate(mention, candidates, top_k=5, full_text=full_text, article_domain=article_domain)
                    if ranked:
                        ranked = _llm_fallback(mention, ranked, full_text, trace)
                        best = ranked[0]
                        result.linked_entity = best.entity
                        result.is_nil = False
                        result.confidence = best.score
                        result.nil_reason = ""
                        if trace:
                            trace.add_step(
                                step_name="BM25+消歧",
                                original_value=mention.text,
                                new_value=f"{best.entity.standard_name} ({best.entity.id})",
                                reason=f"BM25召回{len(bm25_entities)}个候选，消歧得分={best.score:.2f}"
                            )
                        return result

    # NIL: 知识库中无对应实体，或使用NIL检测器验证低置信度结果
    # 如果之前各阶段均未找到匹配，使用NIL检测器做最终判定
    nil_check = nil_detector.detect(
        mention_text=mention.text,
        mention_type=mention.entity_type or "",
        candidates=[],
        best_candidate=None
    )

    result.linked_entity = None
    result.is_nil = True
    result.confidence = nil_check.confidence if nil_check.is_nil else 0.0
    result.nil_reason = nil_check.reason if nil_check.is_nil else f"知识库中未找到与'{mention.text}'匹配的实体"
    if trace:
        trace.add_step(
            step_name="NIL判定",
            original_value=mention.text,
            new_value="NIL",
            reason=result.nil_reason
        )

    return result


def _llm_fallback(mention: Mention, ranked: list, full_text: str, trace=None) -> list:
    """
    LLM消歧兜底：当规则消歧器top-2得分差<阈值时，用LLM重判。
    返回重排后的候选列表。
    """
    if not config.llm_enabled or not llm_disambiguator.available:
        return ranked
    if len(ranked) < 2:
        return ranked

    gap = ranked[0].score - ranked[1].score
    if gap >= config.llm_score_gap:
        return ranked  # 得分差足够大，信任规则消歧器

    if trace:
        trace.add_step(
            step_name="LLM消歧",
            original_value=f"top-2 gap={gap:.3f}<{config.llm_score_gap}",
            new_value="调用LLM...",
            reason="规则消歧得分过于接近，调用LLM判别"
        )

    llm_ranked = llm_disambiguator.disambiguate(mention, ranked, full_text)

    if trace and llm_ranked and llm_ranked[0].entity.id != ranked[0].entity.id:
        trace.add_step(
            step_name="LLM消歧结果",
            original_value=ranked[0].entity.standard_name,
            new_value=llm_ranked[0].entity.standard_name,
            reason="LLM根据文章语境选择了不同候选"
        )

    return llm_ranked


def _to_response(result: LinkResult) -> LinkResponse:
    """将LinkResult转换为LinkResponse"""
    linked_entity_resp = None
    if result.linked_entity:
        linked_entity_resp = EntityResponse(
            id=result.linked_entity.id,
            standard_name=result.linked_entity.standard_name,
            entity_type=result.linked_entity.entity_type,
            aliases=result.linked_entity.aliases,
            description=result.linked_entity.description,
        )

    return LinkResponse(
        linked_entity=linked_entity_resp,
        is_nil=result.is_nil,
        confidence=result.confidence,
        nil_reason=result.nil_reason,
        trace_id=result.trace_id,
        processing_time_ms=result.processing_time_ms,
    )
