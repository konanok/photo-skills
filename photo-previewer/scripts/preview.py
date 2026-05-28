#!/usr/bin/env python3
"""photo-previewer — Local HTTP preview server for photo grading sessions.

Layout: pure scanning helpers → app context builder → HTTP request handler
(closure over the app dict) → inlined single-page frontend constant
(``INDEX_HTML``) → ``main()`` CLI entry.

Deployment note: the server binds 127.0.0.1 and is **not** intended to face
the public internet directly. Exposing it (with TLS, auth, path prefix
rewriting, etc.) is the deployment's responsibility — typically via nginx,
the OpenClaw gateway, a k8s ingress, or similar. Set ``external_url`` in
config.toml (or pass ``--external-url``) so the URL printed at startup
matches what end users see.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from typing import Literal

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # Python 3.8-3.10
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

Mode = Literal["session", "browse"]

_SKILL_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _SKILL_DIR.parent
_DEFAULT_CONFIG_PATH = (
    _SKILL_DIR / "config.toml" if (_SKILL_DIR / "config.toml").exists() else _ROOT_DIR / "config.toml"
)


def load_config(config_path: Path | str | None = None) -> dict:
    """Load configuration from a TOML file.

    Resolution order matches the convention used by other skills in this
    repo (photo-toolkit / photo-grader / photo-screener):

    1. Explicit path passed via the ``config_path`` argument or
       ``--config`` CLI flag.
    2. ``photo-previewer/config.toml`` (next to ``scripts/``).
    3. ``<repo-root>/config.toml`` (single-skill / monorepo-root mode).

    Returns an empty dict when no config is found, when the TOML is
    invalid, or when neither ``tomllib`` (3.11+) nor ``tomli`` (3.8-3.10)
    is available — the previewer is fully usable from CLI flags alone.
    """
    if tomllib is None:
        return {}
    path = Path(config_path or _DEFAULT_CONFIG_PATH).expanduser().resolve()
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"⚠️  ignoring malformed config {path}: {e}", file=sys.stderr)
        return {}
    if not isinstance(cfg, dict):
        return {}
    print(f"📄 Loaded config: {path}", file=sys.stderr)
    return cfg


def detect_mode(path: Path | str) -> Mode:
    """Decide whether ``path`` points at a single session or a project root.

    A path is treated as **session mode** when it directly contains a
    ``grading_params.json`` file. Otherwise, if any of its immediate
    sub-directories contains a ``grading_params.json``, it is treated as
    **browse mode** (a project root holding multiple sessions).

    Args:
        path: Filesystem path to inspect.

    Returns:
        ``"session"`` or ``"browse"``.

    Raises:
        FileNotFoundError: ``path`` does not exist.
        NotADirectoryError: ``path`` exists but is not a directory.
        ValueError: ``path`` is a directory but is neither a session nor a
            project root containing sessions.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"path does not exist: {p}")
    if not p.is_dir():
        raise NotADirectoryError(f"path is not a directory: {p}")
    if (p / "grading_params.json").is_file():
        return "session"
    for child in p.iterdir():
        if child.is_dir() and (child / "grading_params.json").is_file():
            return "browse"
    raise ValueError(
        f"path is neither a session (no grading_params.json) " f"nor a project root (no */grading_params.json): {p}"
    )


def match_graded_to_style(filename: str) -> tuple[str, str | None]:
    """Parse a graded JPG filename into ``(original_stem, style)``.

    Naming convention from photo-grader: ``<stem>_<style>.<ext>``. Examples:

    - ``"DSC_0001_暖春丝滑.jpg"`` → ``("DSC_0001", "暖春丝滑")``
    - ``"001_DSC_0001_暖春丝滑.jpg"`` → ``("001_DSC_0001", "暖春丝滑")``
    - ``"DSC_0001_warm_spring.jpg"`` → ``("DSC_0001_warm", "spring")``
      (rpartition once: ``style`` is the trailing segment)
    - ``"photo.jpg"`` → ``("photo", None)``

    Args:
        filename: Just the filename (or any path; only the stem is used).

    Returns:
        ``(stem, style)`` where ``style`` is ``None`` if the stem contains no
        underscore.
    """
    stem = Path(filename).stem
    if "_" not in stem:
        return (stem, None)
    head, _, tail = stem.rpartition("_")
    return (head, tail)


