#!/usr/bin/env python3
"""Read-only Java item inventory. No renderer, aesthetic verdict or file mutation."""
import argparse
import base64
import collections
import hashlib
import io
import json
import math
import struct
from pathlib import Path


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def resolve_texture(value, textures):
    # BBModel face references: array index or texture UUID. Export #keys are not indices.
    if isinstance(value, int) and not isinstance(value, bool):
        return value if 0 <= value < len(textures) else None
    if isinstance(value, str):
        return next((i for i, t in enumerate(textures) if t.get('uuid') == value), None)
    return None


def audit(model, pixels=False, frame_sizes=None):
    Image = None
    if pixels:
        from PIL import Image
    frame_sizes = frame_sizes or {}
    errors, warnings, rows = [], [], []
    textures = model.get('textures', [])
    elements = model.get('elements', [])
    face_uses, element_uses = collections.Counter(), collections.Counter()
    unresolved = []
    ids = [e.get('uuid') for e in elements if e.get('uuid')]
    if len(ids) != len(set(ids)):
        errors.append('Duplicate element UUIDs')
    for e in elements:
        used = set()
        for face_name, face in e.get('faces', {}).items():
            ref = face.get('texture')
            if ref is None:
                continue
            idx = resolve_texture(ref, textures)
            if idx is None:
                unresolved.append({'element': e.get('name', e.get('uuid')), 'face': face_name, 'reference': ref})
                continue
            face_uses[idx] += 1
            used.add(idx)
        element_uses.update(used)
    if unresolved:
        warnings.append(f'{len(unresolved)} unresolved texture references; inspect reference scheme before changing them')

    for i, t in enumerate(textures):
        name = t.get('name', str(i))
        row = {'index': i, 'name': name, 'faces': face_uses[i], 'elements': element_uses[i],
               'metadata_size': [t.get('width'), t.get('height')],
               'uv_domain': [t.get('uv_width'), t.get('uv_height')],
               'frame_time': t.get('frame_time'), 'fps_hint': t.get('fps'),
               'order_type': t.get('frame_order_type', 'loop'),
               'interpolate': t.get('frame_interpolate')}
        raw = None
        source = t.get('source', '')
        if source.startswith('data:image/png;base64,'):
            try:
                raw = base64.b64decode(source.split(',', 1)[1], validate=True)
                if len(raw) < 24 or raw[:8] != b'\x89PNG\r\n\x1a\n' or raw[12:16] != b'IHDR':
                    raise ValueError('invalid PNG header')
                w, h = struct.unpack('>II', raw[16:24])
                if not w or not h:
                    raise ValueError('zero image dimension')
                row['png_size'] = [w, h]
                if row['metadata_size'] != [w, h]:
                    warnings.append(name + ': metadata/PNG dimension mismatch')
            except (ValueError, struct.error) as exc:
                errors.append(name + ': invalid embedded PNG: ' + str(exc))
                rows.append(row)
                continue
        else:
            row['pixel_check'] = 'External/unsupported source not loaded'
            warnings.append(name + ': embedded PNG unavailable; verify external asset')
            w, h = t.get('width'), t.get('height')
        if not positive(w) or not positive(h):
            warnings.append(name + ': missing/invalid image dimensions')
            rows.append(row)
            continue

        explicit = frame_sizes.get(i)
        if explicit:
            fw, fh = explicit
            basis = 'explicit frame dimensions; row-major layout'
        elif h >= w and h % w == 0:
            fw = fh = int(w)
            basis = 'square vertical-strip candidate; confirm layout'
        else:
            fw = fh = None
            basis = 'unknown layout; pass --frame-size INDEX:WxH'
        row['frame_basis'] = basis
        frames = None
        if fw and fh:
            if w % fw or h % fh:
                errors.append(name + ': frame dimensions do not divide PNG')
            else:
                frames = int((w // fw) * (h // fh))
                row['frame_size'] = [fw, fh]
                row['frame_count_candidate'] = frames

        order = None
        if row['order_type'] == 'custom':
            tokens = str(t.get('frame_order', '')).split()
            try:
                order = [int(x) for x in tokens]
            except ValueError:
                warnings.append(name + ': custom order not an integer list; inspect exporter syntax')
            if order is not None:
                row['order_length'] = len(order)
                row['referenced_frames'] = sorted(set(order))
                if not order:
                    warnings.append(name + ': empty custom frame order')
                if frames and any(x < 0 or x >= frames for x in order):
                    warnings.append(name + ': custom index outside candidate layout; confirm frame dimensions')
        elif row['order_type'] == 'loop' and frames:
            order = list(range(frames))
        if frames and frames > 1:
            ft = t.get('frame_time')
            if not positive(ft):
                warnings.append(name + ': invalid/missing frame_time; verify exported timing')
            elif order:
                row['cycle_ticks_if_uniform'] = len(order) * ft
            warnings_needed = bool(t.get('frame_interpolate'))
            if warnings_needed:
                warnings.append(name + ': interpolation enabled; inspect pixel edges')

        if Image and raw:
            try:
                with Image.open(io.BytesIO(raw)) as image:
                    image = image.convert('RGBA')
                    row['alpha_levels'] = [v for v, count in enumerate(image.getchannel('A').histogram()) if count]
                    if frames:
                        hashes, alpha_bounds = [], []
                        for y in range(0, int(h), fh):
                            for x in range(0, int(w), fw):
                                frame = image.crop((x, y, x + fw, y + fh))
                                # Transparent RGB noise is not a visible animation change.
                                frame = frame.copy()
                                transparent = frame.getchannel('A').point(lambda a: 255 if a == 0 else 0)
                                frame.paste((0, 0, 0, 0), mask=transparent)
                                hashes.append(hashlib.sha256(frame.tobytes()).hexdigest())
                                alpha_bounds.append(frame.getchannel('A').getextrema())
                        row['distinct_rgba_frames'] = len(set(hashes))
                        row['transparent_frame_indices'] = [j for j, (_, high) in enumerate(alpha_bounds) if high == 0]
                        if order and all(0 <= x < len(hashes) for x in order):
                            row['distinct_played_frames'] = len({hashes[x] for x in order})
                            if frames > 1 and row['distinct_played_frames'] == 1:
                                warnings.append(name + ': playback references only one distinct RGBA frame')
            except Exception as exc:
                errors.append(name + ': PNG decode failed: ' + str(exc))
        rows.append(row)

    groups = {g.get('uuid'): g for g in model.get('groups', []) if g.get('uuid')}
    def walk(nodes):
        for n in nodes:
            if isinstance(n, dict):
                if n.get('uuid'):
                    groups.setdefault(n['uuid'], n)
                walk(n.get('children', []))
    walk(model.get('outliner', []))
    return {'errors': errors, 'warnings': warnings,
            'stats': {'format': model.get('meta', {}).get('model_format'),
                      'elements': len(elements), 'groups': len(groups), 'textures': len(textures),
                      'bone_animation_clips': len(model.get('animations', [])),
                      'texture_strip_candidates': sum(r.get('frame_count_candidate', 0) > 1 for r in rows),
                      'textured_faces': sum(face_uses.values()),
                      'unused_texture_indices': [i for i in range(len(textures)) if not face_uses[i]],
                      'nonzero_light_emission_elements': sum(bool(e.get('light_emission', 0)) for e in elements),
                      'display_slots': sorted(model.get('display', {}))},
            'textures': rows, 'unresolved_references': unresolved,
            'limits': ['Frame candidates need layout confirmation; atlas dimensions are not pixel-style verdicts.',
                       'Does not inspect external mcmeta, target renderer, texel density, occlusion or performance.',
                       'RGBA frame changes do not prove visible motion on mapped faces or in-game playback.',
                       'Emission fields and alpha values do not prove runtime glow or transparency.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--pixels', action='store_true', help='Decode embedded PNGs using Pillow')
    parser.add_argument('--frame-size', action='append', default=[], metavar='INDEX:WxH', help='Override inferred layout; repeatable')
    args = parser.parse_args()
    sizes = {}
    try:
        for spec in args.frame_size:
            idx, size = spec.split(':')
            dims = tuple(int(x) for x in size.lower().split('x'))
            if len(dims) != 2 or min(dims) <= 0 or int(idx) < 0:
                raise ValueError('expected nonnegative index and positive WxH')
            sizes[int(idx)] = dims
        model = json.loads(args.model.read_text(encoding='utf-8'))
        if any(i >= len(model.get('textures', [])) for i in sizes):
            raise ValueError('frame-size index outside texture list')
        if args.report and args.report.resolve() == args.model.resolve():
            raise ValueError('report path must differ from input model')
        result = audit(model, args.pixels, sizes)
    except (ValueError, OSError, ImportError) as exc:
        parser.error(str(exc))
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        args.report.write_text(rendered, encoding='utf-8')
    else:
        print(rendered, end='')
    return bool(result['errors'])


if __name__ == '__main__':
    raise SystemExit(main())
