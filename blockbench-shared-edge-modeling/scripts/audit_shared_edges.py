#!/usr/bin/env python3
"""Read-only static BBModel actual-edge audit. Standard library only.

Exit: 0 all declared numeric checks pass; 1 a declared seam differs;
2 invalid/unsupported input. No visual, closure or animation certification.
"""
import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import sys


def number(x, label):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise ValueError(f'{label}: expected a finite number')
    return float(x)


def vec(x, label):
    if not isinstance(x, list) or len(x) != 3:
        raise ValueError(f'{label}: expected three coordinates')
    return [number(v, label) for v in x]


def matrix(angles):
    x, y, z = map(math.radians, angles)
    sx, cx, sy, cy, sz, cz = math.sin(x), math.cos(x), math.sin(y), math.cos(y), math.sin(z), math.cos(z)
    return [[cz*cy, cz*sy*sx-sz*cx, cz*sy*cx+sz*sx],
            [sz*cy, sz*sy*sx+cz*cx, sz*sy*cx-cz*sx],
            [-sy, cy*sx, cy*cx]]


def transform(p, origin, rotation):
    d = [a-b for a, b in zip(p, origin)]
    return [origin[i] + sum(rotation[i][j]*d[j] for j in range(3)) for i in range(3)]


def verify_supported(obj):
    for field in ['inflate', 'stretch']:
        value = obj.get(field, 0)
        if value not in (0, 0.0, None):
            raise ValueError(f'{obj.get("uuid")}: {field} requires native geometry evaluation')
    if obj.get('rescale'):
        raise ValueError('rescale requires native geometry evaluation')
    if obj.get('scale', [1, 1, 1]) not in (1, 1.0, [1, 1, 1]):
        raise ValueError('non-unit scale requires native geometry evaluation')


def geometry(model):
    if not isinstance(model, dict):
        raise ValueError('model must be a JSON object')
    elements = {}
    for e in model.get('elements', []):
        u = e.get('uuid')
        if not isinstance(u, str) or not u or u in elements:
            raise ValueError('missing or duplicate element UUID')
        elements[u] = e
    groups = {}
    for g in model.get('groups', []):
        u = g.get('uuid')
        if not isinstance(u, str) or not u or u in groups or u in elements:
            raise ValueError('missing, duplicate or cross-type group UUID')
        groups[u] = g
    parents = {}
    seen_groups = set()

    def walk(nodes, chain=(), ancestors=frozenset()):
        for node in nodes:
            if isinstance(node, str) and node in elements:
                if node in parents:
                    raise ValueError('element appears more than once in outliner')
                parents[node] = chain
                continue
            if isinstance(node, str):
                if node not in groups:
                    raise ValueError(f'unresolved outliner UUID: {node}')
                node = groups[node]
            if not isinstance(node, dict) or not node.get('uuid'):
                raise ValueError('invalid outliner group')
            u = node['uuid']
            if u in elements or u in ancestors or u in seen_groups:
                raise ValueError('cyclic or cross-type group UUID')
            seen_groups.add(u)
            g = {**groups.get(u, {}), **node}
            verify_supported(g)
            o = vec(g.get('origin', [0, 0, 0]), 'group origin')
            r = matrix(vec(g.get('rotation', [0, 0, 0]), 'group rotation'))
            walk(g.get('children', []), chain + ((o, r),), ancestors | {u})

    walk(model.get('outliner', []))
    out = {}
    for u, e in elements.items():
        if e.get('type', 'cube') != 'cube':
            continue
        verify_supported(e)
        lo, hi = vec(e.get('from'), 'from'), vec(e.get('to'), 'to')
        if any(a >= b for a, b in zip(lo, hi)):
            raise ValueError(f'{u}: positive dimensions required')
        o = vec(e.get('origin', [0, 0, 0]), 'origin')
        r = matrix(vec(e.get('rotation', [0, 0, 0]), 'rotation'))
        points = []
        for i in range(8):
            p = [hi[j] if i & (1 << j) else lo[j] for j in range(3)]
            p = transform(p, o, r)
            # Stored group origins are in the model-coordinate convention.
            # Apply nearest parent first, then its enclosing parents.
            for po, pr in reversed(parents.get(u, ())):
                p = transform(p, po, pr)
            points.append(p)
        out[u] = {'name': e.get('name', u), 'corners': points}
    return out


