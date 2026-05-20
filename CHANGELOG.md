# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Each ClawHub-published skill carries its own version per [strategy C in RELEASING.md](./RELEASING.md).

## [Unreleased]

## [1.0.0] - 2026-05-20

Initial public release on [ClawHub](https://clawhub.ai).

### photo-toolkit

- Convert RAW / JPG / HEIC to JPG thumbnails (`convert.py`).
- Find photos by EXIF shooting date (`find_by_date.py`), supports timelapse sequence detection.
- Generate before/after layout previews (`layout_preview.py`).
- Deflicker timelapse frames (`deflicker.py`).
- Assemble JPG frames into MP4 (`assemble.py`).
- Supports Nikon (NEF), Canon (CR2/CR3), Sony (ARW), Fujifilm (RAF), Olympus (ORF), Panasonic (RW2), Pentax (PEF), Samsung (SRW), Leica (DNG), Hasselblad (3FR), Phase One (IIQ), Sigma (X3F), plus standard JPEG and Apple HEIC/HEIF.

### photo-screener

- AI-powered photo pre-screening using MobileCLIP2-S0.
- Aesthetic scoring (1–10), burst-shot deduplication, 14-category scene classification.
- Outputs `filter_report.json` with batches grouped by scene for downstream LLM consumption.
- Adaptive threshold when no photos pass the configured `min_score`.

### photo-grader

- Apply Lightroom-style color grading to RAW / JPG / HEIC photos via RawTherapee CLI.
- 13 LR→RT auto-mappers covering exposure, contrast, HSL, tone curve, and effects.
- Multi-format JSON input (nested array, single object, `{files: [...]}` wrapper, flat params).
- Uniform mode (`--uniform-dir`) for timelapse / batch grading.
- Cross-format file matching by stem name (`DSC_0001.NEF` matches `DSC_0001.CR2`).

### openclaw-photo-agents-creator

- One-shot deployment of OpenClaw dual-agent photo workflow (PhotoArtist + PhotoCurator).
- Templated BOOTSTRAP.md and Curator prompts.
- Auto-injects LR→RT mapping reference into Curator's grading prompt.
- Auto-writes `subagents.allowAgents` into `~/.openclaw/openclaw.json`.
- Compatible with photo-toolkit ≥ 1.0, photo-screener ≥ 1.0, photo-grader ≥ 1.0.
