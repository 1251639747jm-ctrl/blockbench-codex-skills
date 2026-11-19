// Executed inside a dedicated Blockbench renderer by bb_review.mjs.
async function createReview(config) {
    if (ModelProject.all.length) throw new Error('Use an empty, dedicated Blockbench instance; existing projects will not be closed.');
    if (config.plugin) {
        const plugin = new Plugin(config.plugin.split(/[\\/]/).pop().replace(/\.js$/, ''));
        await plugin.loadFromFile({name: plugin.id + '.js', path: config.plugin}, false);
    }
    const file = await new Promise(resolve => Blockbench.read([config.model], {}, files => resolve(files[0])));
    const source = JSON.parse(file.content);
    if (!source.meta?.model_format) throw new Error('Expected a standard .bbmodel project; dedicated formats such as Animated Java Blueprint require their own codec.');
    if (!Formats[source.meta.model_format]) throw new Error('Missing format plugin: ' + source.meta.model_format);
    Codecs.project.load(source, file);
    const project = Project;
    let preview;
    const background = Canvas.scene.background;
    const visibility = new Map();
    const cleanup = async () => {
        for (const [node, visible] of visibility) node.visible = visible;
        Canvas.scene.background = background;
        if (preview) preview.delete();
        Timeline.pause();
        // Only this tool-created tab is closed; no source file is saved.
        project.saved = true;
        await project.close();
    };
    try {
        await Promise.all(Texture.all.map(t => t.img.decode()));
        const failed = Texture.all.filter(t => t.error);
        if (failed.length) throw new Error('Texture errors: ' + failed.map(t => t.name).join(', '));
        Timeline.pause();
        if (Animation.all.length) Modes.options.animate.select();
        for (const a of Animation.all) a.playing = false;
        const animation = config.animation ? Animation.all.find(a => a.name === config.animation) : null;
        if (config.animation && !animation) throw new Error('Unknown animation: ' + config.animation);
        if (animation && (!(animation.length > 0) || animation.length > 1000)) throw new Error('Animation length must be in (0, 1000] seconds.');
        const times = animation ? (config.times || Array.from({length: Math.ceil(animation.length * config.fps)}, (_, i) => i / config.fps)) : [];
        if (animation && !times.includes(animation.length)) times.push(animation.length);
        times.sort((a, b) => a - b);
        if (times.some(t => !Number.isFinite(t) || t < 0 || t > animation.length)) throw new Error('Sample time outside animation.');
        if (times.length > 1000) throw new Error('Over 1000 samples; reduce fps or use --times.');
        const elements = [...Cube.all, ...Mesh.all];
        if (!elements.length) throw new Error('No cube or mesh geometry to render.');
        const tracked = config.track.map(name => {
            const matches = [...Group.all, ...elements].filter(n => n.name === name || n.uuid === name);
            if (matches.length !== 1) throw new Error('Track name must resolve uniquely (use UUID if ambiguous): ' + name);
            return matches[0];
        });
        const keep = new Set([Canvas.scene]);
        for (const e of elements) {
            e.mesh.traverse(n => { if (n.isMesh) keep.add(n); });
            for (let n = e.mesh; n; n = n.parent) keep.add(n);
        }
        Canvas.scene.traverse(n => {
            if (n.isLight) for (let p = n; p; p = p.parent) keep.add(p);
        });
        Canvas.scene.traverse(n => visibility.set(n, n.visible));
        function pose(time) {
            for (const a of Animation.all) a.playing = false;
            Animator.showDefaultPose();
            if (time !== null) {
                animation.select();
                animation.playing = true;
                Timeline.setTime(time);
                Animator.preview();
            }
            Canvas.scene.updateMatrixWorld(true);
        }
        function bounds() {
            const box = new THREE.Box3();
            for (const e of elements) {
                let visible = true;
                for (let n = e.mesh; n; n = n.parent) visible &&= n.visible;
                if (visible) {
                    e.mesh.geometry.computeBoundingBox();
                    box.union(e.mesh.geometry.boundingBox.clone().applyMatrix4(e.mesh.matrixWorld));
                }
            }
            if (box.isEmpty()) throw new Error('No visible geometry at this sample.');
            return box;
        }
        function snapshot(time) {
            pose(time);
            const box = bounds();
            return {time, bounds: {min: box.min.toArray(), max: box.max.toArray()}, tracks: tracked.map(n => ({
                name: n.name, uuid: n.uuid,
                position: n.mesh.getWorldPosition(new THREE.Vector3()).toArray(),
                quaternion: n.mesh.getWorldQuaternion(new THREE.Quaternion()).toArray(),
                scale: n.mesh.getWorldScale(new THREE.Vector3()).toArray()
            }))};
        }
        const rest = snapshot(null);
        const samples = times.map(snapshot);
        const union = new THREE.Box3().set(new THREE.Vector3(...rest.bounds.min), new THREE.Vector3(...rest.bounds.max));
        for (const s of samples) union.union(new THREE.Box3(new THREE.Vector3(...s.bounds.min), new THREE.Vector3(...s.bounds.max)));
        const center = union.getCenter(new THREE.Vector3()), diagonal = union.getSize(new THREE.Vector3()).length();
        const directions = {front:[0,0,-1],right:[1,0,0],back:[0,0,1],top:[0,1,0],three_quarter:[1,0.55,-1]};
        preview = new Preview({id:'skill_review_' + Date.now(),offscreen:true});
        preview.isOrtho = true;
        preview.renderer.setPixelRatio(1);
        preview.resize(config.width, config.height);
        const cam = preview.camOrtho;
        function applyCamera(c) {
            cam.position.fromArray(c.position); cam.up.fromArray(c.up); cam.lookAt(...c.target);
            cam.left = -c.span * config.width / config.height / 2;
            cam.right = -cam.left; cam.top = c.span / 2; cam.bottom = -cam.top;
            cam.near = 0.01; cam.far = c.far; cam.zoom = 1;
            cam.updateProjectionMatrix(); cam.updateMatrixWorld(true);
        }
        const cameras = {};
        for (const name of new Set([...config.views, ...config.motionViews])) {
            if (!directions[name]) throw new Error('Unknown view: ' + name);
            if (config.cameras) {
                if (!config.cameras[name]) throw new Error('Baseline lacks camera: ' + name);
                cameras[name] = config.cameras[name];
            } else {
                const c = {position:center.clone().add(new THREE.Vector3(...directions[name]).normalize().multiplyScalar(diagonal * 3 + 1)).toArray(),target:center.toArray(),up:name === 'top' ? [0,0,1] : [0,1,0],span:diagonal,far:diagonal * 10 + 10};
                applyCamera(c);
                const cameraBox = union.clone().applyMatrix4(cam.matrixWorldInverse);
                const size = cameraBox.getSize(new THREE.Vector3());
                c.span = Math.max(size.y, size.x * config.height / config.width, 0.1) * 1.15;
                cameras[name] = c;
            }
        }
        const lighting = {
            shading: Settings.get('shading'), brightness: Settings.get('brightness'),
            lights: []
        };
        Canvas.scene.traverse(n => {if (n.isLight) lighting.lights.push({type:n.type,color:n.color.getHexString(),intensity:n.intensity,position:n.getWorldPosition(new THREE.Vector3()).toArray()});});
        const metadata = {blockbench:Blockbench.version,format:Format.id,model:config.model,
            animation:animation ? {name:animation.name,length:animation.length,loop:animation.loop} : null,
            textures:Texture.all.map(t=>({name:t.name,path:t.path,width:t.width,height:t.height,mode:t.mode,error:t.error})),
            width:config.width,height:config.height,background:config.background,lighting,cameras,rest,samples};
        return {metadata, async frame(view, time) {
            pose(time);
            Canvas.scene.traverse(n => {if (!keep.has(n)) n.visible = false;});
            Canvas.scene.background = new THREE.Color(config.background);
            applyCamera(cameras[view]);
            const projected = bounds().applyMatrix4(cam.matrixWorldInverse);
            const clipped = projected.min.x < cam.left || projected.max.x > cam.right || projected.min.y < cam.bottom || projected.max.y > cam.top || -projected.min.z > cam.far || -projected.max.z < cam.near;
            preview.renderer.render(Canvas.scene,cam);
            return {data:preview.canvas.toDataURL('image/png'),clipped};
        }, cleanup};
    } catch (error) {
        await cleanup();
        throw error;
    }
}
