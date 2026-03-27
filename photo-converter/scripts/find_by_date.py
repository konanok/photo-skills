#!/usr/bin/env python3
"""
Photo File Finder — Find photo files by shooting date.

Read EXIF DateTimeOriginal from camera RAW/JPG/HEIC files and filter by date criteria.
Supports all major camera RAW formats (NEF, CR2, CR3, ARW, RAF, ORF, DNG, etc.)

Dependencies:
    None (pure Python EXIF parsing via struct)

    Check & install: bash scripts/setup_deps.sh

Usage:
    python find_by_date.py --date 2026-03-15
    python find_by_date.py --date 03-15
    python find_by_date.py --from 2026-03-10 --to 2026-03-15
    python find_by_date.py --date 2026-03-15 --copy-to ~/Downloads/output/session/selected
    python find_by_date.py --list-dates
"""

import argparse
import json
import os
import re
import shutil
import struct
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed


# ── Supported photo extensions ─────────────────────────────────
RAW_EXTENSIONS = {
    ".nef", ".nrw",          # Nikon
    ".cr2", ".cr3", ".crw",  # Canon
    ".arw", ".srf", ".sr2",  # Sony
    ".raf",                   # Fujifilm
    ".orf",                   # Olympus / OM System
    ".rw2",                   # Panasonic
    ".pef",                   # Pentax
    ".srw",                   # Samsung
    ".rwl",                   # Leica
    ".dng",                   # Adobe DNG
    ".3fr", ".fff",           # Hasselblad
    ".iiq",                   # Phase One
    ".x3f",                   # Sigma
}

JPG_EXTENSIONS = {".jpg", ".jpeg"}

HEIC_EXTENSIONS = {".heic", ".heif"}

# All supported input formats
SUPPORTED_EXTENSIONS = RAW_EXTENSIONS | JPG_EXTENSIONS | HEIC_EXTENSIONS


# ── Configuration ───────────────────────────────────────────────

_SKILL_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG_PATH = _SKILL_DIR / "config.json"


