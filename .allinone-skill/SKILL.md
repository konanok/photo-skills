---
name: photo-skills
description: |
  AI photography toolkit: batch convert RAW/JPG/HEIC to thumbnails,
  smart screening (aesthetic scoring + dedup + scene tagging),
  and Lightroom-style color grading driven by LLM-generated parameters.

  Use when the user wants to:
    - Convert camera RAW/JPG/HEIC files to JPG thumbnails
    - Find or filter photos by shooting date
    - Score, filter, or deduplicate a batch of photos
    - Classify photos by scene type
    - Apply color grading or post-processing to camera photos
    - Generate before/after comparison or grid preview images

  Triggers: User mentions processing camera photos, converting RAW files,
  selecting/filtering photos, color grading, Lightroom adjustments,
  or any photography post-processing workflow.
---

# photo-skills

AI-powered photography post-processing toolkit — convert, screen, and color-grade camera photos.

## Pipeline

```
RAW / JPG / HEIC
    │
    ▼  photo-toolkit/scripts/convert.py
    │  Generate JPG thumbnails for preview
    │
    ▼  photo-screener/scripts/screen.py        (optional, for large batches)
    │  AI scoring + dedup + scene classification
    │  → filter_report.json
    │
    ▼  [LLM generates grading_params.json]
    │
    ▼  photo-grader/scripts/grade.py
    │  Batch color grading (RawTherapee)
    │
    ▼  photo-toolkit/scripts/layout_preview.py
       Before/After comparison or grid preview
```

## Skills

### photo-toolkit

Convert camera photos to JPG thumbnails, find photos by EXIF date, detect timelapse sequences, generate layout previews, deflicker frame sequences, and assemble frames into video.

| Script              | Purpose                                                                   |
| ------------------- | ------------------------------------------------------------------------- |
| `convert.py`        | RAW/JPG/HEIC → JPG thumbnails (parallel, configurable size/quality)       |
| `find_by_date.py`   | Find photos by EXIF date; detect timelapse sequences (`--timelapse`)      |
| `layout_preview.py` | Side-by-side BEFORE\|AFTER comparison (default) or grid layout            |
| `deflicker.py`      | Smooth luminance fluctuations in timelapse JPG frame sequences (in-place) |
| `assemble.py`       | Assemble JPG frames into H.264 MP4 video via FFmpeg                       |

```bash
python3 photo-toolkit/scripts/convert.py <input> <output> [--size 1200] [--quality 85]
python3 photo-toolkit/scripts/find_by_date.py --date 2026-03-15
python3 photo-toolkit/scripts/find_by_date.py <input> --timelapse [--copy-to <output>]
python3 photo-toolkit/scripts/layout_preview.py <graded_dir> --originals <raw_dir>
python3 photo-toolkit/scripts/deflicker.py <frames_dir> [--window 11]
python3 photo-toolkit/scripts/assemble.py <frames_dir> --output <video.mp4> [--fps 25] [--crf 18]
```

### photo-screener

AI-powered pre-screening using MobileCLIP2-S0 (18x faster than ViT-L/14, 80% selection consistency).

Four-stage pipeline:

1. **CLIP Encoding** — 512-dim embeddings (~27ms/image)
2. **Aesthetic Scoring** — LAION MLP predicts 1-10 score
3. **Deduplication** — Cosine similarity removes burst duplicates
4. **Scene Classification** — Zero-shot matching across 14 categories

```bash
python3 photo-screener/scripts/screen.py <thumbnails_dir> [--min-score 4.0] [--auto-download]
```

Output: `filter_report.json` with scores, scene tags, and LLM-ready batches.

Auto-skipped when photo count ≤ 20. Model (~300MB) downloads on first run with user confirmation.

### photo-grader

Apply professional-grade color grading driven by JSON parameters, using RawTherapee CLI as the sole engine.

Grading features: exposure, contrast, highlights/shadows/whites/blacks, white balance,
vibrance/saturation, parametric tone curve, HSL per-channel, three-way color grading,
sharpening (RL Deconvolution), noise reduction (IWT/astronomy), vignette, film grain.

```bash
python3 photo-grader/scripts/grade.py <grading_params.json> --raw-dir <raw_dir> --output <output_dir>
# Uniform mode: apply one parameter set to ALL files in a directory (timelapse / batch)
python3 photo-grader/scripts/grade.py <grading_params.json> --uniform-dir <dir> --output <output_dir>
# PP3-only: generate PP3 sidecar files without rendering
python3 photo-grader/scripts/grade.py <grading_params.json> --pp3-only --pp3-output ./pp3/
# Fast export mode
python3 photo-grader/scripts/grade.py <grading_params.json> --fast-export --lens-corr --auto-match
```

