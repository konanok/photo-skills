---
name: openclaw-photo-agents-creator
version: 1.0.1
description: |
  创建或更新 OpenClaw 双 Agent 摄影工作流系统（重跑即升级）。

  一键部署 PhotoArtist Agent（艺术总监 — 编排执行）和 PhotoCurator Agent（策展师 — 选片/排版/调色），
  包含完整的 Skill 配置、Agent 灵魂定义、工作流编排和协作协议。同一脚本同时承担"首次创建"
  和"既有 agent 升级"两条路径——重跑会自动识别既有 agent，从 .creator-state.json 恢复参数，
  并刷新 AGENTS.md 业务规则块（marker-based upsert）/ prompts / skills/ 到仓库最新版本。
  BOOTSTRAP.md 仅首次创建时写入（OpenClaw 在 setup 完成后会主动删除，升级模式跳过避免反复写-删）。

  Use when the user wants to:
  - 快速搭建 OpenClaw 摄影后期工作流
  - 创建 photoartist + photocurator 双 Agent 系统
  - 部署 RAW → 缩略图 → 选片 → 调色 → 排版的完整流水线
  - **更新 / 升级既有的 photoartist + photocurator agent 到 photo-skills 仓库最新版**
  - **同步本地 skill 代码改动到 OpenClaw 运行时（重跑 creator）**
  - **拉取 photo-skills 新版本后让 agent 用上新代码 / 新 BOOTSTRAP / 新 prompts**

  Triggers: User mentions creating OpenClaw agents, setting up photo workflow,
  deploying photographer agent, auto photo grading system, **updating photo agents,
  upgrading photo-skills, refreshing agent workspace, applying new BOOTSTRAP/AGENTS/prompts
  to running agent, syncing local skill changes to OpenClaw runtime,
  fixing photo dark/black output, restoring spawn-curator behavior,
  升级 / 更新 photo agent，刷新 agent 工作区，把新代码部署到 agent，
  修复照片输出死黑 / 偏暗问题，恢复 artist 委派 curator 行为**.
metadata:
  openclaw:
    homepage: https://github.com/konanok/photo-skills
    emoji: "🎬"
    requires:
      bins:
        - python3
        - openclaw
---

# OpenClaw Photo Agents Creator

自动创建 OpenClaw 双 Agent 摄影工作流系统。

## 创建内容

运行后会创建两个 Agent：

| Agent            | ID             | 职责                          | 工作区                    |
| ---------------- | -------------- | ----------------------------- | ------------------------- |
| **PhotoArtist**  | `photoartist`  | 艺术总监 — 编排执行、用户对话 | `workspace-photoartist/`  |
| **PhotoCurator** | `photocurator` | 策展师 — 选片、排版、调色方案 | `workspace-photocurator/` |

每个 Agent 包含两类文档（语义截然不同）：

- **`AGENTS.md`** — 持久业务硬约束。OpenClaw 始终把 AGENTS.md 注入到 system prompt（main session 与 subagent/cron 都注入），无任何过滤。`create_agents.py` 用 marker-based upsert（`<!-- BEGIN/END: photo-skills-{role}-rules:v1 -->`）把业务规则块插入 AGENTS.md，**保留** OpenClaw 默认 seed 的通用工作区行为（First Run / Session Startup / Memory / Red Lines 等）以及用户手动加的内容。**这是真理之源**。
- **`BOOTSTRAP.md`** — **一次性**引导文档（first-run only）。仅在 workspace 首次创建（`.openclaw/workspace-state.json` 的 `setupCompletedAt` 未设置）时被 OpenClaw 注入到 system prompt 一次。**Setup 完成后 OpenClaw 会主动 `fs.rm` 删除它**（见 `workspace-DNgRLjQy.js` 的 `reconcileWorkspaceBootstrapCompletionState`），所以它不是持久文档。`create_agents.py` 在升级模式（agent 已存在）下**跳过写入**，避免反复"写-删"循环。

Artist 额外包含 skills/（三个 photo skill）。Curator 额外包含 prompts/（选片/调色 User Prompt，调色 prompt 自动注入 LR→RT 映射参考）。

## 使用方法

### 交互式创建

```bash
python3 scripts/create_agents.py
```

