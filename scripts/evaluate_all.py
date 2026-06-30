"""
实体链接与知识对齐智能体 - 完整评测脚本

按任务书要求计算全部指标：
1. 链接准确率        ≥ 85%
2. 消歧准确率        ≥ 85%
3. NIL检测 F1        ≥ 0.80
4. 别名标准化召回率   ≥ 85%
5. 共指消解准确率     ≥ 80%（--enable-coref 按需启用）

用法:
  python scripts/evaluate_all.py                        # 全部（含共指）
  python scripts/evaluate_all.py --no-coref             # 不含共指
  python scripts/evaluate_all.py --max-articles 100     # 小规模
"""

import json
import time
import sys
import argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.knowledge_base import knowledge_base
from elagent.core.bm25_index import bm25_index
from elagent.core.llm_disambiguator import llm_disambiguator
from elagent.core.coref_resolver import evaluate_coref, resolve_coreference, is_coreference_mention
from elagent.models.mention import Mention
from elagent.api.routes import _enhanced_link


def evaluate_entity_linking(articles, max_articles=99999):
    """评测实体链接（链接准确率 + 消歧准确率 + 别名召回率）"""
    articles = articles[:max_articles]

    total_mentions = 0
    correct_links = 0
    multi_candidate_total = 0
    multi_candidate_correct = 0
    single_candidate_total = 0
    single_candidate_correct = 0
    alias_mentions = 0
    alias_correct = 0
    errors = []
    mention_errors = defaultdict(list)

    for art_idx, article in enumerate(articles):
        if art_idx % 200 == 0:
            print(f"  实体链接进度: {art_idx}/{len(articles)}")

        text = article.get("text", "")
        for mention_data in article.get("mentions", []):
            # 跳过指代词 mention
            if mention_data.get("is_coref") or is_coreference_mention(mention_data.get("text", "")):
                continue

            total_mentions += 1
            expected_id = mention_data.get("entity_id")
            expected_name = mention_data.get("standard_name", "")

            mention = Mention(
                text=mention_data["text"],
                start_pos=mention_data["start"],
                end_pos=mention_data["end"],
                entity_type=mention_data.get("entity_type"),
                context=text,
            )

            result = _enhanced_link(mention, full_text=text)

            is_correct = False
            if result.linked_entity:
                if result.linked_entity.standard_name == expected_name:
                    is_correct = True
                elif result.linked_entity.id == expected_id:
                    is_correct = True

            if is_correct:
                correct_links += 1
            else:
                errors.append({
                    "mention": mention.text,
                    "expected_name": expected_name,
                    "predicted_name": result.linked_entity.standard_name if result.linked_entity else "NIL",
                    "entity_type": mention_data.get("entity_type"),
                })
                mention_errors[mention.text].append({
                    "expected_name": expected_name,
                    "predicted_name": result.linked_entity.standard_name if result.linked_entity else "NIL",
                })

            # 消歧统计
            alias_candidates = knowledge_base.search_by_alias(mention.text)
            name_candidate = knowledge_base.get_entity_by_name(mention.text)
            all_candidates = set()
            if name_candidate:
                all_candidates.add(name_candidate.id)
            for c in alias_candidates:
                all_candidates.add(c.id)

            if len(all_candidates) == 1:
                single_candidate_total += 1
                if is_correct:
                    single_candidate_correct += 1
            elif len(all_candidates) > 1:
                multi_candidate_total += 1
                if is_correct:
                    multi_candidate_correct += 1

            if alias_candidates:
                alias_mentions += 1
                if is_correct:
                    alias_correct += 1

    return {
        "link_accuracy": correct_links / max(total_mentions, 1),
        "disambiguation_accuracy": multi_candidate_correct / max(multi_candidate_total, 1),
        "alias_recall": alias_correct / max(alias_mentions, 1),
        "single_candidate_accuracy": single_candidate_correct / max(single_candidate_total, 1),
        "total_mentions": total_mentions,
        "correct_links": correct_links,
        "multi_candidate_total": multi_candidate_total,
        "multi_candidate_correct": multi_candidate_correct,
        "alias_mentions": alias_mentions,
        "alias_correct": alias_correct,
        "errors": errors,
        "mention_errors": mention_errors,
    }


