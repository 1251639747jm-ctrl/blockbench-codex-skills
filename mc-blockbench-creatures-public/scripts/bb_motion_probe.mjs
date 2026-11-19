#!/usr/bin/env node
// Node 22+, read-only native Blockbench FK sampling on an empty dedicated instance.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const args = process.argv.slice(2), options = {};
if (!args.length || args.includes('--help')) {
    console.log('node bb_motion_probe.mjs --port 9250 --model file.bbmodel --animation attack --out probe.json [--fps 40] [--times 0,0.25,1] [--spec landmarks.json] [--plugin geckolib.js]\nSpec: {points:[{name,node,local:[x,y,z]}],elements:[nameOrUUID],perturb:{node,rotation_degrees:[x,y,z]}}. Local points use native mesh coordinates relative to the bone pivot. All bones are sampled. perturb is temporary, post-animation, and never saved.');
    process.exit(0);
}
const accepted = new Set(['port','model','animation','out','fps','times','spec','plugin']);
for (let i=0;i<args.length;i+=2) {
    const key=args[i].replace(/^--/,'');
    if (!accepted.has(key) || !args[i+1]) throw new Error('Invalid option '+args[i]);
    options[key]=args[i+1];
}
if (!options.port || !options.model || !options.out) throw new Error('--port, --model and --out required');
const output=path.resolve(options.out), model=path.resolve(options.model);
if (fs.existsSync(output)) throw new Error('Output exists; choose a new evidence filename');
const sha=filename=>crypto.createHash('sha256').update(fs.readFileSync(filename)).digest('hex');
const original=sha(model);
const spec=options.spec ? JSON.parse(fs.readFileSync(options.spec,'utf8')) : {};
const config={model,animation:options.animation || null,fps:Number(options.fps || 40),times:options.times?options.times.split(',').map(Number):null,
    plugin:options.plugin?path.resolve(options.plugin):null,spec};
