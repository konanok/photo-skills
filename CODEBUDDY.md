# CODEBUDDY.md This file provides guidance to CodeBuddy when working with code in this repository.

## Overview

This is a **photo-skills** monorepo — three independent Python CLI tools forming an end-to-end photography post-processing pipeline. Each skill is self-contained with its own `config.json`, `requirements.txt`, `SKILL.md`, and `scripts/` directory.

## Architecture

### Pipeline Flow

```
RAW / JPG / HEIC files
    → convert.py   (thumbnails, with smart symlink for small files)
    → screen.py    (CLIP aesthetic scoring + dedup + scene classification)
    → [LLM generates grading_params.json]
    → grade.py     (Lightroom-style color grading with adaptive parameter mapping)
    → layout_preview.py (BEFORE|AFTER comparison or grid)
```

### Key Design Patterns

- **Config merging**: All scripts resolve config via `_SKILL_DIR = Path(__file__).resolve().parent.parent / "config.json"`, then CLI args override. Config files are gitignored; use `config.example.json` as template.
- **Extension sets**: `RAW_EXTENSIONS`, `JPG_EXTENSIONS`, `HEIC_EXTENSIONS` are defined identically in each skill (not shared as a module). HEIC support is optional via `pillow-heif` and gracefully degrades.
- **Cross-format file matching**: `grade.py`'s `find_raw_file()` uses stem-based matching with glob fallback — if grading params reference `DSC_0001.NEF` but the actual file is `.CR2` or `.JPG`, it still finds it. `layout_preview.py` uses similar suffix-stripping logic to match graded files (`DSC_0001_暖春丝滑.jpg` → `DSC_0001`) back to originals.
- **Parallel processing**: `convert.py` and `grade.py` use `ProcessPoolExecutor`; `find_by_date.py` uses `ThreadPoolExecutor` (I/O-bound). Worker count defaults to `min(cpu_count, 8)`.
- **Dependency gating**: Each script calls `check_dependencies()` at import time, failing fast with install instructions including the skill-specific `setup_deps.sh` path.
- **Per-file error isolation**: Processing functions return `(filename, success, message, elapsed)` tuples. A single file failure never aborts the batch.

### photo-converter: Thumbnails & Utilities

**Smart skip mechanism**: When `max_total_mb` is set (default: 50MB for LLM vision input budget), the converter calculates `budget / n_files` per image. JPG/HEIC files smaller than this budget are symlinked (or copied on cross-device) instead of re-encoded, avoiding pointless recompression.

**EXIF handling**: `convert.py` extracts EXIF bytes by finding `\xff\xe1` APP1 marker in the first 64KB header (simple binary search). `find_by_date.py` has a completely independent zero-dependency EXIF parser using `struct` to walk TIFF IFD entries, supporting big/little endian and Fujifilm RAF's embedded TIFF header.

**rawpy parameters**: Uses camera white balance (`use_camera_wb=True`), AHD demosaic, sRGB output. `size ≤ 2048` triggers `half_size=True` for speed. JPEG subsampling: 4:4:4 when quality ≥ 90, 4:2:0 otherwise.

### photo-grader: Color Grading Engine

The grading pipeline in `grade.py` has a two-phase parameter processing design:

1. **`map_lr_to_engine(lr_params, hist_stats)`**: Converts Lightroom-standard parameters (exposure ±2.0, contrast ±100) to engine-equivalent values using scaling factors. When `hist_stats` is provided (computed from the actual image), scaling adapts: bright images get more conservative exposure push (scale 0.10 vs 0.15), low dynamic range images get more conservative contrast (0.25 vs 0.35), etc. **Warning**: this function mutates `lr_params` in-place, but ProcessPoolExecutor's pickle serialization prevents cross-process contamination.

2. **`clamp_params(params)`**: Post-mapping safety net. Hard-clamps every numeric value to `_SAFE_RANGES` dict (e.g., exposure ±0.3, contrast -30~+40). Operates recursively on nested dicts (basic, detail, effects, color_grading, raw).

**Grading pipeline order**: exposure → white balance → highlights/shadows/whites/blacks → contrast → tone curve (CubicSpline 5-point) → HSL (8 channels) → vibrance/saturation → color grading (3-zone: shadows/midtones/highlights) → vignette → [PIL domain] sharpen (UnsharpMask) → noise reduction (Gaussian blend) → grain.

