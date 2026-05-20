#!/usr/bin/env python3
"""
publish.py — 一键发布单个 skill 到 ClawHub

⚠️ 安全开关（重要）：
  本脚本默认运行在 **dry-run 模式**。最后一步的 `clawhub skill publish` 调用
  被显式禁用，只打印将要执行的 argv，不会真正触达 ClawHub。

  要真正发布需满足两条：
    1. 显式传 --no-dry-run 标志
    2. 进程的 stdin + stderr 必须都是 TTY（人在真实终端前敲命令）
       — 这是防止 AI 工具调用 / CI / 子 shell 偷偷触发的物理拦阻

  CI 场景例外：在 workflow yaml 里显式设置
  CLAWHUB_PUBLISH_I_ACCEPT_IRREVERSIBILITY=1 可绕过 TTY 校验。这个 env var
  名字故意冗长，是为了让它在 workflow 文件里成为审计可见的决策痕迹，
  而不是悄悄存在某台开发机上。

  这套设计是因为：
    1. clawhub CLI 没有原生 --dry-run（只有 clawhub sync 有）
    2. 历史上有过两次"调试时误发布"事件——两次都是 AI 在工具调用里
       追加 --no-dry-run 触发。TTY 校验把这个攻击面物理关死。

流程：
  1. 跑 sync_versions.sh --check 确保版本一致 + changelog 段就位
  2. 从 SKILL.md frontmatter 读 version
  3. 校验 <skill>/CHANGELOG.md 中存在 ## [VERSION] 段（最后一道防线）
  4. 检查 ClawHub 上该版本是否已发过（避免重发失败）
  5. 提取该版本对应的 release notes（除非显式传 --changelog）
  6. 调用 clawhub skill publish（默认 dry-run；--no-dry-run 才真发）

用法：
  python3 scripts/publish.py <skill-name>                         dry-run（默认）
  python3 scripts/publish.py <skill-name> --no-dry-run            真发布（需显式开关）
  python3 scripts/publish.py <skill-name> --changelog "..."       显式 changelog
  python3 scripts/publish.py <skill-name> --skip-version-check    跳过 ClawHub 查重
  python3 scripts/publish.py <skill-name> --owner <handle>        发布到指定 owner

<skill-name> 必须是 4 个之一：
  photo-toolkit / photo-screener / photo-grader / openclaw-photo-agents-creator

实现注意：
  - subprocess 用 argv list 形式调用 clawhub（不经过 shell）
  - 显式传 --workdir <repo-root> + 绝对 path，避免 clawhub 的 workdir 解析
    在装了 OpenClaw 的机器上 fallback 到 OpenClaw default workspace
    （会让 ./photo-toolkit 解析到错误目录，报 "Path must be a folder"）

退出码：
  0  发布成功（或 dry-run 通过）
  1  版本一致性失败 / changelog 段缺失 / 版本已存在于 ClawHub
  2  参数错误 / 文件缺失 / clawhub CLI 未安装
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ---------- 颜色 ----------
_USE_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
if _USE_COLOR:
    C_RED = "\033[0;31m"
    C_GREEN = "\033[0;32m"
    C_YELLOW = "\033[0;33m"
    C_CYAN = "\033[0;36m"
    C_BOLD = "\033[1m"
    C_OFF = "\033[0m"
else:
    C_RED = C_GREEN = C_YELLOW = C_CYAN = C_BOLD = C_OFF = ""


def err(msg: str) -> None:
    print(f"{C_RED}error:{C_OFF} {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"{C_YELLOW}warn:{C_OFF} {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"{C_CYAN}→{C_OFF} {msg}")


def ok(msg: str) -> None:
    print(f"{C_GREEN}✓{C_OFF} {msg}")


# ---------- 路径 ----------
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

KNOWN_SKILLS = (
    "photo-toolkit",
    "photo-screener",
    "photo-grader",
    "openclaw-photo-agents-creator",
)

# ---------- semver ----------
SEMVER_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Publish a photo-skills skill to ClawHub.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("skill", choices=KNOWN_SKILLS, help="skill name")
    p.add_argument("--changelog", default=None, help="override changelog text")
    p.add_argument(
        "--skip-version-check",
        action="store_true",
        help="skip ClawHub version-already-published lookup",
    )
    p.add_argument("--owner", default=None, help="publish under specific owner")
    p.add_argument(
        "--no-dry-run",
        action="store_true",
        help=(
            "ACTUALLY publish to ClawHub. Without this flag the script runs in "
            "dry-run mode and only prints what it would do. This flag is the "
            "'red button' — never auto-add it; it should only be set when a "
            "human operator is actively releasing."
        ),
    )
    return p.parse_args()


# ---------- frontmatter version 解析 ----------
def read_skill_version(skill_md: Path) -> str:
    """从 SKILL.md frontmatter 提取顶层 `version:` 字段。"""
    text = skill_md.read_text(encoding="utf-8")
    in_fm = False
    fm_count = 0
    for line in text.splitlines():
        stripped = line.rstrip()
        if re.match(r"^---\s*$", stripped):
            fm_count += 1
            if fm_count == 1:
                in_fm = True
                continue
            if fm_count == 2:
                break
            continue
        if in_fm:
            m = re.match(r"^version:\s*(.+?)\s*(?:#.*)?$", line)
            if m:
                v = m.group(1).strip()
                # 去掉首尾引号
                v = re.sub(r'^["\']|["\']$', "", v)
                return v.strip()
    return ""


# ---------- changelog 段抽取 ----------
def extract_changelog_section(changelog_md: Path, version: str) -> str:
    """从 <skill>/CHANGELOG.md 提取 `## [VERSION]` 段（到下一个 `## [` 或文件末尾）。

    返回纯文本（首尾空白已 trim）。如果段不存在或为空，返回空串。
    """
    if not changelog_md.is_file():
        return ""
    text = changelog_md.read_text(encoding="utf-8")
    # 匹配 "## [VERSION]" 行（允许 # 后多个空格、行尾日期等）
    header_re = re.compile(rf"^##\s*\[{re.escape(version)}\][^\n]*$", re.MULTILINE)
    m = header_re.search(text)
    if not m:
        return ""
    start = m.end()
    # 找下一个 "## [...]" 头作为终止
    next_re = re.compile(r"^##\s*\[", re.MULTILINE)
    n = next_re.search(text, pos=start)
    end = n.start() if n else len(text)
    section = text[start:end].strip("\n")
    return section.strip()


# ---------- ClawHub 查重 ----------
def clawhub_inspect_versions(skill: str) -> list[str] | None:
    """查询 ClawHub 上该 skill 的已发版本号列表。

    返回：
      - list[str]：能查到时的版本列表（可能为空 list）
      - None：skill 在 ClawHub 上不存在（首次发布）
    异常：
      - 其它错误透传 RuntimeError
    """
    try:
        result = subprocess.run(
            ["clawhub", "inspect", skill, "--versions", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError("clawhub CLI not found") from e

    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    if re.search(r"(not found|404|no such|does not exist)", combined, re.I):
        return None

    if result.returncode != 0:
        # 拿不到结构化结果但又不是 not-found，谨慎放行（warn）
        raise RuntimeError(f"clawhub inspect failed (exit {result.returncode}): {combined.strip()}")

    # 解析 JSON
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"clawhub inspect returned non-JSON: {e}") from e

    # 兼容两种结构：{"versions": [{"version": "1.0.0"}, ...]} 或顶层 list
    if isinstance(data, dict):
        versions = data.get("versions") or []
    elif isinstance(data, list):
        versions = data
    else:
        versions = []

    out: list[str] = []
    for v in versions:
        if isinstance(v, dict) and "version" in v:
            out.append(str(v["version"]))
        elif isinstance(v, str):
            out.append(v)
    return out


def main() -> int:
    args = parse_args()
    skill: str = args.skill
    skill_dir = REPO_ROOT / skill
    skill_md = skill_dir / "SKILL.md"
    changelog_md = skill_dir / "CHANGELOG.md"

    os.chdir(REPO_ROOT)

    # ---------- Step 1: 一致性校验 ----------
    print(f"{C_BOLD}[1/6]{C_OFF} verifying version consistency...")
    sync_script = SCRIPT_DIR / "sync_versions.sh"
    sync_proc = subprocess.run(
        ["bash", str(sync_script), "--check", skill],
        capture_output=True,
        text=True,
    )
    if sync_proc.returncode != 0:
        err(f"version sync check failed for {skill}")
        # 把脚本输出回放给用户
        sys.stderr.write(sync_proc.stdout)
        sys.stderr.write(sync_proc.stderr)
        err("fix the inconsistency before publishing (run: bash scripts/sync_versions.sh)")
        return 1
    ok("SKILL.md and VERSION are in sync")

    # ---------- Step 2: 读 version ----------
    print()
    print(f"{C_BOLD}[2/6]{C_OFF} reading version...")
    if not skill_md.is_file():
        err(f"{skill_md} not found")
        return 2
    version = read_skill_version(skill_md)
    if not version:
        err(f"could not read version from {skill_md}")
        return 2
    if not SEMVER_RE.match(version):
        err(f"version '{version}' is not valid semver")
        return 2
    ok(f"version: {C_BOLD}{version}{C_OFF}")

    # ---------- Step 3: changelog 段存在性校验（独立于 sync） ----------
    print()
    print(f"{C_BOLD}[3/6]{C_OFF} verifying changelog entry...")
    if not changelog_md.is_file():
        err(f"{skill}/CHANGELOG.md not found")
        err(f"create one with a [{version}] section before publishing")
        return 1
    section = extract_changelog_section(changelog_md, version)
    if not section:
        err(f"no `## [{version}]` section found in {skill}/CHANGELOG.md")
        err("add a release note section before publishing.")
        return 1
    ok(f"[{version}] section exists in {skill}/CHANGELOG.md")

    # ---------- Step 4: ClawHub 查重 ----------
    print()
    print(f"{C_BOLD}[4/6]{C_OFF} checking ClawHub for existing version...")
    if args.skip_version_check:
        warn("skipped (--skip-version-check)")
    else:
        if shutil.which("clawhub") is None:
            err("clawhub CLI not found. install: npm i -g clawhub")
            return 2
        try:
            existing = clawhub_inspect_versions(skill)
        except RuntimeError as e:
            warn(f"could not query ClawHub ({e}); proceeding cautiously")
            existing = []  # 兜底放行
        if existing is None:
            info(f"skill '{skill}' is not yet on ClawHub (first publish)")
        elif version in existing:
            err(f"version {version} already exists on ClawHub for {skill}")
            print(
                f"    bump the version in {skill}/SKILL.md, then re-run.",
                file=sys.stderr,
            )
            return 1
        else:
            ok(f"version {version} not yet published")

    # ---------- Step 5: 准备 changelog ----------
    print()
    print(f"{C_BOLD}[5/6]{C_OFF} preparing changelog...")
    if args.changelog:
        changelog = args.changelog
        ok("using --changelog override")
    else:
        # Step 3 已确认 section 非空
        changelog = section
        info(f"extracted [{version}] section from {skill}/CHANGELOG.md")

    print("----- changelog -----")
    print(changelog)
    print("---------------------")

    # ---------- Step 6: 发布 ----------
    print()
    print(f"{C_BOLD}[6/6]{C_OFF} publishing...")
    if shutil.which("clawhub") is None:
        err("clawhub CLI not found")
        return 2

    # 关键：把 path 和 workdir 都用绝对路径，不依赖 cwd 和环境状态。
    #
    # 历史背景：clawhub 的 `resolveWorkdir()` 优先级是
    #   --workdir > $CLAWHUB_WORKDIR > cwd 含 .clawhub/ marker > OpenClaw 默认 workspace > cwd
    # 当机器上装了 OpenClaw 且配置了默认 workspace（比如 photo-agents 用户）时，
    # 第 4 条会让 workdir 解析到 OpenClaw workspace 而不是仓库根，于是
    # `./photo-toolkit` 被解析到错误目录，clawhub 报 "Path must be a folder"。
    # 显式传 --workdir 和绝对 path 把这个不确定性彻底消除。
    #
    # 对没装 OpenClaw 的开发者：原来的 `./photo-toolkit` 形式靠 rule 5（fallback
    # 到 cwd）也能 work，本改动对他们等价 —— 只是把"靠 cwd"的隐式依赖换成
    # 显式传参，行为不变只会更确定。无回归风险。
    skill_abs = str(skill_dir.resolve())
    publish_argv: list[str] = [
        "clawhub",
        "--workdir",
        str(REPO_ROOT.resolve()),
        "skill",
        "publish",
        skill_abs,
        "--slug",
        skill,
        "--version",
        version,
        "--changelog",
        changelog,
    ]
    if args.owner:
        publish_argv += ["--owner", args.owner]

    # 回显将要执行的命令（仅显示用，实际执行不经过 shell）
    print("+ " + " ".join(_shell_quote(a) for a in publish_argv))

    # ⚠️ 安全开关：默认 dry-run；只有显式 --no-dry-run 才真发。
    # 这是因为 clawhub CLI 不支持原生 --dry-run，且历史上发生过两次
    # "调试时误发布"事件。脚本层硬保险：必须由人显式按下"红按钮"。
    if not args.no_dry_run:
        print()
        warn("DRY-RUN MODE — clawhub publish was NOT actually invoked.")
        warn("To actually publish: re-run with --no-dry-run (manually, never auto-added).")
        print()
        ok(f"dry-run OK for {skill}@{version}")
        return 0

    # === 真发布路径 ===
    # 抵达这里意味着调用方已显式传入 --no-dry-run。但单凭 flag 不够：
    # 历史上发生过两次"AI 在调试时自行追加 flag"事件。增加一道 TTY 物理校验——
    # AI 工具调用、CI 任务等 non-interactive 场景没有真正的终端，会被这道校验拦下。
    # CI 场景需要显式设置 CLAWHUB_PUBLISH_I_ACCEPT_IRREVERSIBILITY=1 走可审计旁路。
    is_tty = sys.stdin.isatty() and sys.stderr.isatty()
    ci_bypass = (
        os.environ.get("CLAWHUB_PUBLISH_I_ACCEPT_IRREVERSIBILITY") == "1"
    )
    if not is_tty and not ci_bypass:
        err("--no-dry-run requires an interactive TTY.")
        err(
            "this script refuses to perform an irreversible publish from a "
            "non-interactive shell (AI tool calls, sub-shells, pipes, "
            "automation scripts)."
        )
        err(
            "if you are a human running this in a real terminal and still see "
            "this error, your shell may be redirecting stdin/stderr."
        )
        err(
            "for CI workflows: set CLAWHUB_PUBLISH_I_ACCEPT_IRREVERSIBILITY=1 "
            "in the job env. this should be a deliberate, audited workflow "
            "edit, not an env var that lives on a developer machine."
        )
        return 2

    print()
    if ci_bypass and not is_tty:
        warn(
            f"--no-dry-run via CLAWHUB_PUBLISH_I_ACCEPT_IRREVERSIBILITY: "
            f"about to REALLY publish {skill}@{version} to ClawHub."
        )
    else:
        warn(f"--no-dry-run: about to REALLY publish {skill}@{version} to ClawHub.")
    warn("This is irreversible — the version slot will be permanently consumed.")
    print()

    proc = subprocess.run(publish_argv, check=False)
    if proc.returncode != 0:
        err(f"clawhub publish failed (exit {proc.returncode})")
        # 负数（信号杀死）会被 sys.exit 截断成奇怪的退出码，归一到 1
        return proc.returncode if proc.returncode > 0 else 1

    print()
    ok(f"published {skill}@{version} to ClawHub")
    return 0


def _shell_quote(s: str) -> str:
    """仅用于回显友好；实际执行不经过 shell。"""
    if not s or re.search(r"[\s\"'$`\\!*?#&|<>;()\[\]{}]", s):
        # 对单引号做转义
        return "'" + s.replace("'", "'\\''") + "'"
    return s


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        err("interrupted")
        sys.exit(130)