def main():
    parser = argparse.ArgumentParser(description="实体链接与知识对齐智能体 - 完整评测")
    parser.add_argument("--no-coref", action="store_true", help="跳过共指消解评测")
    parser.add_argument("--max-articles", type=int, default=99999, help="最大评测文章数")
    parser.add_argument("--articles", default="Dataset/llm_extracted_merged.json", help="实体链接数据")
    parser.add_argument("--coref-articles", default="Dataset/annotations_with_pronouns_v2.json", help="共指消解数据")
    args = parser.parse_args()

    enable_coref = not args.no_coref

    print("=" * 60)
    print("实体链接与知识对齐智能体 - 完整评测")
    print("=" * 60)

    # ==========================================
    # 初始化
    # ==========================================
    print("\n[初始化] 加载知识库...")
    knowledge_base.load()
    print(f"  实体数: {knowledge_base.entity_count}")

    llm_disambiguator.reset()

    print("  构建BM25索引...")
    bm25_index.build(knowledge_base.entities)

    # ==========================================
    # 1-4: 实体链接评测
    # ==========================================
    print(f"\n[实体链接] 加载数据: {args.articles}")
    with open(args.articles, "r", encoding="utf-8") as f:
        el_articles = json.load(f)
    print(f"  文章数: {len(el_articles)}")

    el_result = evaluate_entity_linking(el_articles, args.max_articles)

    # ==========================================
    # 5: 共指消解评测（按需启用）
    # ==========================================
    coref_result = None
    if enable_coref:
        print(f"\n[共指消解] 加载数据: {args.coref_articles}")
        coref_path = Path(args.coref_articles)
        if coref_path.exists():
            with open(coref_path, "r", encoding="utf-8") as f:
                coref_articles = json.load(f)
            coref_articles = coref_articles[:args.max_articles]
            print(f"  文章数: {len(coref_articles)}")
            coref_result = evaluate_coref(coref_articles)
        else:
            print(f"  文件不存在，跳过共指评测（需先合并数据）")

    # ==========================================
    # 输出报告
    # ==========================================
    print("\n" + "=" * 60)
    print("评测结果")
    print("=" * 60)

    print(f"\n一、链接准确率")
    print(f"  样本数: {el_result['total_mentions']}")
    print(f"  正确: {el_result['correct_links']}")
    print(f"  准确率: {el_result['link_accuracy']:.2%}")
    print(f"  目标: >= 85%  {'PASS' if el_result['link_accuracy'] >= 0.85 else 'FAIL'}")

    print(f"\n二、消歧准确率")
    print(f"  多候选: {el_result['multi_candidate_total']}")
    print(f"  正确: {el_result['multi_candidate_correct']}")
    print(f"  准确率: {el_result['disambiguation_accuracy']:.2%}")
    print(f"  目标: >= 85%  {'PASS' if el_result['disambiguation_accuracy'] >= 0.85 else 'FAIL'}")

    print(f"\n三、别名标准化")
    print(f"  别名数: {el_result['alias_mentions']}")
    print(f"  正确: {el_result['alias_correct']}")
    print(f"  召回率: {el_result['alias_recall']:.2%}")
    print(f"  目标: >= 85%  {'PASS' if el_result['alias_recall'] >= 0.85 else 'FAIL'}")

    print(f"\n四、NIL检测")
    print(f"  注: 当前数据集无NIL样本，暂未计算")

    if coref_result:
        print(f"\n五、共指消解 [按需启用]")
        print(f"  指代词数: {coref_result['total']}")
        print(f"  正确: {coref_result['correct']}")
        print(f"  准确率: {coref_result['accuracy']:.2%}")
        print(f"  目标: >= 80%  {'PASS' if coref_result['accuracy'] >= 0.8 else 'FAIL'}")
    elif enable_coref:
        print(f"\n五、共指消解 [按需启用]")
        print(f"  状态: 数据文件不存在，跳过")

    print(f"\n六、单候选准确率")
    single = el_result["single_candidate_accuracy"]
    print(f"  准确率: {single:.2%}")

    # 高频错误
    print(f"\n七、高频实体链接错误 (Top 15)")
    for mention, errs in sorted(el_result["mention_errors"].items(), key=lambda x: -len(x[1]))[:15]:
        print(f"  {mention} ({len(errs)}次) 预期={errs[0]['expected_name']}  预测={errs[0]['predicted_name']}")

    # 保存报告
    report = {
        "metrics": {
            "link_accuracy": round(el_result["link_accuracy"], 4),
            "disambiguation_accuracy": round(el_result["disambiguation_accuracy"], 4),
            "alias_recall": round(el_result["alias_recall"], 4),
            "single_candidate_accuracy": round(single, 4),
            "total_mentions": el_result["total_mentions"],
            "correct_links": el_result["correct_links"],
            "multi_candidate_total": el_result["multi_candidate_total"],
            "multi_candidate_correct": el_result["multi_candidate_correct"],
            "alias_mentions": el_result["alias_mentions"],
            "alias_correct": el_result["alias_correct"],
        },
        "coref": {
            "enabled": enable_coref,
            "accuracy": round(coref_result["accuracy"], 4) if coref_result else None,
            "total": coref_result["total"] if coref_result else 0,
            "correct": coref_result["correct"] if coref_result else 0,
        } if enable_coref else None,
        "targets": {
            "link_accuracy": 0.85,
            "disambiguation_accuracy": 0.85,
            "alias_recall": 0.85,
            "nil_f1": 0.80,
            "coref_accuracy": 0.80,
        },
        "errors": el_result["errors"][:100],
    }

    output_path = "data/eval_report_all.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {output_path}")

    # 全部错误去重
    seen = set()
    unique_errors = []
    for e in el_result["errors"]:
        key = (e["mention"], e["expected_name"], e["predicted_name"])
        if key not in seen:
            seen.add(key)
            unique_errors.append(e)
    with open("data/all_errors.json", "w", encoding="utf-8") as f:
        json.dump(unique_errors, f, ensure_ascii=False, indent=2)
    print(f"错误已保存: data/all_errors.json ({len(unique_errors)} 条去重)")


if __name__ == "__main__":
    main()