def load_config(config_path=None):
    """Load configuration from config.json."""
    path = Path(config_path or _DEFAULT_CONFIG_PATH).expanduser().resolve()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return cfg if isinstance(cfg, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


# ── EXIF Date Reader ────────────────────────────────────────────

def _read_uint16(data, offset, big_endian):
    fmt = ">H" if big_endian else "<H"
    return struct.unpack_from(fmt, data, offset)[0]


def _read_uint32(data, offset, big_endian):
    fmt = ">I" if big_endian else "<I"
    return struct.unpack_from(fmt, data, offset)[0]


def read_exif_date(raw_path):
    """
    Read DateTimeOriginal from a camera RAW file's EXIF data.
    Works with NEF, CR2, ARW, DNG, and other TIFF-based RAW formats.
    """
    try:
        with open(raw_path, "rb") as f:
            header = f.read(256 * 1024)

        exif_data = None
        exif_offset = 0

        # Try TIFF header directly (most RAW files: NEF, CR2, ARW, DNG, ORF, PEF, etc.)
        if header[:2] in (b"MM", b"II"):
            exif_data = header
            exif_offset = 0
        else:
            # Look for EXIF APP1 marker (0xFFE1) — JPEG-wrapped formats
            idx = header.find(b"\xff\xe1")
            if idx != -1:
                length = struct.unpack(">H", header[idx + 2:idx + 4])[0]
                if header[idx + 4:idx + 10] == b"Exif\x00\x00":
                    exif_data = header[idx + 10:idx + 2 + length]
                    exif_offset = 0

        # For Fujifilm RAF: look for TIFF header after RAF magic
        if exif_data is None and header[:15] == b"FUJIFILMCCD-RAW":
            # RAF files have TIFF-like EXIF embedded at an offset
            for search_start in range(0, min(len(header) - 2, 4096)):
                if header[search_start:search_start + 2] in (b"MM", b"II"):
                    magic_offset = search_start + 2
                    if magic_offset + 2 <= len(header):
                        try:
                            be = header[search_start:search_start + 2] == b"MM"
                            fmt = ">H" if be else "<H"
                            magic = struct.unpack_from(fmt, header, magic_offset)[0]
                            if magic == 42:
                                exif_data = header[search_start:]
                                exif_offset = 0
                                break
                        except Exception:
                            continue

        if exif_data is None:
            return None

        # Parse TIFF header
        byte_order = exif_data[exif_offset:exif_offset + 2]
        big_endian = byte_order == b"MM"
        if byte_order not in (b"MM", b"II"):
            return None

        magic = _read_uint16(exif_data, exif_offset + 2, big_endian)
        if magic != 42:
            return None

        ifd_offset = _read_uint32(exif_data, exif_offset + 4, big_endian)

        # Walk IFD0 to find ExifIFD pointer (tag 0x8769)
        exif_ifd_offset = _find_tag_in_ifd(exif_data, exif_offset, ifd_offset, 0x8769, big_endian)

        if exif_ifd_offset is not None:
            date_str = _find_string_tag_in_ifd(exif_data, exif_offset, exif_ifd_offset, 0x9003, big_endian)
            if date_str:
                return _parse_exif_datetime(date_str)
            date_str = _find_string_tag_in_ifd(exif_data, exif_offset, exif_ifd_offset, 0x9004, big_endian)
            if date_str:
                return _parse_exif_datetime(date_str)

        date_str = _find_string_tag_in_ifd(exif_data, exif_offset, ifd_offset, 0x0132, big_endian)
        if date_str:
            return _parse_exif_datetime(date_str)

        return None

    except Exception:
        return None


def _find_tag_in_ifd(data, base, ifd_offset, target_tag, big_endian):
    """Find a tag in an IFD and return its value as uint32."""
    try:
        abs_offset = base + ifd_offset
        num_entries = _read_uint16(data, abs_offset, big_endian)
        for i in range(num_entries):
            entry_offset = abs_offset + 2 + i * 12
            tag = _read_uint16(data, entry_offset, big_endian)
            if tag == target_tag:
                value = _read_uint32(data, entry_offset + 8, big_endian)
                return value
        return None
    except Exception:
        return None


def _find_string_tag_in_ifd(data, base, ifd_offset, target_tag, big_endian):
    """Find a string tag in an IFD and return its value."""
    try:
        abs_offset = base + ifd_offset
        num_entries = _read_uint16(data, abs_offset, big_endian)
        for i in range(num_entries):
            entry_offset = abs_offset + 2 + i * 12
            tag = _read_uint16(data, entry_offset, big_endian)
            if tag == target_tag:
                typ = _read_uint16(data, entry_offset + 2, big_endian)
                count = _read_uint32(data, entry_offset + 4, big_endian)
                if typ == 2:  # ASCII
                    if count <= 4:
                        str_data = data[entry_offset + 8:entry_offset + 8 + count]
                    else:
                        str_offset = _read_uint32(data, entry_offset + 8, big_endian)
                        str_data = data[base + str_offset:base + str_offset + count]
                    return str_data.rstrip(b"\x00").decode("ascii", errors="ignore")
        return None
    except Exception:
        return None


def _parse_exif_datetime(s):
    """Parse EXIF datetime string."""
    try:
        return datetime.strptime(s.strip(), "%Y:%m:%d %H:%M:%S")
    except ValueError:
        try:
            return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None


# ── File Finder ─────────────────────────────────────────────────

def find_raw_files(input_path, recursive=False):
    """Find all supported photo files (RAW/JPG/HEIC) in directory."""
    input_path = Path(input_path)
    if input_path.is_file():
        if input_path.suffix.lower() in SUPPORTED_EXTENSIONS:
            return [input_path]
        return []

    results = []
    if recursive:
        for p in sorted(input_path.rglob("*")):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                results.append(p)
    else:
        for p in sorted(input_path.iterdir()):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                results.append(p)
    return results


def get_file_dates(raw_files, workers=None):
    """Read EXIF dates from multiple RAW files in parallel."""
    max_workers = workers or min(os.cpu_count() or 4, 16)
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(read_exif_date, f): f for f in raw_files}
        for future in as_completed(futures):
            raw_path = futures[future]
            try:
                dt = future.result()
            except Exception:
                dt = None
            results.append((raw_path, dt))

    results.sort(key=lambda x: x[0].name)
    return results


# ── Date Parsing ────────────────────────────────────────────────

def parse_date_arg(date_str, reference_year=None):
    """
    Parse a flexible date string into a date object.

    Supported formats:
        2026-03-15, 2026/03/15, 03-15, 3-15, 0315,
        3月15日, 3月15, today, yesterday, "3 days ago"
    """
    if reference_year is None:
        reference_year = datetime.now().year

    s = date_str.strip()

    if s.lower() == "today":
        return date.today()
    if s.lower() == "yesterday":
        return date.today() - timedelta(days=1)

    m = re.match(r"(\d+)\s*days?\s*ago", s, re.IGNORECASE)
    if m:
        return date.today() - timedelta(days=int(m.group(1)))

    m = re.match(r"(\d{1,2})月(\d{1,2})日?$", s)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        return date(reference_year, month, day)

    m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

    m = re.match(r"(\d{1,2})[-/](\d{1,2})$", s)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        return date(reference_year, month, day)

    m = re.match(r"(\d{2})(\d{2})$", s)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            return date(reference_year, month, day)

    raise ValueError(f"无法解析日期: '{date_str}'。支持格式: 2026-03-15, 03-15, 3月15日, today, yesterday, '3 days ago'")


# ── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="按拍照日期查找相机 RAW 文件（支持 NEF/CR2/CR3/ARW/RAF/ORF/DNG 等）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --date 3月15日
  %(prog)s --date 2026-03-15
  %(prog)s --from 2026-03-10 --to 2026-03-15
  %(prog)s --date 3月15日 --copy-to ~/Downloads/output/session/selected
  %(prog)s --date 3月15日 --link-to ~/Downloads/output/session/selected
  %(prog)s --list-dates
        """,
    )

    parser.add_argument("input", nargs="?", default=None, help="RAW 文件所在目录（默认: config.json 的 input_dir 或 ~/Downloads/RAW）")
    parser.add_argument("--config", type=str, default=None, help="config.json 路径")

    date_group = parser.add_argument_group("日期过滤")
    date_group.add_argument("--date", "-d", type=str, default=None, help="精确日期")
    date_group.add_argument("--from", dest="date_from", type=str, default=None, help="起始日期（含）")
    date_group.add_argument("--to", dest="date_to", type=str, default=None, help="结束日期（含）")
    date_group.add_argument("--list-dates", action="store_true", help="列出所有 RAW 文件的拍照日期")

    action_group = parser.add_argument_group("输出操作")
    action_group.add_argument("--copy-to", type=str, default=None, help="将匹配的 RAW 文件复制到指定目录")
    action_group.add_argument("--link-to", type=str, default=None, help="将匹配的 RAW 文件创建软链接到指定目录")
    action_group.add_argument("--json", action="store_true", help="以 JSON 格式输出结果")

    parser.add_argument("--recursive", "-r", action="store_true", help="递归搜索子目录")
    parser.add_argument("--workers", type=int, default=None, help="并行工作线程数")

    args = parser.parse_args()

    if not args.date and not args.date_from and not args.date_to and not args.list_dates:
        parser.error("请指定 --date、--from/--to 或 --list-dates 之一")

    cfg = load_config(args.config)
    input_raw = args.input or cfg.get("input_dir", "~/Downloads/RAW")
    input_path = Path(input_raw).expanduser().resolve()

    if not input_path.exists():
        print(f"❌ 输入目录不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    target_date = None
    from_date = None
    to_date = None

    if args.date:
        target_date = parse_date_arg(args.date)
    if args.date_from:
        from_date = parse_date_arg(args.date_from)
    if args.date_to:
        to_date = parse_date_arg(args.date_to)

    raw_files = find_raw_files(input_path, args.recursive)
    if not raw_files:
        print("📷 未找到 RAW 文件。")
        sys.exit(0)

    # Summarize formats found
    ext_counts = {}
    for f in raw_files:
        ext = f.suffix.upper()
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    ext_summary = ", ".join(f"{ext}: {cnt}" for ext, cnt in sorted(ext_counts.items()))
    print(f"📷 扫描 {len(raw_files)} 个 RAW 文件的 EXIF 日期... ({ext_summary})", file=sys.stderr)

    start_time = time.monotonic()
    file_dates = get_file_dates(raw_files, args.workers)
    scan_elapsed = time.monotonic() - start_time

    if args.list_dates:
        _print_date_list(file_dates, args.json)
        return

    matched = []
    no_date = []

    for raw_path, dt in file_dates:
        if dt is None:
            no_date.append(raw_path)
            continue
        shot_date = dt.date()
        if target_date:
            if shot_date == target_date:
                matched.append((raw_path, dt))
        else:
            if from_date and shot_date < from_date:
                continue
            if to_date and shot_date > to_date:
                continue
            matched.append((raw_path, dt))

    if args.json:
        _print_json_result(matched, no_date, target_date, from_date, to_date, scan_elapsed)
    else:
        _print_human_result(matched, no_date, target_date, from_date, to_date, scan_elapsed, len(raw_files))

    if matched and (args.copy_to or args.link_to):
        dest_dir = Path(args.copy_to or args.link_to).expanduser().resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        action = "copy" if args.copy_to else "link"
        _perform_action(matched, dest_dir, action)

    sys.exit(0 if matched else 1)


def _print_date_list(file_dates, as_json):
    """Print all files with their shooting dates."""
    if as_json:
        items = []
        for raw_path, dt in sorted(file_dates, key=lambda x: (x[1] or datetime.min, x[0].name)):
            items.append({
                "file": raw_path.name,
                "path": str(raw_path),
                "format": raw_path.suffix.upper().lstrip("."),
                "date": dt.strftime("%Y-%m-%d") if dt else None,
                "datetime": dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None,
            })
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        by_date = {}
        no_date = []
        for raw_path, dt in file_dates:
            if dt is None:
                no_date.append(raw_path)
            else:
                key = dt.date()
                by_date.setdefault(key, []).append((raw_path, dt))

        for d in sorted(by_date.keys()):
            files = by_date[d]
            print(f"\n📅 {d.strftime('%Y-%m-%d')} ({len(files)} 张)")
            for raw_path, dt in sorted(files, key=lambda x: x[1]):
                ext = raw_path.suffix.upper().lstrip(".")
                print(f"   {dt.strftime('%H:%M:%S')}  {raw_path.name} [{ext}]")

        if no_date:
            print(f"\n⚠️  无法读取日期 ({len(no_date)} 张)")
            for p in no_date:
                print(f"   {p.name}")


def _print_json_result(matched, no_date, target_date, from_date, to_date, elapsed):
    """Print filter results as JSON."""
    result = {
        "filter": {},
        "matched_count": len(matched),
        "no_date_count": len(no_date),
        "scan_time_seconds": round(elapsed, 2),
        "matched": [],
    }
    if target_date:
        result["filter"]["date"] = target_date.isoformat()
    if from_date:
        result["filter"]["from"] = from_date.isoformat()
    if to_date:
        result["filter"]["to"] = to_date.isoformat()

    for raw_path, dt in sorted(matched, key=lambda x: x[1]):
        result["matched"].append({
            "file": raw_path.name,
            "path": str(raw_path),
            "format": raw_path.suffix.upper().lstrip("."),
            "datetime": dt.strftime("%Y-%m-%d %H:%M:%S"),
        })

    print(json.dumps(result, ensure_ascii=False, indent=2))


def _print_human_result(matched, no_date, target_date, from_date, to_date, elapsed, total):
    """Print filter results in human-readable format."""
    if target_date:
        date_desc = target_date.strftime("%Y-%m-%d")
    elif from_date and to_date:
        date_desc = f"{from_date.isoformat()} ~ {to_date.isoformat()}"
    elif from_date:
        date_desc = f"{from_date.isoformat()} 起"
    elif to_date:
        date_desc = f"至 {to_date.isoformat()}"
    else:
        date_desc = "全部"

    print(f"\n🔍 日期过滤: {date_desc}", file=sys.stderr)
    print(f"   扫描 {total} 个文件，耗时 {elapsed:.1f}s", file=sys.stderr)

    if not matched:
        print(f"\n😔 未找到匹配的照片。", file=sys.stderr)
        if no_date:
            print(f"   （{len(no_date)} 个文件无法读取 EXIF 日期）", file=sys.stderr)
        return

    print(f"\n✅ 找到 {len(matched)} 张照片：\n")
    for raw_path, dt in sorted(matched, key=lambda x: x[1]):
        ext = raw_path.suffix.upper().lstrip(".")
        print(f"  📸 {raw_path.name}    {dt.strftime('%H:%M:%S')}  [{ext}]")

    if no_date:
        print(f"\n  ⚠️  {len(no_date)} 个文件无法读取 EXIF 日期", file=sys.stderr)


def _perform_action(matched, dest_dir, action):
    """Copy or symlink matched files to destination."""
    print(f"\n{'📋 复制' if action == 'copy' else '🔗 链接'}到: {dest_dir}", file=sys.stderr)

    count = 0
    for raw_path, dt in matched:
        dest_path = dest_dir / raw_path.name
        try:
            if action == "copy":
                if not dest_path.exists():
                    shutil.copy2(str(raw_path), str(dest_path))
                    count += 1
                else:
                    print(f"  ⏭  {raw_path.name}（已存在）", file=sys.stderr)
            else:
                if dest_path.exists() or dest_path.is_symlink():
                    dest_path.unlink()
                dest_path.symlink_to(raw_path)
                count += 1
        except OSError as e:
            print(f"  ❌ {raw_path.name}: {e}", file=sys.stderr)

    print(f"  ✅ {'复制' if action == 'copy' else '链接'} {count} 个文件完成", file=sys.stderr)


if __name__ == "__main__":
    main()
