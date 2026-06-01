# Changelog — openclaw-photo-agents-creator

All notable changes to this skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This skill carries its own version per [strategy C in RELEASING.md](../RELEASING.md).

## [Unreleased]

### Added

- **重跑即升级**：`create_agents.py` 现在能识别既有 agent 并自动进入更新流程，无需 `agents remove` + 重新创建。
- `.creator-state.json` 持久化：每个 workspace 写入一份记录 agent 的 id/role/name/emoji + 跨 agent 的 user_name + peer_agent_id。下次重跑 zero-arg 即可。
- 默认 ID 兜底：现存用户首次升级（state 文件还不存在）时，若使用默认 `photoartist` + `photocurator` ID，自动识别并补写 state。自定义 ID 用户首次升级仍需显式传入 `--artist-id` / `--curator-id`。
- SKILL.md 新增"更新已有 Agent"章节，执行规范分"创建模式 / 更新模式"两条路径。

### Fixed

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