EDGES = [(i, i ^ (1 << bit)) for i in range(8) for bit in range(3) if i < (i ^ (1 << bit))]


def edge_indices(x):
    if not isinstance(x, list) or len(x) != 2 or any(type(v) is not int for v in x):
        raise ValueError('edge must contain two integer corner indices')
    if not all(0 <= v < 8 for v in x) or (x[0] ^ x[1]) not in (1, 2, 4):
        raise ValueError('corner indices must form an actual Cube edge')
    return tuple(x)


def edge_error(a, b):
    return min(max(math.dist(a[0], b[0]), math.dist(a[1], b[1])),
               max(math.dist(a[0], b[1]), math.dist(a[1], b[0])))


def audit(model, manifest):
    if not isinstance(manifest, dict):
        raise ValueError('manifest must be a JSON object')
    if manifest.get('rotation_order') != 'ZYX':
        raise ValueError('explicit rotation_order ZYX is required')
    tolerance = number(manifest.get('tolerance'), 'tolerance')
    if tolerance <= 0:
        raise ValueError('tolerance must be positive')
    seams = manifest.get('seams')
    if not isinstance(seams, list) or not seams:
        raise ValueError('at least one declared seam is required')
    cubes = geometry(model)
    result = []
    names = set()
    for item in seams:
        if not isinstance(item, dict):
            raise ValueError('each seam must be a JSON object')
        sid = item.get('id')
        if not isinstance(sid, str) or not sid.strip() or sid in names:
            raise ValueError('each seam requires a unique non-empty id')
        names.add(sid)
        a, b = item.get('a'), item.get('b')
        if a == b or a not in cubes or b not in cubes:
            raise ValueError(f'{sid}: two distinct existing Cube UUIDs required')
        if ('edge_a' in item) != ('edge_b' in item):
            raise ValueError('declare both edge indices or omit both')
        ea = [edge_indices(item['edge_a'])] if 'edge_a' in item else EDGES
        eb = [edge_indices(item['edge_b'])] if 'edge_b' in item else EDGES
        expected = item.get('expected_edge')
        if expected is not None:
            if not isinstance(expected, list) or len(expected) != 2:
                raise ValueError('expected_edge requires two endpoints')
            expected = [vec(p, 'expected edge') for p in expected]
            if math.dist(*expected) <= tolerance:
                raise ValueError('expected edge length must exceed tolerance')
        candidates = []
        for ai, bi in itertools.product(ea, eb):
            pa = [cubes[a]['corners'][i] for i in ai]
            pb = [cubes[b]['corners'][i] for i in bi]
            err = edge_error(pa, pb)
            target_error = max(edge_error(pa, expected), edge_error(pb, expected)) if expected else 0.
            candidates.append((max(err, target_error), err, target_error, ai, bi, pa, pb))
        score, err, target, ai, bi, pa, pb = min(candidates, key=lambda c: c[0])
        result.append({'id': sid, 'a': a, 'b': b, 'edge_a': ai, 'edge_b': bi,
                       'world_edge_a': pa, 'world_edge_b': pb, 'endpoint_error': err,
                       'expected_edge_error': target if expected else None,
                       'passed_numeric': score <= tolerance})
    return {'rotation_order': 'ZYX', 'scope': 'static declared actual Cube edges only',
            'tolerance': tolerance, 'passed_numeric': all(r['passed_numeric'] for r in result),
            'seams': result, 'not_evaluated': ['visual exterior', 'undeclared seams', 'volume closure', 'textures', 'animation']}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.report.resolve() in (args.model.resolve(), args.manifest.resolve()):
            raise ValueError('report path must differ from both input files')
        raw = args.model.read_bytes()
        report = audit(json.loads(raw.decode('utf-8-sig')), json.loads(args.manifest.read_text(encoding='utf-8-sig')))
        report['model'] = str(args.model.resolve())
        report['model_sha256'] = hashlib.sha256(raw).hexdigest()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'passed_numeric': report['passed_numeric'], 'seams': len(report['seams']),
                          'report': str(args.report.resolve())}, ensure_ascii=False))
        return 0 if report['passed_numeric'] else 1
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f'Input not evaluated: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
