"""
基于文章数据的评测脚本

使用 llm_extracted_merged.json 中的标注文章进行评测。
"""

import json
import time
import sys
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, field

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.knowledge_base import knowledge_base, KnowledgeBase
from elagent.core.bm25_index import bm25_index
from elagent.models.mention import Mention
from elagent.api.routes import _enhanced_link


@dataclass
class EvalMetrics:
    """评测指标"""
    total: int = 0
    correct: int = 0
    wrong: int = 0

    # 混淆矩阵
    true_positive: int = 0   # 正确链接到实体
    false_positive: int = 0  # 错误链接（应为NIL）
    true_negative: int = 0   # 正确判断为NIL
    false_negative: int = 0  # 漏判NIL（应有链接）

    total_time_ms: float = 0.0
    errors: List[Dict] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        """准确率"""
        return self.correct / self.total if self.total > 0 else 0.0

    @property
    def precision(self) -> float:
        """精确率（针对非NIL）"""
        tp = self.true_positive
        fp = self.false_positive
        return tp / (tp + fp) if (tp + fp) > 0 else 0.0

    @property
    def recall(self) -> float:
        """召回率（针对非NIL）"""
        tp = self.true_positive
        fn = self.false_negative
        return tp / (tp + fn) if (tp + fn) > 0 else 0.0

    @property
    def f1(self) -> float:
        """F1分数"""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        """平均延迟"""
        return self.total_time_ms / self.total if self.total > 0 else 0.0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "total_samples": self.total,
            "correct": self.correct,
            "wrong": self.wrong,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "confusion_matrix": {
                "true_positive": self.true_positive,
                "false_positive": self.false_positive,
                "true_negative": self.true_negative,
                "false_negative": self.false_negative,
            },
        }


def evaluate_mention(mention_data: dict, text: str, kb: KnowledgeBase) -> Dict:
    """
    评测单个mention

    Args:
        mention_data: 标注的mention数据
        text: 完整文本
        kb: 知识库

    Returns:
        评测结果
    """
    # 构建Mention对象
    mention = Mention(
        text=mention_data["text"],
        start_pos=mention_data["start"],
        end_pos=mention_data["end"],
        entity_type=mention_data.get("entity_type"),
        context=text,
    )

    # 预期结果
    expected_nil = mention_data.get("is_nil", False)
    expected_entity_id = mention_data.get("entity_id")

    # 运行链接
    start_time = time.time()
    result = _enhanced_link(mention, full_text=text)
    elapsed_ms = (time.time() - start_time) * 1000

    # 判断是否正确
    predicted_nil = result.is_nil
    is_correct = False

    if expected_nil and predicted_nil:
        is_correct = True
    elif not expected_nil and not predicted_nil:
        if result.linked_entity:
            # 优先使用标准名称判断（更稳定）
            expected_name = mention_data.get("standard_name", "")
            predicted_name = result.linked_entity.standard_name

            if expected_name and predicted_name == expected_name:
                is_correct = True
            elif result.linked_entity.id == expected_entity_id:
                # 回退到ID判断
                is_correct = True

    return {
        "is_correct": is_correct,
        "expected_nil": expected_nil,
        "predicted_nil": predicted_nil,
        "expected_entity_id": expected_entity_id,
        "expected_standard_name": mention_data.get("standard_name"),
        "predicted_entity_id": result.linked_entity.id if result.linked_entity else None,
        "predicted_standard_name": result.linked_entity.standard_name if result.linked_entity else None,
        "elapsed_ms": elapsed_ms,
        "mention_text": mention_data["text"],
        "entity_type": mention_data.get("entity_type"),
    }


