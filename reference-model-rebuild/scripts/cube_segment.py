#!/usr/bin/env python3
"""Calculate Cube transforms from explicitly authored segment geometry.

Standard library only. Uses column vectors and R = Rz(z) @ Ry(y) @ Rx(x).
Does not read reference images, infer shapes, edit a scene, or test seams.
Exit codes: 0 success; 2 invalid input, unsupported convention, or I/O error.
"""

from __future__ import annotations

import argparse
from itertools import product
import json
import math
from pathlib import Path
import sys


def number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"{label} is outside the supported numeric range") from error
    if not math.isfinite(result):
        raise ValueError(f"{label} must be a finite number")
    return result


def vector(value: object, label: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{label} must be an array of three numbers")
    return [number(item, f"{label}[{index}]") for index, item in enumerate(value)]


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def cross(a: list[float], b: list[float]) -> list[float]:
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def unit(a: list[float], label: str) -> list[float]:
    length = math.hypot(*a)
    if not math.isfinite(length) or length == 0:
        raise ValueError(f"{label} has zero or non-finite length")
    return [value / length for value in a]


def fields(value: object, required: set[str], optional: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    missing = required - value.keys()
    unknown = value.keys() - required - optional
    if missing or unknown:
        details = []
        if missing:
            details.append("missing: " + ", ".join(sorted(missing)))
        if unknown:
            details.append("unknown: " + ", ".join(sorted(unknown)))
        raise ValueError(f"{label}: {'; '.join(details)}")
    return value


def euler_zyx(matrix: list[list[float]]) -> tuple[list[float], bool]:
    """Return native [x, y, z] degrees for Rz @ Ry @ Rx, with a stable lock case."""
    cos_y = math.hypot(matrix[0][0], matrix[1][0])
    y = math.atan2(-matrix[2][0], cos_y)
    singular = cos_y <= 1e-12
    if singular:
        x = 0.0
        z = math.atan2(-matrix[0][1], matrix[1][1])
    else:
        x = math.atan2(matrix[2][1], matrix[2][2])
        z = math.atan2(matrix[1][0], matrix[0][0])
    return [math.degrees(angle) for angle in (x, y, z)], singular


def matrix_zyx(angles: list[float]) -> list[list[float]]:
    x, y, z = map(math.radians, angles)
    sx, cx = math.sin(x), math.cos(x)
    sy, cy = math.sin(y), math.cos(y)
    sz, cz = math.sin(z), math.cos(z)
    return [[cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx],
            [sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx],
            [-sy, cy * sx, cy * cx]]


def calculate_segment(raw: object, index: int) -> dict:
    label = f"segments[{index}]"
    item = fields(raw, {"name", "a", "b", "width", "depth", "width_hint"},
                  {"overlap"}, label)
    name = item["name"]
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"{label}.name must be a non-empty string")
    a = vector(item["a"], f"{label}.a")
    b = vector(item["b"], f"{label}.b")
    width = number(item["width"], f"{label}.width")
    depth = number(item["depth"], f"{label}.depth")
    overlap = number(item.get("overlap", 0), f"{label}.overlap")
    if width <= 0 or depth <= 0 or overlap < 0:
        raise ValueError(f"{label}: width/depth must be positive; overlap must be non-negative")

    delta = [x - y for x, y in zip(a, b)]
    length = math.hypot(*delta)
    up = unit(delta, f"{label}: a - b")
    hint = unit(vector(item["width_hint"], f"{label}.width_hint"),
                f"{label}.width_hint")
    projection = dot(hint, up)
    projected_hint = [h - u * projection for h, u in zip(hint, up)]
    if math.hypot(*projected_hint) <= 1e-10:
        raise ValueError(f"{label}: width_hint is parallel or nearly parallel to the segment; choose an explicit transverse hint")
    right = unit(projected_hint, f"{label}: projected width_hint")
    normal = unit(cross(right, up), f"{label}: normal")
    right = unit(cross(up, normal), f"{label}: right")
    matrix = [[right[i], up[i], normal[i]] for i in range(3)]
    rotation, singular = euler_zyx(matrix)
    rebuilt = matrix_zyx(rotation)
    matrix_error = max(abs(matrix[i][j] - rebuilt[i][j])
                       for i in range(3) for j in range(3))
    if matrix_error > 1e-9:
        raise ValueError(f"{label}: unstable Euler conversion; inspect the explicit frame")

    center = [x / 2 + y / 2 for x, y in zip(a, b)]
    size = [width, length + overlap, depth]
    start = [c - s / 2 for c, s in zip(center, size)]
    end = [c + s / 2 for c, s in zip(center, size)]
    if (not all(math.isfinite(v) for v in size + start + end)
            or not all(lo < hi for lo, hi in zip(start, end))):
        raise ValueError(f"{label}: positive dimensions cannot be represented at this scale/center; rescale or recenter the input")

    def endpoint(distance: float) -> list[float]:
        return [center[i] + rebuilt[i][1] * distance for i in range(3)]

    nominal = {"a": endpoint(length / 2), "b": endpoint(-length / 2)}
    actual = {"positive_y": endpoint(size[1] / 2),
              "negative_y": endpoint(-size[1] / 2)}
    corners = [[center[i] + sum(rebuilt[i][j] * signs[j] * size[j] / 2
                                for j in range(3)) for i in range(3)]
               for signs in product((-1, 1), repeat=3)]
    if not all(math.isfinite(value) for point in list(nominal.values())
               + list(actual.values()) + corners for value in point):
        raise ValueError(f"{label}: transformed points exceed the supported numeric range")
    endpoint_error = max(math.hypot(*(x - y for x, y in zip(nominal[key], original)))
                         for key, original in (("a", a), ("b", b)))
    axes = [right, up, normal]
    orthogonality_error = max(abs(dot(axes[i], axes[j]) - (1 if i == j else 0))
                              for i in range(3) for j in range(3))
    return {
        "name": name,
        "center": center,
        "size": size,
        "from": start,
        "to": end,
        "origin": center,
        "rotation": rotation,
        "rotation_matrix_rows": matrix,
        "axes": {"right": right, "up": up, "normal": normal},
        "nominal_endpoints": nominal,
        "extended_endpoints": actual,
        "corners_in_input_space": corners,
        "arithmetic_checks": {
            "matrix_roundtrip_max_error": matrix_error,
            "nominal_endpoint_max_error": endpoint_error,
            "orthonormality_max_error": orthogonality_error,
        },
        "warnings": (["Euler gimbal lock: x is set to zero; compare the matrix, not individual angles."]
                     if singular else []),
    }


def calculate_plan(raw: object) -> dict:
    data = fields(raw, {"coordinate_space", "rotation_order", "segments"}, set(), "input")
    space = data["coordinate_space"]
    if not isinstance(space, str) or not space.strip():
        raise ValueError("coordinate_space must explicitly name the input coordinate frame")
    if data["rotation_order"] != "ZYX":
        raise ValueError("Only rotation_order 'ZYX' (Rz @ Ry @ Rx) is supported; verify the target editor convention")
    items = data["segments"]
    if not isinstance(items, list) or not items:
        raise ValueError("segments must be a non-empty array")
    results = []
    names = set()
    for index, item in enumerate(items):
        result = calculate_segment(item, index)
        if result["name"] in names:
            raise ValueError(f"Duplicate input segment name: {result['name']}")
        names.add(result["name"])
        results.append(result)
    return {
        "coordinate_space": space,
        "rotation_order": "ZYX",
        "rotation_field_order": ["x", "y", "z"],
        "angle_unit": "degrees",
        "matrix_convention": "column vectors; R = Rz(z) @ Ry(y) @ Rx(x)",
        "status": "arithmetic_only",
        "notice": "No scene edits. Not a seam, collision, UV, rigging, or visual-fidelity check. Convert to the actual parent coordinate system before use.",
        "segments": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Explicit segment JSON; see cube-placement-and-curves.md")
    parser.add_argument("--json-out", type=Path, help="Optional output .json file; never the input or a model")
    args = parser.parse_args()
    try:
        source = args.input.resolve(strict=True)
        output = args.json_out.resolve() if args.json_out else None
        if output:
            if output == source or (output.exists() and output.samefile(source)):
                raise ValueError("Output must not overwrite the input")
            if output.suffix.lower() != ".json":
                raise ValueError("Output must end in .json; model files cannot be overwritten")
        plan = calculate_plan(json.loads(source.read_text(encoding="utf-8-sig")))
        encoded = json.dumps(plan, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(encoded, encoding="utf-8")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(encoded, end="")
        return 0
    except (OSError, UnicodeError, ValueError, OverflowError) as error:
        parser.exit(2, f"cube_segment: {error}\n")


if __name__ == "__main__":
    sys.exit(main())
