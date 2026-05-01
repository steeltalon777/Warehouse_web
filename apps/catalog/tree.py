from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


TreeUrlBuilder = Callable[[dict[str, Any]], str]


def normalize_tree_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        **item,
        "id": _normalize_id(item.get("id") or item.get("item_id")),
        "category_id": _normalize_id(item.get("category_id")),
        "name": str(item.get("name") or item.get("sku") or "").strip(),
        "sku": str(item.get("sku") or "").strip(),
        "unit_symbol": str(item.get("unit_symbol") or item.get("unit") or "").strip(),
        "is_active": bool(item.get("is_active", True)),
    }


def build_category_item_tree(
    *,
    categories: list[dict[str, Any]],
    items: list[dict[str, Any]],
    category_url_builder: TreeUrlBuilder,
    item_url_builder: TreeUrlBuilder,
    category_delete_builder: TreeUrlBuilder | None = None,
    item_delete_builder: TreeUrlBuilder | None = None,
    selected_kind: str | None = None,
    selected_id: str | int | None = None,
) -> list[dict[str, Any]]:
    normalized_selected_id = _normalize_id(selected_id)
    category_by_id: dict[str, dict[str, Any]] = {}
    normalized_categories: list[dict[str, Any]] = []

    for category in categories:
        category_id = _normalize_id(category.get("id") or category.get("category_id"))
        if not category_id:
            continue
        normalized = {
            **category,
            "id": category_id,
            "parent_id": _normalize_id(category.get("parent_id")),
            "name": str(category.get("name") or "").strip(),
            "code": str(category.get("code") or "").strip(),
            "is_active": bool(category.get("is_active", True)),
        }
        category_by_id[category_id] = normalized
        normalized_categories.append(normalized)

    categories_by_parent: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    for normalized in normalized_categories:
        parent_id = normalized["parent_id"]
        if parent_id and parent_id not in category_by_id:
            parent_id = None
        categories_by_parent[parent_id].append(normalized)

    items_by_category: dict[str | None, list[dict[str, Any]]] = defaultdict(list)
    item_by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        normalized_item = normalize_tree_item(item)
        item_id = normalized_item["id"]
        if not item_id:
            continue
        item_by_id[item_id] = normalized_item
        category_id = normalized_item["category_id"]
        if category_id and category_id not in category_by_id:
            category_id = None
        items_by_category[category_id].append(normalized_item)

    for siblings in categories_by_parent.values():
        siblings.sort(key=lambda entry: (entry.get("name", "").casefold(), entry.get("id", "")))
    for siblings in items_by_category.values():
        siblings.sort(key=lambda entry: (entry.get("name", "").casefold(), entry.get("sku", ""), entry.get("id", "")))

    expanded_category_ids = _resolve_expanded_category_ids(
        category_by_id=category_by_id,
        item_by_id=item_by_id,
        selected_kind=selected_kind,
        selected_id=normalized_selected_id,
    )

    counter = 0

    def build_category_node(category: dict[str, Any], *, level: int = 0) -> dict[str, Any]:
        nonlocal counter
        counter += 1
        category_id = category["id"]
        child_categories = [
            build_category_node(child_category, level=level + 1)
            for child_category in categories_by_parent.get(category_id, [])
        ]
        child_items = [
            build_item_node(item, level=level + 1)
            for item in items_by_category.get(category_id, [])
        ]
        children = [*child_categories, *child_items]
        is_selected = selected_kind == "category" and category_id == normalized_selected_id
        return {
            "uid": f"tree-node-{counter}",
            "node_type": "category",
            "id": category_id,
            "name": category.get("name") or category_id,
            "meta": category.get("code") or "",
            "is_active": bool(category.get("is_active", True)),
            "href": category_url_builder(category),
            "delete_url": category_delete_builder(category) if category_delete_builder else "",
            "selected": is_selected,
            "expanded": level == 0 or category_id in expanded_category_ids,
            "children": children,
            "level": level,
        }

    def build_item_node(item: dict[str, Any], *, level: int = 0) -> dict[str, Any]:
        nonlocal counter
        counter += 1
        item_id = item["id"]
        is_selected = selected_kind == "item" and item_id == normalized_selected_id
        meta_parts = [part for part in [item.get("sku"), item.get("unit_symbol")] if part]
        return {
            "uid": f"tree-node-{counter}",
            "node_type": "item",
            "id": item_id,
            "name": item.get("name") or item_id,
            "meta": " / ".join(meta_parts),
            "is_active": bool(item.get("is_active", True)),
            "href": item_url_builder(item),
            "delete_url": item_delete_builder(item) if item_delete_builder else "",
            "selected": is_selected,
            "expanded": False,
            "children": [],
            "level": level,
        }

    root_nodes = [build_category_node(category) for category in categories_by_parent.get(None, [])]
    orphan_items = [build_item_node(item) for item in items_by_category.get(None, [])]
    return [*root_nodes, *orphan_items]


def _resolve_expanded_category_ids(
    *,
    category_by_id: dict[str, dict[str, Any]],
    item_by_id: dict[str, dict[str, Any]],
    selected_kind: str | None,
    selected_id: str | None,
) -> set[str]:
    if not selected_kind or not selected_id:
        return set()

    if selected_kind == "item":
        selected_item = item_by_id.get(selected_id)
        if not selected_item:
            return set()
        current_category_id = _normalize_id(selected_item.get("category_id"))
    else:
        current_category_id = selected_id

    expanded: set[str] = set()
    while current_category_id:
        expanded.add(current_category_id)
        current_category = category_by_id.get(current_category_id)
        if not current_category:
            break
        current_category_id = _normalize_id(current_category.get("parent_id"))
    return expanded


def _normalize_id(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None
