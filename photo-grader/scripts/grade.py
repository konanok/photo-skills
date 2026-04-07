#!/usr/bin/env python3
"""
Photo Grader — Apply Lightroom-style color grading to camera photos.

Reads a JSON parameter file (from LLM output or manual creation) and applies
professional color grading to each specified photo file, exporting high-quality JPGs.

Supported Camera RAW Formats:
    Nikon (.nef .nrw), Canon (.cr2 .cr3 .crw), Sony (.arw .srf .sr2),
    Fujifilm (.raf), Olympus (.orf), Panasonic (.rw2), Pentax (.pef),
    Samsung (.srw), Leica (.rwl .dng), Adobe (.dng), Hasselblad (.3fr .fff),
    Phase One (.iiq), Sigma (.x3f)

Dependencies:
    System: libraw (RedHat: dnf install LibRaw-devel / Debian: apt-get install libraw-dev)
    Python: pip install rawpy pillow numpy scipy

    Check & install: bash scripts/setup_deps.sh

Usage:
    python grade.py grading_params.json
    python grade.py grading_params.json --raw-dir ~/Photos/RAW --output ~/Photos/Graded
    python grade.py grading_params.json --dry-run
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed


# ── Supported extensions ───────────────────────────────────────
RAW_EXTENSIONS = {
    ".nef", ".nrw", ".cr2", ".cr3", ".crw", ".arw", ".srf", ".sr2",
    ".raf", ".orf", ".rw2", ".pef", ".srw", ".rwl", ".dng",
    ".3fr", ".fff", ".iiq", ".x3f",
}

JPG_EXTENSIONS = {".jpg", ".jpeg"}

HEIC_EXTENSIONS = {".heic", ".heif"}

# All supported input formats (RAW 走 rawpy，JPG/HEIC 走 Pillow)
SUPPORTED_EXTENSIONS = RAW_EXTENSIONS | JPG_EXTENSIONS | HEIC_EXTENSIONS

# Check HEIC support availability
_HEIC_AVAILABLE = False
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    _HEIC_AVAILABLE = True
except ImportError:
    pass


# ── Configuration ───────────────────────────────────────────────

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

_SKILL_DIR = Path(__file__).resolve().parent.parent
_ROOT_DIR = _SKILL_DIR.parent
_DEFAULT_CONFIG_PATH = (
    _SKILL_DIR / "config.toml"
    if (_SKILL_DIR / "config.toml").exists()
    else _ROOT_DIR / "config.toml"
)


def load_config(config_path=None):
    """Load configuration from config.toml."""
    path = Path(config_path or _DEFAULT_CONFIG_PATH).expanduser().resolve()
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            cfg = tomllib.load(f)
        if not isinstance(cfg, dict):
            print(f"⚠️  Config is not a valid mapping, ignoring: {path}", file=sys.stderr)
            return {}
        print(f"📄 Loaded config: {path}")
        return cfg
    except Exception as e:
        print(f"⚠️  Failed to read config ({path}): {e}", file=sys.stderr)
        return {}


# ── Dependency Check ────────────────────────────────────────────


def check_dependencies():
    """Check if required packages are installed."""
    missing = []
    for pkg, pip_name in [("rawpy", "rawpy"), ("PIL", "pillow"), ("numpy", "numpy"), ("scipy", "scipy")]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pip_name)
    if missing:
        print("❌ Missing dependencies:", file=sys.stderr)
        for pkg in missing:
            print(f"  - {pkg}", file=sys.stderr)
        print(f"\nInstall with:\n  pip3 install {' '.join(missing)}", file=sys.stderr)
        print(f"\nOr run:\n  bash {_SKILL_DIR}/scripts/setup_deps.sh", file=sys.stderr)
        sys.exit(1)


check_dependencies()

import rawpy
import numpy as np
from PIL import Image, ImageFilter, ImageOps
from scipy.interpolate import CubicSpline


# ═══════════════════════════════════════════════════════════════
# Color Grading Engine (identical to nef-color-grader)
# ═══════════════════════════════════════════════════════════════


def _clamp(arr, lo=0.0, hi=1.0):
    return np.clip(arr, lo, hi)


def _to_float(img_array):
    return img_array.astype(np.float64) / 255.0


def _to_uint8(img_float):
    return (_clamp(img_float) * 255.0 + 0.5).astype(np.uint8)


def _rgb_to_hsl(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    max_c = np.maximum(np.maximum(r, g), b)
    min_c = np.minimum(np.minimum(r, g), b)
    delta = max_c - min_c
    l = (max_c + min_c) / 2.0
    s = np.zeros_like(l)
    mask = delta > 1e-10
    low = l <= 0.5
    s[mask & low] = delta[mask & low] / (max_c[mask & low] + min_c[mask & low] + 1e-10)
    s[mask & ~low] = delta[mask & ~low] / (2.0 - max_c[mask & ~low] - min_c[mask & ~low] + 1e-10)
    h = np.zeros_like(l)
    m = mask & (max_c == r)
    h[m] = 60.0 * (((g[m] - b[m]) / (delta[m] + 1e-10)) % 6)
    m = mask & (max_c == g)
    h[m] = 60.0 * (((b[m] - r[m]) / (delta[m] + 1e-10)) + 2)
    m = mask & (max_c == b)
    h[m] = 60.0 * (((r[m] - g[m]) / (delta[m] + 1e-10)) + 4)
    h[h < 0] += 360.0
    return np.stack([h, s, l], axis=-1)


def _hsl_to_rgb(hsl):
    h, s, l = hsl[..., 0], hsl[..., 1], hsl[..., 2]
    c = (1.0 - np.abs(2.0 * l - 1.0)) * s
    h_prime = h / 60.0
    x = c * (1.0 - np.abs(h_prime % 2 - 1.0))
    m = l - c / 2.0
    r2 = np.zeros_like(h)
    g2 = np.zeros_like(h)
    b2 = np.zeros_like(h)
    for sector, (rc, gc, bc) in enumerate([
        (1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 1), (0, 0, 1), (1, 0, 0)
    ]):
        pass  # Simplified — use full implementation below

    # Full sector implementation
    mask = (h_prime >= 0) & (h_prime < 1)
    r2[mask] = c[mask] + m[mask]; g2[mask] = x[mask] + m[mask]; b2[mask] = m[mask]
    mask = (h_prime >= 1) & (h_prime < 2)
    r2[mask] = x[mask] + m[mask]; g2[mask] = c[mask] + m[mask]; b2[mask] = m[mask]
    mask = (h_prime >= 2) & (h_prime < 3)
    r2[mask] = m[mask]; g2[mask] = c[mask] + m[mask]; b2[mask] = x[mask] + m[mask]
    mask = (h_prime >= 3) & (h_prime < 4)
    r2[mask] = m[mask]; g2[mask] = x[mask] + m[mask]; b2[mask] = c[mask] + m[mask]
    mask = (h_prime >= 4) & (h_prime < 5)
    r2[mask] = x[mask] + m[mask]; g2[mask] = m[mask]; b2[mask] = c[mask] + m[mask]
    mask = (h_prime >= 5) & (h_prime < 6)
    r2[mask] = c[mask] + m[mask]; g2[mask] = m[mask]; b2[mask] = x[mask] + m[mask]
    return _clamp(np.stack([r2, g2, b2], axis=-1))


def apply_exposure(img, value):
    if abs(value) < 0.001:
        return img
    return _clamp(img * (2.0 ** value))


def apply_contrast(img, value):
    if abs(value) < 0.5:
        return img
    factor = 1.0 + value / 100.0
    return _clamp((img - 0.5) * factor + 0.5)


def apply_highlights_shadows(img, highlights, shadows, whites, blacks):
    if all(abs(v) < 0.5 for v in [highlights, shadows, whites, blacks]):
        return img
    luminance = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
    factor = np.ones_like(luminance)
    if abs(highlights) >= 0.5:
        weight = _clamp((luminance - 0.5) * 2.0)
        hl_mult = 1.0 + highlights / 100.0 * 0.45
        factor *= (1.0 - weight) + weight * hl_mult
    if abs(shadows) >= 0.5:
        weight = _clamp((0.5 - luminance) * 2.0)
        sh_mult = 1.0 + shadows / 100.0 * 0.55
        factor *= (1.0 - weight) + weight * sh_mult
    if abs(whites) >= 0.5:
        weight = _clamp((luminance - 0.75) * 4.0)
        wh_mult = 1.0 + whites / 100.0 * 0.3
        factor *= (1.0 - weight) + weight * wh_mult
    if abs(blacks) >= 0.5:
        weight = _clamp((0.25 - luminance) * 4.0)
        bk_mult = 1.0 + blacks / 100.0 * 0.35
        factor *= (1.0 - weight) + weight * bk_mult
    return _clamp(img * factor[..., np.newaxis])


def apply_temp_tint(img, temp_offset, tint_offset):
    if abs(temp_offset) < 0.5 and abs(tint_offset) < 0.5:
        return img
    result = img.copy()
    if abs(temp_offset) >= 0.5:
        t = temp_offset / 100.0
        result[..., 0] *= 1.0 + t * 0.12
        result[..., 1] *= 1.0 + t * 0.02
        result[..., 2] *= 1.0 - t * 0.12
    if abs(tint_offset) >= 0.5:
        t = tint_offset / 100.0
        result[..., 0] *= 1.0 + t * 0.05
        result[..., 1] *= 1.0 - t * 0.08
        result[..., 2] *= 1.0 + t * 0.05
    return _clamp(result)


def apply_vibrance_saturation(img, vibrance, saturation):
    if abs(vibrance) < 0.5 and abs(saturation) < 0.5:
        return img
    hsl = _rgb_to_hsl(img)
    s = hsl[..., 1]
    if abs(saturation) >= 0.5:
        s = s * (1.0 + saturation / 100.0)
    if abs(vibrance) >= 0.5:
        v_factor = vibrance / 100.0
        s = s + v_factor * (1.0 - s) * 0.5
    hsl[..., 1] = _clamp(s)
    return _hsl_to_rgb(hsl)


def apply_tone_curve(img, highlights, lights, darks, shadows):
    if all(abs(v) < 0.5 for v in [highlights, lights, darks, shadows]):
        return img
    scale = 0.3 / 100.0
    points_x = np.array([0.0, 0.25, 0.5, 0.75, 1.0])
    points_y = np.array([0.0, 0.25 + shadows * scale, 0.5 + (darks + lights) * scale * 0.5, 0.75 + highlights * scale, 1.0])
    points_y = np.clip(points_y, 0.0, 1.0)
    cs = CubicSpline(points_x, points_y, bc_type="clamped")
    luminance = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
    new_lum = _clamp(cs(luminance))
    ratio = np.where(luminance > 1e-6, new_lum / (luminance + 1e-10), 1.0)
    return _clamp(img * ratio[..., np.newaxis])


def apply_hsl(img, hsl_params):
    if not hsl_params:
        return img
    has_adj = any(abs(p.get("hue", 0)) >= 0.5 or abs(p.get("saturation", 0)) >= 0.5 or abs(p.get("luminance", 0)) >= 0.5 for p in hsl_params)
    if not has_adj:
        return img

    channel_hue_ranges = {
        "red": (0, 30), "orange": (30, 15), "yellow": (60, 15), "green": (120, 45),
        "aqua": (180, 15), "blue": (225, 30), "purple": (270, 15), "magenta": (315, 30),
    }

    hsl_img = _rgb_to_hsl(img)
    h, s, l = hsl_img[..., 0], hsl_img[..., 1], hsl_img[..., 2]

    for param in hsl_params:
        channel = param.get("channel", "").lower()
        hue_shift = param.get("hue", 0)
        sat_shift = param.get("saturation", 0)
        lum_shift = param.get("luminance", 0)
        if channel not in channel_hue_ranges:
            continue
        if abs(hue_shift) < 0.5 and abs(sat_shift) < 0.5 and abs(lum_shift) < 0.5:
            continue

        center, half_width = channel_hue_ranges[channel]
        dist = np.abs(h - center)
        dist = np.minimum(dist, 360.0 - dist)
        weight = _clamp(1.0 - dist / (half_width + 1e-6))
        weight = weight * _clamp(s * 3.0)

        if abs(hue_shift) >= 0.5:
            h = (h + hue_shift * weight) % 360.0
        if abs(sat_shift) >= 0.5:
            s = s * (1.0 + (sat_shift / 100.0) * weight)
        if abs(lum_shift) >= 0.5:
            l = l + (lum_shift / 100.0 * 0.3) * weight

    hsl_img[..., 0] = h % 360.0
    hsl_img[..., 1] = _clamp(s)
    hsl_img[..., 2] = _clamp(l)
    return _hsl_to_rgb(hsl_img)


def apply_color_grading(img, params):
    if not params:
        return img
    sh, ss = params.get("shadow_hue", 0), params.get("shadow_saturation", 0)
    mh, ms = params.get("midtone_hue", 0), params.get("midtone_saturation", 0)
    hh, hs = params.get("highlight_hue", 0), params.get("highlight_saturation", 0)
    if all(v < 0.5 for v in [ss, ms, hs]):
        return img

    luminance = 0.2126 * img[..., 0] + 0.7152 * img[..., 1] + 0.0722 * img[..., 2]
    result = img.copy()

    def _hue_to_rgb(hue_deg):
        h_rad = np.radians(hue_deg)
        return np.array([0.5 + 0.5 * np.cos(h_rad), 0.5 + 0.5 * np.cos(h_rad - 2.094), 0.5 + 0.5 * np.cos(h_rad + 2.094)])

    if ss >= 0.5:
        weight = _clamp(1.0 - luminance * 2.0)
        tint = _hue_to_rgb(sh)
        strength = ss / 100.0 * 0.15
        for c in range(3):
            result[..., c] += (tint[c] - 0.5) * weight * strength
    if ms >= 0.5:
        weight = _clamp(1.0 - np.abs(luminance - 0.5) * 2.0)
        tint = _hue_to_rgb(mh)
        strength = ms / 100.0 * 0.1
        for c in range(3):
            result[..., c] += (tint[c] - 0.5) * weight * strength
    if hs >= 0.5:
        weight = _clamp(luminance * 2.0 - 1.0)
        tint = _hue_to_rgb(hh)
        strength = hs / 100.0 * 0.15
        for c in range(3):
            result[..., c] += (tint[c] - 0.5) * weight * strength
    return _clamp(result)


def apply_sharpen(pil_img, amount, radius):
    if amount < 1:
        return pil_img
    return pil_img.filter(ImageFilter.UnsharpMask(radius=max(0.5, min(radius, 3.0)), percent=int(amount), threshold=2))


def apply_noise_reduction(pil_img, luminance_nr, detail):
    if luminance_nr < 1:
        return pil_img
    blur_radius = luminance_nr / 100.0 * 2.0
    detail_factor = detail / 100.0
    blurred = pil_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    return Image.blend(blurred, pil_img, detail_factor)


def apply_vignette(img, amount):
    if abs(amount) < 0.5:
        return img
    h, w = img.shape[:2]
    cy, cx = h / 2, w / 2
    max_dist = np.sqrt(cx**2 + cy**2)
    y, x = np.ogrid[:h, :w]
    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    dist_norm = dist / max_dist
    strength = amount / 100.0 * 0.6
    vignette = 1.0 + strength * (dist_norm**2)
    return _clamp(img * vignette[..., np.newaxis])


def apply_grain(pil_img, amount, size):
    if amount < 1:
        return pil_img
    img_arr = np.array(pil_img).astype(np.float64)
    h, w = img_arr.shape[:2]
    scale = max(1, int(size / 25))
    nh, nw = h // scale, w // scale
    noise = np.random.normal(0, 1, (nh, nw))
    if scale > 1:
        noise_img = Image.fromarray(((noise + 3) / 6 * 255).clip(0, 255).astype(np.uint8))
        noise_img = noise_img.resize((w, h), Image.Resampling.BILINEAR)
        noise = np.array(noise_img).astype(np.float64) / 255.0 * 6 - 3
    strength = amount / 100.0 * 30.0
    for c in range(3):
        img_arr[..., c] += noise[:h, :w] * strength
    return Image.fromarray(np.clip(img_arr, 0, 255).astype(np.uint8))


# ═══════════════════════════════════════════════════════════════
# Pipeline
# ═══════════════════════════════════════════════════════════════


# ── Histogram Statistics ────────────────────────────────────────


def compute_histogram_stats(img_float):
    """Compute histogram statistics from a [0,1] float image.

    Used by `map_lr_to_engine()` for adaptive parameter mapping.
    """
    luminance = 0.2126 * img_float[..., 0] + 0.7152 * img_float[..., 1] + 0.0722 * img_float[..., 2]
    return {
        "mean_luminance": float(np.mean(luminance)),
        "dynamic_range": float(np.percentile(luminance, 95) - np.percentile(luminance, 5)),
        "highlight_ratio": float(np.mean(luminance > 0.75)),
        "shadow_ratio": float(np.mean(luminance < 0.25)),
    }


# ── Lightroom → Engine Parameter Mapping ───────────────────────


def map_lr_to_engine(lr_params, hist_stats=None):
    """Map Lightroom-style parameters to engine-equivalent values.

    AI models naturally output Lightroom-style values (exposure ±2.0,
    contrast ±100, sharpen 0-150, etc.). This function converts them
    to values that produce comparable results in our engine, preserving
    the relative parameter relationships (the AI's "intent").

    Optionally uses histogram statistics for adaptive scaling.
    """
    basic = lr_params.get("basic", {})
    detail = lr_params.get("detail", {})
    effects = lr_params.get("effects", {})
    cg = lr_params.get("color_grading", {})
    tc = lr_params.get("tone_curve", {})
    hsl = lr_params.get("hsl", [])

    # ── Exposure: LR ±2.0 → engine 2^x ──
    lr_exp = basic.get("exposure", 0)
    if hist_stats and abs(lr_exp) > 0.01:
        mean_lum = hist_stats["mean_luminance"]
        if (lr_exp > 0 and mean_lum > 0.55) or (lr_exp < 0 and mean_lum < 0.35):
            exp_scale = 0.10
        else:
            exp_scale = 0.15
    else:
        exp_scale = 0.15

    # ── Contrast: LR ±100 → engine ±40 ──
    lr_contrast = basic.get("contrast", 0)
    if hist_stats and abs(lr_contrast) > 0.5:
        contrast_scale = 0.25 if hist_stats["dynamic_range"] < 0.5 and lr_contrast > 0 else 0.35
    else:
        contrast_scale = 0.35

    # ── Highlights: LR ±100 → engine ±55 ──
    lr_hl = basic.get("highlights", 0)
    if hist_stats and abs(lr_hl) > 0.5:
        hl_scale = 0.45 if hist_stats["highlight_ratio"] > 0.15 and lr_hl < 0 else 0.55
    else:
        hl_scale = 0.55

    # ── Shadows: LR ±100 → engine ±45 ──
    lr_sh = basic.get("shadows", 0)
    if hist_stats and abs(lr_sh) > 0.5:
        sh_scale = 0.35 if hist_stats["shadow_ratio"] > 0.3 and lr_sh > 0 else 0.45
    else:
        sh_scale = 0.45

    mapped_basic = {
        "exposure":    round(lr_exp * exp_scale, 3),
        "contrast":    round(lr_contrast * contrast_scale, 1),
        "highlights":  round(lr_hl * hl_scale, 1),
        "shadows":     round(lr_sh * sh_scale, 1),
        "whites":      round(basic.get("whites", 0) * 0.30, 1),
        "blacks":      round(basic.get("blacks", 0) * 0.30, 1),
        "temp_offset": round(basic.get("temp_offset", 0) * 0.20, 1),
        "tint_offset": round(basic.get("tint_offset", 0) * 0.15, 1),
        "vibrance":    round(basic.get("vibrance", 0) * 0.35, 1),
        "saturation":  round(basic.get("saturation", 0) * 0.20, 1),
    }
    lr_params["basic"] = mapped_basic

    # ── Detail ──
    if detail:
        lr_params["detail"] = {
            "sharpen_amount": round(max(0, 10 + detail.get("sharpen_amount", 0) * 0.20), 1),
            "sharpen_radius": round(min(2.5, max(0.5, detail.get("sharpen_radius", 1.0))), 1),
            "noise_reduction": round(detail.get("noise_reduction", 0) * 0.50, 1),
            "noise_detail":    round(detail.get("noise_detail", 50), 1),
        }

    # ── Effects ──
    if effects:
        lr_params["effects"] = {
            "vignette_amount": round(effects.get("vignette_amount", 0) * 0.20, 1),
            "grain_amount":    round(effects.get("grain_amount", 0) * 0.30, 1),
            "grain_size":      round(effects.get("grain_size", 25), 1),
        }

    # ── Color Grading ──
    if cg:
        mapped_cg = {}
        for key in ("shadow_hue", "midtone_hue", "highlight_hue"):
            if key in cg:
                mapped_cg[key] = cg[key]
        for key in ("shadow_saturation", "midtone_saturation", "highlight_saturation"):
            if key in cg:
                mapped_cg[key] = round(cg[key] * 0.15, 1)
        lr_params["color_grading"] = mapped_cg

    # ── Tone Curve ──
    if tc:
        lr_params["tone_curve"] = {
            "highlights": round(tc.get("highlights", 0) * 0.40, 1),
            "lights":     round(tc.get("lights", 0) * 0.40, 1),
            "darks":      round(tc.get("darks", 0) * 0.40, 1),
            "shadows":    round(tc.get("shadows", 0) * 0.40, 1),
        }

    # ── HSL ──
    if hsl:
        mapped_hsl = []
        for item in hsl:
            m = dict(item)
            m["saturation"] = round(item.get("saturation", 0) * 0.40, 1)
            m["luminance"] = round(item.get("luminance", 0) * 0.40, 1)
            mapped_hsl.append(m)
        lr_params["hsl"] = mapped_hsl

    return lr_params


# ── Parameter Safety Clamp (post-mapping safety net) ───────────
# After mapping, values should already be in safe range. This clamp
# serves as a final safety net to catch edge cases.

_SAFE_RANGES = {
    # basic
    "exposure":       (-0.3,  0.3),
    "contrast":       (-30,   40),
    "highlights":     (-60,   50),
    "shadows":        (-30,   50),
    "whites":         (-30,   30),
    "blacks":         (-30,   10),
    "temp_offset":    (-20,   20),
    "tint_offset":    (-15,   15),
    "vibrance":       (-20,   40),
    "saturation":     (-20,   20),
    # detail
    "sharpen_amount": (0,     40),
    "sharpen_radius": (0.5,   2.5),
    "noise_reduction":(0,     50),
    "noise_detail":   (20,    70),
    # effects
    "vignette_amount":(-20,   10),
    "grain_amount":   (0,     30),
    "grain_size":     (10,    80),
    # color grading saturation (per zone)
    "shadow_saturation":   (0, 15),
    "midtone_saturation":  (0, 15),
    "highlight_saturation":(0, 15),
    # raw
    "bright":         (0.5,   2.0),
}


def clamp_params(params):
    """Deep-clamp every numeric value in *params* to engine safe ranges.

    Operates in-place on nested dicts (basic, detail, effects, color_grading, raw)
    as well as flat top-level keys.  Returns *params* for chaining.
    """
    def _clamp_dict(d, prefix=""):
        if not isinstance(d, dict):
            return
        for key in list(d.keys()):
            val = d[key]
            if isinstance(val, dict):
                _clamp_dict(val, prefix=f"{prefix}{key}.")
                continue
            if key not in _SAFE_RANGES:
                continue
            lo, hi = _SAFE_RANGES[key]
            try:
                num = float(val)
            except (TypeError, ValueError):
                continue
            clamped = max(lo, min(hi, num))
            if clamped != num:
                print(f"  ⚠️  Clamped {prefix}{key}: {num} → {clamped}  (safe range {lo}~{hi})")
                d[key] = clamped

    for section in ("basic", "detail", "effects", "color_grading", "raw"):
        _clamp_dict(params.get(section, {}), prefix=f"{section}.")
    # Also clamp any flat top-level numeric keys (defensive)
    _clamp_dict(params, prefix="")
    return params


def grade_single_file(raw_path, output_dir, params, quality=95, size=None, overwrite=False, preserve_exif=True):
    """Apply color grading to a single photo file (RAW/JPG/HEIC) and export as JPG."""
    start = time.monotonic()
    raw_name = raw_path.name
    ext_lower = raw_path.suffix.lower()

    try:
        stem = raw_path.stem
        style_tag = params.get("style", "graded")
        safe_style = "".join(c if c.isalnum() or c in "-_" else "_" for c in style_tag)[:20]
        jpg_name = f"{stem}_{safe_style}.jpg"
        jpg_path = output_dir / jpg_name

        if jpg_path.exists() and not overwrite:
            elapsed = time.monotonic() - start
            return (raw_name, True, f"⏭ Skipped (exists): {jpg_name}", elapsed)

        # ── Load image data ──────────────────────────────────────
        if ext_lower in RAW_EXTENSIONS:
            # RAW Processing via rawpy (16-bit)
            raw_params = params.get("raw", {})
            use_auto_bright = raw_params.get("auto_bright", False)
            raw_bright = raw_params.get("bright", None)

            postprocess_kw = dict(
                use_camera_wb=True,
                use_auto_wb=False,
                no_auto_bright=not use_auto_bright,
                output_bps=16,
                half_size=False,
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
                output_color=rawpy.ColorSpace.sRGB,
            )
            if raw_bright is not None:
                postprocess_kw["bright"] = float(raw_bright)

            with rawpy.imread(str(raw_path)) as raw:
                rgb = raw.postprocess(**postprocess_kw)

            img = rgb.astype(np.float64) / 65535.0

        elif ext_lower in HEIC_EXTENSIONS:
            # HEIC/HEIF via pillow-heif (8-bit)
            if not _HEIC_AVAILABLE:
                elapsed = time.monotonic() - start
                return (raw_name, False, f"✗ {raw_name}: pillow-heif not installed (pip install pillow-heif)", elapsed)
            pil_src = Image.open(str(raw_path)).convert("RGB")
            img = np.array(pil_src).astype(np.float64) / 255.0

        else:
            # JPG/JPEG via Pillow (8-bit)
            pil_src = Image.open(str(raw_path)).convert("RGB")
            img = np.array(pil_src).astype(np.float64) / 255.0

        # ── Apply Grading Pipeline ──────────────────────────────
        # Step 1: Map Lightroom-style values → engine values (histogram-aware)
        hist_stats = compute_histogram_stats(img)
        map_lr_to_engine(params, hist_stats)
        # Step 2: Safety clamp as final safety net
        clamp_params(params)
        basic = params.get("basic", {})
        tc = params.get("tone_curve", {})
        hsl_params = params.get("hsl", [])
        cg = params.get("color_grading", {})
        detail = params.get("detail", {})
        effects = params.get("effects", {})

        img = apply_exposure(img, basic.get("exposure", 0))
        img = apply_temp_tint(img, basic.get("temp_offset", 0), basic.get("tint_offset", 0))
        img = apply_highlights_shadows(img, basic.get("highlights", 0), basic.get("shadows", 0), basic.get("whites", 0), basic.get("blacks", 0))
        img = apply_contrast(img, basic.get("contrast", 0))
        img = apply_tone_curve(img, tc.get("highlights", 0), tc.get("lights", 0), tc.get("darks", 0), tc.get("shadows", 0))
        img = apply_hsl(img, hsl_params)
        img = apply_vibrance_saturation(img, basic.get("vibrance", 0), basic.get("saturation", 0))
        img = apply_color_grading(img, cg)
        img = apply_vignette(img, effects.get("vignette_amount", 0))

        pil_img = Image.fromarray(_to_uint8(img))
        try:
            pil_img = ImageOps.exif_transpose(pil_img)
        except Exception:
            pass

        if size is not None:
            pil_img.thumbnail((size, size), Image.Resampling.LANCZOS)

        pil_img = apply_sharpen(pil_img, detail.get("sharpen_amount", 0), detail.get("sharpen_radius", 1.0))
        pil_img = apply_noise_reduction(pil_img, detail.get("noise_reduction", 0), detail.get("noise_detail", 50))
        pil_img = apply_grain(pil_img, effects.get("grain_amount", 0), effects.get("grain_size", 25))

        # ── EXIF ────────────────────────────────────────────────
        exif_bytes = None
        if preserve_exif:
            try:
                with open(str(raw_path), "rb") as f:
                    header = f.read(65536)
                exif_start = header.find(b"\xff\xe1")
                if exif_start != -1:
                    exif_length = int.from_bytes(header[exif_start + 2 : exif_start + 4], "big")
                    exif_bytes = header[exif_start : exif_start + 2 + exif_length]
            except Exception:
                exif_bytes = None

        save_kwargs = {"format": "JPEG", "quality": quality, "optimize": True, "subsampling": 0 if quality >= 90 else 2}
        if exif_bytes:
            save_kwargs["exif"] = exif_bytes

        pil_img.save(jpg_path, **save_kwargs)

        elapsed = time.monotonic() - start
        file_size_kb = jpg_path.stat().st_size / 1024
        return (raw_name, True, f"✓ {jpg_name} ({pil_img.width}×{pil_img.height}, {file_size_kb:.0f}KB)", elapsed)

    except Exception as e:
        elapsed = time.monotonic() - start
        return (raw_name, False, f"✗ {raw_name}: {e}", elapsed)


def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds) // 60
    secs = seconds - minutes * 60
    return f"{minutes}m {secs:.0f}s"


def get_cpu_count():
    try:
        return min(os.cpu_count() or 4, 8)
    except Exception:
        return 4


def _normalize_flat_params(entry):
    """Convert a flat params dict into the nested structure grade.py expects.

    Handles the case where the Agent writes:
        {"file": "xxx", "params": {"exposure": 0.15, "contrast": 20, ...}}
    and converts it to:
        {"file": "xxx", "basic": {"exposure": 0.15, ...}, "detail": {...}, "effects": {...}}
    """
    BASIC_KEYS = {
        "exposure", "contrast", "highlights", "shadows",
        "whites", "blacks", "temp_offset", "tint_offset",
        "vibrance", "saturation",
    }
    DETAIL_KEYS = {
        "sharpen_amount", "sharpen_radius",
        "noise_reduction", "noise_detail",
    }
    EFFECTS_KEYS = {
        "vignette_amount", "grain_amount", "grain_size",
    }
    RAW_KEYS = {"auto_bright", "bright"}

    flat = entry.get("params", {})
    if not flat:
        return entry  # Already in nested format or empty

    # Already has nested groups → nothing to do
    if any(k in entry for k in ("basic", "detail", "effects", "tone_curve", "hsl")):
        return entry

    result = {"file": entry.get("file", ""), "style": entry.get("style", "graded")}

    basic, detail, effects, raw_params = {}, {}, {}, {}
    for k, v in flat.items():
        if k in BASIC_KEYS:
            basic[k] = v
        elif k in DETAIL_KEYS:
            detail[k] = v
        elif k in EFFECTS_KEYS:
            effects[k] = v
        elif k in RAW_KEYS:
            raw_params[k] = v
        # Ignore unknown keys like "color_grading_sat" (not used by engine)

    if basic:
        result["basic"] = basic
    if detail:
        result["detail"] = detail
    if effects:
        result["effects"] = effects
    if raw_params:
        result["raw"] = raw_params

    return result


def load_grading_params(json_path):
    """Load grading parameters from JSON file.

    Supports multiple JSON formats:
      1. Standard array: [{file, basic:{}, detail:{}, effects:{}}]
      2. Single object:  {file, basic:{}, detail:{}, effects:{}}
      3. Agent flat:     {files: [{file, params: {exposure, contrast, ...}}]}
      4. Agent flat single: {file, params: {exposure, contrast, ...}}
    """
    path = Path(json_path).expanduser().resolve()
    if not path.exists():
        print(f"❌ Parameter file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        # Handle {files: [...]} wrapper format
        if "files" in data and isinstance(data["files"], list):
            entries = data["files"]
        else:
            entries = [data]
    else:
        print(f"❌ Invalid JSON format: expected object or array", file=sys.stderr)
        sys.exit(1)

    # Normalize flat params → nested structure
    return [_normalize_flat_params(e) for e in entries]


def find_raw_file(raw_dir, filename):
    """
    Find a photo file by filename, case-insensitive, trying multiple extensions.
    Supports cross-format matching: if grading_params says DSC_0001.NEF but the actual
    file is DSC_0001.CR2 or DSC_0001.JPG, it will still be found.
    """
    raw_dir = Path(raw_dir)

    # Try exact match first
    for candidate in [raw_dir / filename, raw_dir / filename.upper(), raw_dir / filename.lower()]:
        if candidate.exists():
            return candidate

    # Try stem with any supported extension
    stem = Path(filename).stem
    for ext in SUPPORTED_EXTENSIONS:
        for name in [f"{stem}{ext}", f"{stem.upper()}{ext}", f"{stem.lower()}{ext}", f"{stem}{ext.upper()}"]:
            candidate = raw_dir / name
            if candidate.exists():
                return candidate

    # Try glob
    matches = []
    for ext in SUPPORTED_EXTENSIONS:
        matches.extend(raw_dir.glob(f"{stem}*{ext}"))
        matches.extend(raw_dir.glob(f"{stem.upper()}*{ext}"))
    file_matches = [m for m in matches if m.suffix.lower() in SUPPORTED_EXTENSIONS]
    if file_matches:
        return file_matches[0]

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Apply Lightroom-style color grading to camera RAW files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Supported formats: RAW (NEF, CR2, CR3, ARW, RAF, ORF, RW2, DNG, PEF, SRW, etc.), JPG, HEIC/HEIF
Note: JPG/HEIC files will use Pillow for processing (limited compared to RAW). HEIC requires: pip install pillow-heif

Examples:
  %(prog)s grading_params.json
  %(prog)s grading_params.json --raw-dir ~/Photos/RAW --output ~/Photos/Graded
  %(prog)s grading_params.json --quality 98 --no-resize
  %(prog)s grading_params.json --dry-run
        """,
    )
    parser.add_argument("params_json", help="JSON file with grading parameters")
    parser.add_argument("--raw-dir", type=str, default=None, help="Directory containing RAW files (default: from config)")
    parser.add_argument("--output", type=str, default=None, help="Output directory for graded JPGs")
    parser.add_argument("--config", type=str, default=None, help="Path to config.json")
    parser.add_argument("--quality", type=int, default=None, help="JPEG quality 1-100 (default: 95)")
    parser.add_argument("--size", type=int, default=None, help="Max output dimension in px")
    parser.add_argument("--workers", type=int, default=None, help="Parallel workers")
    parser.add_argument("--overwrite", action="store_true", default=None, help="Overwrite existing output files")
    parser.add_argument("--no-resize", action="store_true", help="Export at full RAW resolution")
    parser.add_argument("--no-exif", action="store_true", default=None, help="Do not copy EXIF metadata")
    parser.add_argument("--dry-run", action="store_true", help="Preview without processing")

    args = parser.parse_args()

    cfg = load_config(args.config)

    raw_dir_raw = args.raw_dir or cfg.get("raw_dir") or cfg.get("nef_dir")
    output_raw = args.output or cfg.get("output_dir")
    quality = args.quality if args.quality is not None else cfg.get("jpeg_quality", 95)
    size = None if args.no_resize else (args.size if args.size is not None else cfg.get("max_size") or None)
    workers = args.workers if args.workers is not None else cfg.get("workers") or get_cpu_count()
    overwrite = args.overwrite if args.overwrite is not None else cfg.get("overwrite", False)
    preserve_exif = not args.no_exif if args.no_exif is not None else cfg.get("preserve_exif", True)

    if not raw_dir_raw:
        parser.error("--raw-dir is required. Provide it as an argument or set 'raw_dir' in config.toml")
    if not output_raw:
        parser.error("--output is required. Provide it as an argument or set 'output_dir' in config.toml")

    if not 1 <= quality <= 100:
        print("Error: --quality must be between 1 and 100", file=sys.stderr)
        sys.exit(1)

    raw_dir = Path(raw_dir_raw).expanduser().resolve()
    output_dir = Path(output_raw).expanduser().resolve()

    if not raw_dir.exists():
        print(f"❌ RAW directory not found: {raw_dir}", file=sys.stderr)
        sys.exit(1)

    all_params = load_grading_params(args.params_json)
    print(f"📋 Loaded {len(all_params)} grading parameter set(s)")

    tasks = []
    for p in all_params:
        filename = p.get("file", "")
        if not filename:
            print(f"  ⚠️  Skipping entry with no 'file' field: {p.get('style', '?')}")
            continue

        raw_path = find_raw_file(raw_dir, filename)
        if raw_path is None:
            print(f"  ⚠️  RAW file not found: {filename} (in {raw_dir})")
            continue

        tasks.append((raw_path, p))

    if not tasks:
        print("❌ No matching RAW files found for any parameter set.")
        sys.exit(1)

    print(f"\n📷 Will process {len(tasks)} file(s)")

    if args.dry_run:
        print(f"\n🔍 Dry run — files that would be graded:")
        for raw_path, p in tasks:
            print(f"  📸 {raw_path.name} [{raw_path.suffix.upper().lstrip('.')}] → style: {p.get('style', '?')}")
        sys.exit(0)

    output_dir.mkdir(parents=True, exist_ok=True)

    size_str = f"{size}px" if size else "full resolution"
    print(f"\n⚙️  Grading: quality={quality}, size={size_str}, workers={workers}")
    print(f"   RAW dir: {raw_dir}")
    print(f"   Output:  {output_dir}\n")

    total_start = time.monotonic()
    success_count = 0
    skip_count = 0
    error_count = 0
    total = len(tasks)

    if workers <= 1 or total == 1:
        for i, (raw_path, p) in enumerate(tasks, 1):
            raw_name, success, message, elapsed = grade_single_file(raw_path, output_dir, p, quality, size, overwrite, preserve_exif)
            print(f"  [{i}/{total}] {message} ({format_time(elapsed)})")
            if success:
                skip_count += 1 if "Skipped" in message else 0
                success_count += 0 if "Skipped" in message else 1
            else:
                error_count += 1
    else:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(grade_single_file, raw_path, output_dir, p, quality, size, overwrite, preserve_exif): raw_path for raw_path, p in tasks}
            done = 0
            for future in as_completed(futures):
                done += 1
                raw_name, success, message, elapsed = future.result()
                print(f"  [{done}/{total}] {message} ({format_time(elapsed)})")
                if success:
                    skip_count += 1 if "Skipped" in message else 0
                    success_count += 0 if "Skipped" in message else 1
                else:
                    error_count += 1

    total_elapsed = time.monotonic() - total_start
    print(f"\n{'─' * 55}")
    print(f"✅ Done in {format_time(total_elapsed)}")
    print(f"   Graded: {success_count}  |  Skipped: {skip_count}  |  Errors: {error_count}")
    print(f"   Output: {output_dir}")

    if error_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