创建过程中会提示输入：

- **Artist 昵称**：如"照片艺术总监"（默认）
- **Artist Emoji**：如 🎬（默认）
- **Curator 昵称**：如"照片策展师"（默认）
- **Curator Emoji**：如 🎨（默认）
- **用户称呼**：Agent 如何称呼你（默认"用户"）

### 一键创建（使用默认值）

```bash
python3 scripts/create_agents.py --yes
```

### 自定义创建

```bash
python3 scripts/create_agents.py \
    --artist-name "照片艺术总监" \
    --artist-emoji "🎬" \
    --artist-id "photoartist" \
    --curator-name "照片策展师" \
    --curator-emoji "🎨" \
    --curator-id "photocurator" \
    --user-name "你" \
    --yes
```

**参数说明：**

| 参数              | 说明                         | 默认值       |
| ----------------- | ---------------------------- | ------------ |
| `--artist-name`   | Artist 昵称                  | 照片艺术总监 |
| `--artist-emoji`  | Artist Emoji                 | 🎬           |
| `--artist-id`     | Artist ID                    | photoartist  |
| `--curator-name`  | Curator 昵称                 | 照片策展师   |
| `--curator-emoji` | Curator Emoji                | 🎨           |
| `--curator-id`    | Curator ID                   | photocurator |
| `--user-name`     | 用户称呼（Agent 如何称呼你） | 用户         |
| `--yes`, `-y`     | 非交互模式，使用默认配置     | -            |

> 工作区基目录通过环境变量 `OPENCLAW_STATE_DIR` 指定（默认 `~/.openclaw`），与 OpenClaw 官方保持一致。

## 更新已有 Agent（重跑 = 升级）

仓库代码改了想让运行中的 agent 用上新版？**直接重跑本脚本**——脚本会自动识别并进入更新模式：

```bash
cd ~/.openclaw/skills/photo-skills        # 或你的 clone 路径
git pull                                    # 拉取最新代码（如适用）
python3 openclaw-photo-agents-creator/scripts/create_agents.py --yes
```

更新模式下脚本会：

- ✅ **自动发现** — 扫描所有 workspace 找到上次创建的 agent，无需重新指定 `--artist-id` 等参数
- ✅ **保留参数** — 上次的昵称 / Emoji / 用户称呼自动从 `.creator-state.json` 恢复
- ✅ **跳过注册** — 已注册的 agent 不会再过 `openclaw agents add`
- 🔄 **AGENTS.md 业务规则块更新**（marker-based upsert）— 只替换 `<!-- BEGIN/END: photo-skills-{role}-rules:v1 -->` 之间的内容，保留 OpenClaw 默认 seed 与用户在 marker 外的自定义内容
- 🔄 **覆盖刷新** — `prompts/` / `skills/<photo-*>/` 全部重写为最新模板/代码
- ⏭ **跳过 BOOTSTRAP.md** — 升级模式下不写（OpenClaw 在 setup 完成后会主动 fs.rm 删除它，反复写无意义）
- 🛡️ **保护用户配置** — `skills/config.toml`（照片输入/输出目录）**永不覆盖**；如新版 schema 有变更脚本会提示手动 diff

**显式覆盖参数**：如想顺带改昵称/Emoji，仍可通过 CLI 传入：

```bash
python3 openclaw-photo-agents-creator/scripts/create_agents.py --yes \
    --artist-name "新名字"
```

CLI 参数 > `.creator-state.json` 中的旧值 > `DEFAULTS`，逐项覆盖。

**何时需要重启 gateway**：

| 改动范围                                     | 是否需要 `openclaw gateway restart`        |
| -------------------------------------------- | ------------------------------------------ |
| 仅 `skills/<skill>/scripts/*.py`（脚本逻辑） | 否，agent 调用 skill 时才读                |
| `BOOTSTRAP.md` / `prompts/*.md` 模板         | 是，agent 启动时已读入做系统消息           |
| `requirements.txt` / 系统依赖                | 否（脚本会重跑 `setup_deps.sh` 检查/安装） |

### 老用户首次升级（`.creator-state.json` 还不存在）

`.creator-state.json` 是较新引入的——在它之前创建的 agent，第一次升级时 workspace 里还没这个文件。脚本会按以下顺序兜底：

