#!/usr/bin/env python3
"""Read-only cube face alpha coverage audit. Requires Pillow; never repairs UVs."""
import argparse, base64, io, json, math
from pathlib import Path
from PIL import Image

AXES={'north':(0,1),'south':(0,1),'east':(2,1),'west':(2,1),'up':(0,2),'down':(0,2)}

def box_faces(e, float_size=True):
    size=[e['to'][i]-e['from'][i] for i in range(3)]
    if not float_size:size=[math.floor(v+1e-7) for v in size]
    w,h,d=size; u,v=e.get('uv_offset',[0,0])
    rects={'east':[0,d,d,d+h],'west':[d+w,d,2*d+w,d+h],
           'up':[d+w,d,d,0],'down':[d+2*w,0,d+w,d],
           'south':[2*d+w,d,2*d+2*w,d+h],'north':[d,d,d+w,d+h]}
    if e.get('mirror_uv'):
        rects={k:[r[2],r[1],r[0],r[3]] for k,r in rects.items()}
        rects['east'],rects['west']=rects['west'],rects['east']
    return {k:[r[0]+u,r[1]+v,r[2]+u,r[3]+v] for k,r in rects.items()}

def audit(model, base=Path('.')):
    textures=model.get('textures',[]); images={}; errors=[]; warnings=[]; rows=[]; skipped=[]
    for i,t in enumerate(textures):
        try:
            source=t.get('source','')
            if source.startswith('data:image/'):
                im=Image.open(io.BytesIO(base64.b64decode(source.split(',',1)[1]))).convert('RGBA')
            else:
                path=Path(t.get('path') or source)
                if not path.is_absolute():path=base/path
                im=Image.open(path).convert('RGBA')
            # Animation strips require explicit frame-aware review; do not fold frames into one UV domain.
            if t.get('frameCount',1)>1:
                skipped.append({'texture':i,'reason':'animated texture; frame-aware inspection required'});continue
            images[i]=im
        except (OSError,ValueError,KeyError) as ex:errors.append({'texture':i,'reason':str(ex)})
    lookup={str(i):i for i in range(len(textures))}
    for i,t in enumerate(textures):
        for k in ('uuid','id'):
            if t.get(k) is not None:lookup[str(t[k])]=i
    modded=model.get('meta',{}).get('model_format')=='modded_entity'
    for e in model.get('elements',[]):
        if e.get('type','cube')!='cube':skipped.append({'element':e.get('name'),'reason':'non-cube'});continue
        if not e.get('visibility',True) or not e.get('export',True):continue
        dims=[abs(e['to'][i]-e['from'][i]) for i in range(3)]
        # 5.2.2 Modded Entity uses mandatory, floating-size Box UV even if the source says false.
        forced=modded and not e.get('box_uv',model.get('meta',{}).get('box_uv',False))
        effective=box_faces(e) if modded else None
        if forced:warnings.append({'element':e.get('name'),'reason':'Modded Entity 5.2.2 forces Box UV; inspect native round trip'})
        for face,f in e.get('faces',{}).items():
            if face not in AXES or f.get('texture') is None:continue
            a,b=AXES[face]
            if dims[a]<1e-8 or dims[b]<1e-8:continue
            i=lookup.get(str(f['texture'])); uv=(effective or {}).get(face,f.get('uv'))
            label={'element':e.get('name',e.get('uuid')),'uuid':e.get('uuid'),'face':face,'texture':i,'uv':uv}
            if i not in images:errors.append({**label,'reason':'texture unavailable'});continue
            if not uv or len(uv)!=4:errors.append({**label,'reason':'missing cube face UV'});continue
            if effective and any(abs(x-y)>1e-4 for x,y in zip(uv,f.get('uv',uv))):
                warnings.append({**label,'reason':'stored face UV differs from effective Box UV'})
            im=images[i];t=textures[i];res=model.get('resolution',{})
            uw=t.get('uv_width') or res.get('width') or im.width
            uh=t.get('uv_height') or res.get('height') or im.height
            px=[uv[0]*im.width/uw,uv[1]*im.height/uh,uv[2]*im.width/uw,uv[3]*im.height/uh]
            lo=[min(px[0],px[2]),min(px[1],px[3])];hi=[max(px[0],px[2]),max(px[1],px[3])]
            if lo[0]<-1e-6 or lo[1]<-1e-6 or hi[0]>im.width+1e-6 or hi[1]>im.height+1e-6:
                errors.append({**label,'reason':'UV outside atlas'});continue
            if hi[0]-lo[0]<1e-8 or hi[1]-lo[1]<1e-8:
                warnings.append({**label,'reason':'degenerate UV on nonzero-area face'});continue
            bounds=(math.floor(lo[0]),math.floor(lo[1]),math.ceil(hi[0]),math.ceil(hi[1]))
            alpha=im.getchannel('A').crop(bounds);hist=alpha.histogram();total=sum(hist);colored=total-hist[0]
            coverage=colored/total if total else 0
            rows.append({**label,'colored_fraction':round(coverage,6)})
            if not colored:errors.append({**label,'reason':'entire sampled UV rectangle is transparent'})
    return {'errors':errors,'warnings':warnings,'skipped':skipped,'faces':rows,
            'summary':{'checked_faces':len(rows),'fully_transparent_faces':sum(x['reason'].startswith('entire sampled') for x in errors)},
            'limits':'Partial transparency may be a designed silhouette. Coverage does not prove correct material, occlusion, render sidedness or in-game appearance. Modded Entity Box UV profile verified on Blockbench 5.2.2; other formats use stored face UV and must also be opened natively.'}

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('model',type=Path);ap.add_argument('--report',type=Path);args=ap.parse_args()
    if args.report and args.report.resolve()==args.model.resolve():ap.error('report must not overwrite model')
    result=audit(json.loads(args.model.read_text(encoding='utf-8-sig')),args.model.parent)
    text=json.dumps(result,ensure_ascii=False,indent=2)
    if args.report:args.report.write_text(text+'\n',encoding='utf-8')
    else:print(text)
    raise SystemExit(bool(result['errors']))
