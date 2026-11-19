#!/usr/bin/env python3
"""Read-only Blockbench structural and animation editability audit (stdlib)."""
import argparse, collections, json, math
from pathlib import Path

def audit(d, fps=None, max_keys_warning=9):
    errors, warnings, tracks = [], [], []
    # Declarations, not outliner references, define object identity.
    for kind, objects in [('element', d.get('elements', [])), ('group', d.get('groups', []))]:
        ids = collections.Counter(o.get('uuid') for o in objects if o.get('uuid'))
        for uid, count in ids.items():
            if count > 1:
                errors.append(f'duplicate {kind} UUID {uid}: {count} declarations')
    groups = {g['uuid']: g for g in d.get('groups', [])}
    def walk(items):
        for g in items:
            if isinstance(g, dict):
                groups.setdefault(g.get('uuid'), g)
                walk(g.get('children', []))
    walk(d.get('outliner', []))
    for e in d.get('elements', []):
        if e.get('uuid') and e['uuid'] in groups:
            errors.append(f"{e.get('name', e['uuid'])}: element/group UUID collision {e['uuid']}")
    for a in d.get('animations', []):
        rate = fps or a.get('snapping', 20) or 20
        if not isinstance(rate, (float, int)) or not math.isfinite(rate) or rate <= 0:
            errors.append(str(a.get('name')) + ': invalid snapping rate')
            continue
        length = a.get('length')
        valid_length = isinstance(length, (float, int)) and math.isfinite(length) and length >= 0
        if not valid_length:
            warnings.append(str(a.get('name')) + ': missing or invalid explicit animation length; confirm runtime length')
        for uid, tr in a.get('animators', {}).items():
            if tr.get('type', 'bone') != 'bone':
                continue
            label = f"{a.get('name')}/{tr.get('name', uid)}"
            if uid not in groups:
                errors.append(label + ': animator bone UUID missing')
            seen, counts, grid_times = set(), collections.Counter(), {}
            for k in tr.get('keyframes', []):
                ch, t = k.get('channel'), k.get('time')
                if ch not in ('rotation', 'position', 'scale'):
                    errors.append(label + ': invalid bone channel ' + str(ch))
                if not isinstance(t, (float, int)) or not math.isfinite(t):
                    errors.append(label + ': invalid key time')
                    continue
                if abs(t * rate - round(t * rate)) > 1e-5:
                    warnings.append(f'{label}/{ch}: time {t} outside {rate} FPS grid')
                if t < 0:
                    errors.append(f'{label}/{ch}: negative time {t}')
                if valid_length and length > 0 and t > length + 1e-5:
                    warnings.append(f'{label}/{ch}: time {t} exceeds declared length {length}')
                grid_key = (ch, round(t * rate))
                if grid_key in grid_times and abs(grid_times[grid_key] - t) > 1e-7:
                    warnings.append(f'{label}/{ch}: snapping {grid_times[grid_key]} and {t} would merge distinct key times')
                grid_times[grid_key] = t
                if (ch, t) in seen:
                    errors.append(f'{label}/{ch}: duplicate time {t}')
                seen.add((ch, t)); counts[ch] += 1
                for point in k.get('data_points', []):
                    for axis in 'xyz':
                        value = point.get(axis)
                        try:
                            number = float(value)
                        except (TypeError, ValueError):
                            continue  # Expressions are valid; do not evaluate Molang.
                        if not math.isfinite(number):
                            errors.append(f'{label}/{ch}/{axis}: nonfinite value')
            for ch, count in counts.items():
                tracks.append({'track': label + '/' + str(ch), 'keys': count})
                if max_keys_warning > 0 and count > max_keys_warning:
                    warnings.append(f'{label}/{ch}: {count} keys; inspect before simplifying')
    pairs = [('west', 'east'), ('down', 'up'), ('north', 'south')]
    for e in d.get('elements', []):
        if 'from' not in e or 'to' not in e:
            continue
        faces = e.get('faces', {})
        for i, pair in enumerate(pairs):
            if abs(e['from'][i] - e['to'][i]) < 1e-7 and all(faces.get(f, {}).get('texture') is not None for f in pair):
                warnings.append(f"{e.get('name', e.get('uuid'))}: zero-thickness opposing faces {pair}; inspect overlap, do not auto-delete")
    return {'errors': errors, 'warnings': warnings, 'stats': {'bones': len(groups), 'animations': len(d.get('animations', [])), 'tracks': len(tracks), 'max_keys_per_track': max((t['keys'] for t in tracks), default=0)}, 'tracks': tracks}

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('model', type=Path); p.add_argument('--fps', type=float); p.add_argument('--report', type=Path)
    p.add_argument('--max-keys-warning', type=int, default=9,
                   help='Per-track review hint only; 0 disables it for long or baked clips')
    args = p.parse_args()
    if args.fps is not None and (args.fps <= 0 or not math.isfinite(args.fps)):
        p.error('--fps must be positive and finite')
    if args.max_keys_warning < 0:
        p.error('--max-keys-warning must be nonnegative')
    if args.report and args.report.resolve() == args.model.resolve():
        p.error('report path must differ from input model')
    result = audit(json.loads(args.model.read_text(encoding='utf-8-sig')), args.fps, args.max_keys_warning)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.write_text(text + '\n', encoding='utf-8')
    else:
        print(text)
    raise SystemExit(bool(result['errors']))
