#!/usr/bin/env python3
"""Read-only BBModel change inventory; optional explicit edit-scope verification."""
import argparse
import base64
from collections import Counter
import hashlib
import io
import json
from pathlib import Path
import sys


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def pointer(key):
    return str(key).replace('~', '~0').replace('/', '~1')


def changes(before, after, path=''):
    """Missing differs from null. Lists retain order (including keyframe order)."""
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            child = path + '/' + pointer(key)
            if key not in before:
                yield {'path': child, 'operation': 'add', 'after': after[key]}
            elif key not in after:
                yield {'path': child, 'operation': 'remove', 'before': before[key]}
            else:
                yield from changes(before[key], after[key], child)
    elif isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        for index, (a, b) in enumerate(zip(before, after)):
            yield from changes(a, b, path + '/' + str(index))
    elif before != after or isinstance(before, bool) != isinstance(after, bool):
        yield {'path': path, 'operation': 'replace', 'before': before, 'after': after}


def indexed(items, kind, warnings):
    result = {}
    for index, item in enumerate(items):
        key = item.get('uuid')
        if not key:
            key = '@index:' + str(index)
            warnings.append(f'{kind}[{index}] has no UUID; matched by array position, not identity.')
        if key in result:
            raise ValueError(f'Duplicate {kind} UUID: {key}')
        result[key] = item
    return result


def normalize(model, warnings):
    groups = indexed(model.get('groups', []), 'group', warnings).copy()
    hierarchy = {}

    def walk(nodes, parent=None):
        for index, node in enumerate(nodes):
            key = node if isinstance(node, str) else node['uuid']
            if key in hierarchy:
                raise ValueError(f'Duplicate outliner reference: {key}')
            hierarchy[key] = {'parent': parent, 'order': index}
            if isinstance(node, dict):
                data = {k: v for k, v in node.items() if k not in ('uuid', 'children')}
                # Older BBModel stores group properties directly in outliner.
                if key in groups:
                    # Both representations are saved data; neither may hide the other.
                    hierarchy[key]['outliner_properties'] = data
                else:
                    groups[key] = {'uuid': key, **data}
                walk(node.get('children', []), key)

    walk(model.get('outliner', []))
    elements = indexed(model.get('elements', []), 'element', warnings)
    textures = indexed(model.get('textures', []), 'texture', warnings)
    texture_ids = list(textures)
    bindings = {}
    for key, element in elements.items():
        faces = {}
        for face, data in element.get('faces', {}).items():
            ref = data.get('texture')
            if isinstance(ref, int) and not isinstance(ref, bool):
                faces[face] = texture_ids[ref] if 0 <= ref < len(texture_ids) else {'unresolved_index': ref}
            elif isinstance(ref, str) and ref.isdecimal():
                index = int(ref)
                faces[face] = texture_ids[index] if index < len(texture_ids) else {'unresolved_index': index}
            else:
                faces[face] = ref
        bindings[key] = faces
    return {
        'elements': elements,
        'groups': groups,
        'hierarchy': hierarchy,
        'animations': indexed(model.get('animations', []), 'animation', warnings),
        'textures': {k: {a: b for a, b in t.items() if a != 'source' or not isinstance(b, str) or not b.startswith('data:')} for k, t in textures.items()},
        'texture_bindings': bindings,
        'project': {'project': {k: v for k, v in model.items() if k not in ('elements', 'groups', 'outliner', 'animations', 'textures')}},
    }, textures


def image_data(texture, model_path):
    source = texture.get('source', '')
    if source.startswith('data:'):
        header, encoded = source.split(',', 1)
        if ';base64' not in header:
            raise ValueError('Texture data URL must use base64 encoding')
        return base64.b64decode(encoded, validate=True), 'embedded'
    for key in ('relative_path', 'path', 'source'):
        value = texture.get(key)
        if value and not value.startswith('data:'):
            path = Path(value)
            if not path.is_absolute():
                path = model_path.parent / path
            if path.is_file():
                return path.read_bytes(), str(path.resolve())
    raise ValueError('No readable embedded or external texture; preserve external images with each snapshot')


