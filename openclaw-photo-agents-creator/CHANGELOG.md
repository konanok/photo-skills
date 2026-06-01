# Changelog — openclaw-photo-agents-creator

All notable changes to this skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This skill carries its own version per [strategy C in RELEASING.md](../RELEASING.md).

## [Unreleased]

## [1.0.1] - 2026-06-02

修复"用户照片输出死黑"事件的架构层根因 + 累积之前未发布的"重跑即升级"改造。

### Fixed

- **AGENTS.md marker-based upsert**：硬约束（必须 spawn curator / JSON schema
  要求 / session 目录约定 / 已知错误模式）现在写到 workspace 的 `AGENTS.md`
  里一个带 `<!-- BEGIN/END: photo-skills-{role}-rules:v1 -->` marker 的 block。
  OpenClaw 始终把 AGENTS.md 注入到 system prompt（main session / subagent / cron，
  无任何过滤），所以硬约束**长期生效**。

  根因：早期版本只写 `BOOTSTRAP.md` 并假设它一直被注入。但 OpenClaw 源码
  （`workspace-DNgRLjQy.js` 的 `filterCompletedWorkspaceBootstrapFile` 和
  `reconcileWorkspaceBootstrapCompletionState`）显示：一旦 workspace
  `setupCompletedAt` 设置，BOOTSTRAP.md 不仅会从注入清单里被过滤掉，**还会
  被主动 `fs.rm` 删除**。结果用户的 photoartist 在 setup 完成后丢失了"必须
  spawn curator"等业务约束，自己脑补 grading_params.json schema，触发一连串
  静默失败，最终用户拿到"画面死黑"的产物。

  marker upsert 协议保护用户：保留 OpenClaw 默认 seed 的通用工作区行为
  （First Run / Session Startup / Memory / Red Lines 约 7-8KB 内容）以及
  用户手动加在 marker 之外的自定义笔记。重跑只替换 marker 之间的内容。

- **BOOTSTRAP.md 升级模式跳过写入**：避免在 `setupCompletedAt` 已设置的
  workspace 上反复经历"create_agents.py 写 BOOTSTRAP → 下次 session 启动被
  reconcile 删 → 下次升级再写 → 又被删"的无效循环。首次创建（agent_exists=False）
  时仍写入，承担 OpenClaw 设计的"first-run 一次性引导"语义。

### Added

- 两个新模板 `templates/agents-artist.md` + `templates/agents-curator.md`，
  各自把硬约束块包裹在 `<!-- BEGIN/END: photo-skills-{role}-rules:v1 -->`
  marker 之间。重跑 `create_agents.py` 只替换 marker 之间的内容，不破坏
  marker 之外的 OpenClaw 默认 seed 和用户自定义内容。
- BOOTSTRAP.md 顶部说明改为「first-run only」语义提示，并明示真理之源是
  AGENTS.md（避免下游 agent 误以为 BOOTSTRAP 还在持久生效）。
- SKILL.md / README.md 同步：文件结构图、创建步骤、Triggers 关键词扩展
  （加入"修复 photo dark / 偏暗输出 / 恢复 artist 委派 curator 行为"等
  常见自然语言触发词，让其他调度器/AI 能搜到本 skill）。
- agents-{role}.md 内嵌「已知错误模式」表格，把本次事件的真实踩坑（21 次
  image 调用 + 0 次 sessions_spawn、错 schema 静默丢字段等）当反面教材，
  让 LLM 在执行前能看到。

### From previously unreleased

以下条目最初在 1.0.0 之后积累到 [Unreleased]，本次 1.0.1 一并发布：

- **重跑即升级**：`create_agents.py` 现在能识别既有 agent 并自动进入更新流程，无需 `agents remove` + 重新创建。
- `.creator-state.json` 持久化：每个 workspace 写入一份记录 agent 的 id/role/name/emoji + 跨 agent 的 user_name + peer_agent_id。下次重跑 zero-arg 即可。
- 默认 ID 兜底：现存用户首次升级（state 文件还不存在）时，若使用默认 `photoartist` + `photocurator` ID，自动识别并补写 state。自定义 ID 用户首次升级仍需显式传入 `--artist-id` / `--curator-id`。
- SKILL.md 新增"更新已有 Agent"章节，执行规范分"创建模式 / 更新模式"两条路径。
- 既有 agent 上重跑 `create_agents.py` 不再因 `openclaw agents add ... already exists` 而中止整个流程（改造前会跳过 BOOTSTRAP / skills / prompts 全部刷新）。
- `get_existing_agent_workspace` 不再吞 `Exception` — 未知异常（如 `agents list --json` schema 漂移）会被打印，避免被误判为"未注册"导致 `agents add` 撞错。
- `discover_existing_agents` 用 `is_dir()` 防御 base_dir 是文件路径时的 `NotADirectoryError`。
- `.creator-state.json` 改为原子写入（tmp + `os.replace`），防止 Ctrl-C / 磁盘满产生半截 JSON。
- `read_creator_state` 增加 `schema_version` 前向兼容防护：高版本 state 被老工具读到时退化为 None 而非错误解释。
- `create_merged_config` 跳过已存在的 `config.toml` 时打印 `diff` 命令引导手动核对 schema 漂移（保护用户配置不被覆盖）。

## [1.0.0] - 2026-05-20

> **Not yet on ClawHub.** The initial publish attempt was rejected because
> the slug `openclaw-photo-agents-creator` falls inside ClawHub's protected
> `openclaw-` namespace. The feature set below is implemented and verified
> locally; it will appear on ClawHub after a rename (leading candidate:
> `photo-agents-creator`). See the root
> [CHANGELOG.md](../CHANGELOG.md) "Cross-skill milestones" section for the
> bigger picture.

### Added

- One-shot deployment of OpenClaw dual-agent photo workflow (PhotoArtist + PhotoCurator).
- Templated BOOTSTRAP.md and Curator prompts.
- Auto-injects LR→RT mapping reference into Curator's grading prompt.
- Auto-writes `subagents.allowAgents` into `~/.openclaw/openclaw.json`.
- Compatible with photo-toolkit ≥ 1.0, photo-screener ≥ 1.0, photo-grader ≥ 1.0.
