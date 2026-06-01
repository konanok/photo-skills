# Changelog — photo-toolkit

All notable changes to this skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This skill carries its own version per [strategy C in RELEASING.md](../RELEASING.md).

## [Unreleased]

## [1.0.1] - 2026-06-02

### Added

- `find_by_date.py --mtime-fallback`: when a file's EXIF `DateTimeOriginal`
  can't be read (e.g. partial read on fuse / COS-mounted volumes), fall back
  to filesystem `mtime` instead of returning `None`. Avoids silent empty
  results on slow remote storage that previously made agents abandon
  `find_by_date.py` and reimplement date filtering by hand.
- `find_by_date.py --progress-interval N`: print "N/total processed (failures
  so far: X)" to stderr every N files during EXIF scan (default 100, set 0
  to disable). Useful when scanning thousands of files over slow storage.
- `find_by_date.py` now prints a summary at end of scan:
  `⚠ Skipped X/N file(s) (EXIF unreadable). Add --mtime-fallback to use
  filesystem mtime instead.` (or recovery stats when `--mtime-fallback` is on)

## [1.0.0] - 2026-05-20

Initial public release on [ClawHub](https://clawhub.ai).

### Added

- Convert RAW / JPG / HEIC to JPG thumbnails (`convert.py`).
- Find photos by EXIF shooting date (`find_by_date.py`), supports timelapse sequence detection.
- Generate before/after layout previews (`layout_preview.py`).
- Deflicker timelapse frames (`deflicker.py`).
- Assemble JPG frames into MP4 (`assemble.py`).
- Supports Nikon (NEF), Canon (CR2/CR3), Sony (ARW), Fujifilm (RAF), Olympus (ORF), Panasonic (RW2), Pentax (PEF), Samsung (SRW), Leica (DNG), Hasselblad (3FR), Phase One (IIQ), Sigma (X3F), plus standard JPEG and Apple HEIC/HEIF.
