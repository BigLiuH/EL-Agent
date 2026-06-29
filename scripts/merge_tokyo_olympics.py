"""
合并2020年东京奥运会重复实体。

重复实体（同一真实事件）：
- EVENT_0003: "2020年东京奥运会" (保留)
- EVENT_0005: "2020年夏季奥林匹克运动会" (合并入 EVENT_0003)
- EVENT_0643: "2020年东京夏季奥运会" (合并入 EVENT_0003)

不合并：
- EVENT_0004: "2020年东京奥运会羽毛球比赛" (子赛事，不同实体)

修改三个文件：
1. knowledge_base_merged.json - 删除EVENT_0005/EVENT_0643，合并到EVENT_0003
2. aliases_merged.json - 修改别名指向EVENT_0003
3. llm_extracted_merged.json - 替换entity_id引用
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
KB_PATH = ROOT / "Dataset" / "knowledge_base_merged.json"
ALIASES_PATH = ROOT / "Dataset" / "aliases_merged.json"
LLM_PATH = ROOT / "Dataset" / "llm_extracted_merged.json"


def merge_kb():
    """合并知识库"""
    with open(KB_PATH, "r", encoding="utf-8") as f:
        kb = json.load(f)

    entities = kb["entities"]
    new_entities = []
    merged_aliases = set()
    merged_sources = set()
    merged_descriptions = []

    # Find EVENT_0003 and collect data from entities to merge
    for e in entities:
        eid = e["entity_id"]
        if eid == "EVENT_0003":
            # Collect existing data
            merged_aliases.update(e.get("aliases", []))
            merged_sources.update(e.get("sources", []))
            if e.get("description"):
                merged_descriptions.append(e["description"])
        elif eid in ("EVENT_0005", "EVENT_0643"):
            # Collect data from entities to be merged
            merged_aliases.update(e.get("aliases", []))
            merged_sources.update(e.get("sources", []))
            if e.get("description"):
                merged_descriptions.append(e["description"])
            print(f"  [KB] Removing {eid}: {e['standard_name']}")
            continue  # skip this entity (delete)
        new_entities.append(e)

    # Pick best description (longest)
    best_desc = max(merged_descriptions, key=len) if merged_descriptions else ""

    # Update EVENT_0003 in new_entities
    for e in new_entities:
        if e["entity_id"] == "EVENT_0003":
            e["aliases"] = sorted(set(a for a in merged_aliases if a != e["standard_name"]))
            e["sources"] = sorted(merged_sources)
            e["description"] = best_desc
            print(f"  [KB] Updated EVENT_0003: aliases={e['aliases']}, sources={e['sources']}")
            break

    kb["entities"] = new_entities
    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    print(f"  [KB] Saved: {len(new_entities)} entities (removed 2)")


def merge_aliases():
    """更新别名文件"""
    with open(ALIASES_PATH, "r", encoding="utf-8") as f:
        aliases = json.load(f)

    # Update alias entries that point to EVENT_0005 or EVENT_0643
    updates = 0
    for alias_key, entry in aliases.items():
        if entry.get("entity_id") in ("EVENT_0005", "EVENT_0643"):
            old_eid = entry["entity_id"]
            old_name = entry["standard_name"]
            entry["entity_id"] = "EVENT_0003"
            entry["standard_name"] = "2020年东京奥运会"
            updates += 1
            print(f"  [Aliases] '{alias_key}': {old_eid}/{old_name} → EVENT_0003/2020年东京奥运会")

    with open(ALIASES_PATH, "w", encoding="utf-8") as f:
        json.dump(aliases, f, ensure_ascii=False, indent=2)
    print(f"  [Aliases] Updated {updates} alias entries")


def merge_llm():
    """更新标注文件"""
    with open(LLM_PATH, "r", encoding="utf-8") as f:
        articles = json.load(f)

    updates = 0
    for article in articles:
        for mention in article.get("mentions", []):
            eid = mention.get("entity_id")
            if eid == "EVENT_0005":
                mention["entity_id"] = "EVENT_0003"
                mention["standard_name"] = "2020年东京奥运会"
                updates += 1
            elif eid == "EVENT_0643":
                mention["entity_id"] = "EVENT_0003"
                mention["standard_name"] = "2020年东京奥运会"
                updates += 1

    with open(LLM_PATH, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"  [LLM] Updated {updates} mention entries")


if __name__ == "__main__":
    print("Merging 2020 Tokyo Olympics duplicate entities...\n")
    merge_kb()
    print()
    merge_aliases()
    print()
    merge_llm()
    print("\nDone! EVENT_0005 + EVENT_0643 → EVENT_0003")
