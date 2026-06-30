"""
共指消解模块

代词/指代词回链到前序实体提及。
按任务书要求：共指消解准确率 ≥ 80%。
"""

import re
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

# 人称代词 → 实体类型映射
PERSONAL_PRONOUN_TYPE = {
    "她": "PER",
    "他": "PER",
    "她们": "PER",
    "他们": "PER",
    "它": "ORG",
    "其": "PER",
}

# 指示代词模式 → 实体类型
DEMONSTRATIVE_PATTERNS = [
    (r"^本次赛事$", "EVENT"),
    (r"^该赛事$", "EVENT"),
    (r"^本届赛事$", "EVENT"),
    (r"^本届比赛$", "EVENT"),
    (r"^本次比赛$", "EVENT"),
    (r"^该比赛$", "EVENT"),
    (r"^此项赛事$", "EVENT"),
    (r"^该项赛事$", "EVENT"),
    (r"^此役$", "EVENT"),
    (r"^该队$", "ORG"),
    (r"^该组合$", "ORG"),
    (r"^该支队$", "ORG"),
    (r"^该队伍$", "ORG"),
    (r"^该组织$", "ORG"),
    (r"^该协会$", "ORG"),
    (r"^该俱乐部$", "ORG"),
    (r"^该公司$", "ORG"),
    (r"^该品牌$", "ORG"),
    (r"^本次大会$", "EVENT"),
    (r"^该大会$", "EVENT"),
    (r"^本次活动$", "EVENT"),
    (r"^该活动$", "EVENT"),
    (r"^该地区$", "LOC"),
    (r"^该城市$", "LOC"),
    (r"^该省$", "LOC"),
    (r"^该国$", "LOC"),
    (r"^该场馆$", "LOC"),
    (r"^该场地$", "LOC"),
    (r"^该地点$", "LOC"),
]


def is_coreference_mention(text: str) -> Optional[str]:
    """判断是否为指代词，返回实体类型"""
    if text in PERSONAL_PRONOUN_TYPE:
        return PERSONAL_PRONOUN_TYPE[text]
    for pattern, etype in DEMONSTRATIVE_PATTERNS:
        if re.match(pattern, text):
            return etype
    return None


def resolve_coreference(mention_index: int, all_mentions: List[Dict]) -> Optional[Dict]:
    """
    回链：找到最近的前序非指代 mention。

    策略：按优先级
    1. 同类型 + 非指代 → 最可靠
    2. 非同类型 + 非指代 → 兜底
    3. 同类型指代 → 链式回指

    Args:
        mention_index: 当前指代词在列表中的位置
        all_mentions: 按 start 排序的全部 mention 列表

    Returns:
        目标 mention，或 None
    """
    current = all_mentions[mention_index]
    target_type = current.get("entity_type")

    # 策略1：同类型非指代 mention
    for i in range(mention_index - 1, -1, -1):
        prev = all_mentions[i]
        if prev.get("entity_type") == target_type and not is_coreference_mention(prev.get("text", "")):
            return prev

    # 策略2：任意非同类型非指代（兜底）
    for i in range(mention_index - 1, -1, -1):
        prev = all_mentions[i]
        if not is_coreference_mention(prev.get("text", "")):
            return prev

    # 策略3：同类型指代（链式回指）
    for i in range(mention_index - 1, -1, -1):
        prev = all_mentions[i]
        if prev.get("entity_type") == target_type:
            return prev

    return None


def evaluate_coref(articles: List[Dict]) -> Dict:
    """
    评测共指消解准确率

    对每篇文章：
    1. 找到所有指代词 mention
    2. 用规则回链到前序同类型 mention
    3. 对比回链目标的 entity_id 与标注的 entity_id

    Returns:
        {accuracy, total, correct, errors}
    """
    total = 0
    correct = 0
    errors = []

    for article in articles:
        mentions = sorted(article.get("mentions", []), key=lambda m: m["start"])

        for idx, mention in enumerate(mentions):
            if not is_coreference_mention(mention.get("text", "")):
                continue

            total += 1
            target = resolve_coreference(idx, mentions)

            if target:
                predicted_id = target.get("entity_id")
                expected_id = mention.get("entity_id")

                if predicted_id == expected_id:
                    correct += 1
                else:
                    errors.append({
                        "mention": mention["text"],
                        "expected": expected_id,
                        "predicted": predicted_id,
                        "target_text": target.get("text", ""),
                        "article_text": article.get("text", "")[:100],
                    })
            else:
                # 无法回链
                expected_id = mention.get("entity_id")
                errors.append({
                    "mention": mention["text"],
                    "expected": expected_id,
                    "predicted": None,
                    "target_text": None,
                    "article_text": article.get("text", "")[:100],
                })

    accuracy = correct / max(total, 1)
    return {
        "accuracy": accuracy,
        "total": total,
        "correct": correct,
        "errors": errors[:50],
    }
