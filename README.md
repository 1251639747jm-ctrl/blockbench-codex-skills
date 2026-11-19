# Blockbench 共边建模与参考还原 · Codex Skills

**简体中文** · [English](README.en.md)

这个仓库收录了四个中文 Codex 技能。你可以从一张参考图开始做可编辑模型，也可以带着已有的 `.bbmodel`，只修一束头发、一处接缝或一个动作。每个技能都有独立的 `SKILL.md` 入口，三个建模技能还附有专题说明和检查脚本。

## 核心方法：用一条真实边连接两个 Cube

以弯曲的发束为例。先在参考上找出发束转折处的横边，记下左右端点 `P0`、`P1`。上一段在这条边结束，下一段从同一条边转向。两块可以有各自的长度、外表面朝向和厚度，厚度从外表面向内建立。这样转折的位置和发束的外轮廓都能由参考决定。

**怎样确认真的共边？** 保存工程，读取两个 Cube 各自的八个角点，应用自身旋转和静态父组变换，换算到同一坐标系。各取一条完整的实际边，配对两个端点，允许顺序相反。只有两对端点的距离都在声明的容差内，才通过这个接头的数值检查。随后在 Blockbench 查看严格侧视和转折近景，检查内角有没有鼓包、外侧有没有亮缝。动作会改变接头姿态时，还需回放对应动作。[构造公式、角点编号与检查示例](blockbench-shared-edge-modeling/references/shared-edge-construction.md)

## 按手上的任务选技能

| 你手上有什么，想完成什么 | 从这里开始 | 主要成果 |
| --- | --- | --- |
| 有角色或道具参考图，希望模型在对应视角下形似 | [reference-model-rebuild](reference-model-rebuild/SKILL.md) | 可编辑工程、匹配参考的相机、轮廓叠图、剩余差异记录 |
| 已有纯 Cube 工程，想让弯曲发束、袖口或饰边接得严，或希望减块后保持外形 | [blockbench-shared-edge-modeling](blockbench-shared-edge-modeling/SKILL.md) | 修正后的 Cube、接头端点误差、原生近景或减块前后对照 |
| 要制作 Minecraft 风格的人物、生物或物品，还要考虑像素贴图、绑定、动作或导出 | [mc-blockbench-creatures-public](mc-blockbench-creatures-public/SKILL.md) | 符合目标格式的模型，以及任务需要的纹理、动作和导出资源 |
| 多轮调整仍卡在同一问题，想换一种办法取得可检查的进展 | [task-progress](task-progress/SKILL.md) | 一次针对具体原因的尝试、可检查的结果和明确的未解决项 |

## 安装与第一次使用

在 Codex 中可以直接让内置的 `$skill-installer` 按仓库和目录安装。将下面这段作为一条请求发送给 Codex：

```text
$skill-installer 请从 https://github.com/1251639747jm-ctrl/blockbench-codex-skills 安装这四个目录中的技能：
blockbench-shared-edge-modeling
mc-blockbench-creatures-public
reference-model-rebuild
task-progress
```

