# Changelog — openclaw-photo-agents-creator

All notable changes to this skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This skill carries its own version per [strategy C in RELEASING.md](../RELEASING.md).

## [Unreleased]

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