def grid_columns_for(n: int) -> int:
    """Desktop grid column count for ``n`` cells.

    Buckets: ``n ≤ 1 → 1``, ``≤ 4 → 2``, ``≤ 9 → 3``, otherwise ``4`` (with
    vertical scroll when the cells exceed one screen).

    Mobile uses the same Python-side computation; the small-screen
    "max 3 columns" cap is enforced purely in CSS via a media query
    against the ``--cols-desktop`` custom property, so there is no
    separate ``grid_columns_for_mobile`` function.
    """
    if n <= 1:
        return 1
    if n <= 4:
        return 2
    if n <= 9:
        return 3
    return 4


def build_session_manifest(session_dir: Path | str) -> dict:
    """Scan a single session directory and produce a manifest dict.

    The manifest groups cells by ``style`` and reports per-cell whether the
    graded JPG is on disk. It does **not** verify thumbnail availability —
    that is checked lazily when the HTTP layer serves ``/img/.../original``.

    ``grading_params.json`` is the source of truth for which cells exist:
    extra JPG files in ``graded/`` that do not correspond to any params
    entry are silently ignored (they will not be exposed via the HTTP
    routes either).

    Limitation: cell discovery uses ``rpartition('_')`` once on graded
    filenames, so style names containing underscores combined with stems
    lacking underscores (e.g. params stem ``IMG`` with style
    ``warm_spring`` and graded file ``IMG_warm_spring.jpg``) may
    misattribute the trailing segment as the style and miss the match.
    Encode style names without underscores to avoid this.

    Returns:
        ``{"session_id": str, "styles": [str, ...],
           "cells_by_style": {style: [{"stem", "graded_filename",
           "graded_missing", "original_path"}, ...]}}``

    Raises:
        FileNotFoundError: ``grading_params.json`` is missing in
            ``session_dir``.
        ValueError: ``graded/`` directory is missing or empty.
    """
    session_path = Path(session_dir)
    params_file = session_path / "grading_params.json"
    if not params_file.is_file():
        raise FileNotFoundError(f"grading_params.json not found in {session_path}")
    graded_dir = session_path / "graded"
    if not graded_dir.is_dir() or not any(graded_dir.iterdir()):
        raise ValueError(f"graded/ directory missing or empty in {session_path}")

    with open(params_file, "r", encoding="utf-8") as f:
        params = json.load(f)
    if isinstance(params, dict):
        params = [params]

    # Index actual graded files by (stem, style). Both keys are exactly what
    # match_graded_to_style returns from the on-disk filenames.
    actual: dict[tuple[str, str | None], str] = {}
    for p in graded_dir.iterdir():
        if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg"):
            stem, style = match_graded_to_style(p.name)
            actual[(stem, style)] = p.name

    cells_by_style: dict[str, list[dict]] = {}
    for item in params:
        file_ref = item.get("file", "")
        style = item.get("style", "")
        if not style:
            continue
        stem = Path(file_ref).stem
        graded_filename = actual.get((stem, style))
        # Subdirectory-prefix variant: photo-grader may have written
        # "001_DSC_0001_<style>.jpg" while params reference "DSC_0001.NEF".
        # Fall back to suffix-matching the actual stems.
        if graded_filename is None:
            for (a_stem, a_style), a_name in actual.items():
                if a_style == style and a_stem.endswith("_" + stem):
                    graded_filename = a_name
                    break
        cells_by_style.setdefault(style, []).append(
            {
                "stem": stem,
                "graded_filename": graded_filename or f"{stem}_{style}.jpg",
                "graded_missing": graded_filename is None,
                "original_path": file_ref,
            }
        )

    return {
        "session_id": session_path.name,
        "styles": list(cells_by_style.keys()),
        "cells_by_style": cells_by_style,
    }


def discover_sessions(project_dir: Path | str) -> list[dict]:
    """List session sub-directories of ``project_dir`` (browse mode).

    A sub-directory qualifies as a session iff it contains
    ``grading_params.json``. Results are sorted by ``session_id`` in
    lexicographic descending order — for the convention
    ``YYYYMMDD-HHMMSS`` this is equivalent to newest-first chronological
    order.

    Returns:
        ``[{"session_id": str, "path": Path}, ...]``. Empty list when
        ``project_dir`` does not exist, is not a directory, or has no session
        sub-directories.
    """
    p = Path(project_dir)
    if not p.is_dir():
        return []
    found: list[dict] = []
    for child in p.iterdir():
        if child.is_dir() and (child / "grading_params.json").is_file():
            found.append({"session_id": child.name, "path": child})
    found.sort(key=lambda s: s["session_id"], reverse=True)
    return found


