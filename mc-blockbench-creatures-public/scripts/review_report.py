"""Build contact sheets, a timed GIF, and a local HTML player from native captures.

Usage: python review_report.py REVIEW_DIR [--baseline PREVIOUS_REVIEW_DIR]
Requires Pillow; does not edit model files or generate new animation keys.
"""
import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def contact_sheet(entries, destination, columns=4, cell=256):
    if not entries:
        return
    rows = math.ceil(len(entries) / columns)
    sheet = Image.new("RGB", (columns * cell, rows * (cell + 30)), "#edf0f3")
    draw = ImageDraw.Draw(sheet)
    for i, (filename, label) in enumerate(entries):
        with Image.open(filename) as im:
            thumb = im.convert("RGB")
            thumb.thumbnail((cell, cell), Image.Resampling.LANCZOS)
        x, y = i % columns * cell, i // columns * (cell + 30)
        sheet.paste(thumb, (x + (cell - thumb.width) // 2, y + (cell - thumb.height) // 2))
        draw.text((x + 8, y + cell + 5), label, fill="#172637", font=ImageFont.load_default(size=14))
    sheet.save(destination)


def selected(frames, count=12):
    if len(frames) <= count:
        return frames
    return [frames[round(i * (len(frames) - 1) / (count - 1))] for i in range(count)]


def report(root, baseline=None):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if not manifest.get("captureComplete"):
        raise ValueError("Capture is incomplete or source changed; recapture before reporting.")
    rest = [f for f in manifest["frames"] if f["time"] is None]
    motion = [f for f in manifest["frames"] if f["time"] is not None]
    contact_sheet([(root / f["file"], f["view"]) for f in rest], root / "views.png", columns=3)
    views = list(dict.fromkeys(f["view"] for f in motion))
    for view in views:
        frames = [f for f in motion if f["view"] == view]
        contact_sheet([(root / f["file"], f'{view}  t={f["time"]:.4f}s') for f in selected(frames)], root / f"motion_{view}_sheet.png")
        # GIF time differences follow the sample times. Loop endpoints are kept in
        # the sheet/report but omitted from looping playback to avoid an extra hold.
        looping = manifest["animation"]["loop"] == "loop"
        play = frames[:-1] if looping and len(frames) > 1 else frames
        images, durations = [], []
        for i, frame in enumerate(play):
            with Image.open(root / frame["file"]) as im:
                images.append(im.convert("RGB"))
            dt = frames[i + 1]["time"] - frame["time"] if i + 1 < len(frames) else 0.1
            # GIF uses 10 ms units. Round cumulative timestamps rather than
            # truncating every 1/12 s interval to 80 ms and speeding up playback.
            durations.append(max(10, round((frame["time"] + dt) * 100) * 10 - round(frame["time"] * 100) * 10))
        if images:
            images[0].save(root / f"motion_{view}.gif", save_all=True, append_images=images[1:], duration=durations, disposal=2, **({"loop": 0} if looping else {}))
    diagnostics = {"warnings": manifest["warnings"], "units": "Blockbench world units; tracked positions are node origins, not sole/contact points", "tracks": []}
    samples = manifest["samples"]
    if samples:
        for i, first in enumerate(samples[0]["tracks"]):
            positions = [s["tracks"][i]["position"] for s in samples]
            last = samples[-1]["tracks"][i]
            dot = abs(sum(a * b for a, b in zip(first["quaternion"], last["quaternion"])))
            diagnostics["tracks"].append({"name": first["name"],
                "positionRange": [max(p[k] for p in positions) - min(p[k] for p in positions) for k in range(3)],
                "firstLastPositionDistance": math.dist(first["position"], last["position"]),
                "firstLastRotationDegrees": math.degrees(2 * math.acos(min(1, dot))),
                "firstLastScaleDelta": [b-a for a,b in zip(first["scale"],last["scale"])]})
        diagnostics["endpointTimes"] = [samples[0]["time"], samples[-1]["time"]]
    if baseline:
        old = json.loads((baseline / "manifest.json").read_text(encoding="utf-8"))
        comparable = old.get("captureComplete") and all(old[k] == manifest[k] for k in ("cameras", "lighting", "width", "height", "background", "blockbench", "format"))
        if not comparable:
            raise ValueError("Baseline camera, lighting, renderer or format differs. Recapture using --camera-from and matching settings.")
        if motion and (old.get("animation") or {}).get("name") != manifest["animation"]["name"]:
            raise ValueError("Cannot pair different animations by time; choose matching clips or compare event stages manually.")
        old_frames = {(f["view"], f["time"]): f for f in old["frames"]}
        pairs = []
        for frame in rest + selected(motion, 6):
            previous = old_frames.get((frame["view"], frame["time"]))
            if previous:
                label = frame["view"] + (f' {frame["time"]:.4f}s' if frame["time"] is not None else " rest")
                pairs.extend([(baseline / previous["file"], "Before: " + label), (root / frame["file"], "After: " + label)])
        contact_sheet(pairs, root / "comparison.png", columns=2, cell=360)
        diagnostics["comparison"] = {"baseline": str(baseline.resolve()), "sourceSha256": old["sourceSha256"], "matchedPairs": len(pairs) // 2}
    (root / "diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8")
    data = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    page = '''<!doctype html><meta charset="utf-8"><title>Blockbench 模型验收</title>
<style>body{font:16px system-ui;margin:24px;background:#edf0f3;color:#172637}img{max-width:100%}.row{display:flex;gap:24px;flex-wrap:wrap}.panel{background:white;padding:16px;border-radius:12px;max-width:700px}button,select,input{font:inherit;margin:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere}#frame{width:640px}</style>
<h1>Blockbench 原生模型预览</h1><p id="source"></p><p>这是保存文件的编辑器采样，不代表游戏实测。静态检查和轨迹数值不能代替视觉判断。</p>
<div class="row"><div class="panel"><h2>固定视角</h2><img src="views.png"></div>
<div class="panel" id="player"><h2>动画采样</h2><select id="view"></select><button id="play">播放 / 暂停</button><input id="slider" type="range" min="0" value="0"><p id="time"></p><img id="frame"></div></div>
<h2>记录</h2><p><a href="manifest.json">采样与源文件记录</a> · <a href="diagnostics.json">轨迹与首尾差异</a></p><pre id="warnings"></pre>
<script>const m=__DATA__;
document.querySelector('#source').textContent=m.model+' | '+m.blockbench+' | SHA256 '+m.sourceSha256;
document.querySelector('#warnings').textContent=m.warnings.join('\\n')||'采样过程无警告；视觉质量仍需审阅。';
const all=m.frames.filter(f=>f.time!==null),views=[...new Set(all.map(f=>f.view))];
const select=document.querySelector('#view'),slider=document.querySelector('#slider');
let frames=[],playing=false,start=0;
for(const v of views){const o=document.createElement('option');o.textContent=v;select.append(o);}
function draw(){const f=frames[+slider.value];if(!f)return;document.querySelector('#frame').src=f.file;document.querySelector('#time').textContent=m.animation.name+' | '+f.time.toFixed(4)+' s';}
function choose(){playing=false;frames=all.filter(f=>f.view===select.value);slider.max=frames.length-1;slider.value=0;draw();}
select.onchange=choose;slider.oninput=()=>{playing=false;draw();};
document.querySelector('#play').onclick=()=>{if(!frames.length)return;playing=!playing;start=performance.now()-frames[+slider.value].time*1000;};
function tick(now){if(playing){let t=(now-start)/1000;const end=m.animation.length;if(t>=end){if(m.animation.loop==='loop'){t%=end;start=now-t*1000;}else{t=end;playing=false;}}let i=frames.findLastIndex(f=>f.time<=t);slider.value=Math.max(0,i);draw();}requestAnimationFrame(tick);}
if(frames.length||views.length){choose();requestAnimationFrame(tick);}else document.querySelector('#player').hidden=true;
</script>'''.replace("__DATA__", data)
    if baseline:
        page += '<h2>修改前后（左：之前；右：之后）</h2><img src="comparison.png">'
    (root / "index.html").write_text(page, encoding="utf-8")
    print(json.dumps({"viewer": str((root / "index.html").resolve()), "views": len(rest), "motionViews": views, "tracks": diagnostics["tracks"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    report(args.review, args.baseline)