Key behaviors:

- Accepts Lightroom-style parameter values — auto-maps to RT PP3 format
- Professional RAW pipeline: AMAZE demosaicing, RL Deconvolution sharpening, IWT denoise, lensfun correction, Auto-Matched Camera Profiles
- Cross-format file matching: params say `DSC_0001.NEF`, actual file is `.CR2` → still works
- RAW files: full 16-bit editing latitude. JPG/HEIC: 8-bit, keep adjustments conservative.
- `--uniform-dir`: apply first param set to every file in directory (ignores `file` field in JSON)

## Setup

**Prefer venv**: Before running scripts, activate the project-root virtual environment (e.g. `.venv/`). If it doesn't exist, create one first:

```bash
# 1. Create config files
cp photo-toolkit/config.example.toml photo-toolkit/config.toml
cp photo-grader/config.example.toml    photo-grader/config.toml
cp photo-screener/config.example.toml  photo-screener/config.toml
# Edit each config.toml to set your input/output directories

# 2. Create venv and install dependencies (recommended)
python3 -m venv .venv
source .venv/bin/activate
pip install -r photo-toolkit/requirements.txt -r photo-grader/requirements.txt -r photo-screener/requirements.txt

# Or run each skill's setup script
bash photo-toolkit/scripts/setup_deps.sh
bash photo-screener/scripts/setup_deps.sh
bash photo-grader/scripts/setup_deps.sh

# Before each session, activate venv
source .venv/bin/activate
```

### System Requirements

- Python 3.8+
- libraw — `brew install libraw` (macOS) / `apt-get install libraw-dev` (Debian)
- FFmpeg — `brew install ffmpeg` (macOS) / `apt-get install ffmpeg` (Debian). Only needed for `assemble.py`
- PyTorch — screener only, CPU sufficient

### Config Files

Each skill reads defaults from its `config.toml`. CLI arguments always override config values.

| Skill          | Key config fields                                                          |
| -------------- | -------------------------------------------------------------------------- |
| photo-toolkit  | `input_dir`, `output_dir`, `size` (1200), `quality` (85)                   |
| photo-grader   | `raw_dir`, `output_dir`, `quality` (95)                                    |
| photo-screener | `clip_model`, `min_score` (4.0), `sim_threshold` (0.97), `batch_size` (20) |

## Agent Integration

When integrating with an AI agent:

1. Run each skill's `scripts/setup_deps.sh` to verify and install dependencies
2. Use `--dry-run` on any script to preview before executing
3. For screener, use `--auto-download` to skip model download prompt
4. All scripts output structured progress to stdout, errors to stderr
5. Scripts exit with code 0 on success, 1 on error

### Typical agent workflow

```bash
# Step 1: Convert
python3 photo-toolkit/scripts/convert.py ~/Photos/RAW ~/output/thumbnails

# Step 2: Screen (skip if ≤ 20 photos)
python3 photo-screener/scripts/screen.py ~/output/thumbnails \
    --output ~/output/filter_report.json --auto-download

# Step 3: [Agent reads filter_report.json + thumbnails → generates grading_params.json]

# Step 4: Grade
python3 photo-grader/scripts/grade.py ~/output/grading_params.json \
    --raw-dir ~/Photos/RAW --output ~/output/graded

# Step 5: Preview
python3 photo-toolkit/scripts/layout_preview.py ~/output/graded \
    --originals ~/Photos/RAW --params ~/output/grading_params.json
```

### Timelapse workflow

```bash
# Step 1: Detect & extract timelapse frames (exclude casual shots)
python3 photo-toolkit/scripts/find_by_date.py ~/Photos/RAW \
    --timelapse --copy-to ~/output/timelapse_frames

# Step 2: Uniform grade — one parameter set for all frames
python3 photo-grader/scripts/grade.py ~/output/grading_params.json \
    --uniform-dir ~/output/timelapse_frames --output ~/output/graded

# Step 3: Deflicker — smooth luminance fluctuations
python3 photo-toolkit/scripts/deflicker.py ~/output/graded

# Step 4: Assemble — frames → MP4 video
python3 photo-toolkit/scripts/assemble.py ~/output/graded \
    --output ~/output/timelapse.mp4 --fps 25
```
