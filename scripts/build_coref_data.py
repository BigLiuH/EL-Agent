"""
构建共指消解数据集

第1步：自动提取人称代词和指示代词
第2步：规则回链到最近同类型前序 mention
第3步：融合到 llm_extracted_merged.json 中
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
ARTICLES_PATH = ROOT / "Dataset" / "llm_extracted_merged.json"
OUTPUT_PATH = ROOT / "Dataset" / "llm_extracted_with_coref.json"

# === 代词匹配规则 ===
# 人称代词
PERSONAL_PRONOUNS = {
    "她": "PER",
    "他": "PER",
    "它": "ORG",       # 通常指组织/事物
    "她们": "PER",
    "他们": "PER",
    "她们": "PER",
    "其": "PER",       # 多用于正式文本
}

# 指示代词模式 (pattern, entity_type)
DEMONSTRATIVE_PATTERNS = [
    (r"该队", "ORG"),
    (r"该选手", "PER"),
    (r"这位选手", "PER"),
    (r"这名选手", "PER"),
    (r"该运动员", "PER"),
    (r"这名运动员", "PER"),
    (r"该球员", "PER"),
    (r"该名将", "PER"),
    (r"该教练", "PER"),
    (r"该组合", "ORG"),
    (r"这支队伍", "ORG"),
    (r"该支队", "ORG"),
    (r"本次赛事", "EVENT"),
    (r"该赛事", "EVENT"),
    (r"本届赛事", "EVENT"),
    (r"本届比赛", "EVENT"),
    (r"本次比赛", "EVENT"),
    (r"该比赛", "EVENT"),
    (r"该项目", "EVENT"),
    (r"该组织", "ORG"),
    (r"该协会", "ORG"),
    (r"该俱乐部", "ORG"),
    (r"该公司", "ORG"),
    (r"该企业", "ORG"),
    (r"该品牌", "ORG"),
    (r"该地区", "LOC"),
    (r"该城市", "LOC"),
    (r"该省", "LOC"),
    (r"该国", "LOC"),
    (r"该场馆", "LOC"),
    (r"该场地", "LOC"),
    (r"此地", "LOC"),
    (r"这里", "LOC"),
]

# 反例：不应被当作指代词的情况
EXCLUDE_PATTERNS = [
    r"其他",
    r"其他选手",
    r"其他队伍",
    r"其他人",
    r"其它",
]


def find_pronouns_in_text(text: str, existing_mentions: list) -> list:
    """在文本中找到所有代词/指代词的位置"""
    # 获取已有 mention 的位置范围（避免重复标注）
    existing_ranges = [(m["start"], m["end"]) for m in existing_mentions]

    new_mentions = []

    # 1. 人称代词
    for pronoun, etype in PERSONAL_PRONOUNS.items():
        for match in re.finditer(re.escape(pronoun), text):
            start, end = match.start(), match.end()
            # 检查是否和已有 mention 重叠
            if any(s <= start < e or s < end <= e for s, e in existing_ranges):
                continue
            new_mentions.append({
                "text": pronoun,
                "start": start,
                "end": end,
                "entity_type": etype,
                "is_coref": True,
                "coref_source": "personal_pronoun",
            })

    # 2. 指示代词
    for pattern, etype in DEMONSTRATIVE_PATTERNS:
        for match in re.finditer(pattern, text):
            start, end = match.start(), match.end()
            if any(s <= start < e or s < end <= e for s, e in existing_ranges):
                continue
            new_mentions.append({
                "text": match.group(),
                "start": start,
                "end": end,
                "entity_type": etype,
                "is_coref": True,
                "coref_source": "demonstrative",
            })

    return new_mentions


def resolve_coref(mention: dict, prev_mentions: list, same_sentence_only: bool = False) -> dict:
    """
    回链：找到最近的前序同类型 mention。
    优先同句，无同句则向前找。
    """
    etype = mention["entity_type"]
    candidates = [m for m in prev_mentions if m.get("entity_type") == etype and not m.get("is_coref")]

    if not candidates:
        # 允许回链到前序共指 mention（链式回指）
        candidates = [m for m in prev_mentions if m.get("entity_type") == etype]

    if not candidates:
        mention["coref_target"] = None
        mention["coref_resolved"] = False
        return mention

    # 选位置最近的（end 最大的）
    candidates.sort(key=lambda m: m["end"], reverse=True)
    target = candidates[0]

    mention["coref_target"] = target.get("standard_name") or target["text"]
    mention["coref_target_entity_id"] = target.get("entity_id")
    mention["coref_target_start"] = target["start"]
    mention["coref_target_end"] = target["end"]
    mention["coref_resolved"] = True

    return mention


def main():
    print("加载文章数据...")
    with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
        articles = json.load(f)

    total_coref = 0
    total_resolved = 0

    for art_idx, article in enumerate(articles):
        text = article.get("text", "")
        existing_mentions = article.get("mentions", [])

        # 第一步：找到所有代词
        pronoun_mentions = find_pronouns_in_text(text, existing_mentions)

        # 第二步：回链
        all_mentions = existing_mentions.copy()
        for pm in pronoun_mentions:
            resolved = resolve_coref(pm, all_mentions)
            all_mentions.append(resolved)
            total_coref += 1
            if resolved.get("coref_resolved"):
                total_resolved += 1

        # 第三步：按位置排序所有 mention
        all_mentions.sort(key=lambda m: m["start"])
        article["mentions"] = all_mentions

        if art_idx % 200 == 0:
            print(f"  进度: {art_idx}/{len(articles)}")

    print(f"\n=== 共指数据构建完成 ===")
    print(f"总文章数: {len(articles)}")
    print(f"提取代词/指代词: {total_coref}")
    print(f"成功回链: {total_resolved} ({total_resolved/max(total_coref,1)*100:.1f}%)")
    print(f"回链失败: {total_coref - total_resolved}")

    # 保存
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"\n已保存到: {OUTPUT_PATH}")

    # 统计样本
    coref_samples = []
    for art in articles:
        for m in art["mentions"]:
            if m.get("is_coref"):
                coref_samples.append(m)
                if len(coref_samples) >= 5:
                    break
        if len(coref_samples) >= 5:
            break

    print(f"\n=== 样本展示 ===")
    for m in coref_samples:
        print(f"  '{m['text']}' ({m['entity_type']}) → '{m.get('coref_target', '未解析')}'")


if __name__ == "__main__":
    main()
