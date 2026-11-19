# Shared-edge modeling and reference reconstruction in Blockbench

[简体中文](README.md) · **English**

Four Codex skills for building editable models from reference images and refining existing Blockbench projects. The skill instructions and topic guides are in Chinese. You can invoke each skill by its directory name and describe your task in English.

> [!IMPORTANT]
> **Reference-based modeling depends heavily on the quality of the references. Provide at least four views: front, back, true left and true right.** A single turnaround sheet or four separate images will work. Show the full silhouette in the same pose and at the same scale throughout. Show each side separately so an asymmetric accessory or lock of hair stays on the correct side.
>
> To generate a turnaround, we recommend **Nano Banana 2** or **Nano Banana 2.1** in Gemini. Supply the same original design and ask for four equally scaled views aligned to a common baseline. Before modeling, check the position, count and orientation of accessories against the original and confirm any hidden details the generator has filled in. [Google DeepMind model card](https://deepmind.google/models/model-cards/nano-banana-2-1/)

## The core technique: build two cubes from one shared edge

Take a lock of hair that bends halfway down. Mark the two ends of the bend on its outer surface, `P0` and `P1`. The upper segment ends along that line and the lower segment starts along it. Give each cube its own length and outward-facing surface normal, and build its thickness inward. This lets you set the bend angle while keeping its position and the silhouette tied to the reference.

**To verify the seam**, read the eight corners of each saved cube and transform them into the same coordinate system, including the cube's rotation and its static parent-group transforms. Pick one complete edge on each cube and pair their endpoints in either order. Both endpoint distances must fall within the declared tolerance. Then inspect the joint in Blockbench from a true side view and close up. Look for a sliver of daylight on the outside or a bulge on the inside. If the pieces move relative to one another, inspect the joint during playback as well. [Construction math, corner indices and seam manifest](blockbench-shared-edge-modeling/references/shared-edge-construction.md)

## Pick a skill

| Task | Skill | What to expect |
| --- | --- | --- |
| Build or repair a curved strand, sleeve or trim using cubes, or reduce the cube count while preserving the shape | [blockbench-shared-edge-modeling](blockbench-shared-edge-modeling/SKILL.md) | Editable geometry, measured seam errors and close-ups, or before-and-after views for a reduction |
| Reconstruct a character or prop from a four-view reference sheet or image set | [reference-model-rebuild](reference-model-rebuild/SKILL.md) | A model, matched camera views, reference overlays and a record of inferred details |
| Make a Minecraft-style character, creature or item for a particular project | [mc-blockbench-creatures-public](mc-blockbench-creatures-public/SKILL.md) | A model in the target format, with the textures, rig, animation or exports requested |
| Get a stalled revision moving again | [task-progress](task-progress/SKILL.md) | A test that distinguishes plausible causes, a revised asset or finding, and the remaining work |

## Install and use

Paste this request into Codex to install all four skills:

```text
$skill-installer Install these skill directories from
https://github.com/1251639747jm-ctrl/blockbench-codex-skills
blockbench-shared-edge-modeling
mc-blockbench-creatures-public
reference-model-rebuild
task-progress
```

For a project-local installation, download and extract the repository and copy the skill directories you want into `.agents/skills/` at the root of your project. For example, the shared-edge instructions should end up at `.agents/skills/blockbench-shared-edge-modeling/SKILL.md`. Keep the folders intact and install the shared-edge and reconstruction skills side by side if you use both. Restart Codex if a newly installed skill does not appear. [Official Codex skill documentation](https://developers.openai.com/codex/skills)

## Example requests

**Repair one seam.** Supply an approved model and identify which joint can change. The skill records the cube IDs and checks the transformed edge before expanding the change to other segments. [Shared-edge construction](blockbench-shared-edge-modeling/references/shared-edge-construction.md) · [Texture and shape-preserving optimization](blockbench-shared-edge-modeling/references/texture-and-optimization.md)

> `$blockbench-shared-edge-modeling` Fix the bright gap between segments two and three of the right fringe in character.bbmodel. Keep the tip position, silhouette and texture. Save a new editable file and show the endpoint errors and close-ups from the front and right.

**Rebuild from images.** A nominal side view may still show part of the face. Fit the viewing angle before using the image to estimate depth. Record any surfaces that remain hidden in all four views as inferred. [Camera calibration and overlays](reference-model-rebuild/references/calibration-and-review.md)

> `$reference-model-rebuild` Rebuild this backpack from its front, back, left and right views. Match the body and flap first, then add the buckles and straps. Deliver an editable model and an overlay for each view, and identify inferred details beneath the straps.

**Build for the target game asset.** Specify how the asset will be used. A quadruped needs a convincing support phase, while a handheld item needs a suitable grip point and display transform. The project format determines what can be exported. [Humanoids](mc-blockbench-creatures-public/references/humanoids.md) · [Creatures](mc-blockbench-creatures-public/references/creatures.md) · [Items](mc-blockbench-creatures-public/references/items.md) · [Format selection](mc-blockbench-creatures-public/references/format-routing.md)

> `$mc-blockbench-creatures-public` Add an in-place walk cycle to this quadruped. Keep its project format and pixel texture. Check foot sliding and how the tail follows the body. Deliver editable keyframes and a preview of one full cycle.

**Diagnose a stalled revision.** After two checks with the same result, use the next attempt to test a different cause. A locked camera and one isolated joint can distinguish a shape error from an apparent shift caused by the view. [Task progress instructions](task-progress/SKILL.md)

> `$task-progress` Two thickness changes have left the same bulge at the cuff. Isolate the joint and test whether the bulge follows the cross-section or the parent rotation. Fix the cause you find and show the result from the original camera.

## Worked sequence for a cube-only character

1. **Record the starting point.** Identify the approved file, references, editable parts and budget. A budget of 300 cubes includes hidden cubes. Report groups separately for that budget.
2. **Match the cameras.** Use the reconstruction skill to align visible landmarks such as the crown, shoulders and cuffs. Save the camera settings before shaping the smaller parts.
3. **Build one representative joint.** Use the shared-edge skill on one strand or sleeve. Record the two cube IDs, measure the endpoints and inspect a side close-up. Extend the construction once that joint works.
4. **Reopen the saved model.** Inspect UVs, textures and visible inner walls. For an animated or game-ready asset, follow the relevant Minecraft asset guide and check pivots, motion and exports. Record which checks used the saved file, Blockbench playback or the game itself.

## Inspect a saved model from the command line

Run these examples from the repository root with Python 3. Replace the sample paths and the object budget with those of your project.

```bash
# Count objects and groups and check the cube-only constraint.
python reference-model-rebuild/scripts/audit_bbmodel.py "model.bbmodel" --limit 2000 --cube-only --json-out "object-count.json"

# Measure declared joints between static cubes.
python blockbench-shared-edge-modeling/scripts/audit_shared_edges.py "model.bbmodel" "seams.json" --report "seam-report.json"

# Inspect rig structure and animation data. Supply --fps 20 for a 20 FPS project.
python mc-blockbench-creatures-public/scripts/audit_bbmodel.py "creature.bbmodel" --report "animation-report.json"
```

Populate the seam manifest with real cube UUIDs from the saved model. The report covers the declared joints. Use the native views to assess thickness, visible gaps, texture continuity and moving parts. For a tightly scoped edit, compare the two saved projects to identify changes to geometry, hierarchy, UVs, texture pixels and animation. [Manifest example](blockbench-shared-edge-modeling/references/shared-edge-construction.md) · [Local edit comparison](mc-blockbench-creatures-public/references/local-edit-diff.md) · [Native review](mc-blockbench-creatures-public/references/native-review.md) · [Tool setup](mc-blockbench-creatures-public/references/tool-setup.md)

## License and commercial modeling

You may use these skills for paid commissions and deliver or sell your independently created models. Documentation uses CC BY-NC-SA 4.0 with additional permission for commercial modeling. Scripts and supporting files have separate terms. Charging for access to the original or modified skill materials, including in a paid bundle, requires separate permission. [License, scope and examples](LICENSE.md)