# ── App context / HTTP server ───────────────────────────────────────


# Inlined frontend (HTML + CSS + JS). Single-file so the server has zero
# external resources. Phase 3 builds this up incrementally:
#   3.1 — HTML/CSS skeleton (this task): topbar, mode indicator, style-tab
#         container, grid container, mobile viewport meta, base styling.
#   3.2 — JS behaviour: manifest fetch, tab/grid render, graded↔original
#         toggle, keyboard.
#   3.3 — Mobile gestures: swipe to switch style, fullscreen <dialog>.
INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>photo-previewer</title>
<style>
  :root {
    --bg: #111;
    --fg: #eee;
    --muted: #888;
    --accent: #4af;
    --gap: 4px;
  }
  * {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
    touch-action: manipulation;
  }
  html, body {
    background: var(--bg);
    color: var(--fg);
    height: 100%;
    overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "PingFang SC", "Helvetica Neue", sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  body {
    display: flex;
    flex-direction: column;
  }
  #topbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 12px;
    border-bottom: 1px solid #333;
    flex: 0 0 auto;
  }
  #mode-indicator {
    font-size: 12px;
    color: var(--muted);
    letter-spacing: 1px;
    flex: 0 0 auto;
    user-select: none;
  }
  #mode-indicator.original {
    color: var(--accent);
  }
  #style-tabs {
    display: flex;
    gap: 8px;
    flex: 1;
    overflow-x: auto;
    overflow-y: hidden;
    scrollbar-width: thin;
  }
  .tab {
    padding: 4px 10px;
    border: 1px solid #333;
    border-radius: 4px;
    cursor: pointer;
    white-space: nowrap;
    color: var(--fg);
    user-select: none;
  }
  .tab.active {
    border-color: var(--accent);
    color: var(--accent);
  }
  #grid {
    flex: 1;
    display: grid;
    gap: var(--gap);
    padding: var(--gap);
    overflow: auto;
    grid-template-columns: 1fr;
  }
  .cell {
    background: #000;
    aspect-ratio: 3 / 2;
    overflow: hidden;
    position: relative;
  }
  .cell img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }
  .cell.missing::after {
    content: attr(data-missing);
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #666;
    font-size: 12px;
    padding: 8px;
    text-align: center;
    white-space: pre-line;
  }
  /* On narrow screens (phone portrait), cap at 3 columns to keep cells
     usable. This means 9 photos still render as a 3×3 grid (朋友圈 style)
     and ≥10 photos scroll vertically in 3 columns rather than shrinking
     to 4 columns of fingertip-sized thumbnails. Larger viewports use the
     full desktop bucketing 1/2/2x2/3x3/4xN. */
  @media (max-width: 600px) {
    #grid {
      grid-template-columns: repeat(min(3, var(--cols-desktop, 3)), 1fr) !important;
    }
  }
  /* Fullscreen single-image dialog (Phase 3.3) */
  #fs-dialog {
    border: 0;
    padding: 0;
    margin: 0;
    width: 100vw;
    height: 100vh;
    max-width: 100vw;
    max-height: 100vh;
    background: #000;
  }
  #fs-dialog::backdrop {
    background: #000;
  }
  #fs-img {
    width: 100%;
    height: 100%;
    object-fit: contain;
    display: block;
    touch-action: pinch-zoom;
  }