如果只想在某个建模项目中使用，也可以下载仓库 ZIP 并解压，把需要的技能文件夹放到**该项目根目录**的 `.agents/skills/` 下。例如，复制后应能打开 `.agents/skills/reference-model-rebuild/SKILL.md`。保留各技能内部的目录结构；组合使用参考还原和共边建模时，将两个技能文件夹并排放置，方便访问相互引用的文档。安装后可在请求中写出技能名。如果列表没有更新，重启 Codex 再查看。[Codex 官方技能文档](https://developers.openai.com/codex/skills)

第一次使用可以从一个小部件开始。把参考图和工程放进工作区，在请求中写明文件名、允许修改的部位、目标格式和预算。只有图片也能开始参考还原；已有工程时，指出哪一版是你认可的起点，能让前后对照更有意义。

## 四个技能怎样工作

### 从图片恢复轮廓与厚度

`reference-model-rebuild` 先对齐参考图的观察角度。比如一张被称为“侧视”的图还能看见脸的正面，直接照着外轮廓加厚，就容易把视角造成的宽度误当成头部深度。技能会根据多个可见特征校准相机，再分别核对轮廓转折、孔洞、遮挡和厚度。在单图任务中，被遮住的背面可以补全，并在记录中标明推断。具体比较方法见[校准与叠图](reference-model-rebuild/references/calibration-and-review.md)。

> **请求示例**　使用 reference-model-rebuild，依据正面图和右侧参考图重建这个背包。先对齐包体和翻盖，再做搭扣与肩带。输出可编辑工程和两个参考角度的叠图，说明背面哪些结构来自推断。

### 让旋转后的 Cube 沿同一条边连接

`blockbench-shared-edge-modeling` 适合处理正面似乎接上、转到侧面却透光或鼓包的问题。做一束弯发时，先选相邻两块，计算它们经过自身旋转和父组变换后的边端点，再检查外表面走向、厚度和内弯。样件通过后，再沿发束扩展。做保形减块时，还要在相同相机和光照下对比前后画面，检查材质、可见内壁和运动归属。[共边构造与接头声明](blockbench-shared-edge-modeling/references/shared-edge-construction.md) · [贴图与保形优化](blockbench-shared-edge-modeling/references/texture-and-optimization.md)

> **请求示例**　使用 blockbench-shared-edge-modeling，以我上传的角色工程为基线，只修右侧刘海第二段和第三段之间的亮缝。保留发梢位置、外轮廓和现有贴图。交付另存的模型、这两块的接头检查结果，以及正面和右侧近景。

### 按 Minecraft 资产的用途制作和验收

`mc-blockbench-creatures-public` 将资产分为人模、非人型生物和物品。做四足生物时，先看躯干、肢体支撑与步态；做手持道具时，优先确认轮廓、握持点、材质和显示方式。目标工程格式决定能够导出哪些数据。已有项目可以先查格式、骨骼和动画，再决定哪些资源需要一起交付。[人模](mc-blockbench-creatures-public/references/humanoids.md) · [生物](mc-blockbench-creatures-public/references/creatures.md) · [物品](mc-blockbench-creatures-public/references/items.md) · [格式选择](mc-blockbench-creatures-public/references/format-routing.md)

> **请求示例**　使用 mc-blockbench-creatures-public，为现有四足生物制作原地行走循环。沿用工程格式和像素贴图。请检查支撑脚有没有滑动、尾巴是否跟随躯干，并交付可编辑动作和一个完整循环的预览。

### 在反复修改时找到下一步

`task-progress` 可以单独使用，也可以配合建模技能。当相同检查已经做过两轮，又没有实质修改、新证据或新假设时，第三次检查前应更换方法。例如袖口看起来一直偏厚，可以先隔离袖口、锁定严格侧视，判断偏差来自截面还是相机，然后只改一个样件，观察结果再决定下一步。[完整执行约定](task-progress/SKILL.md)

## 组合示例：把角色参考图做成纯 Cube 模型

1. **确定基线。** 指定参考图、是否从零制作、纯 Cube 约束和预算。已有工程时先留起始副本。如果预算写的是“最多 300 个 Cube”，统计时包括隐藏 Cube，并单列分组数量。
2. **校准相机。** 用 `reference-model-rebuild` 找到头顶、肩线、袖口等跨视图可辨认的位置，先建立主要体块。保存匹配参考的视角，便于修改后回到同一位置比较。
3. **制作一个曲线样件。** 用 `blockbench-shared-edge-modeling` 处理一侧发束或袖体。记录参与连接的两块 UUID，对照旋转后的端点和原生侧视近景，再扩展到其余段。
4. **检查最终文件。** 重开保存后的模型，核对图集、UV 和可见内壁。需要动画或游戏导出时，接着按 `mc-blockbench-creatures-public` 的对应分支检查枢轴、动作和资源。交付时写明检查使用的工程版本，并区分文件检查、Blockbench 回放和游戏内实测。

## 从命令行检查已保存的模型

以下示例在**本仓库根目录**运行，需要 Python 3。将模型路径和接头声明文件替换为项目中的实际文件。命令会把 JSON 报告写到当前目录。

```bash
# 统计模型元素、分组等对象，并检查纯 Cube 要求。把 2000 改成本次总对象预算。
python reference-model-rebuild/scripts/audit_bbmodel.py "模型.bbmodel" --limit 2000 --cube-only --json-out "对象统计.json"

# 核对声明文件中登记的静态 Cube 接头，输出实际边、端点误差和模型指纹。
python blockbench-shared-edge-modeling/scripts/audit_shared_edges.py "模型.bbmodel" "接头声明.json" --report "共边检查.json"

# 检查骨骼资产的结构和动画数据。若工程采用 20 FPS，可显式传入 --fps 20。
python mc-blockbench-creatures-public/scripts/audit_bbmodel.py "生物.bbmodel" --report "骨骼与动画.json"
```

共边检查需要先登记要验的 Cube 对。使用保存文件里的实际 UUID 填写声明，格式见[接头 JSON 示例](blockbench-shared-edge-modeling/references/shared-edge-construction.md)。端点误差能说明登记的两条边是否重合；厚度方向、接缝在正常观看距离下的表现，以及动画中是否穿插，仍需查看模型。

如果只允许改一个部位，可用版本差异工具比较前后两份工程的几何、骨骼、UV、贴图和动作。需要可重复的多视图或动画采样时，按原生验收说明准备 Blockbench、Node.js 和对应工具。[局部修改差异检查](mc-blockbench-creatures-public/references/local-edit-diff.md) · [Blockbench 原生验收](mc-blockbench-creatures-public/references/native-review.md) · [工具准备](mc-blockbench-creatures-public/references/tool-setup.md)

## 授权与商业建模

可以用这套技能接付费建模商单，交付或销售独立创作的模型、贴图、动画和渲染图。技能文档采用 CC BY-NC-SA 4.0，并额外允许商业建模；脚本及配套文件有单独条款。出售原版或改版技能、将技能材料放入付费资源包，须另获许可。[完整授权与使用示例](LICENSE.md)