def evaluate(articles_path: str = "Dataset/llm_extracted_merged.json",
             max_articles: int = 1239,
             output_path: str = "data/eval_report_articles.json"):
    """
    运行评测

    Args:
        articles_path: 文章数据路径
        max_articles: 最大评测文章数
        output_path: 评测报告输出路径
    """
    print("=" * 60)
    print("实体链接系统评测 - 基于标注文章")
    print("=" * 60)

    # 加载知识库（使用全局实例）
    print("\n[1/4] 加载知识库...")
    knowledge_base.load()
    kb = knowledge_base
    print(f"  知识库加载完成: {kb.entity_count}个实体")

    # 构建BM25索引
    print("\n[2/4] 构建BM25索引...")
    bm25_index.build(kb.entities)
    print(f"  BM25索引构建完成")

    # 加载文章（优先使用修复后的标注数据）
    print("\n[3/4] 加载文章数据...")
    fixed_path = Path('data/annotations_fixed.json')
    if fixed_path.exists():
        print("  使用修复后的标注数据")
        with open(fixed_path, 'r', encoding='utf-8') as f:
            articles = json.load(f)
    else:
        with open(articles_path, 'r', encoding='utf-8') as f:
            articles = json.load(f)

    # 限制文章数量
    articles = articles[:max_articles]
    print(f"  加载了 {len(articles)} 篇文章")

    # 统计mentions数量
    total_mentions = sum(len(a.get("mentions", [])) for a in articles)
    print(f"  总mention数: {total_mentions}")

    # 运行评测
    print("\n[4/4] 运行评测...")
    metrics = EvalMetrics()
    article_count = 0
    mention_count = 0

    for article in articles:
        article_count += 1
        text = article.get("text", "")
        mentions = article.get("mentions", [])

        if not mentions:
            continue

        if article_count % 10 == 0:
            print(f"  进度: {article_count}/{len(articles)} 篇文章, {mention_count} 个mentions")

        for mention_data in mentions:
            mention_count += 1
            result = evaluate_mention(mention_data, text, kb)

            # 更新指标
            metrics.total += 1
            metrics.total_time_ms += result["elapsed_ms"]

            if result["is_correct"]:
                metrics.correct += 1
            else:
                metrics.wrong += 1
                if len(metrics.errors) < 10000:  # 保存所有错误
                    metrics.errors.append({
                        "mention": result["mention_text"],
                        "entity_type": result["entity_type"],
                        "expected_nil": result["expected_nil"],
                        "predicted_nil": result["predicted_nil"],
                        "expected_id": result["expected_entity_id"],
                        "expected_name": result["expected_standard_name"],
                        "predicted_id": result["predicted_entity_id"],
                        "predicted_name": result["predicted_standard_name"],
                    })

            # 更新混淆矩阵
            if result["expected_nil"] and result["predicted_nil"]:
                metrics.true_negative += 1
            elif result["expected_nil"] and not result["predicted_nil"]:
                metrics.false_positive += 1
            elif not result["expected_nil"] and not result["predicted_nil"]:
                metrics.true_positive += 1
            else:
                metrics.false_negative += 1

    # 输出报告
    print("\n" + "=" * 60)
    print("评测结果")
    print("=" * 60)

    report = metrics.to_dict()
    print(f"\n评测文章数: {len(articles)}")
    print(f"总样本数:     {report['total_samples']}")
    print(f"正确数:       {report['correct']}")
    print(f"错误数:       {report['wrong']}")
    print(f"\n准确率 (Accuracy):   {report['accuracy']:.2%}")
    print(f"精确率 (Precision):  {report['precision']:.2%}")
    print(f"召回率 (Recall):     {report['recall']:.2%}")
    print(f"F1分数:              {report['f1']:.2%}")
    print(f"\n平均延迟:     {report['avg_latency_ms']:.2f} ms")

    print(f"\n混淆矩阵:")
    print(f"  TP (正确链接):   {report['confusion_matrix']['true_positive']}")
    print(f"  FP (误判为实体): {report['confusion_matrix']['false_positive']}")
    print(f"  TN (正确NIL):    {report['confusion_matrix']['true_negative']}")
    print(f"  FN (漏判NIL):    {report['confusion_matrix']['false_negative']}")

    # 显示错误案例
    if metrics.errors:
        print(f"\n错误案例 (前10个):")
        for err in metrics.errors[:10]:
            print(f"  [{err['mention']}] ({err['entity_type']})")
            print(f"    预期: {err['expected_name']} (NIL={err['expected_nil']})")
            print(f"    预测: {err['predicted_name']} (NIL={err['predicted_nil']})")

    # 保存报告
    full_report = {
        "metadata": {
            "articles_path": articles_path,
            "evaluated_articles": len(articles),
            "total_mentions": metrics.total,
            "kb_entities": kb.entity_count,
        },
        "metrics": report,
        "errors": metrics.errors,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(full_report, f, ensure_ascii=False, indent=2)

    print(f"\n评测报告已保存到: {output_path}")

    return metrics


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="实体链接系统评测")
    parser.add_argument("--articles", default="Dataset/llm_extracted_merged.json", help="文章数据路径")
    parser.add_argument("--max-articles", type=int, default=99999, help="最大评测文章数（默认使用全部）")
    parser.add_argument("--output", default="data/eval_report_articles.json", help="报告输出路径")

    args = parser.parse_args()
    evaluate(args.articles, args.max_articles, args.output)