</style>
</head>
<body>
  <div id="topbar">
    <div id="mode-indicator">MODE: GRADED</div>
    <div id="style-tabs"></div>
  </div>
  <div id="grid"></div>
  <dialog id="fs-dialog"><img id="fs-img" alt=""></dialog>
  <script>
  (() => {
    'use strict';

    const state = {
      mode: 'session',          // 'session' | 'browse'
      sessionManifest: null,    // populated in session view
      currentStyle: null,
      imgMode: 'graded',        // 'graded' | 'original'
    };

    const $grid = document.getElementById('grid');
    const $tabs = document.getElementById('style-tabs');
    const $mode = document.getElementById('mode-indicator');

    function gridColsDesktop(n) {
      if (n <= 1) return 1;
      if (n <= 4) return 2;
      if (n <= 9) return 3;
      return 4;
    }

    function imgUrl(cell, mode) {
      const sid = state.sessionManifest.session_id;
      if (mode === 'graded') {
        return `/img/${encodeURIComponent(sid)}` +
               `/graded/${encodeURIComponent(state.currentStyle)}` +
               `/${encodeURIComponent(cell.stem)}`;
      }
      return `/img/${encodeURIComponent(sid)}` +
             `/original/${encodeURIComponent(cell.stem)}`;
    }

    function updateModeIndicator() {
      $mode.textContent = `MODE: ${state.imgMode.toUpperCase()}`;
      $mode.classList.toggle('original', state.imgMode === 'original');
    }

    function renderTabs() {
      $tabs.innerHTML = '';
      const styles = state.sessionManifest.styles || [];
      for (const style of styles) {
        const cells = state.sessionManifest.cells_by_style[style] || [];
        const tab = document.createElement('div');
        tab.className = 'tab' + (style === state.currentStyle ? ' active' : '');
        tab.textContent = `${style} (${cells.length})`;
        tab.addEventListener('click', (e) => {
          e.stopPropagation();
          if (state.currentStyle === style) return;
          state.currentStyle = style;
          state.imgMode = 'graded';
          renderTabs();
          renderGrid();
          preloadAll();
        });
        $tabs.appendChild(tab);
      }
    }

    function renderGrid() {
      const cells = state.sessionManifest.cells_by_style[state.currentStyle] || [];
      const colsDesktop = gridColsDesktop(cells.length);
      $grid.style.gridTemplateColumns = `repeat(${colsDesktop}, 1fr)`;
      // Mobile media query reads --cols-desktop and caps at 3 columns.
      $grid.style.setProperty('--cols-desktop', String(colsDesktop));
      $grid.innerHTML = '';
      for (const cell of cells) {
        const div = document.createElement('div');
        div.className = 'cell';
        if (state.imgMode === 'graded' && cell.graded_missing) {
          div.classList.add('missing');
          div.dataset.missing = `(graded missing)\n${cell.stem}`;
        } else {
          const img = document.createElement('img');
          img.src = imgUrl(cell, state.imgMode);
          img.alt = cell.stem;
          img.addEventListener('error', () => {
            div.classList.add('missing');
            div.dataset.missing = state.imgMode === 'original'
              ? `(thumbnail missing — run convert.py first)\n${cell.stem}`
              : `(graded load failed)\n${cell.stem}`;
            if (img.parentNode) img.remove();
          });
          div.appendChild(img);
        }
        $grid.appendChild(div);
      }
      updateModeIndicator();
    }

    function preloadAll() {
      const cells = state.sessionManifest.cells_by_style[state.currentStyle] || [];
      for (const cell of cells) {
        for (const m of ['graded', 'original']) {
          if (m === 'graded' && cell.graded_missing) continue;
          const img = new Image();
          img.src = imgUrl(cell, m);
        }
      }
    }

    function toggleMode() {
      state.imgMode = state.imgMode === 'graded' ? 'original' : 'graded';
      renderGrid();
    }

    function initSessionView(manifest) {
      state.sessionManifest = manifest;
      state.currentStyle = (manifest.styles && manifest.styles[0]) || null;
      state.imgMode = 'graded';
      renderTabs();
      renderGrid();
      preloadAll();
    }

    function initBrowseList(sessions) {
      $grid.style.gridTemplateColumns = '1fr';
      $grid.innerHTML = '';
      $tabs.innerHTML = '';
      $mode.textContent = 'BROWSE';
      $mode.classList.remove('original');
      for (const s of sessions) {
        const a = document.createElement('a');
        a.href = '#';
        a.textContent = s.session_id;
        a.style.cssText =
          'display:block;padding:12px;color:var(--fg);text-decoration:none;' +
          'border-bottom:1px solid #222;';
        a.addEventListener('click', (e) => {
          e.preventDefault();
          loadSession(s.session_id);
        });
        $grid.appendChild(a);
      }
    }

    async function loadSession(sid) {
      const resp = await fetch('/api/manifest/' + encodeURIComponent(sid));
      if (!resp.ok) {
        alert('session not available: ' + sid);
        return;
      }
      const manifest = await resp.json();
      if (manifest.broken) {
        alert('session broken: ' + (manifest.error || 'unknown error'));
        return;
      }
      state.mode = 'session';
      initSessionView(manifest);
    }

    async function loadManifest() {
      const resp = await fetch('/api/manifest');
      const data = await resp.json();
      state.mode = data.mode;
      if (data.mode === 'session') {
        if (data.session && !data.session.broken) {
          initSessionView(data.session);
        } else {
          $grid.textContent = 'session unavailable';
        }
      } else {
        initBrowseList(data.sessions || []);
      }
    }

    // Whole-grid click toggles graded↔original (only meaningful in session view).
    $grid.addEventListener('click', () => {
      if (state.suppressNextClick) {
        state.suppressNextClick = false;
        return;
      }
      if (state.mode === 'session' && state.sessionManifest) toggleMode();
    });

    // Keyboard shortcuts: space toggles, ←/→ switches style, 1-9 jumps style.
    window.addEventListener('keydown', (e) => {
      if (state.mode !== 'session' || !state.sessionManifest) return;
      const styles = state.sessionManifest.styles || [];
      const idx = styles.indexOf(state.currentStyle);
      if (e.key === ' ') {
        e.preventDefault();
        toggleMode();
        return;
      }
      if (e.key === 'ArrowRight' && idx >= 0 && idx < styles.length - 1) {
        state.currentStyle = styles[idx + 1];
        state.imgMode = 'graded';
        renderTabs(); renderGrid(); preloadAll();
        return;
      }
      if (e.key === 'ArrowLeft' && idx > 0) {
        state.currentStyle = styles[idx - 1];
        state.imgMode = 'graded';
        renderTabs(); renderGrid(); preloadAll();
        return;
      }
      if (/^[1-9]$/.test(e.key)) {
        const target = parseInt(e.key, 10) - 1;
        if (target < styles.length) {
          state.currentStyle = styles[target];
          state.imgMode = 'graded';
          renderTabs(); renderGrid(); preloadAll();
        }
      }
    });

    // ── Mobile gestures: swipe to switch style ─────────────────────
    let touchStartX = 0;
    let touchStartY = 0;
    let touchStartT = 0;
    $grid.addEventListener('touchstart', (e) => {
      if (e.touches.length !== 1) return;
      touchStartX = e.touches[0].clientX;
      touchStartY = e.touches[0].clientY;
      touchStartT = Date.now();
    }, { passive: true });
    $grid.addEventListener('touchend', (e) => {
      if (state.mode !== 'session' || !state.sessionManifest) return;
      if (e.changedTouches.length !== 1) return;
      const dx = e.changedTouches[0].clientX - touchStartX;
      const dy = e.changedTouches[0].clientY - touchStartY;
      const dt = Date.now() - touchStartT;
      // Horizontal swipe: |dx| > 50px AND |dx| > 1.5*|dy| AND duration < 600ms.
      // Vertical motion is left to the browser (page scrolling).
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.5 && dt < 600) {
        const styles = state.sessionManifest.styles || [];
        const idx = styles.indexOf(state.currentStyle);
        if (dx < 0 && idx >= 0 && idx < styles.length - 1) {
          state.currentStyle = styles[idx + 1];
          state.imgMode = 'graded';
          renderTabs(); renderGrid(); preloadAll();
          // Suppress the synthetic click that follows touchend so the swipe
          // doesn't also toggle graded↔original.
          state.suppressNextClick = true;
        } else if (dx > 0 && idx > 0) {
          state.currentStyle = styles[idx - 1];
          state.imgMode = 'graded';
          renderTabs(); renderGrid(); preloadAll();
          state.suppressNextClick = true;
        }
      }
    });

    // ── Fullscreen single-image dialog ─────────────────────────────
    const $dlg = document.getElementById('fs-dialog');
    const $fsImg = document.getElementById('fs-img');
    let fsCell = null;
    let fsMode = 'graded';

    function openFullscreen(cell) {
      if (cell.graded_missing && state.imgMode === 'graded') return;
      fsCell = cell;
      fsMode = state.imgMode;
      $fsImg.src = imgUrl(cell, fsMode);
      $fsImg.alt = cell.stem;
      $dlg.showModal();
    }

    // Single click inside the fullscreen image toggles graded↔original
    // (just for that one image; the grid behind keeps its own state).
    $dlg.addEventListener('click', (e) => {
      // Click on backdrop (outside the image) → close.
      if (e.target === $dlg) {
        $dlg.close();
        return;
      }
      if (!fsCell) return;
      fsMode = fsMode === 'graded' ? 'original' : 'graded';
      if (fsMode === 'graded' && fsCell.graded_missing) {
        fsMode = 'original';
      }
      $fsImg.src = imgUrl(fsCell, fsMode);
    });

    // Double-click on the dialog (or its image) exits fullscreen.
    $dlg.addEventListener('dblclick', () => $dlg.close());

    // Double-click on a grid cell enters fullscreen for that cell.
    $grid.addEventListener('dblclick', (e) => {
      if (state.mode !== 'session' || !state.sessionManifest) return;
      const cellEl = e.target.closest('.cell');
      if (!cellEl) return;
      const idx = Array.from($grid.children).indexOf(cellEl);
      const cells = state.sessionManifest.cells_by_style[state.currentStyle] || [];
      if (idx >= 0 && idx < cells.length) {
        e.stopPropagation();
        // The first of the two clicks that compose this dblclick already
        // toggled graded↔original; revert it before opening fullscreen so
        // the user-perceived sequence is "double-click stays neutral".
        state.imgMode = state.imgMode === 'graded' ? 'original' : 'graded';
        renderGrid();
        openFullscreen(cells[idx]);
      }
    });

    loadManifest();
  })();
  </script>
