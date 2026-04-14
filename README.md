# photo-skills

[简体中文](./README_zh-CN.md) | English

An end-to-end photography post-processing toolkit — convert, screen, and color-grade camera photos using AI.

## Features

| Skill              | What it does                                                                                                                                   |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| **photo-toolkit**  | Photography utilities: RAW/JPG/HEIC → thumbnails, find photos by EXIF date, before/after layout previews, timelapse deflicker & video assembly |
| **photo-screener** | AI-powered pre-screening with MobileCLIP2-S0 — aesthetic scoring (1-10), burst-shot deduplication, 14-category scene classification            |
| **photo-grader**   | Apply professional-grade color grading via RawTherapee CLI, driven by Lightroom-style JSON parameters                                          |

### Pipeline

```
RAW / JPG / HEIC
    │
    ▼  1. convert.py — generate thumbnails
    │
    ▼  2. screen.py — aesthetic filter + dedup + scene tagging
    │
    ▼  3. [LLM generates grading_params.json]
    │
    ▼  4. grade.py — batch color grading
    │
    ▼  5. layout_preview.py — BEFORE | AFTER comparison
```

### Supported Formats

- **Camera RAW**: Nikon (NEF), Canon (CR2/CR3), Sony (ARW), Fujifilm (RAF), Olympus (ORF), Panasonic (RW2), Pentax (PEF), Samsung (SRW), Leica (DNG), Hasselblad (3FR), Phase One (IIQ), Sigma (X3F), and more
- **Standard**: JPEG (.jpg/.jpeg)
- **Apple**: HEIC/HEIF (.heic/.heif) — requires `pillow-heif`

## Getting Started

### 1. Clone & configure

```bash
git clone https://github.com/konanok/photo-skills.git
cd photo-skills

# Create config files from templates
cp photo-toolkit/config.example.toml photo-toolkit/config.toml
cp photo-grader/config.example.toml    photo-grader/config.toml
cp photo-screener/config.example.toml  photo-screener/config.toml

# Edit configs — set your input/output directories
# e.g. input_dir = "~/Photos/RAW"
```

### 2. Install dependencies

```bash
# Each skill has its own setup script (checks + installs missing deps interactively)
bash photo-toolkit/scripts/setup_deps.sh
bash photo-screener/scripts/setup_deps.sh
bash photo-grader/scripts/setup_deps.sh
```

### 3. Convert photos to thumbnails

```bash
# Default: thumbnails output to {input}/thumbnails/
python3 photo-toolkit/scripts/convert.py ~/Photos/RAW \
    --size 1200 --quality 85

# Or specify output directory explicitly
python3 photo-toolkit/scripts/convert.py ~/Photos/RAW ~/Photos/thumbnails

# Pipe from find_by_date output
python3 photo-toolkit/scripts/find_by_date.py --date today ~/Photos/RAW | \
    python3 photo-toolkit/scripts/convert.py --from-stdin
```

### 4. Screen & filter (optional, recommended for large batches)

```bash
python3 photo-screener/scripts/screen.py ~/Photos/RAW/thumbnails \
    --min-score 4.0 --auto-download
# Outputs filter_report.json with scores, scene tags, and LLM-ready batches

# Or pass specific files via --paths
python3 photo-screener/scripts/screen.py \
    --paths ~/Photos/RAW/001/thumbnails/DSC_0001.jpg ~/Photos/RAW/001/thumbnails/DSC_0002.jpg
```

### 5. Color grade

```bash
# With absolute paths in grading_params.json (--raw-dir not needed)
python3 photo-grader/scripts/grade.py grading_params.json \
    --output ~/Photos/graded

# With relative filenames in params (needs --raw-dir)
python3 photo-grader/scripts/grade.py grading_params.json \
    --raw-dir ~/Photos/RAW --output ~/Photos/graded
```

### 6. Preview results

```bash
# Side-by-side BEFORE | AFTER comparison (default)
# With absolute paths in grading_params.json (--originals not needed)
python3 photo-toolkit/scripts/layout_preview.py ~/Photos/graded \
    --params grading_params.json

# Or specify originals directory explicitly
python3 photo-toolkit/scripts/layout_preview.py ~/Photos/graded \
    --originals ~/Photos/RAW --params grading_params.json

# Or grid layout
python3 photo-toolkit/scripts/layout_preview.py ~/Photos/graded --grid
```

### 7. Timelapse workflow (optional)

```bash
# Step 0: Find timelapse frames (outputs JSON path list)
python3 photo-toolkit/scripts/find_by_date.py ~/Photos/RAW \
    --timelapse --output ~/Photos/timelapse_found.json

# Step 1: Uniform grade — apply one parameter set to all frames
python3 photo-grader/scripts/grade.py grading_params.json \
    --uniform-dir ~/Photos/timelapse --output ~/Photos/graded

# Step 2: Deflicker — smooth luminance fluctuations
python3 photo-toolkit/scripts/deflicker.py ~/Photos/graded

# Step 3: Assemble — combine frames into MP4 video
python3 photo-toolkit/scripts/assemble.py ~/Photos/graded \
    --output ~/Photos/timelapse.mp4 --fps 25
```

