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

## 更新已有 Agent（重跑即升级）

仓库代码改动后想让运行中的 agent 用上新版？**直接重跑本脚本**——脚本会自动识别既有 agent 并进入更新流程：

```bash
cd ~/.openclaw/skills/photo-skills && git pull
python3 openclaw-photo-agents-creator/scripts/create_agents.py --yes
```

更新模式下：

- ✅ 自动从 `.creator-state.json` 恢复 ID / 昵称 / Emoji，无需重传参数
- 🔄 覆盖刷新 `BOOTSTRAP.md` / `prompts/` / `skills/<photo-*>/`
- 🛡️ `skills/config.toml`（照片输入/输出目录）永不覆盖；schema 有变更时打印 `diff` 命令提示手动核对
- ⚠️ `BOOTSTRAP.md` / `prompts/*.md` 改动需要 `openclaw gateway restart` 才能被运行中的 agent 加载；仅 `skills/<skill>/scripts/*.py` 改动则不必

详细的判定逻辑、老用户首次升级注意事项、参数优先级（CLI > state > DEFAULTS）等见 [`SKILL.md`](./SKILL.md) 的"更新已有 Agent"章节。

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

每个 Agent 包含两类系统文档（语义截然不同，互补不重叠）：

- **`AGENTS.md`** — 持久业务硬约束。OpenClaw 始终把它注入 system prompt（main session 与 subagent / cron 都注入，不被 `setupCompletedAt` 过滤）——这是**真理之源**。`create_agents.py` 用 marker-based upsert 把业务规则块插入到现有 AGENTS.md，**保留** OpenClaw 默认 seed 的通用工作区行为（First Run / Session Startup / Memory / Red Lines 等约 7-8KB 内容）以及用户手动添加的笔记。
- **`BOOTSTRAP.md`** — **一次性引导文档**（first-run only）。仅在 workspace 首次创建（`.openclaw/workspace-state.json` 的 `setupCompletedAt` 未设置）时被 OpenClaw 注入一次。**Setup 完成后 OpenClaw 会主动 `fs.rm` 删除它**（见 `workspace-DNgRLjQy.js:197-241` 的 `reconcileWorkspaceBootstrapCompletionState`），所以它**不是**持久 reference 文档。

> ⚠️ 历史教训：早期版本只写 BOOTSTRAP.md 并假设它一直被注入。一旦 OpenClaw 把 workspace 标记为 setup 完成，BOOTSTRAP 被过滤并删除，agent 就丢失所有业务约束（"必须 spawn curator" 等），自己脑补 grading_params.json schema，最终造成用户拿到"画面死黑"的产物。AGENTS.md marker-based upsert 是这件事的修复——硬约束随 OpenClaw 注入路径长期生效，**且不会破坏用户在 AGENTS.md 内的其他内容**。
>
> 升级模式（重跑 `create_agents.py`）下 BOOTSTRAP.md 跳过写入，避免反复"写-删"循环。

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

## 依赖初始化注意事项

创建脚本会运行各 photo skill 的 `setup_deps.sh`，并汇总失败项。若 `photo-grader` 初始化失败，需要先确认 `rawtherapee-cli` 可用。

macOS 下先确认 `rawtherapee-cli` 已被用户显式打开/授权，然后运行：

```bash
rawtherapee-cli -h
```

如果 CLI 以 `133` / `SIGTRAP` 退出，通常表示它在启动前被 macOS 安全机制拦截。Agent 自动通过 Homebrew 安装后，用户往往还没有手动打开/授权该应用或 CLI，因此更容易触发拦截；用户自己提前通过 Homebrew 安装并完成授权也可以使用。无法完成授权时，改用官网包中的独立 CLI 后再重新运行 `photo-grader/scripts/setup_deps.sh`。

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
