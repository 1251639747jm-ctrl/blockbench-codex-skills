#!/usr/bin/env python3
"""Read-only object budget audit for uncompressed Blockbench .bbmodel JSON.

Counts elements, groups (deduplicated across groups/outliner), and saved
reference images. Does not assess visual fidelity or modify the model.
Uses only the Python standard library. Exit codes: 0 checks pass, 1 checks
fail, 2 invalid input or report path.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


def audit_model(source: Path, limit: int = 2000, cube_only: bool = False) -> dict:
    raw = source.read_bytes()
    model = json.loads(raw.decode("utf-8-sig"))
    if not isinstance(model, dict) or "elements" not in model:
        raise ValueError("Expected a .bbmodel JSON object with an elements array")

    def array(container: dict, key: str) -> list:
        value = container.get(key, [])
        if not isinstance(value, list):
            raise ValueError(f"{key} must be an array")
        return value

    elements = array(model, "elements")
    definitions = array(model, "groups")
    outliner = array(model, "outliner")
    references = array(model, "reference_images")
    issues: list[str] = []
    kinds: Counter = Counter()
    element_ids: list[str] = []
    group_ids: set[str] = set()
    declared_group_ids: list[str] = []
    placed_group_ids: list[str] = []
    leaf_references: list[str] = []
    anonymous_groups = 0
    vertex_count = 0
    face_count = 0

    def identifier(item: dict, label: str) -> str | None:
        value = item.get("uuid")
        if not isinstance(value, str) or not value:
            issues.append(f"{label}: missing or invalid UUID; identity cannot be verified")
            return None
        return value

    for index, element in enumerate(elements):
        if not isinstance(element, dict):
            raise ValueError(f"elements[{index}] must be an object")
        item_id = identifier(element, f"elements[{index}]")
        if item_id:
            element_ids.append(item_id)
        kind = element.get("type")
        if kind is None and "from" in element and "to" in element:
            kind = "cube"
        if not isinstance(kind, str) or not kind:
            kind = "unknown"
        kinds[kind] += 1
        if kind == "mesh":
            for key in ("vertices", "faces"):
                value = element.get(key, {})
                if not isinstance(value, (dict, list)):
                    raise ValueError(f"elements[{index}].{key} must be an object or array")
                if key == "vertices":
                    vertex_count += len(value)
                else:
                    face_count += len(value)

    def register_group(group: dict, label: str, placed: bool) -> None:
        nonlocal anonymous_groups
        item_id = identifier(group, label)
        if item_id:
            group_ids.add(item_id)
            (placed_group_ids if placed else declared_group_ids).append(item_id)
        else:
            # Count each occurrence conservatively and fail the identity
            # check instead of claiming an exact passing count.
            anonymous_groups += 1

    for index, group in enumerate(definitions):
        if not isinstance(group, dict):
            raise ValueError(f"groups[{index}] must be an object")
        register_group(group, f"groups[{index}]", placed=False)

    def walk(nodes: list, path: str) -> None:
        for index, node in enumerate(nodes):
            label = f"{path}[{index}]"
            if isinstance(node, str):
                leaf_references.append(node)
            elif isinstance(node, dict):
                register_group(node, label, placed=True)
                walk(array(node, "children"), f"{label}.children")
            else:
                raise ValueError(f"{label} must be a UUID string or group object")

    walk(outliner, "outliner")

    for label, values in (
        ("elements", element_ids),
        ("groups definitions", declared_group_ids),
        ("outliner group placements", placed_group_ids),
        ("outliner leaf references", leaf_references),
    ):
        repeated = sorted(key for key, count in Counter(values).items() if count > 1)
        if repeated:
            issues.append(f"Duplicate UUIDs in {label}: {', '.join(repeated[:5])}")
    collisions = set(element_ids) & group_ids
    if collisions:
        issues.append("UUIDs shared by an element and a group: " + ", ".join(sorted(collisions)[:5]))
    dangling = set(leaf_references) - set(element_ids) - group_ids
    if dangling:
        issues.append("Outliner references unknown UUIDs: " + ", ".join(sorted(dangling)[:5]))

    group_count = len(group_ids) + anonymous_groups
    total = len(elements) + group_count + len(references)
    checks = {
        "within_budget": total <= limit,
        "identities_consistent": not issues,
    }
    if cube_only:
        checks["cube_only"] = kinds.get("cube", 0) == len(elements)
    meta = model.get("meta", {})
    if not isinstance(meta, dict):
        meta = {}

    return {
        "source": str(source.resolve()),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "model_format": meta.get("model_format"),
        "format_version": meta.get("format_version"),
        "limit": limit,
        "elements": len(elements),
        "elements_by_type": dict(sorted(kinds.items())),
        "groups": group_count,
        "saved_reference_images": len(references),
        "total_objects": total,
        "remaining_budget": limit - total,
        "mesh_vertices": vertex_count,
        "mesh_faces": face_count,
        "elements_with_visibility_false": sum(e.get("visibility") is False for e in elements),
        "checks": checks,
        "counts_check_passed": all(checks.values()),
        "structural_issues": issues,
        "scope": "Saved elements, groups/outliner, and reference_images only; count plugin-specific and unsaved scene objects separately. Visual fidelity is not assessed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path, help="Uncompressed .bbmodel JSON file")
    parser.add_argument("--limit", type=int, default=2000, help="Total object limit (default: 2000)")
    parser.add_argument("--cube-only", action="store_true", help="Also require every element to be a Cube")
    parser.add_argument("--json-out", type=Path, help="Optional .json report file; never the source model")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    try:
        source = args.model.resolve(strict=True)
        output = args.json_out.resolve() if args.json_out else None
        if output:
            if output == source or (output.exists() and output.samefile(source)):
                raise ValueError("Report path must not refer to the source model")
            if output.suffix.lower() != ".json":
                raise ValueError("Report path must end in .json; model files cannot be overwritten")
        report = audit_model(source, args.limit, args.cube_only)
        encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(encoded, encoding="utf-8")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(encoded, end="")
        return 0 if report["counts_check_passed"] else 1
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        parser.exit(2, f"audit_bbmodel: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
