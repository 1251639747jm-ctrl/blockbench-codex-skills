#!/usr/bin/env node
// Node >= 22. No npm dependencies. Connect only to a local Blockbench CDP port.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';

const help = `Usage:
  node bb_review.mjs inspect --port 9237
  node bb_review.mjs capture --port 9237 --model model.bbmodel --out review [options]
Options: --plugin installed/geckolib.js --animation idle --fps 12
  --times 0,0.15,0.5,1 --track head,tail_tip
  --views front,right,back,top,three_quarter --motion-views three_quarter
  --width 640 --height 640 --background '#b6c3cd'
  --camera-from previous/manifest.json
Capture requires an empty dedicated Blockbench instance. Never saves the model.
--fps controls review sampling, never animation keyframes. Explicit --times adds the end sample.
After capture: python review_report.py review
`;
const args = process.argv.slice(2), command = args.shift();
if (!command || command === '--help') { console.log(help); process.exit(0); }
const allowed = new Set(['port','model','out','plugin','animation','fps','times','track','views','motion-views','width','height','background','camera-from']);
const options = {};
for (let i=0;i<args.length;i+=2) {
    const key=args[i].replace(/^--/,'');
    if (!allowed.has(key) || !args[i+1] || args[i+1].startsWith('--')) throw new Error('Invalid option: ' + args[i]);
    options[key]=args[i+1];
}
if (!['inspect','capture'].includes(command)) throw new Error('Unknown command: '+command);
if (!/^\d+$/.test(options.port || '') || +options.port < 1 || +options.port > 65535) throw new Error('--port is required (1..65535).');
const sha = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const list = (value, fallback) => (value ?? fallback).split(',').filter(Boolean);
let config, baseline, output, originalHash;
if (command === 'capture') {
    if (!options.model || !options.out) throw new Error('--model and --out are required.');
    output=path.resolve(options.out);
    if (fs.existsSync(output) && fs.readdirSync(output).length) throw new Error('Output directory must be empty; choose a new review version.');
    config={model:path.resolve(options.model),plugin:options.plugin ? path.resolve(options.plugin) : null,
        animation:options.animation,fps:Number(options.fps ?? 12),times:options.times ? options.times.split(',').map(Number) : null,
        track:list(options.track,''),views:list(options.views,'front,right,back,top,three_quarter'),
        motionViews:list(options['motion-views'],'three_quarter'),width:Number(options.width ?? 640),height:Number(options.height ?? 640),background:options.background ?? '#b6c3cd'};
    if (!(config.fps>0 && config.fps<=120)) throw new Error('fps must be in (0,120].');
    if (![config.width,config.height].every(v=>Number.isInteger(v)&&v>=64&&v<=2048)) throw new Error('Image dimensions must be integers in 64..2048.');
    originalHash=sha(config.model);
    if (options['camera-from']) {
        baseline=JSON.parse(fs.readFileSync(options['camera-from'],'utf8'));
        config.cameras=baseline.cameras;
        config.width=baseline.width; config.height=baseline.height; config.background=baseline.background;
    }
}
const tabs=await (await fetch(`http://127.0.0.1:${options.port}/json`,{signal:AbortSignal.timeout(5000)})).json();
const pages=tabs.filter(t=>t.type==='page' && /blockbench|app\.asar/i.test(t.url));
if (pages.length!==1) throw new Error('Expected exactly one Blockbench page; inspect the selected local port.');
const ws=new WebSocket(pages[0].webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
let seq=0;
const pending=new Map();
ws.onmessage=e=>{const m=JSON.parse(e.data);const p=pending.get(m.id);if(p){clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(new Error(JSON.stringify(m.error))):p.resolve(m.result);}};
ws.onclose=()=>{for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('Blockbench connection closed'));}pending.clear();};
async function evaluate(expression) {
    const id=++seq;
    const result=await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>{pending.delete(id);reject(new Error('Blockbench evaluation timed out'));},60000);
        pending.set(id,{resolve,reject,timer});
        ws.send(JSON.stringify({id,method:'Runtime.evaluate',params:{expression,awaitPromise:true,returnByValue:true}}));
    });
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
}
let started=false;
try {
    if(command==='inspect') {
        console.log(JSON.stringify(await evaluate(`({version:Blockbench.version,projects:ModelProject.all.map(p=>({name:p.name,saved:p.saved,path:p.save_path})),formats:Object.keys(Formats),animations:Animation.all.map(a=>({name:a.name,length:a.length,loop:a.loop}))})`),null,2));
    } else {
        const native=fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)),'bb_review_native.js'),'utf8');
        const manifest=await evaluate(`(async()=>{${native}\nwindow.__bbSkillReview=await createReview(${JSON.stringify(config)});return window.__bbSkillReview.metadata;})()`);
        started=true;
        Object.assign(manifest,{schema:1,createdAt:new Date().toISOString(),sourceSha256:originalHash,sampling:{fps:config.times?null:config.fps,explicitTimes:config.times},frames:[],warnings:[]});
        if (baseline && JSON.stringify(baseline.lighting)!==JSON.stringify(manifest.lighting)) manifest.warnings.push('Lighting differs from baseline; camera matching alone does not make a fair material comparison.');
        manifest.externalTextures=manifest.textures.filter(t=>t.mode==='link' && t.path && fs.existsSync(t.path)).map(t=>({path:t.path,sha256:sha(t.path)}));
        fs.mkdirSync(output,{recursive:true});
        const jobs=config.views.map(view=>({view,time:null,file:`rest_${view}.png`}));
        for (const view of config.motionViews) for (let i=0;i<manifest.samples.length;i++) jobs.push({view,time:manifest.samples[i].time,file:`motion_${view}_${String(i).padStart(4,'0')}.png`});
        for (const [i,job] of jobs.entries()) {
            const frame=await evaluate(`window.__bbSkillReview.frame(${JSON.stringify(job.view)},${JSON.stringify(job.time)})`);
            fs.writeFileSync(path.join(output,job.file),Buffer.from(frame.data.split(',')[1],'base64'));
            manifest.frames.push({...job,clipped:frame.clipped});
            if(frame.clipped) manifest.warnings.push('Potential clipping: '+job.file);
            if(i%20===0) console.error(`Rendered ${i+1}/${jobs.length}`);
        }
        manifest.sourceUnchanged=sha(config.model)===originalHash;
        manifest.externalTexturesUnchanged=manifest.externalTextures.every(t=>sha(t.path)===t.sha256);
        manifest.captureComplete=manifest.sourceUnchanged && manifest.externalTexturesUnchanged;
        fs.writeFileSync(path.join(output,'manifest.json'),JSON.stringify(manifest,null,2));
        if(!manifest.captureComplete) throw new Error('Source changed during capture; discard this review and capture a stable version.');
        console.log(JSON.stringify({output,frames:jobs.length,samples:manifest.samples.length,sourceUnchanged:true,warnings:manifest.warnings},null,2));
    }
} finally {
    try { if(started) await evaluate('(async()=>{await window.__bbSkillReview.cleanup();delete window.__bbSkillReview;return true;})()'); }
    finally { ws.close(); }
}
