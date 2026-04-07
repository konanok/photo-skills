# photo-skills

[简体中文](./README_zh-CN.md) | English

An end-to-end photography post-processing toolkit — convert, screen, and color-grade camera photos using AI.

## Features

| Skill               | What it does                                                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **photo-converter** | Convert camera RAW/JPG/HEIC to JPG thumbnails, find photos by EXIF shooting date, generate before/after layout previews              |
| **photo-screener**  | AI-powered pre-screening with MobileCLIP2-S0 — aesthetic scoring (1-10), burst-shot deduplication, 14-category scene classification  |
| **photo-grader**    | Apply Lightroom-style color grading (exposure, contrast, HSL, tone curve, color grading, sharpening, etc.) driven by JSON parameters |

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
git clone https://github.com/<your-username>/photo-skills.git
cd photo-skills

# Create config files from templates
cp photo-converter/config.example.toml photo-converter/config.toml
cp photo-grader/config.example.toml    photo-grader/config.toml
cp photo-screener/config.example.toml  photo-screener/config.toml

# Edit configs — set your input/output directories
# e.g. input_dir = "~/Photos/RAW"
```

### 2. Install dependencies

```bash
# One-command install (interactive, covers all three skills)
bash setup.sh

# Or check environment status without installing
bash check_env.sh
```

### 3. Convert photos to thumbnails

```bash
python3 photo-converter/scripts/convert.py ~/Photos/RAW ~/Photos/thumbnails \
    --size 1200 --quality 85
```

### 4. Screen & filter (optional, recommended for large batches)

```bash
python3 photo-screener/scripts/screen.py ~/Photos/thumbnails \
    --min-score 4.0 --auto-download
# Outputs filter_report.json with scores, scene tags, and LLM-ready batches
```

### 5. Color grade

```bash
# Prepare grading_params.json (via LLM or manually)
python3 photo-grader/scripts/grade.py grading_params.json \
    --raw-dir ~/Photos/RAW --output ~/Photos/graded
```

### 6. Preview results

```bash
# Side-by-side BEFORE | AFTER comparison (default)
python3 photo-converter/scripts/layout_preview.py ~/Photos/graded \
    --originals ~/Photos/RAW --params grading_params.json

# Or grid layout
python3 photo-converter/scripts/layout_preview.py ~/Photos/graded --grid
```

### 7. Timelapse workflow (optional)

```bash
# Step 0: Extract timelapse frames (auto-detect regular-interval sequences, exclude casual shots)
python3 photo-converter/scripts/find_by_date.py ~/Photos/RAW \
    --timelapse --copy-to ~/Photos/timelapse

# Step 1: Uniform grade — apply one parameter set to all frames
python3 photo-grader/scripts/grade.py grading_params.json \
    --uniform-dir ~/Photos/timelapse --output ~/Photos/graded

# Step 2: Deflicker — smooth luminance fluctuations
python3 photo-converter/scripts/deflicker.py ~/Photos/graded

# Step 3: Assemble — combine frames into MP4 video
python3 photo-converter/scripts/assemble.py ~/Photos/graded \
    --output ~/Photos/timelapse.mp4 --fps 25
```

## System Requirements

| Requirement | Details                                                                                                   |
| ----------- | --------------------------------------------------------------------------------------------------------- |
| **Python**  | 3.8+                                                                                                      |
| **libraw**  | `brew install libraw` (macOS) / `apt-get install libraw-dev` (Debian) / `dnf install LibRaw-devel` (RHEL) |
| **PyTorch** | Required by photo-screener only. CPU is sufficient for MobileCLIP2-S0                                     |
| **FFmpeg**  | Required by `assemble.py` for video encoding. `brew install ffmpeg` / `apt-get install ffmpeg`            |
| **Disk**    | ~300MB for MobileCLIP2-S0 model (downloaded on first run of screener)                                     |

## Important Notes

- **Config before use**: Copy `config.example.toml` to `config.toml` for each skill and set your directories. Config files are gitignored.
- **RAW vs JPG/HEIC grading**: RAW files provide full 16-bit editing latitude. JPG/HEIC are 8-bit — keep exposure adjustments conservative.
- **Model download**: photo-screener's MobileCLIP2-S0 (~300MB) is not bundled. It downloads on first run with user confirmation (uses `hf-mirror.com` for China acceleration). Use `--auto-download` in scripts/CI.
- **Cross-format matching**: The grader matches files by stem name — if your `grading_params.json` says `DSC_0001.NEF` but the file is `DSC_0001.CR2`, it still works.
- **All scripts support `--dry-run`** to preview operations without making changes.

## Project Structure

```
photo-skills/
├── setup.sh                    # Install all dependencies
├── check_env.sh                # Check environment health
├── .allinone-skill/            # Single-skill merge tooling
│   ├── merge.sh                # Merge / revert script
│   ├── SKILL.md                # Merged SKILL.md template
│   └── config.example.toml     # Merged config template
├── photo-converter/
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

After merging, create and edit the root config:

```bash
cp config.example.toml config.toml
# Edit config.toml — set your input/output directories
```

To revert back to three independent skills:

```bash
bash .allinone-skill/merge.sh --revert
```

## License

MIT

> **Note on HEIC/HEIF support**: The optional dependency `pillow-heif` is licensed under GPLv2. It is not installed by default and not required for core functionality. If you install it, please be aware of the GPL license terms.
