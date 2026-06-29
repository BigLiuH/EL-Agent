"""
完整评测脚本

计算所有指标：
1. 链接准确率 - 指称 → 标准实体链接准确率
2. 消歧准确率 - 同名异指消歧准确率
3. NIL检测 - 知识库中不存在实体的 NIL 检测 F1
4. 别名标准化 - 别名/简称/曾用名映射召回率
"""

import json
import time
import sys
from pathlib import Path
from typing import List, Dict
from collections import defaultdict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.knowledge_base import knowledge_base
from elagent.core.bm25_index import bm25_index
from elagent.core.bert_disambiguator import bert_disambiguator
from elagent.models.mention import Mention
from elagent.api.routes import _enhanced_link


def load_articles(articles_path: str):
    """加载文章数据"""
    with open(articles_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def evaluate(articles_path: str = "Dataset/llm_extracted_merged.json",
             max_articles: int = 99999):
    """
    运行完整评测
    """
    print("=" * 70)
    print("实体链接系统完整评测")
    print("=" * 70)

    # 加载知识库
    print("\n[1/4] 加载知识库...")
    knowledge_base.load()
    print(f"  知识库加载完成: {knowledge_base.entity_count}个实体")

    # 构建BM25索引
    print("\n[2/5] 构建BM25索引...")
    bm25_index.build(knowledge_base.entities)
    print(f"  BM25索引构建完成")

    # 加载BERT消歧模型
    print("\n[3/5] 加载BERT消歧模型...")
    bert_disambiguator.load_model()
    if bert_disambiguator.loaded:
        bert_disambiguator.build_index(knowledge_base.entities)
        print(f"  BERT消歧模型加载完成")
    else:
        print(f"  BERT消歧模型加载失败，将使用规则消歧")

    # 加载文章
    print("\n[4/5] 加载文章数据...")
    articles = load_articles(articles_path)
    articles = articles[:max_articles]
    print(f"  加载了 {len(articles)} 篇文章")

    # 运行评测
    print("\n[5/5] 运行评测...")

    # 初始化统计
    total_mentions = 0
    correct_links = 0  # 链接正确数

    # 消歧统计
    multi_candidate_total = 0  # 多候选总数
    multi_candidate_correct = 0  # 多候选消歧正确数
    single_candidate_correct = 0  # 单候选正确数
    single_candidate_total = 0  # 单候选总数

    # 别名标准化统计
    alias_mentions = 0  # 使用别名的mention数
    alias_correct = 0  # 别名映射正确数

    # NIL检测统计（当前数据集无NIL样本，预留）
    nil_total = 0
    nil_correct = 0

    # 错误统计
    errors = []
    mention_errors = defaultdict(list)

    article_count = 0
    for article in articles:
        article_count += 1
        if article_count % 100 == 0:
            print(f"  进度: {article_count}/{len(articles)}")

        text = article.get("text", "")

        for mention_data in article.get("mentions", []):
            total_mentions += 1

            # 构建Mention对象
            mention = Mention(
                text=mention_data["text"],
                start_pos=mention_data["start"],
                end_pos=mention_data["end"],
                entity_type=mention_data.get("entity_type"),
                context=text,
            )

            # 预期结果
            expected_id = mention_data.get("entity_id")
            expected_name = mention_data.get("standard_name", "")

            # 执行链接
            result = _enhanced_link(mention, full_text=text)

            # 判断是否正确
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

            # 统计消歧情况
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

            # 统计别名标准化
            if alias_candidates:
                alias_mentions += 1
                if is_correct:
                    alias_correct += 1

    # 计算指标
    link_accuracy = correct_links / total_mentions if total_mentions > 0 else 0
    disambiguation_accuracy = multi_candidate_correct / multi_candidate_total if multi_candidate_total > 0 else 0
    alias_recall = alias_correct / alias_mentions if alias_mentions > 0 else 0

    # 输出结果
    print("\n" + "=" * 70)
    print("评测结果")
    print("=" * 70)

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
    print(f"  注: 当前数据集无NIL样本，暂未计算")

    print(f"\n五、单候选准确率")
    print(f"  单候选总数: {single_candidate_total}")
    print(f"  单候选正确数: {single_candidate_correct}")
    single_accuracy = single_candidate_correct / single_candidate_total if single_candidate_total > 0 else 0
    print(f"  单候选准确率: {single_accuracy:.2%}")

    # 显示高频错误
    print(f"\n六、高频错误 (前10个)")
    for mention, errs in sorted(mention_errors.items(), key=lambda x: -len(x[1]))[:30]:
        print(f"  {mention} ({len(errs)}次)")
        print(f"    预期: {errs[0]['expected_name']}")
        print(f"    预测: {errs[0]['predicted_name']}")

    # 保存报告
    report = {
        "metrics": {
            "link_accuracy": round(link_accuracy, 4),
            "disambiguation_accuracy": round(disambiguation_accuracy, 4),
            "alias_recall": round(alias_recall, 4),
            "single_candidate_accuracy": round(single_accuracy, 4),
            "total_mentions": total_mentions,
            "correct_links": correct_links,
            "multi_candidate_total": multi_candidate_total,
            "multi_candidate_correct": multi_candidate_correct,
            "alias_mentions": alias_mentions,
            "alias_correct": alias_correct,
        },
        "targets": {
            "link_accuracy": 0.85,
            "disambiguation_accuracy": 0.85,
            "alias_recall": 0.85,
            "nil_f1": 0.80,
        },
        "errors": errors[:100],
    }

    output_path = "data/eval_report_full.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n报告已保存到: {output_path}")

    # 保存全部错误到 all_errors.json（去重）
    seen = set()
    unique_errors = []
    for e in errors:
        key = (e["mention"], e["expected_name"], e["predicted_name"])
        if key not in seen:
            seen.add(key)
            unique_errors.append(e)

    all_errors_path = "data/all_errors.json"
    with open(all_errors_path, 'w', encoding='utf-8') as f:
        json.dump(unique_errors, f, ensure_ascii=False, indent=2)
    print(f"去重错误已保存到: {all_errors_path} (全部{len(errors)}条, 去重后{len(unique_errors)}条)")

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="实体链接系统完整评测")
    parser.add_argument("--articles", default="Dataset/llm_extracted_merged.json", help="文章数据路径")
    parser.add_argument("--max-articles", type=int, default=99999, help="最大评测文章数")

    args = parser.parse_args()
    evaluate(args.articles, args.max_articles)
