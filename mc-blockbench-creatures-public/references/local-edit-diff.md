# 局部修改差异报告

用户要求保留其他部位、动作或贴图时，在修改前保存稳定工程快照，修改后用 `scripts/diff_bbmodel.py` 比较。只读两个 `.bbmodel`，不自动修正、转换或写回。Python 标准库检查工程数据，Pillow 解码像素；缺依赖按 [tool-setup.md](tool-setup.md) 处理。

```powershell
python scripts/diff_bbmodel.py '<before.bbmodel>' '<after.bbmodel>' --out '<工作目录>/diff_v1'
```

输出 `report.md`、完整旧值/新值的 `report.json`、每张已变贴图的红色像素掩码。输出目录必须为空，避免覆盖上轮证据。没有 `--scope` 只列变化，**不把“有差异”自动当错误，也不把“无差异”当修改目标完成**。

## 按用户要求指定允许范围

先从输入工程读取实际 UUID，按本次请求写 `scope.json`。类别、对象 UUID 和 JSON Pointer 路径共同限定范围；不要依据修改后的报告扩大允许范围来消除报警。

```json
{
  "allow": [
    {
      "category": "animations",
      "id": "实际动作UUID",
      "path": "/animators/实际尾骨UUID/keyframes/0/data_points/0/x"
    }
  ],
  "texture_regions": [
    {"id": "实际贴图UUID", "rect": [8, 12, 16, 20]}
  ]
}
```

```powershell
python scripts/diff_bbmodel.py '<before.bbmodel>' '<after.bbmodel>' --scope '<scope.json>' --out '<工作目录>/diff_v2'
```

示例分别允许一个已有关键帧的 X 值与一块像素区域，实际任务按需选择，不能照抄。矩形是 `[左, 上, 右, 下)`，不包含右/下边界；多个矩形取并集，逐个变化像素判定，不用外包矩形代替。需新增/删除关键帧时可以授权对应 `/animators/<UUID>/keyframes`，同时从报告检查轴、时间和插值是否超出文字需求。

省略 `path` 表示该对象整个数据范围；省略 `id` 表示该类别所有对象，仅在用户请求确实覆盖这些范围时使用。空 `allow` 表示任何变化都不允许。字段路径按完整边界匹配，`/animators/tail` 不会顺带允许 `/animators/tail_tip`。

| 类别 | 检查内容 |
| --- | --- |
| `elements` | cube/mesh/locator 的新增删除、尺寸、顶点、变换、UV、面属性等 |
| `groups` | 骨骼名、pivot、旋转、格式专属属性；兼容旧式内嵌 outliner 与独立 groups |
| `hierarchy` | 元素/骨骼的父级与同级顺序；独立 groups 存在时，outliner 自身属性另外保留，不能覆盖骨骼字段 |
| `animations` | 动作元数据、所有 animator、关键帧、插值、表达式、音效/粒子轨道 |
| `textures` | 图集尺寸、材质参数、外部路径等元数据 |
| `texture_bindings` | 将面的贴图索引解析成纹理 UUID 后比较，发现重排贴图引起的错误绑定 |
| `texture_pixels` | 解码后 RGBA 像素、变化数量、区域、掩码、尺寸变化与图像新增/删除 |
| `project` | 格式、分辨率、display 和其他工程顶层字段，对象 ID 为 `project` |

脚本不会删除 editor 状态噪声；在报告中区分 `isOpen` 等状态与实际资产变化。以 UUID 匹配对象，忽略 elements/groups/animations 数组本身的重排；关键帧列表、父子层级和同级顺序仍比较。UUID 缺失会回退数组位置并标记不完整，不猜测同名对象等价。PNG 压缩编码变化但 RGBA 相同不算改色；透明像素中的 RGB 变化仍报告。

## 状态与边界

- `inventory_only`：仅提供差异清单，没有授权范围判断。
- `within_scope`：在声明范围内通过已保存数据的比较。
- `outside_scope`：存在范围外变化；进程退出码 1。
- `incomplete`：纹理无法读取、两版引用同一个外部文件、缺少 UUID 等导致证据不足；退出码 2。输入错误同为 2。

贴图优先嵌入快照。外部贴图要随两个版本分别保存；仅复制 `.bbmodel` 而仍引用同一路径，无法证明旧像素被保留。输入文件在比较时变化也会报告不完整。

外部 `source` 引用变化即使像素相同也列入 `textures`；新增/删除贴图的图像数据也解码验证并列入 `texture_pixels`。若请求允许新增整张贴图，两类都需声明允许，不因元数据合法而跳过图像验证。

报告检查保存数据，不计算握点接触、骨骼世界姿态或模型审美。握持是否改善、动画是否穿插仍按 [native-review.md](native-review.md) 做同条件实际渲染/回放；转换项目还需按 [format-routing.md](format-routing.md) 保存、重开和转回验证。差异范围通过不等于功能目标或用户审美通过。