1. **默认 ID 兜底**：如果你当初用默认 `photoartist` + `photocurator` 创建，且这两个 agent 在 OpenClaw 中已注册——脚本会自动识别并进入更新流程，**无需手动传参数**。完成后会写入 state，下次起完全 zero-arg。
2. **自定义 ID 用户**：第一次升级仍需显式告诉脚本你的 ID：
   ```bash
   python3 openclaw-photo-agents-creator/scripts/create_agents.py --yes \
       --artist-id <你的 artist ID> --curator-id <你的 curator ID>
   ```
   只需做一次——成功后 state 会落盘，之后所有升级 zero-arg。
3. **自定义 workspace 路径用户**（极少数）：当初用 `openclaw agents add foo --workspace /tmp/myws` 这类非 `~/.openclaw/workspace-<id>` 的路径，本工具的 fallback 不能识别。请在升级前手动创建 `<your-workspace>/.creator-state.json`（参考其他 workspace 里的 state 文件结构），或在 OpenClaw 中先 `agents remove` 后用本脚本重新注册。

> 兜底**故意只识别默认 ID**，不做 ID 子串匹配（`"artist"`/`"curator"`）或 BOOTSTRAP 内容嗅探。这是有意的保守设计：宁可让自定义 ID 用户多传一次参数，也不引入容易误判的猜测逻辑。

> **`.creator-state.json` 是什么？** 每次创建/更新成功后，脚本会在
> `~/.openclaw/workspace-<id>/.creator-state.json` 写入该 agent 的角色（artist/curator）、
> 昵称、Emoji 和 peer agent ID。下次重跑时自动发现并复用。手动删除该文件 = 让脚本"忘记"
> 这个 agent 由本工具创建过；自定义 agent ID 的用户首次更新前**不要**删除它，否则脚本将进入
> 创建模式而非更新。

## 创建后配置

脚本会自动完成以下操作：

1. **注册 Agent**：通过 `openclaw agents add` 注册两个 Agent 到 OpenClaw
2. **upsert AGENTS.md**：渲染 `templates/agents-{artist,curator}.md`，用 marker-based upsert 写到 workspace 根目录的 AGENTS.md（OpenClaw 始终注入；保留默认 seed 与用户自定义内容）
3. **写 BOOTSTRAP.md**：仅首次创建时写入（first-run 由 OpenClaw 注入一次后自动删除）。升级模式跳过避免反复写-删
4. **复制 Skills**：将三个 photo skill 复制到 Artist 工作区的 `skills/` 目录
5. **安装依赖**：自动运行各 skill 的 `setup_deps.sh` 检查依赖；失败时必须提示用户先修复，不可静默继续
6. **创建合并配置**：在 `skills/config.toml` 生成合并配置，统一所有 skill 的输入输出路径
7. **注入 LR→RT 映射**：Curator 的调色 prompt 自动注入 `rt-mapping-reference.md` 内容

---

## 创建后 — 必须手动完成的步骤

> **脚本执行完毕后，必须立即按顺序引导用户完成以下步骤**，不可跳过。
>
> 脚本已自动完成：
>
> - 注册 Agent（`openclaw agents add`）
> - **AGENTS.md upsert**：把业务硬约束块插入到 workspace 的 AGENTS.md 里一个带 marker 的 section（OpenClaw 始终注入，是真理之源），保留 OpenClaw 默认 seed 的通用工作区行为与用户自定义内容
> - 写入 BOOTSTRAP.md 种子文件（仅首次创建；升级模式跳过）
> - 复制 Skills 到 Artist 工作区
> - 生成合并 config.toml
> - 注入 LR→RT 映射到 Curator prompt
> - 自动写入 `subagents.allowAgents` 到 openclaw.json
>
> 以下步骤仍需用户手动完成：

### Step 1: 安装依赖（AI 选片功能必需）

脚本执行完成后，**立即询问用户是否需要安装缺少的依赖**。

如果需要使用 AI 智能选片功能（photo-screener），需要安装 PyTorch 和 OpenCLIP：

```bash
pip3 install torch open-clip-torch
```

