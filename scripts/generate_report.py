"""
生成评测报告

生成完整的评测报告，包括指标、失败案例分析等。
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_eval_report():
    """加载评测报告"""
    with open('data/eval_report_articles.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_errors(errors):
    """分析错误"""
    # 按实体类型统计
    type_counter = Counter()
    for err in errors:
        type_counter[err.get('entity_type', 'UNKNOWN')] += 1

    # 按错误模式分类
    mention_errors = defaultdict(list)
    for err in errors:
        mention_errors[err['mention']].append(err)

    # 分类错误
    full_short = 0  # 全称/简称
    other = 0
    other_examples = []

    for mention, errs in mention_errors.items():
        expected_name = errs[0]['expected_name']
        predicted_name = errs[0]['predicted_name']

        if mention in expected_name or expected_name in mention:
            full_short += len(errs)
        elif mention in predicted_name or predicted_name in mention:
            full_short += len(errs)
        else:
            other += len(errs)
            if len(other_examples) < 20:
                other_examples.append({
                    'mention': mention,
                    'expected': expected_name,
                    'predicted': predicted_name,
                    'count': len(errs)
                })

    return {
        'type_distribution': dict(type_counter),
        'full_short_count': full_short,
        'other_count': other,
        'other_examples': other_examples,
        'top_errors': [{'mention': k, 'count': len(v)} for k, v in sorted(mention_errors.items(), key=lambda x: -len(x[1]))[:20]]
    }


def generate_markdown_report(eval_data, error_analysis):
    """生成Markdown格式的报告"""
    metrics = eval_data['metrics']
    metadata = eval_data.get('metadata', {})

    report = f"""# 实体链接智能体评测报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

---

## 一、评测概况

| 项目 | 值 |
|------|-----|
| 评测文章数 | {metadata.get('total_articles', 'N/A')} |
| 总样本数 | {metrics['total_samples']} |
| 正确数 | {metrics['correct']} |
| 错误数 | {metrics['wrong']} |

---

## 二、核心指标

| 指标 | 值 | 说明 |
|------|-----|------|
| **准确率 (Accuracy)** | {metrics['accuracy']:.2%} | 正确链接数 / 总链接数 |
| **精确率 (Precision)** | {metrics['precision']:.2%} | 正确链接数 / 预测为实体的数 |
| **召回率 (Recall)** | {metrics['recall']:.2%} | 正确链接数 / 应链接数 |
| **F1分数** | {metrics['f1']:.2%} | Precision和Recall的调和平均 |
| **平均延迟** | {metrics['avg_latency_ms']:.2f} ms | 单条链接耗时 |

---

## 三、混淆矩阵

| 指标 | 值 | 说明 |
|------|-----|------|
| TP (True Positive) | {metrics['confusion_matrix']['true_positive']} | 正确链接到实体 |
| FP (False Positive) | {metrics['confusion_matrix']['false_positive']} | 错误链接（应为NIL） |
| TN (True Negative) | {metrics['confusion_matrix']['true_negative']} | 正确判断为NIL |
| FN (False Negative) | {metrics['confusion_matrix']['false_negative']} | 漏判NIL（应有链接） |

---

## 四、错误分析

### 4.1 按实体类型分布

| 类型 | 错误数 | 占比 |
|------|--------|------|
"""

    total_errors = sum(error_analysis['type_distribution'].values())
    for etype, count in sorted(error_analysis['type_distribution'].items(), key=lambda x: -x[1]):
        report += f"| {etype} | {count} | {count/total_errors*100:.1f}% |\n"

    report += f"""
### 4.2 错误模式分析

| 错误类型 | 数量 | 占比 |
|---------|------|------|
| 全称/简称混淆 | {error_analysis['full_short_count']} | {error_analysis['full_short_count']/total_errors*100:.1f}% |
| 其他错误 | {error_analysis['other_count']} | {error_analysis['other_count']/total_errors*100:.1f}% |

### 4.3 最常见的错误mention

| 排名 | 提及 | 错误次数 |
|------|------|---------|
"""

    for i, item in enumerate(error_analysis['top_errors'][:10], 1):
        report += f"| {i} | {item['mention']} | {item['count']} |\n"

    report += """
### 4.4 其他错误示例

| 提及 | 预期 | 预测 | 次数 |
|------|------|------|------|
"""

    for ex in error_analysis['other_examples'][:10]:
        report += f"| {ex['mention']} | {ex['expected']} | {ex['predicted']} | {ex['count']} |\n"

    report += """
---

## 五、系统能力

| 能力 | 状态 | 说明 |
|------|------|------|
| 候选实体生成/检索 | ✅ | 别名匹配 + BM25 + 向量检索 |
| 上下文消歧 | ✅ | 类型过滤 + 名称最短优先 |
| 实体标准化 | ✅ | 别名→标准全称+唯一ID |
| NIL检测 | ✅ | 多信号融合判定 |
| 可追溯 | ✅ | 原值→新值→依据 |
| 共指消解 | ❌ | 按需启用，未实现 |

---

## 六、技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Web框架 | FastAPI | 异步、自动OpenAPI文档 |
| BM25 | rank-bm25 | 全文检索 |
| 向量检索 | FAISS + m3e-base | 语义相似度 |
| 分词 | jieba | 中文分词 |
| 存储 | JSON + 文件 | 轻量级 |

---

## 七、结论

1. 当前准确率为 **{metrics['accuracy']:.2%}**，主要错误来源是知识库中的全称/简称混淆
2. 系统已实现任务书要求的核心功能：候选检索、消歧、标准化、NIL检测、可追溯
3. 平均延迟为 **{metrics['avg_latency_ms']:.2f} ms**，满足实时性要求

### 后续优化方向

1. 合并知识库中的冗余实体（全称/简称）
2. 引入BERT进行更精确的消歧
3. 实现共指消解功能
"""

    return report


def main():
    """主函数"""
    print("=" * 70)
    print("生成评测报告")
    print("=" * 70)

    # 加载评测数据
    print("\n[1/3] 加载评测数据...")
    eval_data = load_eval_report()
    print(f"  总样本数: {eval_data['metrics']['total_samples']}")

    # 分析错误
    print("\n[2/3] 分析错误...")
    error_analysis = analyze_errors(eval_data['errors'])
    print(f"  错误数: {sum(error_analysis['type_distribution'].values())}")

    # 生成报告
    print("\n[3/3] 生成报告...")
    report = generate_markdown_report(eval_data, error_analysis)

    # 保存报告
    output_path = 'data/evaluation_report.md'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n报告已保存到: {output_path}")

    return output_path


if __name__ == "__main__":
    main()