</body>
</html>
"""


def build_app(path: Path | str, mode: Mode) -> dict:
    """Build the in-memory app context (``INDEX``) once at startup.

    For ``mode == "session"``: eagerly scan the manifest and cache it under
    a single ``sessions`` entry keyed by the session directory name.

    For ``mode == "browse"``: list session subdirectories cheaply (only
    reading directory entries — no per-session manifest scan yet);
    per-session manifests are populated on first HTTP access via
    :func:`_ensure_session_scanned`.

    Returns:
        ``{"mode", "root", "default_session_id", "sessions": {sid: {"path",
        "manifest"}}}`` where ``manifest`` is ``None`` until lazily filled.
    """
    p = Path(path)
    if mode == "session":
        manifest = build_session_manifest(p)
        sid = manifest["session_id"]
        return {
            "mode": "session",
            "root": p,
            "default_session_id": sid,
            "sessions": {sid: {"path": p, "manifest": manifest}},
        }
    sessions: dict[str, dict] = {}
    for s in discover_sessions(p):
        sessions[s["session_id"]] = {"path": s["path"], "manifest": None}
    return {
        "mode": "browse",
        "root": p,
        "default_session_id": None,
        "sessions": sessions,
    }


def _ensure_session_scanned(app: dict, session_id: str) -> dict | None:
    """Lazy-scan and cache a session's manifest. Thread-safe.

    Returns the manifest dict, or ``None`` when ``session_id`` is unknown to
    this app. Sessions whose manifest fails to build (e.g. empty graded/)
    are cached as ``{"error": <msg>, "broken": True}`` so the broken state
    is sticky and the failing scan is not retried on every request.
    """
    entry = app["sessions"].get(session_id)
    if entry is None:
        return None
    if entry.get("manifest") is not None:
        return entry["manifest"]
    lock = entry.setdefault("_lock", Lock())
    with lock:
        if entry["manifest"] is None:
            try:
                entry["manifest"] = build_session_manifest(entry["path"])
            except (FileNotFoundError, ValueError) as e:
                entry["manifest"] = {"error": str(e), "broken": True}
    return entry["manifest"]


def _find_thumbnail(session_path: Path, stem: str) -> Path | None:
    """Locate the thumbnail JPG for ``stem`` referenced by this session.

    The session's ``grading_params.json`` carries each cell's original path
    (typically a RAW absolute path). photo-toolkit's ``convert.py`` defaults
    to writing thumbnails into ``<raw_root>/thumbnails/``, so we look there.

    Security note: this function trusts the contents of ``grading_params.json``
    and will read whatever path the ``file`` field points at (parented to a
    ``thumbnails/`` sibling directory). This is acceptable because
    photo-previewer is a **local-only single-user tool** bound to 127.0.0.1,
    with grading_params.json produced by the user's own photo-grader run.
    Do not reuse this helper in a multi-tenant / network-exposed context
    without adding path-jail validation against an allow-listed root.

    Returns the thumbnail path if it exists on disk, else ``None``.
    """
    params_file = session_path / "grading_params.json"
    if not params_file.is_file():
        return None
    try:
        with open(params_file, "r", encoding="utf-8") as f:
            params = json.load(f)
        if isinstance(params, dict):
            params = [params]
        for item in params:
            file_ref = item.get("file", "")
            if not file_ref:
                continue
            if Path(file_ref).stem == stem:
                raw_path = Path(file_ref)
                thumbs_dir = raw_path.parent / "thumbnails"
                for ext in (".jpg", ".jpeg"):
                    candidate = thumbs_dir / (stem + ext)
                    if candidate.is_file():
                        return candidate
                return None
    except (json.JSONDecodeError, OSError):
        pass
    return None


def make_handler(app: dict):
    """Return a ``BaseHTTPRequestHandler`` subclass closed over ``app``.

    Routes:

    - ``GET /`` and ``GET /index.html`` → inlined frontend HTML
    - ``GET /api/manifest`` → mode + (session: full manifest of default session;
      browse: list of {session_id})
    - ``GET /api/manifest/<sid>`` → full manifest for ``sid``; lazy-scans on
      first hit. 404 if ``sid`` unknown to this app.
    - ``GET /img/<sid>/graded/<style>/<stem>`` → graded JPG bytes; 404 if
      session is broken or the cell is missing.
    - ``GET /img/<sid>/original/<stem>`` → thumbnail JPG bytes; 404 if no
      thumbnail is found at the conventional location.
    """

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args):  # noqa: A003 — stdlib name
            print(
                f"[preview] {self.address_string()} {fmt % args}",
                file=sys.stderr,
            )

        # ── tiny response helpers ──────────────────────────────────
        def _json(self, status: int, body: dict):
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _html(self, status: int, html: str):
            data = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _serve_file(self, path: Path, content_type: str):
            try:
                data = path.read_bytes()
            except OSError as e:
                self._json(500, {"error": str(e)})
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)

        # ── routing ─────────────────────────────────────────────────
        def do_GET(self):  # noqa: N802 — stdlib name
            parsed = urllib.parse.urlparse(self.path)
            p = parsed.path

            # Frontend HTML
            if p in ("/", "/index.html"):
                self._html(200, INDEX_HTML)
                return

            # Top-level manifest
            if p == "/api/manifest":
                if app["mode"] == "session":
                    sid = app["default_session_id"]
                    self._json(
                        200,
                        {
                            "mode": "session",
                            "default_session_id": sid,
                            "session": _ensure_session_scanned(app, sid),
                        },
                    )
                else:
                    # Browse: list sessions in newest-first order; key
                    # iteration order matches insertion order (3.7+) which
                    # was already sorted by discover_sessions.
                    self._json(
                        200,
                        {
                            "mode": "browse",
                            "sessions": [{"session_id": sid} for sid in app["sessions"].keys()],
                        },
                    )
                return

            # Per-session manifest
            m = re.match(r"^/api/manifest/([^/]+)/?$", p)
            if m:
                sid = urllib.parse.unquote(m.group(1))
                manifest = _ensure_session_scanned(app, sid)
                if manifest is None:
                    self._json(404, {"error": f"unknown session: {sid}"})
                    return
                self._json(200, manifest)
                return

            # Graded image bytes
            m = re.match(r"^/img/([^/]+)/graded/([^/]+)/([^/]+)/?$", p)
            if m:
                sid, style, stem = (urllib.parse.unquote(x) for x in m.groups())
                manifest = _ensure_session_scanned(app, sid)
                if manifest is None or manifest.get("broken"):
                    self._json(404, {"error": "session not available"})
                    return
                cells = manifest.get("cells_by_style", {}).get(style, [])
                cell = next(
                    (c for c in cells if c["stem"] == stem and not c["graded_missing"]),
                    None,
                )
                if cell is None:
                    self._json(404, {"error": "graded image not found"})
                    return
                graded_file = app["sessions"][sid]["path"] / "graded" / cell["graded_filename"]
                self._serve_file(graded_file, "image/jpeg")
                return

            # Original (thumbnail) image bytes
            m = re.match(r"^/img/([^/]+)/original/([^/]+)/?$", p)
            if m:
                sid, stem = (urllib.parse.unquote(x) for x in m.groups())
                if sid not in app["sessions"]:
                    self._json(404, {"error": "unknown session"})
                    return
                thumb = _find_thumbnail(app["sessions"][sid]["path"], stem)
                if thumb is None:
                    self._json(404, {"error": "thumbnail not found"})
                    return
                self._serve_file(thumb, "image/jpeg")
                return

            self._json(404, {"error": "not found"})

    return Handler


def start_server(app: dict, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start the HTTP server bound to 127.0.0.1 in a daemon thread.

    Returns the server (so the caller may shut it down) and the public URL.
    Tests use this for end-to-end smoke checks; the actual ``main()`` runs
    the server on the foreground thread instead so Ctrl-C exits cleanly.
    """
    handler_cls = make_handler(app)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}"
    Thread(target=server.serve_forever, daemon=True).start()
    return server, url


