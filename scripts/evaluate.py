"""
评测脚本

评估实体链接系统的性能指标。
"""

import json
import time
import sys
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, field

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from elagent.core.knowledge_base import KnowledgeBase
from elagent.models.mention import Mention
from elagent.api.routes import _simple_link


@dataclass
class EvalMetrics:
    """评测指标"""
    total: int = 0
    correct: int = 0
    wrong: int = 0
    nil_correct: int = 0
    nil_wrong: int = 0
    non_nil_correct: int = 0
    non_nil_wrong: int = 0
    true_positive: int = 0  # 正确链接到实体
    false_positive: int = 0  # 错误链接到实体（应为NIL）
    true_negative: int = 0  # 正确判断为NIL
    false_negative: int = 0  # 错误判断为NIL（应有链接）
    total_time_ms: float = 0.0
    errors: List[Dict] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        """准确率"""
        return self.correct / self.total if self.total > 0 else 0.0

    @property
    def precision(self) -> float:
        """精确率（针对非NIL）"""
        return self.true_positive / (self.true_positive + self.false_positive) if (self.true_positive + self.false_positive) > 0 else 0.0

    @property
    def recall(self) -> float:
        """召回率（针对非NIL）"""
        return self.true_positive / (self.true_positive + self.false_negative) if (self.true_positive + self.false_negative) > 0 else 0.0

    @property
    def f1(self) -> float:
        """F1分数"""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def nil_precision(self) -> float:
        """NIL精确率"""
        return self.true_negative / (self.true_negative + self.false_negative) if (self.true_negative + self.false_negative) > 0 else 0.0

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
            "nil_precision": round(self.nil_precision, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "confusion_matrix": {
                "true_positive": self.true_positive,
                "false_positive": self.false_positive,
                "true_negative": self.true_negative,
                "false_negative": self.false_negative,
            },
            "error_count": len(self.errors),
        }


def evaluate_single(sample: dict, kb: KnowledgeBase) -> Dict:
    """
    评测单个样本

    Args:
        sample: 评测样本
        kb: 知识库

    Returns:
        评测结果
    """
    mention = Mention(
        text=sample["mention_text"],
        start_pos=0,
        end_pos=len(sample["mention_text"]),
        entity_type=sample.get("entity_type"),
    )

    start_time = time.time()
    result = _simple_link(mention)
    elapsed_ms = (time.time() - start_time) * 1000

    # 判断是否正确
    expected_nil = sample["is_nil"]
    predicted_nil = result.is_nil
    is_correct = False

    if expected_nil and predicted_nil:
        # 都是NIL，正确
        is_correct = True
    elif not expected_nil and not predicted_nil:
        # 都不是NIL，检查实体ID是否匹配
        if result.linked_entity and result.linked_entity.id == sample["expected_entity_id"]:
            is_correct = True

    return {
        "is_correct": is_correct,
        "expected_nil": expected_nil,
        "predicted_nil": predicted_nil,
        "expected_entity_id": sample.get("expected_entity_id"),
        "predicted_entity_id": result.linked_entity.id if result.linked_entity else None,
        "elapsed_ms": elapsed_ms,
        "mention_text": sample["mention_text"],
    }


def evaluate(testset_path: str = "data/testset.json", output_path: str = "data/eval_report.json"):
    """
    运行评测

    Args:
        testset_path: 评测集路径
        output_path: 评测报告输出路径
    """
    print("=" * 60)
    print("实体链接系统评测")
    print("=" * 60)

    # 加载知识库
    print("\n[1/3] 加载知识库...")
    kb = KnowledgeBase()
    kb.load()
    print(f"  知识库加载完成: {kb.entity_count}个实体")

    # 加载评测集
    print("\n[2/3] 加载评测集...")
    with open(testset_path, 'r', encoding='utf-8') as f:
        testset_data = json.load(f)
    samples = testset_data["samples"]
    print(f"  评测集加载完成: {len(samples)}个样本")

    # 运行评测
    print("\n[3/3] 运行评测...")
    metrics = EvalMetrics()

    for i, sample in enumerate(samples):
        if (i + 1) % 50 == 0:
            print(f"  进度: {i+1}/{len(samples)}")

        result = evaluate_single(sample, kb)

        # 更新指标
        metrics.total += 1
        metrics.total_time_ms += result["elapsed_ms"]

        if result["is_correct"]:
            metrics.correct += 1
        else:
            metrics.wrong += 1
            metrics.errors.append({
                "index": i,
                "mention": result["mention_text"],
                "expected_nil": result["expected_nil"],
                "predicted_nil": result["predicted_nil"],
                "expected_id": result["expected_entity_id"],
                "predicted_id": result["predicted_entity_id"],
            })

        # 更新混淆矩阵
        if result["expected_nil"] and result["predicted_nil"]:
            metrics.true_negative += 1
        elif result["expected_nil"] and not result["predicted_nil"]:
            metrics.false_positive += 1
        elif not result["expected_nil"] and not result["predicted_nil"]:
            metrics.true_positive += 1
        else:  # not expected_nil and predicted_nil
            metrics.false_negative += 1

    # 输出报告
    print("\n" + "=" * 60)
    print("评测结果")
    print("=" * 60)

    report = metrics.to_dict()
    print(f"\n总样本数:     {report['total_samples']}")
    print(f"正确数:       {report['correct']}")
    print(f"错误数:       {report['wrong']}")
    print(f"\n准确率 (Accuracy):   {report['accuracy']:.2%}")
    print(f"精确率 (Precision):  {report['precision']:.2%}")
    print(f"召回率 (Recall):     {report['recall']:.2%}")
    print(f"F1分数:              {report['f1']:.2%}")
    print(f"NIL精确率:           {report['nil_precision']:.2%}")
    print(f"\n平均延迟:     {report['avg_latency_ms']:.2f} ms")

    print(f"\n混淆矩阵:")
    print(f"  TP (正确链接): {report['confusion_matrix']['true_positive']}")
    print(f"  FP (误判为实体): {report['confusion_matrix']['false_positive']}")
    print(f"  TN (正确NIL):  {report['confusion_matrix']['true_negative']}")
    print(f"  FN (漏判NIL):  {report['confusion_matrix']['false_negative']}")

    # 保存错误案例
    if metrics.errors:
        print(f"\n错误案例 (前10个):")
        for err in metrics.errors[:10]:
            print(f"  [{err['mention']}] 预期NIL={err['expected_nil']}, 预测NIL={err['predicted_nil']}")

    # 保存报告
    full_report = {
        "metadata": {
            "testset_path": testset_path,
            "total_samples": len(samples),
            "kb_entities": kb.entity_count,
        },
        "metrics": report,
        "errors": metrics.errors[:100],  # 最多保存100个错误案例
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(full_report, f, ensure_ascii=False, indent=2)

    print(f"\n评测报告已保存到: {output_path}")

    return metrics


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="实体链接系统评测")
    parser.add_argument("--testset", default="data/testset.json", help="评测集路径")
    parser.add_argument("--output", default="data/eval_report.json", help="报告输出路径")

    args = parser.parse_args()
    evaluate(args.testset, args.output)