if (!(config.fps>0 && config.fps<=120)) throw new Error('fps must be in (0,120]');
if(config.times && config.times.some(t=>!Number.isFinite(t)||t<0))throw new Error('times must contain finite nonnegative numbers');
const tabs=await(await fetch(`http://127.0.0.1:${options.port}/json`,{signal:AbortSignal.timeout(5000)})).json();
const pages=tabs.filter(t=>t.type==='page' && /blockbench|app\.asar/i.test(t.url));
if(pages.length!==1)throw new Error('Expected one dedicated Blockbench page');
const ws=new WebSocket(pages[0].webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
async function nativeProbe(c) {
    if (ModelProject.all.length) throw new Error('Dedicated instance must be empty');
    if(c.plugin) {
        const plugin=new Plugin(c.plugin.split(/[\\/]/).pop().replace(/\.js$/,''));
        await plugin.loadFromFile({name:plugin.id+'.js',path:c.plugin},false);
    }
    const file=await new Promise(resolve=>Blockbench.read([c.model],{},files=>resolve(files[0])));
    const data=JSON.parse(file.content);
    if(!Formats[data.meta?.model_format]) throw new Error('Missing model format plugin');
    let project;
    try {
        Codecs.project.load(data,file);
        project=Project;
        const animation=c.animation?Animation.all.find(a=>a.name===c.animation):null;
        if(c.animation&&!animation)throw new Error('Unknown animation '+c.animation);
        Timeline.pause();
        if(animation)Modes.options.animate.select();
        const all=[...Group.all,...Cube.all,...Mesh.all];
        function find(name){const nodes=all.filter(n=>n.uuid===name||n.name===name);if(nodes.length!==1)throw new Error('Ambiguous/missing node '+name);return nodes[0];}
        const elements=(c.spec.elements||[]).map(find);
        const tracked=[...Group.all,...elements.filter(n=>!Group.all.includes(n))];
        const points=(c.spec.points||[]).map(p=>{
            if(!p.name||!Array.isArray(p.local)||p.local.length!==3||!p.local.every(Number.isFinite))throw new Error('Invalid point specification');
            return {...p,object:find(p.node)};
        });
        if(new Set(points.map(p=>p.name)).size!==points.length)throw new Error('Point names must be unique');
        const perturb=c.spec.perturb?find(c.spec.perturb.node):null;
        if(perturb && (!Array.isArray(c.spec.perturb.rotation_degrees)||c.spec.perturb.rotation_degrees.length!==3||!c.spec.perturb.rotation_degrees.every(Number.isFinite)))throw new Error('Invalid perturb rotation');
        const times=animation?(c.times||Array.from({length:Math.ceil(animation.length*c.fps)},(_,i)=>i/c.fps)):[null];
        if(animation&&!times.includes(animation.length))times.push(animation.length);
        if(times.length>3000||times.some(t=>animation?(!Number.isFinite(t)||t<0||t>animation.length):t!==null))throw new Error('Invalid sample times');
        times.sort((a,b)=>a-b);
        function pose(t,applyPerturb=true){
            for(const a of Animation.all)a.playing=false;
            Animator.showDefaultPose();
            if(t!==null){animation.select();animation.playing=true;Timeline.setTime(t);Animator.preview();}
            if(perturb&&applyPerturb){const delta=c.spec.perturb.rotation_degrees;perturb.mesh.rotation.x+=delta[0]*Math.PI/180;perturb.mesh.rotation.y+=delta[1]*Math.PI/180;perturb.mesh.rotation.z+=delta[2]*Math.PI/180;}
            Canvas.scene.updateMatrixWorld(true);
        }
        function sample(t,applyPerturb=true){
            pose(t,applyPerturb);
            return {time:t,nodes:Object.fromEntries(tracked.map(n=>[n.uuid,{matrix:n.mesh.matrixWorld.toArray(),localPosition:n.mesh.position.toArray(),localQuaternion:n.mesh.quaternion.toArray(),localScale:n.mesh.scale.toArray()}])),
                points:Object.fromEntries(points.map(p=>[p.name,new THREE.Vector3(...p.local).applyMatrix4(p.object.mesh.matrixWorld).toArray()]))};
        }
        const rest=sample(null,false);
        return {blockbench:Blockbench.version,format:Format.id,animation:animation?{name:animation.name,length:animation.length,loop:animation.loop}:null,
            nodes:tracked.map(n=>({uuid:n.uuid,name:n.name,type:Group.all.includes(n)?'group':n.type,origin:n.origin,parent:n.parent?.uuid||null,
                ...(n.from?{from:n.from,to:n.to}:{}),rotation:n.rotation})),pointDefinitions:c.spec.points||[],perturb:c.spec.perturb||null,rest,samples:times.map(t=>sample(t))};
    } finally {
        // A failed synchronous load can still have created its project tab.
        const loaded=project || ModelProject.all[0];
        if(loaded){Timeline.pause();loaded.saved=true;await loaded.close();}
    }
}
try {
    const reply=await new Promise((resolve,reject)=>{
        const timeout=setTimeout(()=>reject(new Error('Native sampling timed out')),60000);
        ws.onmessage=e=>{clearTimeout(timeout);resolve(JSON.parse(e.data));};
        ws.onerror=e=>{clearTimeout(timeout);reject(e);};
        ws.send(JSON.stringify({id:1,method:'Runtime.evaluate',params:{expression:`(${nativeProbe.toString()})(${JSON.stringify(config)})`,awaitPromise:true,returnByValue:true}}));
    });
    if(reply.error||reply.result?.exceptionDetails)throw new Error(JSON.stringify(reply.error||reply.result.exceptionDetails));
    const report=reply.result.result.value;
    Object.assign(report,{schema:1,model,sourceSha256:original,sourceUnchanged:sha(model)===original,spec});
    if(!report.sourceUnchanged)throw new Error('Source changed while sampling');
    fs.mkdirSync(path.dirname(output),{recursive:true});
    fs.writeFileSync(output,JSON.stringify(report,null,2));
    console.log(JSON.stringify({output,nodes:report.nodes.length,samples:report.samples.length,sourceUnchanged:true}));
} finally {ws.close();}
