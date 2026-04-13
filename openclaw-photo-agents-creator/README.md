# OpenClaw Photo Agents Creator

自动创建 OpenClaw 双 Agent 摄影工作流系统。

## 架构

```
用户
  │
  ▼
🎬 PhotoArtist (艺术总监 — 编排执行)
  │ sessions_spawn (两轮)
  ▼
🎨 PhotoCurator (策展师 — 选片/排版/调色)
  │
  ▼
┌─────────────────────────────────────┐
│  Skills                             │
│  • photo-toolkit (缩略图/日期查找/排版) │
│  • photo-screener (CLIP预筛)       │
│  • photo-grader (批量调色)         │
└─────────────────────────────────────┘
```

## 快速开始

```bash
# 交互式创建（推荐首次使用）
python3 scripts/create_agents.py

# 一键创建（使用默认值）
python3 scripts/create_agents.py --yes

# 自定义昵称
python3 scripts/create_agents.py \
    --artist-name "照片艺术总监" \
    --artist-emoji "🎬" \
    --curator-name "照片策展师" \
    --curator-emoji "🎨" \
    --yes
```

## 创建内容

### PhotoArtist Agent

- **ID**: `photoartist`（可自定义）
- **职责**: 工作流编排、脚本执行、任务调度、与 PhotoCurator 协作
- **工作区**: `workspace-photoartist/`

### PhotoCurator Agent

- **ID**: `photocurator`（可自定义）
- **职责**: 选片、排版编排、风格定义、调色参数生成
- **工作区**: `workspace-photocurator/`

### 配置文件

每个 Agent 包含：

- `BOOTSTRAP.md` — 种子文件，合并了角色定义、行为准则、工具说明等关键约束

Curator 额外包含：

- `prompts/user_prompt_selection.md` — 第一轮：选片+排版
- `prompts/user_prompt_grading.md` — 第二轮：调色

## 自定义配置

创建过程中会提示：

| 配置项        | 默认值       | 说明            |
| ------------- | ------------ | --------------- |
| Artist 昵称   | 照片艺术总监 | 主 Agent 的称呼 |
| Artist Emoji  | 🎬           | 主 Agent 的表情 |
| Curator 昵称  | 照片策展师   | 子 Agent 的称呼 |
| Curator Emoji | 🎨           | 子 Agent 的表情 |

## 创建后配置

脚本通过 `openclaw agents add` 自动注册 Agent（基础字段），需手动补充高级配置。

### 1. 合并配置到 openclaw.json

| 配置项                      | Agent   | 说明                                                  |
| --------------------------- | ------- | ----------------------------------------------------- |
| **bindings**                | Artist  | 路由绑定，如 `qqbot:photoartist`                      |
| **subagents.allowAgents**   | Artist  | 允许调用 Curator（**必须**）                          |
| **model**                   | Artist  | 文本模型即可（可选，默认全局）                        |
| **model**                   | Curator | **视觉模型**（支持图片识别），如 `gpt-4o`（**必须**） |
| **thinkingDefault: "high"** | Curator | 提高审美决策的思考级别（推荐）                        |

### 2. 重启 Gateway

```bash
openclaw gateway restart
```

### 3. 配置照片目录

编辑 `workspace-photoartist/skills/config.toml`，设置 `raw_dir` 和 `output_dir`。

### 4. 开始使用

```bash
openclaw agent --agent photoartist --message "帮我处理 3 月 15 日的照片"
```

## 工作流

```
用户: "帮我处理 3 月 15 日的照片"
    │
    ▼
PhotoArtist
  1. 按日期筛选照片
  2. 生成缩略图
  3. CLIP 预筛（可选）
  4. 第一轮 spawn → PhotoCurator（选片+排版+风格意图）
    │
    ▼
PhotoCurator
  5. 分析照片、选片、设计排版方案、定义风格意图
  6. 返回 selection.md + layout_config.json
    │
    ▼
PhotoArtist
  7. 第二轮 spawn → PhotoCurator（调色）
    │
    ▼
PhotoCurator
  8. 根据风格意图为每张照片生成调色参数
  9. 返回 grading_params.json
    │
    ▼
PhotoArtist
  10. 批量调色（grade.py）
  11. 生成排版预览（layout_preview.py --params）
  12. 展示结果
```

## 模板文件

Agent 配置文件模板位于 `templates/`：

- `bootstrap-artist.md` — Artist Agent 启动配置（角色定义、行为准则、协作协议）
- `bootstrap-curator.md` — Curator Agent 启动配置（角色定义、引擎参数说明）
- `photo-curator-user-prompt-selection.md` — 第一轮：选片+排版
- `photo-curator-user-prompt-grading.md` — 第二轮：调色
- `rt-mapping-reference.md` — Lightroom → RawTherapee 参数映射参考

模板使用 `{{VARIABLE}}` 占位符，创建时自动替换为用户配置。

## License

MIT License
