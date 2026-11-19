# 必要工具缺失时先安装，再验证可用

用户要求：缺少制作所需工具时，先安装所需工具再继续，不把“没工具”直接作为停止理由。只安装当前分支实际需要的工具；已有可用工具直接复用，不为预览任务安装所有格式插件。

## 检查 → 安装 → 小样验证

1. 查实际可执行文件、版本、插件注册格式和连接能力。能启动程序不等于能读取工程/采样；MCP 名称存在也不等于服务已连接。
2. 确认是工具缺失后，从官方发布页或官方包源选择与本机、Minecraft、Blockbench 版本兼容的版本，记录来源与版本。缺少工具的安装由用户本次要求授权，但仍按实际沙箱权限流程执行；需要管理员权限或自动审批被拒绝时说明具体缺口，不擅自改变安全设置。
3. 优先使用任务工作目录的虚拟环境、便携工具或独立 Blockbench 配置；不要为测试覆盖用户常用插件、更新全局版本或修改其他聊天的连接。
4. 验证可执行文件、插件格式是否真正出现，再用小样读取/截图/采样。安装命令成功不是完整可用证明。

## 本技能的工具与安装范围

| 需求 | 先检查 | 缺失时的处理 |
| --- | --- | --- |
| 编辑与原生预览 | Blockbench 路径、版本、现有 MCP/API/CDP 连接 | 从 [Blockbench 官方](https://www.blockbench.net/) 获取兼容版本；自动化测试用独立配置目录 |
| 通用、Java 模组实体、基岩版实体 | `Formats.free`、`Formats.modded_entity`、`Formats.bedrock` | 这些是本次已验证的 Blockbench 内置格式，不额外找同名插件安装 |
| GeckoLib 实体 | 当前插件是否注册 `geckolib_model` | 按 [GeckoLib 官方插件说明](https://wiki.geckolib.com/docs/geckolib5/making-models/blockbench-plugin-usage/) 安装兼容插件；项目库版本与插件版本分别记录，不自动升级项目的 GeckoLib 依赖 |
| Animated Java | 当前插件是否注册其 Blueprint 格式 | 按 [Animated Java 官方安装说明](https://animated-java.dev/docs/getting-started/installing) 安装兼容版本；测试装入隔离配置。已安装却转换报错时记录复现，不能当缺插件重复重装 |
| 本技能原生采集脚本 | `node --version`，要求内置 WebSocket 的 Node 22+ | 从 [Node.js 官方](https://nodejs.org/) 安装或使用工作目录中的兼容便携版本；本脚本无 npm 依赖 |
| 总览图、GIF、差异报告与贴图像素比较 | Python 可执行文件与 `python -c "from PIL import Image"` | 缺 Python 时从 [Python 官方](https://www.python.org/) 安装；缺 Pillow 时优先用任务虚拟环境安装 |

Pillow 安装示例（Windows，路径按当前任务调整）：

```powershell
python -m venv '<工作目录>/.review-venv'
& '<工作目录>/.review-venv/Scripts/python.exe' -m pip install Pillow
& '<工作目录>/.review-venv/Scripts/python.exe' -c 'from PIL import Image; print(Image.__version__)'
& '<工作目录>/.review-venv/Scripts/python.exe' '<技能目录>/scripts/review_report.py' '<预览目录>'
```

在技能工具和配置上仍实行单一写入方：其他对话正在统一维护技能时，将安装说明/工具改动放入本任务交接包，由维护方合并，不双边覆盖。

## 区分故障类型

- **缺程序/依赖**：安装实际缺项。
- **端口 EACCES 或权限拒绝**：走工具权限流程，不重装 Blockbench。
- **未连接 MCP**：先确认当前聊天能否使用该连接；本次已验证的本地 CDP 可完成原生采样，不必仅为名字相同重搭服务。
- **插件已加载、转换报错**：保留小样、版本、错误和菜单操作路径；换隔离环境排除冲突。不要修改正式模型或无休止重装。
- **转换成功但数据丢失**：这是格式/转换能力问题，应改制作约束或采用目标格式直接制作，安装工具本身不能证明解决。
