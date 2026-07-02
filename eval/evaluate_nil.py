"""
NIL检测评测脚本

评测系统正确识别知识库中不存在实体的能力。
使用 Dataset/NIL.json（全部是NIL样本）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from elagent.core.knowledge_base import knowledge_base
from elagent.models.mention import Mention
from elagent.api.routes import _enhanced_link


def main():
    data_path = "Dataset/NIL.json"
    print(f"加载NIL数据: {data_path}")
    with open(data_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("加载知识库...")
    knowledge_base.load()
    print(f"  实体数: {knowledge_base.entity_count}")

    total_nil = 0       # 标注为NIL的
    nil_correct = 0     # 系统正确返回NIL
    nil_missed = 0      # 标注NIL但系统链到实体（该NIL没检测到）
    total_linked = 0    # 标注为非NIL的
    link_correct = 0    # 系统链对了
    false_hits = []     # NIL误判详情

    for art in data:
        text = art.get("text", "")
        for m in art.get("mentions", []):
            mention = Mention(
                text=m["text"],
                start_pos=m["start"],
                end_pos=m["end"],
                entity_type=m.get("entity_type"),
                context=text,
            )
            result = _enhanced_link(mention, full_text=text)
            is_annotated_nil = m.get("is_nil", True)

            if is_annotated_nil:
                total_nil += 1
                if result.is_nil:
                    nil_correct += 1
                else:
                    nil_missed += 1
                    false_hits.append({
                        "mention": m["text"],
                        "entity_type": m.get("entity_type"),
                        "linked_name": result.linked_entity.standard_name if result.linked_entity else "NIL",
                        "linked_id": result.linked_entity.id if result.linked_entity else None,
                        "confidence": result.confidence,
                    })
            else:
                total_linked += 1
                if result.linked_entity and result.linked_entity.id == m.get("entity_id"):
                    link_correct += 1

    nil_accuracy = nil_correct / max(total_nil, 1)
    link_accuracy = link_correct / max(total_linked, 1) if total_linked > 0 else 0

    print(f"\n{'='*50}")
    print(f"NIL数据集评测结果")
    print(f"{'='*50}")
    print(f"\n[NIL检测] 标注为NIL的样本: {total_nil}")
    print(f"  正确返回NIL:  {nil_correct}")
    print(f"  漏检(该NIL却链了): {nil_missed}")
    print(f"  准确率:       {nil_accuracy:.2%}")
    print(f"  目标:         >= 80%")
    print(f"  状态:         {'PASS' if nil_accuracy >= 0.80 else 'FAIL'}")
    if total_linked > 0:
        print(f"\n[实体链接] 标注为非NIL的样本: {total_linked}")
        print(f"  链接正确:     {link_correct}")
        print(f"  准确率:       {link_accuracy:.2%}")

    # 误链分析
    if false_hits:
        print(f"\n=== NIL漏检前20 ===")
        from collections import Counter
        type_counter = Counter()
        for e in false_hits:
            type_counter[e["entity_type"]] += 1
        print(f"类型分布: {dict(type_counter.most_common())}")
        print()
        for e in false_hits[:20]:
            print(f"  '{e['mention']}' ({e['entity_type']}) → {e['linked_name']} (id={e['linked_id']}, conf={e['confidence']:.3f})")

    # 去重
    seen_err = set()
    unique_errors = []
    for e in false_hits:
        key = (e["mention"], e["linked_id"])
        if key not in seen_err:
            seen_err.add(key)
            unique_errors.append(e)

    report = {
        "metrics": {
            "nil_accuracy": round(nil_accuracy, 4),
            "total_nil": total_nil,
            "nil_correct": nil_correct,
            "nil_missed": nil_missed,
            "total_linked": total_linked,
            "link_correct": link_correct,
            "link_accuracy": round(link_accuracy, 4),
        },
        "errors": unique_errors,
    }
    output_path = "data/eval_report_nil.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n报告已保存: {output_path}")


if __name__ == "__main__":
    main()
