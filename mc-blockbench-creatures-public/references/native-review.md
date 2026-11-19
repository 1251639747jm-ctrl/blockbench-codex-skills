# 原生预览、动画采样与版本对照

需要固定视角验收、动作采样、前后对照时读本页。工具渲染真实 `.bbmodel`，不调用图像生成，不保存模型或重写关键帧。Node 22+（内置 WebSocket）用于采集；Python + Pillow 用于总览图、GIF 和 HTML 播放器。

缺少必要工具时先按 [tool-setup.md](tool-setup.md) 安装并验证，再继续；已有可用连接和依赖直接复用。

## 先确认已有连接

能启动 Blockbench 不代表能取得反馈。先验证：读取实际工程/格式 → 设定指定动作和时间 → 取得原生视口 → 保存可追溯结果。已有 MCP/API 能完成这些动作时可以沿用，无需重复搭桥。项目临时脚本不是稳定依赖。

本工具通过本机 CDP 调用 Blockbench API。先 `node scripts/bb_review.mjs inspect --port <实际端口>`；inspect 只读。capture 要求**空的专用实例**，遇到已有工程会停止，不关闭用户标签。不要抢用其他聊天正在编辑的实例。若需检查未保存的修改，先在所属制作流程保存快照，再采集该快照；本工具只读磁盘文件。

未连接时，在当前任务工作目录建立独立配置目录，用实际安装路径启动：

```powershell
$reviewProfile = Join-Path (Get-Location) 'tmp/model_review/blockbench_profile'
New-Item -ItemType Directory -Force $reviewProfile | Out-Null
# 9237 仅是示例，先确认端口未被其他任务占用。路径带空格时保留参数内引号。
Start-Process -FilePath '<Blockbench.exe 的实际绝对路径>' -ArgumentList @(
    ('--user-data-dir="' + $reviewProfile + '"'),
    '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=9237', '--no-first-run'
) -WindowStyle Hidden
```

若沙箱限制访问本地端口或启动进程，按工具权限流程执行，不把 EACCES 误判为 Blockbench 不支持。端口只用于本机，不开放到外网。完成后可以关闭本任务启动的实例；不要结束其他 Blockbench 进程。

## 采集

以下命令相对于技能目录执行；模型、输出和插件均使用实际路径。输出必须是空目录，按版本新建以保留基线。GeckoLib 工程首次加载时，用 `--plugin` 指向用户已经安装的 `geckolib.js`；工具不会下载插件，也不会把未知格式静默改为普通模型。

```powershell
node scripts/bb_review.mjs capture --port 9237 --model '<模型绝对路径>' --out '<工作目录>/review_v1' --plugin '<已安装的 geckolib.js>' --animation idle --fps 12 --track head,tail_tip
python scripts/review_report.py '<工作目录>/review_v1'
```

- 静态模型省略 `--animation` 与 `--track`。默认正面（-Z）、右侧（+X）、背面（+Z）、俯视（+Y）、斜侧五视图；这是相机轴约定，不自动证明角色的语义前向。不要为了适应相机而修改资产坐标。
- `--views front,right,back,top,three_quarter` 选择静态视角；`--motion-views front,three_quarter` 选择动作视角。默认动作只有斜侧视角。
- `--fps 12` 是**验收采样率**，不改变制作 FPS、snapping 或关键帧密度。快速挥击可提高采样率，或用 `--times 0,0.1,0.15,0.175,0.2,0.5` 显式覆盖接触前后；工具额外采样动作结束点。显式时间若不含 0，报告中的首尾差异不是完整循环接缝。
- `--track` 指定骨骼/元素名，重名时传 UUID。报告记录所选对象的世界原点、旋转和缩放。原点位移不是脚底滑移；脚掌接地、武器刃尖与握点需结合局部位置、模型尺寸和画面判断。
- 默认以静止姿态和所有采样姿态的包围盒共同确定相机，同一动作不逐帧自动缩放。大位移模型可能因此显小；用相关视角和局部检查补充，不能只看全身缩略图。

## 同条件对照

修改后使用上版相机，避免因重新取景掩盖变化：

```powershell
node scripts/bb_review.mjs capture --port 9237 --model '<新版模型>' --out '<工作目录>/review_v2' --animation idle --fps 12 --track head,tail_tip --camera-from '<工作目录>/review_v1/manifest.json'
python scripts/review_report.py '<工作目录>/review_v2' --baseline '<工作目录>/review_v1'
```

对照要求 Blockbench 版本、格式、灯光、相机、尺寸与背景相同；报告脚本拒绝将不匹配条件包装成公平对照。动作比较只配对同视角同时间，修改时长后需另外按阶段/事件锚点比较，不能只比较同秒数。

工具保留：

| 输出 | 用途 |
| --- | --- |
| `views.png`、`rest_*.png` | 实际模型多视图 |
| `motion_*_sheet.png` | 含时间标签的代表帧总览，末帧保留 |
| `motion_*.gif` | 按采样时间差播放；GIF 有时间量化，不用于帧级对时 |
| `index.html` | 本地播放器，可选视角、拖动逐帧；配套 PNG 必须保留 |
| `comparison.png` | 左旧右新，固定条件下的对照 |
| `manifest.json` | 源模型 SHA256、外部贴图指纹、版本、相机、灯光、采样时间、轨迹与裁切警告 |
| `diagnostics.json` | 轨迹范围、采样首尾的位置/角度/缩放差；无审美自动合格结论 |

采集完成会确认源文件未改变，并关闭本工具加载的标签；不写回模型。若源文件在采样过程中被另一个任务改动，结果标为不完整，换稳定快照重采。输出中断时不得以部分图片冒充完整验收。

## 结果使用和边界

实际打开 `views.png`、相关动作总览及局部原图，按需要播放 GIF/HTML。仅运行命令或看到 manifest 成功不算视觉检查。先用低成本代表姿态定位问题，再针对快速接触、循环接缝加密采样，不对无关动作无差别生成大量帧。

本工具已按 Blockbench 5.2.2 的原生 Cube/Mesh、Animator 和 Preview 接口实现。其他版本首次使用先验证；材质保留原生渲染，不替换 shader“美化”。这里的截图、轨迹与时间来自编辑器，不模拟 GeckoLib 控制器混合、游戏整体位移、碰撞或运行时 Molang 上下文。Java 物品可检查静态几何，未实现 `.mcmeta` 动态贴图播放器。动态贴图、依赖运行时变量的动作以及多角色接触需用对应专门预览或游戏补验。

已实测 GeckoLib 的骨骼动画、Java 物品静态模型、Java 模组实体静态模型。原生实体写在 Java 代码中的运动不会自动出现在 `.bbmodel` 时间轴里；工具不执行 Java `setupAnim`。Animated Java 的专用 Blueprint、Variant/Texture Slot 与显示节点需要其专门接口，当前脚本不能据此声称完整支持 Animated Java。

裁切检查使用包围盒，可能偏保守；隐藏几何、材质透明度和特效也可能影响观感。轨迹数值、首尾相同、没有裁切均不证明不存在穿插、脚滑或僵硬。不自动修复资产，不自动评定风格合格。