其他 skill 的系统依赖已在脚本执行期间通过 `setup_deps.sh` 检查并尝试安装；如果脚本执行失败，必须提示用户手动修复后再使用对应功能。如果 `photo-grader` 初始化失败，尤其是在 macOS 下出现 `rawtherapee-cli` 的 `133` / `SIGTRAP`，需要先用 `rawtherapee-cli -h` 验证 CLI 是否已被用户显式打开/授权。Agent 自动通过 Homebrew 安装后，用户通常还没有手动打开或授权该应用/CLI，可能会被 macOS 安全机制拦截；但如果用户自己提前通过 Homebrew 安装并完成授权，也可以继续使用。如果无法完成授权，建议改用官网包中的独立 `rawtherapee-cli` 并放入 `PATH`。如果用户选择跳过 AI 选片功能（仅使用格式转换和调色），可暂不安装以上包。

> 引导方式示例：
>
> > 脚本已执行完毕！接下来需要完成几项配置才能开始使用。
> >
> > **首先，你的照片处理流程中是否需要 AI 智能选片功能？**
> > （AI 选片会自动评分、去重、分类照片）
> >
> > - 如果需要 → 引导安装 torch + open-clip-torch
> > - 如果不需要（仅转换格式+调色）→ 跳过此步，继续下一步

### Step 2: 配置照片目录

编辑 `{workspace}/skills/config.toml`，设置照片路径：

```toml
# 你的原始照片目录（RAW/JPG/HEIF 文件所在位置）
raw_dir = "/path/to/your/photos"

# 输出目录（处理后的照片保存位置）
output_dir = "/path/to/output"
```

缩略图默认生成在 RAW 文件同级的 `thumbnails/` 子目录，无需单独配置。

> **请在此步主动询问用户的照片存储路径**，帮助其填写正确的目录。
>
> 示例询问：
>
> > 请告诉我你的照片存放在哪个目录？（例如：`/path/to/Pictures` 或 `/mnt/photos/RAW`）

### Step 3: 配置 openclaw.json（渠道绑定 + 模型设置）

打开 `~/.openclaw/openclaw.json`，找到 `agents.list` 数组，对两个 Agent 条目补充以下配置：

| 配置项            | 所属 Agent | 说明                                                       | 是否必须 |
| ----------------- | ---------- | ---------------------------------------------------------- | -------- |
| `bindings`        | Artist     | 路由绑定，指定哪些渠道的消息路由到此 Agent                 | 推荐     |
| `model`           | Artist     | 模型设置，Artist 做文本编排即可，文本模型足够              | 可选     |
| `model`           | Curator    | 视觉模型，Curator 需要分析照片缩略图，**必须支持图片识别** | **必须** |
| `thinkingDefault` | Curator    | 思考级别，设为 `"high"` 提升审美决策质量                   | 推荐     |

> **注意**：`subagents.allowAgents` 已由脚本自动写入，无需手动添加。

#### 完整配置示例

将以下内容**合并**到对应 Agent 的已有条目中：

**PhotoArtist 完整示例**（在已有字段基础上追加）：

```jsonc
{
  "id": "photoartist",
  // ... 已有字段保持不变 ...

  // ====== 以下为需手动添加的配置 ======

  "bindings": [
    {
      "agentId": "photoartist",
      "match": {
        "channel": "qqbot", // 改为你的实际渠道：qqbot / telegram / discord / wechat 等
        "accountId": "photoartist" // 改为你的实际账号 ID
      }
    }
  ],

  "model": "claude-sonnet-4-20250514" // 文本模型即可，Artist 负责编排不直接看图

  // subagents.allowAgents 已由脚本自动写入，无需重复
}
```

**PhotoCurator 完整示例**（在已有字段基础上追加）：

```jsonc
{
  "id": "photocurator",
  // ... 已有字段保持不变 ...

  // ====== 以下为需手动添加的配置 ======

  "model": "gpt-4o", // 必须是支持图片识别的视觉模型！
  // 推荐选项：gpt-4o / claude-sonnet-4-20250514 / gemini-2.5-pro
  "thinkingDefault": "high" // 高思考模式可显著提升选片和调色决策质量
}
```

