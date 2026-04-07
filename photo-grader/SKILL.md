---
name: photo-grader
description: |
  Apply Lightroom-style color grading to camera RAW files, JPG photos, and Apple HEIC/HEIF images
  using AI-generated parameters. Supports all major camera brands: Nikon (NEF), Canon (CR2/CR3),
  Sony (ARW), Fujifilm (RAF), Olympus (ORF), Panasonic (RW2), Pentax (PEF), Samsung (SRW),
  Leica (DNG), Adobe (DNG), Hasselblad (3FR), Phase One (IIQ), Sigma (X3F),
  plus standard JPEG (.jpg/.jpeg) and Apple HEIC/HEIF (.heic/.heif).
  Note: RAW files provide full 16-bit editing latitude; JPG/HEIC are 8-bit with limited range.

  Use when the user wants to:
  - Apply color grading / post-processing to camera RAW/JPG/HEIC files
  - Batch apply Lightroom-style adjustments (exposure, contrast, HSL, tone curve, etc.)
  - Process a set of photo files with AI-recommended color parameters
  - Export color-graded JPGs from RAW/JPG/HEIC files

  Triggers: User mentions color grading RAW files, applying Lightroom parameters,
  post-processing camera RAW photos, or grading photos based on AI recommendations.

  Dependencies:
    System: libraw (RedHat: dnf install LibRaw-devel / Debian: apt-get install libraw-dev)
    Python: rawpy, pillow, numpy, scipy
    Check: bash scripts/setup_deps.sh

  Workflow:
  1. Use `photo-converter` to generate thumbnails
  2. Use the prompt in `~/.openclaw/workspace-photocurator/prompts/photo_curator_prompt.md` with multimodal LLM
  3. Save LLM's JSON output as `grading_params.json`
  4. Run `grade.py` to batch-apply grading

  ⚠️ IMPORTANT: Use photo_curator_prompt.md V3 (NOT v1/v2). V3 uses Lightroom-standard params with auto-mapping.
---

# Photo Grader

Apply Lightroom-style color grading to camera RAW files, driven by JSON parameters.

## Supported Formats

All RAW formats supported by LibRaw: NEF, CR2, CR3, ARW, RAF, ORF, RW2, DNG, PEF, SRW, 3FR, IIQ, X3F, etc.
Plus: JPEG (.jpg/.jpeg) and Apple HEIC/HEIF (.heic/.heif, requires `pillow-heif`).

> **Note**: RAW files provide full 16-bit editing latitude for maximum quality. JPG/HEIC are 8-bit — grading range is more limited, exposure adjustments should be more conservative.

## Dependencies

**Declaration file:** `requirements.txt`

```bash
# Check environment (dependencies + config)
bash check_env.sh

# Install all skills' dependencies at once (recommended)
bash setup.sh

# Or install this skill only
bash photo-grader/scripts/setup_deps.sh

# Or install manually:
brew install libraw              # macOS
# apt-get install libraw-dev     # Debian/Ubuntu
# dnf install LibRaw-devel       # RedHat/CentOS/Fedora
pip3 install -r photo-grader/requirements.txt
```

## Configuration

Copy `config.example.toml` to `config.toml` and edit to set your directories. See `config.example.toml` for all available options.

## Usage

```bash
# Apply grading
python3 scripts/grade.py grading_params.json \
    --raw-dir ~/data/RAW --output ~/data/output/graded

# Full resolution
python3 scripts/grade.py grading_params.json --no-resize

# Preview
python3 scripts/grade.py grading_params.json --dry-run
```

| Option        | Description              | Default      |
| ------------- | ------------------------ | ------------ |
| `params_json` | Grading parameters JSON  | required     |
| `--raw-dir`   | RAW files directory      | from config  |
| `--output`    | Output directory         | from config  |
| `--quality`   | JPEG quality (1-100)     | 95           |
| `--size`      | Max output dimension     | full res     |
| `--workers`   | Parallel workers         | auto (max 8) |
| `--overwrite` | Overwrite existing files | off          |
| `--no-resize` | Full RAW resolution      | off          |
| `--dry-run`   | Preview only             | off          |

## Color Grading Features

- ✅ Exposure (stop-based)
- ✅ Contrast
- ✅ Highlights / Shadows / Whites / Blacks (multiplicative tone mapping)
- ✅ White Balance (multiplicative channel gains)
- ✅ Vibrance & Saturation
- ✅ Parametric Tone Curve (CubicSpline)
- ✅ HSL Per-channel Adjustments
- ✅ Three-Way Color Grading
- ✅ Sharpening (UnsharpMask)
- ✅ Noise Reduction
- ✅ Vignette
- ✅ Film Grain

## Cross-Format Support

The `find_raw_file()` function intelligently matches filenames across camera brands and formats:

- If `grading_params.json` says `DSC_0001.NEF` but the actual file is `DSC_0001.CR2`, it will still be found
- Also matches JPG and HEIC files: `IMG_0001.HEIC` or `DSC_0001.JPG`
- Stem-based matching with any supported extension

## Agent Integration

1. **Check dependencies**: `bash scripts/setup_deps.sh`
2. **Ensure thumbnails**: use `photo-converter` first
3. **Get grading params**: use `photo_curator_prompt.md` prompt with multimodal LLM
4. **Run grading**: `python3 scripts/grade.py grading_params.json --raw-dir ... --output ...`

### Script Paths

```
~/.openclaw/workspace-photographer/skills/photo-grader/scripts/grade.py
~/.openclaw/workspace-photographer/skills/photo-grader/scripts/setup_deps.sh
```

### Prompt (in sibling skill)

```
~/.openclaw/workspace-photocurator/prompts/photo_curator_prompt.md
```
