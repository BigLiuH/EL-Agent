"""
从 knowledge_base_merged.json 重新生成别名文件 aliases_merged.json

用法:
  python scripts/rebuild_aliases_from_kb.py

输出:
  Dataset/aliases_merged.json  (覆盖)
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
KB_PATH = ROOT / "Dataset" / "knowledge_base_merged.json"
OUT_PATH = ROOT / "Dataset" / "aliases_merged.json"


def rebuild():
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)

    aliases = {}
    dup_count = 0
    total_aliases = 0

    for entity in kb["entities"]:
        eid = entity["entity_id"]
        standard_name = entity["standard_name"]

        # 添加标准名本身作为别名
        if standard_name not in aliases:
            aliases[standard_name] = {"entity_id": eid, "standard_name": standard_name}

        for alias in entity.get("aliases", []):
            if alias == standard_name:
                continue  # 跳过和标准名相同的
            if alias in aliases:
                dup_count += 1
            aliases[alias] = {"entity_id": eid, "standard_name": standard_name}
            total_aliases += 1

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(aliases, f, ensure_ascii=False, indent=2)

    print(f"实体: {len(kb['entities'])}")
    print(f"别名: {total_aliases}（含冲突 {dup_count} 条，后被覆盖）")
    print(f"输出: {OUT_PATH}")


if __name__ == "__main__":
    rebuild()