> **Curator model 常见选择**：
>
> - `gpt-4o` — 多模态能力强，推荐首选
> - `claude-sonnet-4-20250514` — 图片理解优秀
> - `gemini-2.5-pro` — Google 多模态
> - **不要使用纯文本模型**（如 gpt-4、claude-3-haiku），Curator 必须能看照片缩略图

### Step 4: 重启 Gateway 使配置生效

```bash
openclaw gateway restart
```

> ⚠️ **如果你是 OpenClaw 内的 agent（self-mode）**：**不要自己执行这条命令**——你是 gateway 托管的进程，自重启会切断当前会话。请将命令交给用户在另一个终端执行，并提示用户：「重启会切断当前会话，请重启后在新会话里再次发起对话即可。」
>
> 外部 AI（Claude Code / Codex / CodeBuddy / Cursor 等）不受此限制，可直接执行，但执行前向用户口头确认一次。

### Step 5: 开始使用

```bash
openclaw agent --agent photoartist --message "帮我处理照片"
```

> ⚠️ **必须按顺序完成 Step 1 → Step 2 → Step 3 → Step 4**，否则 Agent 无法正常工作或 Curator 无法识别图片。

## 文件结构

```
~/.openclaw/
├── workspace-<artist-id>/            # PhotoArtist（默认 workspace-photoartist）
│   ├── AGENTS.md                     # ★ 持久硬约束（始终注入；marker block + OpenClaw seed + 用户自定义）
│   ├── BOOTSTRAP.md                  # 一次性引导（仅首次创建时写；first-run 后被 OpenClaw 自动删除）
│   └── skills/                       # OpenClaw skills 目录
│       ├── config.toml               # 合并配置（统一输入输出路径）
│       ├── photo-toolkit/
│       ├── photo-screener/
│       └── photo-grader/
└── workspace-<curator-id>/           # PhotoCurator（默认 workspace-photocurator）
    ├── AGENTS.md                     # ★ 持久硬约束（subagent 场景下唯一约束来源；BOOTSTRAP/HEARTBEAT/MEMORY 永远不注入到 subagent）
    ├── BOOTSTRAP.md                  # 一次性引导（仅首次创建时写；first-run 后被 OpenClaw 自动删除）
    └── prompts/
        ├── user_prompt_selection.md  # 第一轮：选片+排版
        └── user_prompt_grading.md   # 第二轮：调色（含 LR→RT 映射注入）
```

## 执行规范

### 先判断：创建 vs 更新

执行前先判断当前是**首次创建**还是**更新已有 agent**：

```bash
# 检查是否已有由本工具创建的 agent
ls ~/.openclaw/workspace-*/.creator-state.json 2>/dev/null
```

- **有输出** → 更新模式，按下方"更新模式"流程
- **无输出** → 首次创建模式，按下方"创建模式"流程

### 创建模式（首次）

1. **必须先收集配置**：在执行脚本前，**逐一确认**以下参数：
   - Artist 昵称（默认"照片艺术总监"）
   - Artist Emoji（默认 🎬）
   - Artist ID（默认 `photoartist`）
   - Curator 昵称（默认"照片策展师"）
   - Curator Emoji（默认 🎨）
   - Curator ID（默认 `photocurator`）
   - 用户称呼（默认"用户"）
2. **使用 CLI 参数显式传入**：收集完参数后，通过 `--xxx` 参数传入脚本，**不要使用 `--yes`**。
3. **仅当用户明确要求**时才用 `--yes`：如用户说"用默认值"、"一键创建"、"不要问我直接跑"等。
4. **展示创建结果**：执行完成后，列出已创建的文件和下一步操作。

### 更新模式（已有 agent）

1. **不要再问参数**：上次的参数会自动从 `.creator-state.json` 恢复。直接：
   ```bash
   python3 scripts/create_agents.py --yes
   ```
2. **仅当用户明确要求改昵称/Emoji**时才传 `--xxx` 覆盖（如 `--artist-name "新名字"`）。
3. **执行后必须告知用户**：
   - 哪些文件被刷新（脚本输出会列出）
   - 是否需要重启 gateway（取决于改动范围，详见上文表格）
   - `skills/config.toml` 不会被覆盖；如 CHANGELOG 提到 schema 变更，提醒用户手动 diff
