"""
消歧模块

提供上下文消歧能力，从候选实体中选择最匹配的实体。
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import Counter

import jieba

from ..models.entity import Entity, Candidate
from ..models.mention import Mention

logger = logging.getLogger(__name__)


class Disambiguator:
    """
    消歧器

    通过多种信号从候选实体中选择最匹配的实体。

    消歧策略（分层漏斗）：
    1. 类型过滤 - 候选实体类型必须与mention类型一致
    2. 规则粗排 - 关键词重叠度 + 实体流行度
    3. 综合打分 - 加权融合多个信号
    """

    def __init__(self):
        """初始化消歧器"""
        # 权重分配：
        #   - 名称匹配是最高优先级信号
        #   - 先验概率基于标注数据统计
        #   - keyword_weight 现在承载上下文得分（区分词文档命中+局部重叠）
        self.name_match_weight = 0.15         # 名称匹配度
        self.prior_weight = 0.17              # 先验概率
        self.name_completeness_weight = 0.15  # 名称完整度
        self.type_weight = 0.15               # 类型一致性
        self.keyword_weight = 0.00            # 关键词重叠
        self.popularity_weight = 0.00         # 实体流行度
        self.domain_weight = 0.15             # 领域匹配（加性）

        # 加载先验概率
        self.prior_probs = self._load_prior_probs()

    def _load_prior_probs(self) -> Dict[str, float]:
        """加载先验概率"""
        prior_path = Path('data/prior_probabilities.json')
        if prior_path.exists():
            with open(prior_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def disambiguate(self,
                     mention: Mention,
                     candidates: List[Candidate],
                     top_k: int = 1,
                     full_text: str = "") -> List[Candidate]:
        if not candidates:
            return []
        if len(candidates) == 1:
            return candidates

        if mention.entity_type:
            type_matched = [c for c in candidates if c.entity.entity_type == mention.entity_type]
            if type_matched:
                candidates = type_matched

        all_entities = [c.entity for c in candidates]
        scored_candidates = []
        for candidate in candidates:
            score = self._compute_score(mention, candidate, full_text, all_entities)
            candidate.score = score
            scored_candidates.append(candidate)
        scored_candidates.sort(key=lambda x: x.score, reverse=True)

        return scored_candidates[:top_k]

    def _compute_score(self, mention: Mention, candidate: Candidate, full_text: str = "",
                        all_entities: list = None) -> float:
        """
        计算候选实体的综合得分

        Args:
            mention: 实体指称
            candidate: 候选实体

        Returns:
            综合得分 (0-1)
        """
        entity = candidate.entity

        # 1. 类型一致性得分
        type_score = self._type_match_score(mention, entity)

        # 2. 关键词重叠得分（全文）
        keyword_score = self._keyword_overlap_score(mention, entity, full_text)

        # 3. 领域匹配得分（加性）
        domain_score = self._domain_score(mention, entity, full_text, all_entities)

        # 4. 先验概率得分
        prior_score = self._prior_probability_score(entity)

        # 5. 名称匹配得分
        name_score = self._name_match_score(mention, entity)

        # 6. 名称完整性得分
        completeness_score = self._name_completeness_score(mention, entity)

        # 7. 实体流行度得分
        popularity_score = self._popularity_score(entity)

        # 加权融合
        total_score = (
            self.type_weight * type_score +
            self.keyword_weight * keyword_score +
            self.prior_weight * prior_score +
            self.name_match_weight * name_score +
            self.name_completeness_weight * completeness_score +
            self.popularity_weight * popularity_score +
            self.domain_weight * domain_score
        )

        return total_score

    def _prior_probability_score(self, entity: Entity) -> float:
        """
        计算先验概率得分

        基于实体在标注数据中出现的频率。

        Args:
            entity: 候选实体

        Returns:
            先验概率得分 (0-1)
        """
        if not self.prior_probs:
            return 0.5  # 无先验概率时给中间分

        prob = self.prior_probs.get(entity.id, 0.0)

        # 归一化到0-1（使用log缩放，避免高频实体过于主导）
        if prob > 0:
            import math
            # 使用log缩放，最大概率约为0.015，归一化到0-1
            normalized = min(math.log(prob * 1000 + 1) / math.log(20), 1.0)
            return normalized

        return 0.1  # 未出现过的实体给低分

    def _type_match_score(self, mention: Mention, entity: Entity) -> float:
        """
        计算类型匹配得分

        Args:
            mention: 实体指称
            entity: 候选实体

        Returns:
            类型匹配得分 (0或1)
        """
        if not mention.entity_type:
            return 0.5  # 无类型信息时给中间分

        if mention.entity_type.upper() == entity.entity_type.upper():
            return 1.0

        return 0.0

    def _keyword_overlap_score(self, mention: Mention, entity: Entity,
                                full_text: str = "") -> float:
        """关键词重叠：全文与实体名的分词重叠率"""
        text = full_text or mention.context or ""
        if not text:
            return 0.5
        text_tokens = set(jieba.cut(text))
        all_names = [entity.standard_name] + list(entity.aliases)
        name_tokens = set()
        for name in all_names:
            name_tokens.update(jieba.cut(name))
        stop_words = {"的", "了", "在", "是", "和", "就", "不", "一", "个"}
        text_tokens -= stop_words
        name_tokens -= stop_words
        if not text_tokens or not name_tokens:
            return 0.5
        overlap = text_tokens & name_tokens
        return len(overlap) / max(len(name_tokens), 1)

    def _domain_score(self, mention: Mention, entity: Entity, full_text: str = "",
                       all_entities: list = None) -> float:
        """领域匹配得分（加性）：实体名区分2-gram在全文中的命中密度"""
        full_text = (full_text or mention.context or "").lower()
        if len(full_text) < 10:
            return 0.0

        all_names = [entity.standard_name] + list(entity.aliases)
        entity_bigrams = set()
        for name in all_names:
            name_lower = name.lower()
            for i in range(len(name_lower) - 1):
                entity_bigrams.add(name_lower[i:i+2])

        mention_bigrams = set()
        mt = mention.text.lower()
        for i in range(len(mt) - 1):
            mention_bigrams.add(mt[i:i+2])

        diff_bigrams = entity_bigrams - mention_bigrams
        if not diff_bigrams:
            return 0.0

        total_hits = sum(full_text.count(bg) for bg in diff_bigrams)
        text_len = max(len(full_text), 1)
        density = total_hits / (text_len / 100.0)

        return min(density / 5.0, 1.0)

    def _name_match_score(self, mention: Mention, entity: Entity) -> float:
        """
        计算名称匹配得分

        精确匹配得分最高，确保精确匹配的实体优先被选中。
        对于简称/缩写匹配全称的场景，添加惩罚因子避免短名称过度胜出。

        Args:
            mention: 实体指称
            entity: 候选实体

        Returns:
            名称匹配得分 (0-1)
        """
        mention_text = mention.text.lower()
        standard_name = entity.standard_name.lower()
        aliases = [a.lower() for a in entity.aliases]

        # 计算基础得分
        base_score = self._compute_raw_name_score(mention_text, standard_name, aliases)

        # 短名称惩罚：当实体标准名比mention短时，降低得分
        # 例如：mention="银川高铁站"，entity="银川站" → 惩罚
        if len(standard_name) < len(mention_text):
            short_penalty = max(len(standard_name) / len(mention_text), 0.5)
            base_score *= short_penalty

        return base_score

    def _compute_raw_name_score(self, mention_text: str, standard_name: str, aliases: list) -> float:
        """计算原始名称匹配得分（不含长度惩罚）"""
        # 精确匹配（最高优先级）
        if mention_text == standard_name:
            # 短名称惩罚：当mention精确命中实体名时，
            # 该实体可能就是简称本身（如KB中同时有"浙江队"和"浙江省羽毛球队"）
            if len(standard_name) <= 2:
                return 0.75  # 1-2字：几乎肯定是简称
            elif len(standard_name) == 3:
                return 0.80  # 3字：如"浙江队""日本队"
            elif len(standard_name) == 4:
                return 0.85  # 4字：轻微惩罚
            elif len(standard_name) <= 5:
                return 0.90
            return 1.0

        # 别名精确匹配
        if mention_text in aliases:
            return 0.95

        # 标准名称包含mention（如"宁夏回族自治区"包含"宁夏"）
        if mention_text in standard_name:
            # 计算包含比例，越接近完整名称得分越高
            ratio = len(mention_text) / len(standard_name)
            # 越接近完整名称，得分越高
            return 0.7 + 0.25 * ratio  # 0.7-0.95

        # mention包含标准名称
        if standard_name in mention_text:
            # 标准名称越长，得分越高
            ratio = len(standard_name) / len(mention_text)
            return 0.6 + 0.1 * ratio

        # 别名包含匹配
        for alias in aliases:
            if mention_text in alias:
                ratio = len(mention_text) / len(alias)
                return 0.5 + 0.2 * ratio
            if alias in mention_text:
                return 0.5

        return 0.2

    def _popularity_score(self, entity: Entity) -> float:
        """
        计算实体流行度得分

        基于实体别名数量计算流行度，别名越多说明越常用。

        Args:
            entity: 候选实体

        Returns:
            流行度得分 (0-1)
        """
        alias_count = len(entity.aliases)
        if alias_count == 0:
            return 0.3
        # 使用对数缩放，避免别名过多时得分过高
        import math
        return min(math.log(alias_count + 1) / math.log(10), 1.0)

    def _name_completeness_score(self, mention: Mention, entity: Entity) -> float:
        """
        计算名称完整性得分

        优先选择名称更完整的实体（全称优先于简称）。
        例如："中国国家羽毛球队" 优先于 "国羽"

        Args:
            mention: 实体指称
            entity: 候选实体

        Returns:
            名称完整性得分 (0-1)
        """
        mention_text = mention.text
        standard_name = entity.standard_name

        # 实体名比mention长超过50% → 是全称，给高分
        if len(standard_name) > len(mention_text) * 1.5:
            return 0.9

        # 实体名比mention长超过20% → 较完整
        if len(standard_name) > len(mention_text) * 1.2:
            return 0.8

        # 长度相近 → 中等分
        if len(standard_name) >= len(mention_text):
            return 0.7

        # 实体名比mention短 → 两种情况
        # A. mention是过度指定（如"银川高铁站"→"银川站"）：实体字符是mention子集 → 高分
        if set(standard_name).issubset(set(mention_text)):
            return 0.85
        # B. mention是全称实体是简称（如"中国羽毛球队"→"国羽"）：低分
        return 0.3


# 全局消歧器实例
disambiguator = Disambiguator()
