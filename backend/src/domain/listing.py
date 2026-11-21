"""备料清单版本展开、版本间差量与分包指纹的纯计算。"""

import hashlib
import json

GROUPS_TABLE = "切树候选组"
ENTRY_FIELDS = ("name", "group", "partners", "shared", "variable")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def entries_from_run(result, rows):
    """从签核运行的候选组表展开每规格清单条目，名称以数据批次为准。"""
    names = {row["spec_id"]: row["name"] for row in rows}
    table = next((item for item in (result or {}).get("tables", []) if item.get("title") == GROUPS_TABLE), None)
    if table is None:
        raise ValueError("签核结果缺少候选组表，无法生成备料清单。")
    entries = []
    for group in table["rows"]:
        members = group["members"].split("、")
        for spec_id in members:
            entries.append({
                "spec_id": spec_id,
                "name": names.get(spec_id, ""),
                "group": group["group"],
                "partners": [item for item in members if item != spec_id],
                "shared": group["shared"],
                "variable": group["variable"],
            })
    entries.sort(key=lambda item: item["spec_id"].casefold())
    return entries


def diff_entries(old_entries, new_entries):
    """按规格编号对齐两版条目；任一条目字段不同即记修改，同组伙伴变化也算。"""
    before = {item["spec_id"]: item for item in old_entries}
    after = {item["spec_id"]: item for item in new_entries}
    items = []
    for spec_id in sorted(before.keys() | after.keys(), key=str.casefold):
        old, new = before.get(spec_id), after.get(spec_id)
        if old is None:
            items.append({"op": "added", "spec_id": spec_id, "after": new})
        elif new is None:
            items.append({"op": "removed", "spec_id": spec_id, "before": old})
        elif canonical(old) != canonical(new):
            changes = [key for key in ENTRY_FIELDS if old[key] != new[key]]
            items.append({"op": "changed", "spec_id": spec_id, "before": old, "after": new, "changes": changes})
    return items


def chunks(items, size):
    return [items[index:index + size] for index in range(0, len(items), size)]


def pack_view(site, from_version, to_version, seq, package_count, items):
    """站点下载的包文档，内容指纹对该文档计算。"""
    return {
        "site": site,
        "from_version": from_version,
        "to_version": to_version,
        "seq": seq,
        "package_count": package_count,
        "items": items,
    }


def summarize(items):
    summary = {"added": 0, "removed": 0, "changed": 0}
    for item in items:
        summary[item["op"]] += 1
    return summary
