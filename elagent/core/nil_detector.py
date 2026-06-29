"""
NIL检测模块

正确识别知识库中不存在的实体。
"""

import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from ..models.entity import Entity, Candidate

logger = logging.getLogger(__name__)


@dataclass
class NILResult:
    """
    NIL检测结果

    Attributes:
        is_nil: 是否为NIL
        confidence: 置信度（0-1）
        reason: 判定理由
        signals: 各信号值
    """
    is_nil: bool
    confidence: float
    reason: str
    signals: Dict = None

    def __post_init__(self):
        if self.signals is None:
            self.signals = {}


class NILDetector:
    """
    NIL检测器

    采用多信号融合的判定策略，综合候选检索得分、
    类型一致性、语义相似度等多个维度信号。
    """

    def __init__(self):
        """初始化NIL检测器"""
        # 阈值配置
        self.score_threshold = 0.4  # 最低分数阈值
        self.type_mismatch_as_nil = True  # 类型不一致视为NIL

    def detect(self,
               mention_text: str,
               mention_type: str,
               candidates: List[Candidate],
               best_candidate: Optional[Candidate] = None) -> NILResult:
        """
        NIL检测

        Args:
            mention_text: 指称文本
            mention_type: 指称类型
            candidates: 候选列表
            best_candidate: 最佳候选

        Returns:
            NIL检测结果
        """
        signals = {}

        # 信号1：是否有候选
        has_candidates = len(candidates) > 0
        signals["has_candidates"] = has_candidates

        if not has_candidates:
            return NILResult(
                is_nil=True,
                confidence=0.95,
                reason="未找到任何候选实体",
                signals=signals
            )

        # 信号2：最佳候选分数
        if best_candidate:
            best_score = best_candidate.score
        else:
            best_score = max(c.score for c in candidates)
        signals["best_score"] = best_score

        # 信号3：类型一致性
        type_match = False
        if best_candidate and mention_type:
            type_match = best_candidate.entity.entity_type == mention_type
        signals["type_match"] = type_match

        # 信号4：候选分数分布
        scores = [c.score for c in candidates]
        score_std = self._calculate_std(scores)
        signals["score_std"] = score_std

        # 综合判定
        is_nil = False
        confidence = 0.0
        reasons = []

        # 规则1：分数过低
        if best_score < self.score_threshold:
            is_nil = True
            confidence = 0.8
            reasons.append(f"最佳候选分数过低({best_score:.2f}<{self.score_threshold})")

        # 规则2：类型不一致
        if self.type_mismatch_as_nil and mention_type and not type_match:
            is_nil = True
            confidence = max(confidence, 0.7)
            reasons.append(f"类型不一致(mention={mention_type}, entity={best_candidate.entity.entity_type if best_candidate else 'N/A'})")

        # 规则3：分数方差过小（无法区分）
        if score_std < 0.1 and len(candidates) > 1:
            is_nil = True
            confidence = max(confidence, 0.6)
            reasons.append(f"候选分数方差过小({score_std:.3f})")

        if not is_nil:
            confidence = 1.0 - best_score  # 置信度与分数相反
            reason = f"找到匹配实体，分数={best_score:.2f}"
        else:
            reason = "; ".join(reasons)

        return NILResult(
            is_nil=is_nil,
            confidence=confidence,
            reason=reason,
            signals=signals
        )

    def _calculate_std(self, values: List[float]) -> float:
        """计算标准差"""
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5


# 全局NIL检测器实例
nil_detector = NILDetector()
