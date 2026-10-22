"""Novel 后端通用纯函数。"""


def merge_named(rows: list[dict], key: str) -> list[dict]:
    """按名称合并章节抽取对象，并保留来源物理段与最高重要度。"""
    merged = {}
    for row in rows:
        for item in row.get(key) or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            current = merged.setdefault(
                name,
                {"name": name, "attributes": {}, "sourceSegmentOrders": [], "importance": 1},
            )
            appearance = str(item.get("appearance") or "").strip()
            if appearance and appearance not in str(current.get("appearance") or "").split("；"):
                current["appearance"] = "；".join(filter(None, [current.get("appearance"), appearance]))
            # 模型偶尔会把 attributes 返回成字符串/数组；不能让单个字段
            # 的协议偏差中断整个副本汇总（dict.update 会抛 sequence length 错误）。
            attributes = item.get("attributes")
            if isinstance(attributes, dict):
                current["attributes"].update(attributes)
            current["importance"] = max(
                current["importance"],
                min(3, max(1, int(item.get("importance") or 1))),
            )
            order = row["sourceSegmentOrder"]
            if order not in current["sourceSegmentOrders"]:
                current["sourceSegmentOrders"].append(order)
    return list(merged.values())
