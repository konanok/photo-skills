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
    ▼  photo-converter/scripts/convert.py
    │  Generate JPG thumbnails for preview
    │
    ▼  photo-screener/scripts/screen.py        (optional, for large batches)
    │  AI scoring + dedup + scene classification
    │  → filter_report.json
    │
    ▼  [LLM generates grading_params.json]
    │
    ▼  photo-grader/scripts/grade.py
    │  Batch Lightroom-style color grading
    │
    ▼  photo-converter/scripts/layout_preview.py
       Before/After comparison or grid preview
```

## Skills

### photo-converter

Convert camera photos to JPG thumbnails, find photos by EXIF date, generate layout previews.

| Script              | Purpose                                                                          |
| ------------------- | -------------------------------------------------------------------------------- |
| `convert.py`        | RAW/JPG/HEIC → JPG thumbnails (parallel, configurable size/quality)              |
| `find_by_date.py`   | Find photos by EXIF shooting date (supports `3月15日`, `yesterday`, date ranges) |
| `layout_preview.py` | Side-by-side BEFORE\|AFTER comparison (default) or grid layout                   |

```bash
python3 photo-converter/scripts/convert.py <input> <output> [--size 1200] [--quality 85]
python3 photo-converter/scripts/find_by_date.py --date 2026-03-15
python3 photo-converter/scripts/layout_preview.py <graded_dir> --originals <raw_dir>
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

Apply Lightroom-style color grading driven by JSON parameters.

Grading features: exposure, contrast, highlights/shadows/whites/blacks, white balance,
vibrance/saturation, parametric tone curve, HSL per-channel, three-way color grading,
sharpening, noise reduction, vignette, film grain.

```bash
python3 photo-grader/scripts/grade.py <grading_params.json> --raw-dir <raw_dir> --output <output_dir>
```

Key behaviors:

- Accepts Lightroom-style parameter values — auto-maps to engine-safe values via histogram-aware scaling
- Cross-format file matching: params say `DSC_0001.NEF`, actual file is `.CR2` → still works
- RAW files: full 16-bit editing latitude. JPG/HEIC: 8-bit, keep adjustments conservative.

## Setup

**Prefer venv**: Before running scripts, activate the project-root virtual environment (e.g. `.venv/`). If it doesn't exist, create one first:

```bash
# 1. Create config files
cp photo-converter/config.example.toml photo-converter/config.toml
cp photo-grader/config.example.toml    photo-grader/config.toml
cp photo-screener/config.example.toml  photo-screener/config.toml
# Edit each config.toml to set your input/output directories

# 2. Create venv and install dependencies (recommended)
python3 -m venv .venv
source .venv/bin/activate
pip install -r photo-converter/requirements.txt -r photo-grader/requirements.txt -r photo-screener/requirements.txt

# Or use the all-in-one setup script
bash setup.sh

# 3. Verify environment
bash check_env.sh

# Before each session, activate venv
source .venv/bin/activate
```

### System Requirements

- Python 3.8+
- libraw — `brew install libraw` (macOS) / `apt-get install libraw-dev` (Debian)
- PyTorch — screener only, CPU sufficient

### Config Files

Each skill reads defaults from its `config.toml`. CLI arguments always override config values.

| Skill           | Key config fields                                                          |
| --------------- | -------------------------------------------------------------------------- |
| photo-converter | `input_dir`, `output_dir`, `size` (1200), `quality` (85)                   |
| photo-grader    | `raw_dir`, `output_dir`, `quality` (95)                                    |
| photo-screener  | `clip_model`, `min_score` (4.0), `sim_threshold` (0.97), `batch_size` (20) |

## Agent Integration

When integrating with an AI agent:

1. Run `bash check_env.sh` to verify environment
2. Use `--dry-run` on any script to preview before executing
3. For screener, use `--auto-download` to skip model download prompt
4. All scripts output structured progress to stdout, errors to stderr
5. Scripts exit with code 0 on success, 1 on error

### Typical agent workflow

```bash
# Step 1: Convert
python3 photo-converter/scripts/convert.py ~/Photos/RAW ~/output/thumbnails

# Step 2: Screen (skip if ≤ 20 photos)
python3 photo-screener/scripts/screen.py ~/output/thumbnails \
    --output ~/output/filter_report.json --auto-download

# Step 3: [Agent reads filter_report.json + thumbnails → generates grading_params.json]

# Step 4: Grade
python3 photo-grader/scripts/grade.py ~/output/grading_params.json \
    --raw-dir ~/Photos/RAW --output ~/output/graded

# Step 5: Preview
python3 photo-converter/scripts/layout_preview.py ~/output/graded \
    --originals ~/Photos/RAW --params ~/output/grading_params.json
```
