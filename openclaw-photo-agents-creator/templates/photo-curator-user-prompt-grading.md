# Photo Curator User Prompt — 第二轮：调色

> PhotoArtist 在第二轮 sessions_spawn 时，将此 Prompt 与缩略图、selection.md、layout_config.json 一起发送给 PhotoCurator。配合 `photo-curator-system-prompt.md` 使用。

---

````

请根据第一轮确定的选片结果和风格意图，为每张入选照片生成调色参数。

## ⚠️ 重要提醒

1. **遵循风格意图**：style_intent 中定义了整组照片的风格方向和一致性模式，调色参数必须与之对齐
2. **请先判断每张照片的曝光情况**：如果偏暗，必须开启 `raw.auto_bright: true`
3. **直接使用 Lightroom 标准参数**（grade.py 自动映射到 RT PP3 格式）
4. **只输出需要修改的参数**，未调整的字段省略（默认值 = 0）
5. 一致性模式 `unified` → 色温/饱和度/色调方向统一，仅逐张微调曝光和细节；`contrast` → 说明哪几张是对比色调并给出理由；`gradient` → 按排列顺序做色彩渐变
6. **file 字段使用绝对路径**（从 Task Context 的 THUMBNAIL_PATHS 推断原始文件路径）

## 每张照片的说明结构

### 📷 照片 [序号] — 文件名

**📊 曝光判断**：（正常 / 偏暗需 auto_bright / 偏亮需压曝光）
**🎨 调色思路**：1-2 句话说明调色意图。

#### ⚙️ 调色参数 JSON

```json
{
  "file": "/absolute/path/to/DSC_XXXX.NEF",
  "style": "风格名称",
  "raw": { "auto_bright": false },
  "basic": { "exposure": 0.0, "contrast": 0 }
}
```

---

## 最终输出

逐张说明后，将所有调色 JSON **汇总**为一个顶层数组：

```json
[
  { "file": "/absolute/path/to/DSC_0001.NEF", "style": "...", "basic": {...}, ... },
  { "file": "/absolute/path/to/DSC_0002.NEF", "style": "...", "basic": {...}, ... }
]
```

保存为 `grading_params.json`，供 `grade.py` 批量处理。

## LR→RT 映射差异

{{RT_MAPPING_REFERENCE}}

## 输出要求

1. 使用中文，Markdown 格式
2. 顺序：逐张调色参数（含 JSON）→ 汇总 JSON 数组
3. JSON 必须严格合法（可被 `json.loads()` 解析），不含注释
4. **只输出需要修改的参数**，未调整的字段和分组省略
5. **汇总数组必须是 `[{...}, {...}]` 顶层数组**，严禁包裹在 `{files: [...]}` 中
6. **file 字段必须使用绝对路径**

````
