# Changelog — photo-screener

All notable changes to this skill will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This skill carries its own version per [strategy C in RELEASING.md](../RELEASING.md).

## [Unreleased]

## [1.0.0] - 2026-05-20

Initial public release on [ClawHub](https://clawhub.ai).

### Added

- AI-powered photo pre-screening using MobileCLIP2-S0.
- Aesthetic scoring (1–10), burst-shot deduplication, 14-category scene classification.
- Outputs `filter_report.json` with batches grouped by scene for downstream LLM consumption.
- Adaptive threshold when no photos pass the configured `min_score`.
