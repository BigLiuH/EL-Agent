"""
交互式审核实体对

让用户手动审核实体对，决定是否合并。
"""

import json
import sys
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))


def load_pairs():
    """加载实体对"""
    with open('data/entity_pairs_for_review.json', 'r', encoding='utf-8') as f:
        return json.load(f)


def display_pair(pair, index):
    """显示实体对信息"""
    e1 = pair['entity1']
    e2 = pair['entity2']

    print(f"\n{'='*70}")
    print(f"实体对 {index + 1}")
    print(f"{'='*70}")
    print(f"\n实体1:")
    print(f"  ID: {e1['id']}")
    print(f"  名称: {e1['name']}")
    print(f"  类型: {e1['type']}")
    print(f"  描述: {e1['description'][:100]}...")

    print(f"\n实体2:")
    print(f"  ID: {e2['id']}")
    print(f"  名称: {e2['name']}")
    print(f"  类型: {e2['type']}")
    print(f"  描述: {e2['description'][:100]}...")


def get_user_decision():
    """获取用户决定"""
    print(f"\n请选择:")
    print(f"  1. 合并 (保留实体1)")
    print(f"  2. 合并 (保留实体2)")
    print(f"  3. 不合并")
    print(f"  4. 跳过")
    print(f"  5. 退出")

    while True:
        choice = input("\n请输入选择 (1-5): ").strip()
        if choice in ['1', '2', '3', '4', '5']:
            return int(choice)
        print("无效选择，请重新输入")


def get_reason():
    """获取判断理由"""
    reason = input("请输入判断理由 (可选): ").strip()
    return reason


def save_decisions(decisions, output_path='data/entity_merge_decisions.json'):
    """保存判断结果"""
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(decisions, f, ensure_ascii=False, indent=2)

    print(f"\n判断结果已保存到: {output_path}")
    return output_path


def main():
    """主函数"""
    print("=" * 70)
    print("交互式审核实体对")
    print("=" * 70)

    # 加载实体对
    print("\n加载实体对...")
    pairs = load_pairs()
    print(f"共 {len(pairs)} 对实体需要审核")

    # 判断结果
    decisions = []

    # 逐个审核
    for i, pair in enumerate(pairs):
        display_pair(pair, i)
        choice = get_user_decision()

        if choice == 5:  # 退出
            break
        elif choice == 4:  # 跳过
            continue
        else:
            reason = get_reason()

            if choice == 1:  # 合并，保留实体1
                decisions.append({
                    'pair_index': i,
                    'entity1': pair['entity1'],
                    'entity2': pair['entity2'],
                    'action': 'merge',
                    'keep_entity': pair['entity1']['id'],
                    'reason': reason
                })
            elif choice == 2:  # 合并，保留实体2
                decisions.append({
                    'pair_index': i,
                    'entity1': pair['entity1'],
                    'entity2': pair['entity2'],
                    'action': 'merge',
                    'keep_entity': pair['entity2']['id'],
                    'reason': reason
                })
            elif choice == 3:  # 不合并
                decisions.append({
                    'pair_index': i,
                    'entity1': pair['entity1'],
                    'entity2': pair['entity2'],
                    'action': 'keep_both',
                    'keep_entity': None,
                    'reason': reason
                })

    # 保存结果
    if decisions:
        output_path = save_decisions(decisions)

        # 统计
        merge_count = sum(1 for d in decisions if d['action'] == 'merge')
        keep_count = sum(1 for d in decisions if d['action'] == 'keep_both')

        print(f"\n统计:")
        print(f"  审核总数: {len(decisions)}")
        print(f"  合并: {merge_count}")
        print(f"  保留: {keep_count}")

    return decisions


if __name__ == "__main__":
    main()
