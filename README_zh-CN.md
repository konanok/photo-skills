# photo-skills

[English](./README.md) | 简体中文

端到端摄影后期处理工具集 —— 使用 AI 完成相机照片的转换、筛选与调色。

## 功能介绍

| 模块                | 功能                                                                                      |
| ------------------- | ----------------------------------------------------------------------------------------- |
| **photo-converter** | 将相机 RAW/JPG/HEIC 文件转换为 JPG 缩略图，按 EXIF 拍摄日期查找照片，生成调色前后对比预览 |
| **photo-screener**  | 基于 MobileCLIP2-S0 的 AI 智能筛片 —— 美学评分（1-10 分）、连拍去重、14 类场景自动分类    |
| **photo-grader**    | Lightroom 风格批量调色（曝光、对比度、HSL、色调曲线、色彩分级、锐化等），由 JSON 参数驱动 |

### 处理流程

```
RAW / JPG / HEIC 原片
    │
    ▼  1. convert.py —— 生成缩略图
    │
    ▼  2. screen.py —— 美学评分 + 去重 + 场景分类
    │
    ▼  3. [LLM 生成 grading_params.json 调色参数]
    │
    ▼  4. grade.py —— 批量调色
    │
    ▼  5. layout_preview.py —— 调色前后对比
```

### 支持格式

- **相机 RAW**：Nikon (NEF)、Canon (CR2/CR3)、Sony (ARW)、Fujifilm (RAF)、Olympus (ORF)、Panasonic (RW2)、Pentax (PEF)、Samsung (SRW)、Leica (DNG)、Hasselblad (3FR)、Phase One (IIQ)、Sigma (X3F) 等
- **标准格式**：JPEG (.jpg/.jpeg)
- **Apple 格式**：HEIC/HEIF (.heic/.heif) —— 需安装 `pillow-heif`

## 使用步骤

### 1. 克隆 & 配置

```bash
git clone https://github.com/<your-username>/photo-skills.git
cd photo-skills

# 从模板创建配置文件
cp photo-converter/config.example.toml photo-converter/config.toml
cp photo-grader/config.example.toml    photo-grader/config.toml
cp photo-screener/config.example.toml  photo-screener/config.toml

# 编辑配置 —— 设置你的输入/输出目录
# 例如 "input_dir": "~/Photos/RAW", "output_dir": "~/Photos/output"
```

### 2. 安装依赖

```bash
# 一键安装所有依赖（交互式，覆盖三个模块）
bash setup.sh

# 或仅检查环境状态（不安装）
bash check_env.sh
```

### 3. 转换照片为缩略图

```bash
python3 photo-converter/scripts/convert.py ~/Photos/RAW ~/Photos/thumbnails \
    --size 1200 --quality 85
```

### 4. AI 筛片（可选，大批量时推荐）

```bash
python3 photo-screener/scripts/screen.py ~/Photos/thumbnails \
    --min-score 4.0 --auto-download
# 输出 filter_report.json，包含评分、场景标签和 LLM 分批信息
```

### 5. 批量调色

```bash
# 准备 grading_params.json（通过 LLM 生成或手动编写）
python3 photo-grader/scripts/grade.py grading_params.json \
    --raw-dir ~/Photos/RAW --output ~/Photos/graded
```

### 6. 预览效果

```bash
# 调色前后并排对比（默认模式）
python3 photo-converter/scripts/layout_preview.py ~/Photos/graded \
    --originals ~/Photos/RAW --params grading_params.json

# 宫格模式
python3 photo-converter/scripts/layout_preview.py ~/Photos/graded --grid
```

## 系统要求

| 项目        | 说明                                                                                                       |
| ----------- | ---------------------------------------------------------------------------------------------------------- |
| **Python**  | 3.8+                                                                                                       |
| **libraw**  | `brew install libraw`（macOS）/ `apt-get install libraw-dev`（Debian）/ `dnf install LibRaw-devel`（RHEL） |
| **PyTorch** | 仅 photo-screener 需要，CPU 即可运行 MobileCLIP2-S0                                                        |
| **磁盘**    | MobileCLIP2-S0 模型约 300MB（screener 首次运行时下载）                                                     |

## 注意事项

- **先配置再使用**：每个模块需将 `config.example.toml` 复制为 `config.toml` 并设置目录路径。`config.toml` 已加入 gitignore，不会被提交。
- **RAW vs JPG/HEIC 调色差异**：RAW 文件提供完整 16-bit 编辑空间，调色效果最佳。JPG/HEIC 为 8-bit，曝光调整幅度应更保守。
- **模型下载**：photo-screener 的 MobileCLIP2-S0 模型（约 300MB）不随仓库分发，首次运行时会提示下载（使用 `hf-mirror.com` 国内加速）。脚本/CI 中可用 `--auto-download` 跳过确认。
- **跨格式文件匹配**：调色器按文件名主干匹配 —— `grading_params.json` 中写的是 `DSC_0001.NEF`，但实际文件是 `DSC_0001.CR2` 也能正确匹配。
- **所有脚本支持 `--dry-run`**：预览操作内容，不实际执行。

## 项目结构

```
photo-skills/
├── setup.sh                    # 一键安装所有依赖
├── check_env.sh                # 环境健康检查
├── .allinone-skill/            # 单 skill 合并工具
│   ├── merge.sh                # 合并 / 还原脚本
│   ├── SKILL.md                # 合并版 SKILL.md 模板
│   └── config.example.toml     # 合并版配置模板
├── photo-converter/
│   ├── config.example.toml
│   ├── requirements.txt
│   ├── SKILL.md
│   └── scripts/
│       ├── convert.py          # RAW/JPG/HEIC → JPG 缩略图
│       ├── find_by_date.py     # 按 EXIF 日期查找照片
│       ├── layout_preview.py   # 调色前后对比 & 宫格预览
│       └── setup_deps.sh
├── photo-grader/
│   ├── config.example.toml
│   ├── requirements.txt
│   ├── SKILL.md
│   └── scripts/
│       ├── grade.py            # Lightroom 风格批量调色
│       └── setup_deps.sh
└── photo-screener/
    ├── config.example.toml
    ├── requirements.txt
    ├── SKILL.md
    └── scripts/
        ├── screen.py           # CLIP 智能筛片流水线
        └── setup_deps.sh
```

## 单 Skill 模式（不推荐）

> **说明**：此模式将所有 skill 合并为一个。仅供只支持单 skill 入口的平台使用。日常使用请保持默认的多 skill 模式 —— 每个 skill 有独立的配置和 SKILL.md，更易管理和扩展。

如需将项目作为单个 skill 使用：

```bash
bash .allinone-skill/merge.sh
```

执行后会：

- 删除各子 skill 的 `SKILL.md`（备份在 `.allinone-skill/stand-alone-skills/`）
- 在项目根目录创建统一的 `SKILL.md` 和 `config.example.toml`
- 各脚本在子 skill 配置不存在时，会自动读取根目录的 `config.toml`

合并后创建并编辑根配置：

```bash
cp config.example.toml config.toml
# 编辑 config.toml —— 设置你的输入/输出目录
```

还原为多个独立 skill：

```bash
bash .allinone-skill/merge.sh --revert
```

## 许可证

MIT

> **关于 HEIC/HEIF 支持**：可选依赖 `pillow-heif` 使用 GPLv2 协议。该库默认不安装，核心功能不依赖它。如需处理 iPhone HEIC/HEIF 照片请自行安装，并注意 GPL 协议条款。
