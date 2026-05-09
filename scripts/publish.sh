#!/usr/bin/env bash
# publish.sh — 一键发布单个 skill 到 ClawHub
#
# 流程：
#   1. 跑 sync_versions.sh --check 确保版本一致
#   2. 从 SKILL.md frontmatter 读 version
#   3. 检查 ClawHub 上该版本是否已发过（避免重发失败）
#   4. 从 CHANGELOG.md 提取该版本对应的 release notes（除非显式传 --changelog）
#   5. 调用 clawhub skill publish
#
# 用法：
#   bash scripts/publish.sh <skill-name>                       发布
#   bash scripts/publish.sh <skill-name> --dry-run             干跑
#   bash scripts/publish.sh <skill-name> --changelog "..."     显式 changelog
#   bash scripts/publish.sh <skill-name> --skip-version-check  跳过 ClawHub 查重
#
# <skill-name> 必须是 4 个之一：
#   photo-toolkit / photo-screener / photo-grader / openclaw-photo-agents-creator
#
# 退出码：
#   0  发布成功 / dry-run 通过
#   1  版本一致性失败 / 版本已存在于 ClawHub
#   2  参数错误 / 文件缺失 / clawhub CLI 未安装

set -euo pipefail

# -------- 颜色 --------
if [[ -t 1 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    C_RED=$'\033[0;31m'
    C_GREEN=$'\033[0;32m'
    C_YELLOW=$'\033[0;33m'
    C_CYAN=$'\033[0;36m'
    C_BOLD=$'\033[1m'
    C_OFF=$'\033[0m'
else
    C_RED='' C_GREEN='' C_YELLOW='' C_CYAN='' C_BOLD='' C_OFF=''
fi

err() { echo "${C_RED}error:${C_OFF} $*" >&2; }
warn() { echo "${C_YELLOW}warn:${C_OFF} $*" >&2; }
info() { echo "${C_CYAN}→${C_OFF} $*"; }
ok() { echo "${C_GREEN}✓${C_OFF} $*"; }

# -------- 路径 --------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

KNOWN_SKILLS=(
    "photo-toolkit"
    "photo-screener"
    "photo-grader"
    "openclaw-photo-agents-creator"
)

# -------- 参数解析 --------
SKILL=""
DRY_RUN=false
CHANGELOG_OVERRIDE=""
SKIP_VERSION_CHECK=false

while [[ $# -gt 0 ]]; do
    case "$1" in
    --dry-run)
        DRY_RUN=true
        shift
        ;;
    --changelog)
        CHANGELOG_OVERRIDE="$2"
        shift 2
        ;;
    --changelog=*)
        CHANGELOG_OVERRIDE="${1#*=}"
        shift
        ;;
    --skip-version-check)
        SKIP_VERSION_CHECK=true
        shift
        ;;
    -h | --help)
        sed -n '2,21p' "$0" | sed 's/^# \?//'
        exit 0
        ;;
    -*)
        err "unknown flag: $1"
        exit 2
        ;;
    *)
        if [[ -n "$SKILL" ]]; then
            err "only one skill name allowed"
            exit 2
        fi
        SKILL="${1%/}"
        shift
        ;;
    esac
done

if [[ -z "$SKILL" ]]; then
    err "skill name required. known skills: ${KNOWN_SKILLS[*]}"
    exit 2
fi

# 校验 skill 在白名单
known=false
for s in "${KNOWN_SKILLS[@]}"; do
    [[ "$s" == "$SKILL" ]] && known=true && break
done
if ! $known; then
    err "unknown skill: $SKILL (known: ${KNOWN_SKILLS[*]})"
    exit 2
fi

SKILL_DIR="$REPO_ROOT/$SKILL"
SKILL_MD="$SKILL_DIR/SKILL.md"
VER_FILE="$SKILL_DIR/VERSION"

# -------- Step 1: 一致性校验 --------
echo "${C_BOLD}[1/5]${C_OFF} verifying version consistency..."
if ! bash "$SCRIPT_DIR/sync_versions.sh" --check "$SKILL" >/dev/null 2>&1; then
    err "version sync check failed for $SKILL"
    echo
    bash "$SCRIPT_DIR/sync_versions.sh" --check "$SKILL" || true
    echo
    err "fix the inconsistency before publishing (run: bash scripts/sync_versions.sh)"
    exit 1
fi
ok "SKILL.md and VERSION are in sync"