def allowed(change, scope):
    for rule in scope.get('allow', []):
        if rule['category'] != change['category']:
            continue
        if 'id' in rule and rule['id'] != change['id']:
            continue
        prefix = rule.get('path', '')
        if not prefix or change['path'] == prefix or change['path'].startswith(prefix + '/'):
            return True
    return False


def texture_diff(key, before, after, paths, output, scope, issues):
    from PIL import Image
    images, origins, hashes = [], [], []
    for texture, model_path in zip((before, after), paths):
        data, origin = image_data(texture, model_path)
        with Image.open(io.BytesIO(data)) as opened:
            images.append(opened.convert('RGBA'))
        origins.append(origin)
        hashes.append(sha(data))
    if origins[0] == origins[1] != 'embedded':
        issues.append(f'Texture {key}: both versions read the same external file; historical pixels cannot be verified. Embed or snapshot external textures separately.')
    a, b = images
    if a.size != b.size:
        return {'path': '', 'operation': 'resize', 'before': list(a.size), 'after': list(b.size), 'source_sha256': hashes, 'origins': origins}
    ap, bp = a.load(), b.load()
    changed = [(x, y) for y in range(a.height) for x in range(a.width) if ap[x, y] != bp[x, y]]
    if not changed:
        return None
    mask = Image.new('RGBA', a.size)
    for point in changed:
        mask.putpixel(point, (255, 0, 80, 255))
    filename = 'texture_' + sha(key.encode())[:12] + '_changes.png'
    mask.save(output / filename)
    regions = [r['rect'] for r in (scope or {}).get('texture_regions', []) if r['id'] == key]
    outside = sum(not any(x0 <= x < x1 and y0 <= y < y1 for x0, y0, x1, y1 in regions) for x, y in changed)
    return {'path': '', 'operation': 'pixels', 'size': list(a.size), 'changed_pixels': len(changed),
            'bounds_xyxy_exclusive': list(mask.getbbox()), 'mask': filename, 'outside_allowed_pixels': outside if scope is not None else None,
            'source_sha256': hashes, 'origins': origins}


def validate_scope(scope):
    categories = {'elements', 'groups', 'hierarchy', 'animations', 'textures', 'texture_bindings', 'texture_pixels', 'project'}
    if set(scope) - {'allow', 'texture_regions'}:
        raise ValueError('Scope accepts only allow and texture_regions')
    for rule in scope.get('allow', []):
        if rule.get('category') not in categories or set(rule) - {'category', 'id', 'path'}:
            raise ValueError(f'Invalid scope rule: {rule}')
        if rule.get('path') and not rule['path'].startswith('/'):
            raise ValueError('Scope paths use JSON Pointer, beginning with /')
    for rule in scope.get('texture_regions', []):
        if set(rule) != {'id', 'rect'} or len(rule['rect']) != 4:
            raise ValueError(f'Invalid texture region: {rule}')
        x0, y0, x1, y1 = rule['rect']
        if not all(isinstance(v, int) for v in rule['rect']) or not (0 <= x0 < x1 and 0 <= y0 < y1):
            raise ValueError('Texture rectangles use nonnegative integer [left, top, right, bottom), with positive area')


