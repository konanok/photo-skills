---
name: openclaw-photo-agents-creator
description: |
  自动创建 OpenClaw 双 Agent 摄影工作流系统。

  一键部署 PhotoArtist Agent（艺术总监 — 编排执行）和 PhotoCurator Agent（策展师 — 选片/排版/调色），
  包含完整的 Skill 配置、Agent 灵魂定义、工作流编排和协作协议。

  Use when the user wants to:
  - 快速搭建 OpenClaw 摄影后期工作流
  - 创建 photoartist + photocurator 双 Agent 系统
  - 部署 RAW → 缩略图 → 选片 → 调色 → 排版的完整流水线

  Triggers: User mentions creating OpenClaw agents, setting up photo workflow,
  deploying photographer agent, auto photo grading system.
---

# OpenClaw Photo Agents Creator

自动创建 OpenClaw 双 Agent 摄影工作流系统。

## 创建内容

运行后会创建两个 Agent：

| Agent            | ID             | 职责                          | 工作区                    |
| ---------------- | -------------- | ----------------------------- | ------------------------- |
| **PhotoArtist**  | `photoartist`  | 艺术总监 — 编排执行、用户对话 | `workspace-photoartist/`  |
| **PhotoCurator** | `photocurator` | 策展师 — 选片、排版、调色方案 | `workspace-photocurator/` |

每个 Agent 包含 BOOTSTRAP.md（种子文件，包含所有关键约束）。

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

## 创建后配置

脚本会自动完成以下操作：

1. **注册 Agent**：通过 `openclaw agents add` 注册两个 Agent 到 OpenClaw
2. **写入 BOOTSTRAP.md**：渲染模板并写入种子文件（Artist 的含完整工作流约束，Curator 的含输出规范）
3. **复制 Skills**：将三个 photo skill 复制到 Artist 工作区的 `skills/` 目录
4. **安装依赖**：自动运行各 skill 的 `setup_deps.sh` 安装依赖
5. **创建合并配置**：在 `skills/config.toml` 生成合并配置，统一所有 skill 的输入输出路径
6. **注入 LR→RT 映射**：Curator 的调色 prompt 自动注入 `rt-mapping-reference.md` 内容

---

## 创建后 — 必须手动完成的步骤

> **脚本执行完毕后，必须立即按顺序引导用户完成以下步骤**，不可跳过。
>
> 脚本已自动完成：
>
> - 注册 Agent（`openclaw agents add`）
> - 写入 BOOTSTRAP.md 种子文件
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

其他 skill 的系统依赖已在脚本执行期间通过 `setup_deps.sh` 检查并提示安装。如果用户选择跳过 AI 选片功能（仅使用格式转换和调色），可暂不安装以上包。

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

### Step 5: 开始使用

```bash
openclaw agent --agent photoartist --message "帮我处理照片"
```

> ⚠️ **必须按顺序完成 Step 1 → Step 2 → Step 3 → Step 4**，否则 Agent 无法正常工作或 Curator 无法识别图片。

## 文件结构

```
~/.openclaw/
├── workspace-<artist-id>/            # PhotoArtist（默认 workspace-photoartist）
│   ├── BOOTSTRAP.md                  # 种子文件（含工作流、约束、进度追踪）
│   └── skills/                       # OpenClaw skills 目录
│       ├── config.toml               # 合并配置（统一输入输出路径）
│       ├── photo-toolkit/
│       ├── photo-screener/
│       └── photo-grader/
└── workspace-<curator-id>/           # PhotoCurator（默认 workspace-photocurator）
    ├── BOOTSTRAP.md                  # 种子文件（含输出规范、安全范围）
    └── prompts/
        ├── user_prompt_selection.md  # 第一轮：选片+排版
        └── user_prompt_grading.md   # 第二轮：调色（含 LR→RT 映射注入）
```

## 执行规范

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