# ── CLI entry ───────────────────────────────────────────────────────


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments. Separated from ``main`` for testability.

    Field precedence applied in ``main``: CLI flag > config.toml > built-in
    default. ``None`` defaults here distinguish "user did not pass it" from
    "user explicitly passed 0 / empty string".
    """
    parser = argparse.ArgumentParser(
        prog="preview.py",
        description=(
            "photo-previewer: web-based preview server for photo grading "
            "sessions. Mode is auto-detected from the path: a directory "
            "containing grading_params.json is a single-session view; a "
            "directory whose subdirectories contain grading_params.json is "
            "a browse view."
        ),
    )
    parser.add_argument(
        "path",
        help="session directory or project root (mode is auto-detected)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help=(
            "Path to config.toml (default: photo-previewer/config.toml or "
            "<repo-root>/config.toml). All fields optional."
        ),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=(
            "TCP port to bind on 127.0.0.1. Default: read 'port' from "
            "config.toml, then fall back to 0 (OS auto-assign)."
        ),
    )
    parser.add_argument(
        "--external-url",
        type=str,
        default=None,
        help=(
            "User-facing URL announced at startup (e.g. behind a reverse "
            "proxy). Default: read 'external_url' from config.toml, then "
            "fall back to printing the internal http://127.0.0.1:<port>/ "
            "URL for local-dev / smoke-test scenarios."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns process exit code.

    Builds the app, starts the HTTP server on the foreground thread, prints
    the public URL to stdout (so callers can capture it line-by-line), and
    blocks until Ctrl-C. Always binds 127.0.0.1 — exposing the server to
    end users is the deployment's job.
    """
    args = parse_args(argv if argv is not None else sys.argv[1:])
    path = Path(args.path).expanduser().resolve()
    try:
        mode = detect_mode(path)
    except (FileNotFoundError, NotADirectoryError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    try:
        app = build_app(path, mode)
    except (FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    cfg = load_config(args.config)

    # Field precedence: CLI > config > built-in default.
    if args.port is not None:
        port = args.port
    else:
        port = int(cfg.get("port", 0) or 0)

    handler_cls = make_handler(app)
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    except OSError as e:
        print(f"error: cannot bind 127.0.0.1:{port}: {e}", file=sys.stderr)
        if port != 0:
            print(
                "hint: set port=0 in config.toml or pass --port 0 to let " "the OS pick a free port",
                file=sys.stderr,
            )
        return 2

    actual_port = server.server_address[1]
    internal_url = f"http://127.0.0.1:{actual_port}"

    # Resolve user-facing URL for the startup banner.
    if args.external_url is not None:
        external_url = args.external_url
    else:
        external_url = cfg.get("external_url", "") or ""

    public_url = external_url.strip() or internal_url
    print(f"Preview ready: {public_url}", flush=True)
    n_sessions = len(app["sessions"])
    print(
        f"mode={mode} sessions={n_sessions} path={path} " f"bind=127.0.0.1:{actual_port}",
        file=sys.stderr,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down…", file=sys.stderr)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
