# Changelog — photo-grader

All notable changes to this skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This skill carries its own version per [strategy C in RELEASING.md](../RELEASING.md).

## [Unreleased]

## [1.0.1] - 2026-06-02

Fixes the "dark output" bug where graded JPGs came out about 1 stop darker
than expected. Root cause was two latent bugs in the RT engine integration
that masked each other:

### Fixed

- **`--auto-match` was a no-op** — `build_pp3` wrote `[Color Management] ToneCurve=false`
  when `auto_matched_curve=true`, but that PP3 key controls the DCP profile's
  embedded tone curve, not RawTherapee's Auto-Matched Camera Curve. The real
  field lives under `[Exposure]`. Now writes `[Exposure] HistogramMatching=true` +
  `CurveFromHistogramMatching=false` (the latter is required — see Ingo Weyrich's
  explanation on discuss.pixls.us, otherwise RT skips the matching step).
  Empirically verified on Nikon NEF (RT 5.10 + RT 5.12): mean luma 32.65 → 82.68
  (2.5× brighter), stddev 54.6 → 77.7 (matches in-camera JPG contrast).

- **`raw.auto_bright` was silently dropped** — `build_pp3` consumed `basic`,
  `tone_curve`, `hsl`, `color_grading`, `detail`, `effects` but never
  `params["raw"]`. Curator agents writing `"raw": {"auto_bright": true}` for
  dark scenes saw the request thrown away. Added `rt_map_raw()` which maps
  `auto_bright: true` → `[Exposure] Auto=true + Clip=0.02` (RT's auto-exposure
  algorithm) and `bright: float` → `[Exposure] Compensation` when user didn't
  already set it via `basic.exposure`.

- **Bad-schema JSON silently dropped fields** — When LLM agents wrote the
  Lightroom-shorthand `temperature: 6500` instead of `temperature_kelvin: 6500`
  (or `tint` instead of `tint_offset`), `rt_map_whitebalance` silently
  ignored the unknown key and the entire `[White Balance]` section was
  missing from the generated PP3. Now `_check_known_aliases()` hard-fails
  with `sys.exit(2)` and prints the correct field name + reason. Top-level
  legacy `{params: {...}}` still works (deprecation warn + migrate) for
  backward compatibility, but its inner fields are still checked for the
  known bad aliases. The `BASIC_KEYS` whitelist now includes
  `temperature_kelvin`, `green`, and `tint_offset` (previously missing,
  which is why these silently dropped through the migration path).

### Changed

- `SKILL.md` workflow step 2 no longer references the non-existent file
  `photo_curator_prompt.md V3`. Replaced with a self-describing pointer
  to the "Color Grading Features" section and the `rt_map_*()` functions
  in `grade.py`. The actual Curator prompt template lives in the
  `openclaw-photo-agents-creator` skill — see its `templates/`.

## [1.0.0] - 2026-05-20

Initial public release on [ClawHub](https://clawhub.ai).

### Added

- Apply Lightroom-style color grading to RAW / JPG / HEIC photos via RawTherapee CLI.
- 13 LR→RT auto-mappers covering exposure, contrast, HSL, tone curve, and effects.
- Multi-format JSON input (nested array, single object, `{files: [...]}` wrapper, flat params).
- Uniform mode (`--uniform-dir`) for timelapse / batch grading.
- Cross-format file matching by stem name (`DSC_0001.NEF` matches `DSC_0001.CR2`).