**RAW vs JPG processing**: RAW files get 16-bit processing (`output_bps=16`, divided by 65535). JPG/HEIC get 8-bit (divided by 255). Output filename: `{stem}_{safe_style}.jpg` where `safe_style` is sanitized to max 20 chars.

**Multi-format JSON input**: The `load_grading_params()` + `_normalize_flat_params()` combo accepts: (a) standard nested array `[{file, basic:{}, detail:{}, effects:{}}]`, (b) single object, (c) `{files: [...]}` wrapper, (d) flat params `{file, params: {exposure, contrast, ...}}` — auto-converting (d) to nested structure.

### photo-screener: CLIP-based Screening

Uses Apple MobileCLIP2-S0 (512-dim, ~27ms/image) via `open_clip`. Key implementation details:

- **512→768 zero-padding**: The LAION aesthetic MLP expects 768-dim (ViT-L/14), but MobileCLIP outputs 512-dim. The gap is zero-padded — an engineering tradeoff that works reasonably well.
- **Adaptive threshold**: When zero photos pass `min_score`, the threshold auto-relaxes to the median to retain top 50%.
- **Scene classification**: 14 categories with Chinese labels (人像/风景/街拍/建筑/美食/动物/夜景/微距/合影/静物/运动/婚礼/旅行/抽象). Dual-label when top-2 score gap < 0.03.
- **LLM-oriented output**: `filter_report.json` contains `batches` (grouped by scene, max 20 per batch) ready for multimodal LLM consumption.
- **Model download safety**: Non-interactive mode refuses to download; requires `--auto-download` flag. Uses `HF_ENDPOINT=hf-mirror.com` during download, then restores original env.
- **Device selection**: CUDA > MPS (Apple Silicon) > CPU.

## Commands

### Initial Setup

```bash
# Create config files from templates (required before first use)
cp photo-converter/config.example.json photo-converter/config.json
cp photo-grader/config.example.json    photo-grader/config.json
cp photo-screener/config.example.json  photo-screener/config.json
# Edit each config.json to set your input/output directories

# One-command dependency install (interactive, all three skills)
bash setup.sh

# Or check environment health without installing
bash check_env.sh
```

### photo-converter

```bash
# Convert RAW/JPG/HEIC to thumbnails
python3 photo-converter/scripts/convert.py <input_dir> <output_dir> [--size 1200] [--quality 85] [--recursive]

# Find photos by EXIF shooting date (supports: 2026-03-15, 03-15, 3月15日, today, yesterday, "3 days ago")
python3 photo-converter/scripts/find_by_date.py --date 2026-03-15 [<input_dir>]
python3 photo-converter/scripts/find_by_date.py --list-dates [<input_dir>]

# Layout preview — side-by-side BEFORE|AFTER comparison (default)
python3 photo-converter/scripts/layout_preview.py <graded_dir> --originals <raw_dir> [--params grading_params.json]
# Grid mode (宫格): 1×1 ~ 3×3 adaptive layout
python3 photo-converter/scripts/layout_preview.py <graded_dir> --grid
```

### photo-screener

```bash
# Screen photos (aesthetic scoring + dedup + scene classification)
python3 photo-screener/scripts/screen.py <thumbnails_dir> [--min-score 4.0] [--sim-threshold 0.97] [--auto-download]
# Output: filter_report.json with batches grouped by scene for LLM
```

### photo-grader

```bash
# Apply color grading from JSON params
python3 photo-grader/scripts/grade.py <grading_params.json> --raw-dir <raw_dir> --output <output_dir>
```

All scripts support `--dry-run` for preview without processing.

## System Dependencies

- **libraw**: Required by photo-converter and photo-grader for RAW decoding. `brew install libraw` (macOS) / `apt-get install libraw-dev` (Debian) / `dnf install LibRaw-devel` (RHEL).
- **Python 3.8+**: All scripts use Python 3.
- **MobileCLIP2-S0 model** (~300MB): Downloaded on-demand by photo-screener. Not pre-bundled. Aesthetic model (~3MB) auto-downloads separately.