## System Requirements

| Requirement     | Details                                                                                                      |
| --------------- | ------------------------------------------------------------------------------------------------------------ |
| **Python**      | 3.8+                                                                                                         |
| **RawTherapee** | `brew install --cask rawtherapee` (macOS) / `apt install rawtherapee-cli` (Debian). Required by photo-grader |
| **libraw**      | `brew install libraw` (macOS) / `apt-get install libraw-dev` (Debian). Required by photo-toolkit             |
| **PyTorch**     | Required by photo-screener only. CPU is sufficient for MobileCLIP2-S0                                        |
| **FFmpeg**      | Required by `assemble.py` for video encoding. `brew install ffmpeg` / `apt-get install ffmpeg`               |
| **Disk**        | ~300MB for MobileCLIP2-S0 model (downloaded on first run of screener)                                        |

## Important Notes

- **Config before use**: Copy `config.example.toml` to `config.toml` for each skill and set your directories. Config files are gitignored.
- **Thumbnails next to RAW**: `convert.py` defaults to outputting thumbnails in `{input}/thumbnails/`, keeping them alongside your original files.
- **RAW vs JPG/HEIC grading**: RAW files provide full 16-bit editing latitude. JPG/HEIC are 8-bit — keep exposure adjustments conservative.
- **Absolute paths in params**: When `grading_params.json` uses absolute paths in the `file` field, `--raw-dir` is not needed for `grade.py`, and `--originals` is not needed for `layout_preview.py`.
- **Model download**: photo-screener's MobileCLIP2-S0 (~300MB) is not bundled. It downloads on first run with user confirmation (uses `hf-mirror.com` for China acceleration). Use `--auto-download` in scripts/CI.
- **Cross-format matching**: The grader matches files by stem name — if your `grading_params.json` says `DSC_0001.NEF` but the file is `DSC_0001.CR2`, it still works.
- **All scripts support `--dry-run`** to preview operations without making changes.

## Project Structure

```
photo-skills/
├── .allinone-skill/            # Single-skill merge tooling
│   ├── merge.sh                # Merge / revert script
│   ├── SKILL.md                # Merged SKILL.md template
│   └── config.example.toml     # Merged config template
├── photo-toolkit/
│   ├── config.example.toml
│   ├── requirements.txt
│   ├── SKILL.md
│   └── scripts/
│       ├── convert.py          # RAW/JPG/HEIC → JPG thumbnails
│       ├── find_by_date.py     # Find photos by EXIF date
│       ├── layout_preview.py   # Before/after & grid previews
│       └── setup_deps.sh
├── photo-grader/
│   ├── config.example.toml
│   ├── requirements.txt
│   ├── SKILL.md
│   └── scripts/
│       ├── grade.py            # Lightroom-style color grading
│       └── setup_deps.sh
└── photo-screener/
    ├── config.example.toml
    ├── requirements.txt
    ├── SKILL.md
    └── scripts/
        ├── screen.py           # CLIP-based screening pipeline
        └── setup_deps.sh
```

## Quickly Create OpenClaw Agents

See [openclaw-photo-agents-creator/README.md](openclaw-photo-agents-creator/README.md) for details.

## Single Skill Mode (Not Recommended)

> **Note**: This mode merges all skills into one. It is provided for platforms that only support a single skill entry point. For normal use, keep the default three-skill setup — it gives each skill its own config and SKILL.md, which is easier to manage and extend.

If you need to use this project as a single skill, run:

```bash
bash .allinone-skill/merge.sh
```

This will:

- Remove each sub-skill's `SKILL.md` (backed up to `.allinone-skill/stand-alone-skills/`)
- Create a top-level `SKILL.md` and `config.example.toml` at the project root
- All scripts will automatically read from the root `config.toml` when their sub-skill config is absent
- **Note**: `openclaw-photo-agents-creator/` is excluded from merge (it's a setup tool, not a photo skill)

After merging, create and edit the root config:

```bash
cp config.example.toml config.toml
# Edit config.toml — set your input/output directories
```

To revert back to three independent skills:

```bash
bash .allinone-skill/merge.sh --revert
```

## Quick Dev Guide

This project includes a dev container configuration for VS Code / GitHub Codespaces. Open the project and run **Dev Containers: Reopen in Container** — the container will build with Node.js, OpenClaw CLI, and Python pre-installed, no manual setup needed.

To add a new skill, create a directory with your scripts, provide `config.example.toml` and `setup_deps.sh`, then register it in `openclaw-photo-agents-creator/`.

## License

MIT

> **Note on HEIC/HEIF support**: The optional dependency `pillow-heif` is licensed under GPLv2. It is not installed by default and not required for core functionality. If you install it, please be aware of the GPL license terms.