def compare(before_path, after_path, output, scope=None):
    paths = [Path(before_path).resolve(), Path(after_path).resolve()]
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('Report output must be empty; keep prior evidence in a separate directory')
    output.mkdir(parents=True, exist_ok=True)
    if scope is not None:
        validate_scope(scope)
    hashes = [sha(p.read_bytes()) for p in paths]
    warnings, issues = [], []
    (a, ta), (b, tb) = [normalize(load(p), warnings) for p in paths]
    result = []
    for category in a:
        for key in sorted(a[category].keys() | b[category].keys()):
            left, right = a[category].get(key), b[category].get(key)
            label = (right or left or {}).get('name', key)
            if left is None or right is None:
                records = [{'path': '', 'operation': 'add' if left is None else 'remove', 'before': left, 'after': right}]
            else:
                records = changes(left, right)
            for change in records:
                result.append({'category': category, 'id': key, 'name': label, **change})
    for key in sorted(ta.keys() | tb.keys()):
        try:
            if key not in ta or key not in tb:
                from PIL import Image
                texture, model_path = (tb[key], paths[1]) if key in tb else (ta[key], paths[0])
                data, origin = image_data(texture, model_path)
                with Image.open(io.BytesIO(data)) as opened:
                    opened.load()
                    size = list(opened.size)
                change = {'path': '', 'operation': 'add' if key in tb else 'remove', 'size': size,
                          'source_sha256': sha(data), 'origin': origin}
            else:
                change = texture_diff(key, ta[key], tb[key], paths, output, scope, issues)
            if change:
                result.append({'category': 'texture_pixels', 'id': key, 'name': (tb.get(key) or ta[key]).get('name', key), **change})
        except (ValueError, OSError, ImportError) as error:
            issues.append(f'Texture {key}: {error}')
    if hashes != [sha(p.read_bytes()) for p in paths]:
        issues.append('A source model changed during comparison; rerun using stable snapshots')
    for change in result:
        if scope is not None:
            within = allowed(change, scope)
            if change['category'] == 'texture_pixels' and change['operation'] == 'pixels':
                within = within or change['outside_allowed_pixels'] == 0
            change['within_scope'] = within
    violations = sum(c.get('within_scope') is False for c in result)
    status = 'incomplete' if issues or warnings else ('outside_scope' if violations else 'within_scope' if scope is not None else 'inventory_only')
    report = {'schema_version': 1, 'before': str(paths[0]), 'after': str(paths[1]), 'source_sha256': hashes,
              'status': status, 'scope': scope, 'summary': dict(Counter(c['category'] for c in result)),
              'change_count': len(result), 'out_of_scope_count': violations, 'warnings': warnings, 'issues': issues, 'changes': result,
              'limits': ['Saved-data comparison, not a visual-quality or contact test.',
                         'UUID identity; missing UUIDs make identity verification incomplete.',
                         'Element/group/animation array reordering is ignored; hierarchy and keyframe order are compared.',
                         'Embedded pixels are RGBA-compared including hidden RGB; PNG encoding differences alone are ignored.',
                         'External textures require independent snapshots to prove historical preservation.',
                         'Editor state fields are included; review them instead of silently discarding changes.']}
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# BBModel 局部修改差异报告', '', f"状态：`{status}`；变更 {len(result)} 项；范围外 {violations} 项。", '',
             f'基线：`{paths[0]}`', f'结果：`{paths[1]}`', '', '未提供 scope 时只列差异，不自动判断哪些修改获得授权。', '']
    for issue in issues + warnings:
        lines += ['- 未验证：' + issue]
    for category, count in report['summary'].items():
        lines += ['', f'## {category}（{count}）', '']
        for change in (c for c in result if c['category'] == category):
            marker = ' [范围外]' if change.get('within_scope') is False else ''
            lines.append(f"- `{change['name']}` / `{change['id']}`：{change['operation']} `{change['path'] or '/'}`{marker}")
            if 'mask' in change:
                lines.append(f"  像素 {change['changed_pixels']}，矩形 {change['bounds_xyxy_exclusive']}，范围外像素 {change['outside_allowed_pixels']}。 ![变更像素]({change['mask']})")
            else:
                values = {k: change[k] for k in ('before', 'after') if k in change}
                text = json.dumps(values, ensure_ascii=False)
                lines.append('  ' + (text if len(text) <= 280 else text[:280] + '…（完整值见 report.json）'))
    lines += ['', '此报告不证明握持、穿插、风格或动画视觉合格；配合原生同条件预览。', '']
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('before', type=Path)
    parser.add_argument('after', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--scope', type=Path, help='JSON allow rules and optional texture_regions; absent = inventory only')
    args = parser.parse_args()
    try:
        report = compare(args.before, args.after, args.out, load(args.scope) if args.scope else None)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, f'Comparison failed: {error}\n')
    print(json.dumps({k: report[k] for k in ('status', 'change_count', 'out_of_scope_count', 'summary', 'issues')}, ensure_ascii=False))
    return 2 if report['status'] == 'incomplete' else 1 if report['out_of_scope_count'] else 0


if __name__ == '__main__':
    sys.exit(main())