# -------- Step 2: 读取版本号 --------
echo
echo "${C_BOLD}[2/5]${C_OFF} reading version..."
VERSION="$(awk '
    BEGIN { in_fm=0; fm_count=0 }
    /^---[[:space:]]*$/ {
        fm_count++
        if (fm_count == 1) { in_fm=1; next }
        if (fm_count == 2) { exit }
        next
    }
    in_fm && /^version:[[:space:]]*/ {
        sub(/^version:[[:space:]]*/, "")
        gsub(/^["'\'']|["'\'']$/, "")
        sub(/[[:space:]]+#.*$/, "")
        sub(/[[:space:]]+$/, "")
        print
        exit
    }
' "$SKILL_MD")"

if [[ -z "$VERSION" ]]; then
    err "could not read version from $SKILL_MD"
    exit 2
fi

# semver 校验（宽松版）
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]; then
    err "version '$VERSION' is not valid semver"
    exit 2
fi
ok "version: ${C_BOLD}$VERSION${C_OFF}"

# -------- Step 3: ClawHub 版本查重 --------
echo
echo "${C_BOLD}[3/5]${C_OFF} checking ClawHub for existing version..."
if $SKIP_VERSION_CHECK; then
    warn "skipped (--skip-version-check)"
elif ! command -v clawhub >/dev/null 2>&1; then
    err "clawhub CLI not found. install: npm i -g clawhub"
    exit 2
else
    # 尝试拿已发布的版本列表。clawhub inspect 输出格式不固定，宽松匹配。
    # owner 由 clawhub login 决定，slug = 文件夹名
    inspect_output="$(clawhub inspect "$SKILL" --versions 2>&1 || true)"
    if echo "$inspect_output" | grep -qE "(not found|404|no such)"; then
        info "skill '$SKILL' is not yet on ClawHub (first publish)"
    elif echo "$inspect_output" | grep -qE "(^|[^0-9])${VERSION//./\\.}([^0-9]|$)"; then
        err "version $VERSION already exists on ClawHub for $SKILL"
        echo "    bump the version in $SKILL/SKILL.md (and run: bash scripts/sync_versions.sh)" >&2
        exit 1
    else
        ok "version $VERSION not yet published"
    fi
fi

# -------- Step 4: 准备 changelog --------
echo
echo "${C_BOLD}[4/5]${C_OFF} preparing changelog..."
if [[ -n "$CHANGELOG_OVERRIDE" ]]; then
    CHANGELOG="$CHANGELOG_OVERRIDE"
    ok "using --changelog override"
else
    CHANGELOG_FILE="$REPO_ROOT/CHANGELOG.md"
    if [[ ! -f "$CHANGELOG_FILE" ]]; then
        warn "$CHANGELOG_FILE not found"
        CHANGELOG="Release $VERSION"
    else
        # 提取 [VERSION] ... 直到下一个 [x.y.z] 或文件末
        # 然后只保留该 skill 相关的子段（按 ### <skill> 分组）；如果没有 skill 子段，用整段
        full_section="$(awk -v ver="$VERSION" '
            /^## *\['"$VERSION"'\]/ { found=1; next }
            found && /^## *\[/ { exit }
            found { print }
        ' "$CHANGELOG_FILE")"

        if [[ -z "$full_section" ]]; then
            warn "no entry for [$VERSION] in CHANGELOG.md"
            CHANGELOG="Release $VERSION"
        else
            # 尝试取 ### <skill> 子段
            skill_section="$(echo "$full_section" | awk -v skill="$SKILL" '
                tolower($0) ~ "^### *" tolower(skill) "([^a-z0-9-]|$)" { found=1; next }
                found && /^### / { exit }
                found { print }
            ')"
            if [[ -n "$(echo "$skill_section" | tr -d '[:space:]')" ]]; then
                CHANGELOG="$(echo "$skill_section" | sed -e '/./,$!d' | awk 'NF{p=1} p')"
                info "extracted skill-specific section from CHANGELOG.md"
            else
                CHANGELOG="$(echo "$full_section" | sed -e '/./,$!d' | awk 'NF{p=1} p')"
                info "extracted full [$VERSION] section from CHANGELOG.md"
            fi
        fi
    fi
fi

echo "----- changelog -----"
echo "$CHANGELOG"
echo "---------------------"

# -------- Step 5: 发布 --------
echo
echo "${C_BOLD}[5/5]${C_OFF} publishing..."
PUBLISH_ARGS=(skill publish "./$SKILL" --version "$VERSION" --changelog "$CHANGELOG")
if $DRY_RUN; then
    PUBLISH_ARGS+=(--dry-run)
    info "DRY RUN — no actual publish"
fi

echo "+ clawhub ${PUBLISH_ARGS[*]}"
if ! command -v clawhub >/dev/null 2>&1; then
    err "clawhub CLI not found"
    exit 2
fi
clawhub "${PUBLISH_ARGS[@]}"

echo
if $DRY_RUN; then
    ok "dry-run complete for $SKILL@$VERSION"
else
    ok "published $SKILL@$VERSION to ClawHub"
fi
