# Changelog — openclaw-photo-agents-creator

All notable changes to this skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This skill carries its own version per [strategy C in RELEASING.md](../RELEASING.md).

## [Unreleased]

## [1.0.0] - 2026-05-20

Initial public release on [ClawHub](https://clawhub.ai).

### Added

- One-shot deployment of OpenClaw dual-agent photo workflow (PhotoArtist + PhotoCurator).
- Templated BOOTSTRAP.md and Curator prompts.
- Auto-injects LR→RT mapping reference into Curator's grading prompt.
- Auto-writes `subagents.allowAgents` into `~/.openclaw/openclaw.json`.
- Compatible with photo-toolkit ≥ 1.0, photo-screener ≥ 1.0, photo-grader ≥ 1.0.
