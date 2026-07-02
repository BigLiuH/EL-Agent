"""
统一评测脚本

基于 Dataset/combined.json，复用 evaluate_full.py / evaluate_nil.py / evaluate_coref.py 的原样逻辑。
所有 mention 都走 _enhanced_link()，和 evaluate_full.py 完全一致。
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.knowledge_base import knowledge_base
from elagent.core.coref_resolver import evaluate_coref
from elagent.models.mention import Mention
from elagent.api.routes import _enhanced_link


def main():
    print("=" * 70)
    print("实体链接与知识对齐智能体 - 统一评测")
    print("=" * 70)

    # 加载知识库
    print("\n[1/5] 加载知识库...")
    knowledge_base.load()
    print(f"  知识库加载完成: {knowledge_base.entity_count}个实体")

    # 加载文章（不构建BM25，与 evaluate_nil.py 一致）
    print("\n[2/4] 加载文章数据...")
    with open("Dataset/combined.json", "r", encoding="utf-8") as f:
        articles = json.load(f)
    print(f"  加载了 {len(articles)} 篇文章")

    # 共指评测数据
    print("\n[3/4] 加载共指数据...")
    coref_path = "Dataset/llm_extracted_with_coref.json"
    if Path(coref_path).exists():
        with open(coref_path, "r", encoding="utf-8") as f:
            coref_articles = json.load(f)
        coref_result = evaluate_coref(coref_articles)
    else:
        coref_result = None

    # 运行评测
    print("\n[4/4] 运行评测...")

    # 初始化统计（和 evaluate_full.py 完全一致）
    total_mentions = 0
    correct_links = 0
    multi_candidate_total = 0
    multi_candidate_correct = 0
    single_candidate_total = 0
    single_candidate_correct = 0
    alias_mentions = 0
    alias_correct = 0

    # NIL 统计（和 evaluate_nil.py 一致）
    nil_total = 0
    nil_correct = 0

    # 错误统计
    errors = []
    mention_errors = defaultdict(list)

    article_count = 0
    for article in articles:
        article_count += 1
        if article_count % 200 == 0:
            print(f"  进度: {article_count}/{len(articles)}")

        text = article.get("text", "")

        for mention_data in article.get("mentions", []):
            # 跳过共指标注（和 evaluate_full.py 一样不处理代词）
            if (mention_data.get("is_coref") or
                mention_data["text"] in ("她", "他", "它", "她们", "他们", "其") or
                any(kw in mention_data["text"] for kw in ("本次", "该", "此"))):
                continue

            total_mentions += 1

            mention = Mention(
                text=mention_data["text"],
                start_pos=mention_data["start"],
                end_pos=mention_data["end"],
                entity_type=mention_data.get("entity_type"),
                context=text,
            )

            expected_id = mention_data.get("entity_id")
            expected_name = mention_data.get("standard_name", "")
            is_nil_annotation = mention_data.get("is_nil", False)

            # 执行链接（和 evaluate_full.py / evaluate_nil.py 完全一致）
            result = _enhanced_link(mention, full_text=text)

            # === NIL 检测（和 evaluate_nil.py 一致）===
            if is_nil_annotation:
                nil_total += 1
                if result.is_nil:
                    nil_correct += 1
                else:
                    errors.append({
                        "mention": mention.text,
                        "expected_name": "NIL",
                        "predicted_name": result.linked_entity.standard_name if result.linked_entity else "NIL",
                        "entity_type": mention_data.get("entity_type"),
                    })
                continue

            # === 实体链接（和 evaluate_full.py 一致）===
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

            # 消歧统计（和 evaluate_full.py 一致）
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

    # 计算指标
    link_accuracy = correct_links / max(total_mentions, 1)
    disambiguation_accuracy = multi_candidate_correct / max(multi_candidate_total, 1)
    alias_recall = alias_correct / max(alias_mentions, 1)
    nil_accuracy = nil_correct / max(nil_total, 1)
    coref_accuracy = coref_result["accuracy"] if coref_result else 0

    # 输出结果
    print(f"\n{'='*70}")
    print("评测结果")
    print(f"{'='*70}")

    print(f"\n一、链接准确率")
    print(f"  总样本数: {total_mentions}")
    print(f"  正确数: {correct_links}")
    print(f"  准确率: {link_accuracy:.2%}")
    print(f"  目标: >= 85%")
    print(f"  状态: {'PASS' if link_accuracy >= 0.85 else 'FAIL'}")

    print(f"\n二、消歧准确率")
    print(f"  多候选总数: {multi_candidate_total}")
    print(f"  消歧正确数: {multi_candidate_correct}")
    print(f"  消歧准确率: {disambiguation_accuracy:.2%}")
    print(f"  目标: >= 85%")
    print(f"  状态: {'PASS' if disambiguation_accuracy >= 0.85 else 'FAIL'}")

    print(f"\n三、别名标准化")
    print(f"  别名mention数: {alias_mentions}")
    print(f"  映射正确数: {alias_correct}")
    print(f"  召回率: {alias_recall:.2%}")
    print(f"  目标: >= 85%")
    print(f"  状态: {'PASS' if alias_recall >= 0.85 else 'FAIL'}")

    print(f"\n四、NIL检测")
    print(f"  NIL样本数: {nil_total}")
    print(f"  正确检测: {nil_correct}")
    print(f"  准确率: {nil_accuracy:.2%}")
    print(f"  目标: >= 80%")
    print(f"  状态: {'PASS' if nil_accuracy >= 0.80 else 'FAIL'}")

    print(f"\n五、共指消解")
    if coref_result:
        print(f"  指代词数: {coref_result['total']}")
        print(f"  正确回链: {coref_result['correct']}")
        print(f"  准确率: {coref_accuracy:.2%}")
        print(f"  目标: >= 80%")
        print(f"  状态: {'PASS' if coref_accuracy >= 0.80 else 'FAIL'}")

    # 高频错误
    print(f"\n六、高频错误 (前10个)")
    for mention, errs in sorted(mention_errors.items(), key=lambda x: -len(x[1]))[:10]:
        print(f"  {mention} ({len(errs)}次)")
        print(f"    预期: {errs[0]['expected_name']}")
        print(f"    预测: {errs[0]['predicted_name']}")

    # 保存报告
    report = {
        "metrics": {
            "link_accuracy": round(link_accuracy, 4),
            "disambiguation_accuracy": round(disambiguation_accuracy, 4),
            "alias_recall": round(alias_recall, 4),
            "nil_accuracy": round(nil_accuracy, 4),
            "coref_accuracy": round(coref_accuracy, 4) if coref_result else None,
            "total_mentions": total_mentions,
            "correct_links": correct_links,
            "multi_candidate_total": multi_candidate_total,
            "multi_candidate_correct": multi_candidate_correct,
            "alias_mentions": alias_mentions,
            "alias_correct": alias_correct,
            "nil_total": nil_total,
            "nil_correct": nil_correct,
        },
        "errors": errors[:100],
    }
    output_path = "data/eval_report_combined.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {output_path}")


if __name__ == "__main__":
    main()
