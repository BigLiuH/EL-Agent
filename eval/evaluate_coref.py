"""
共指消解评测脚本

评测代词/指代词回链准确率。
用合并后的数据: Dataset/llm_extracted_with_coref.json
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from elagent.core.coref_resolver import evaluate_coref


def main():
    data_path = "Dataset/llm_extracted_with_coref.json"
    print(f"加载数据: {data_path}")
    with open(data_path, "r", encoding="utf-8") as f:
        articles = json.load(f)

    result = evaluate_coref(articles)

    print(f"\n{'='*50}")
    print(f"共指消解评测结果")
    print(f"{'='*50}")
    print(f"总指代词:       {result['total']}")
    print(f"正确回链:       {result['correct']}")
    print(f"准确率:         {result['accuracy']*100:.1f}%")
    print(f"目标:           >= 80%")
    print(f"状态:           {'PASS' if result['accuracy'] >= 0.8 else 'FAIL'}")

    print(f"\n前10个错误:")
    for e in result["errors"][:10]:
        print(f"  '{e['mention']}' expected={e['expected']} "
              f"predicted={e['predicted']} target='{e['target_text']}'")


if __name__ == "__main__":
    main()
