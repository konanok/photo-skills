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
#   bash scripts/publish.sh <skill-name> --changelog "..."     显式 changelog
#   bash scripts/publish.sh <skill-name> --skip-version-check  跳过 ClawHub 查重
#   bash scripts/publish.sh <skill-name> --owner <handle>      发布到指定 owner（org/publisher）
#
# <skill-name> 必须是 4 个之一：
#   photo-toolkit / photo-screener / photo-grader / openclaw-photo-agents-creator
#
# 注意：clawhub skill publish 当前 CLI（v0.17.x）不支持 --dry-run。
# 如需预演，建议先在私有/测试 owner 下跑一次，或人工 review SKILL.md / VERSION 后再发。
#
# 退出码：
#   0  发布成功
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
CHANGELOG_OVERRIDE=""
SKIP_VERSION_CHECK=false
OWNER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
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
    --owner)
        OWNER="$2"
        shift 2
        ;;
    --owner=*)
        OWNER="${1#*=}"
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
    # 用 --json 拿版本历史，结构化判断
    inspect_json="$(clawhub inspect "$SKILL" --versions --json 2>&1 || true)"
    # 失败/未发布 → 通常 stderr 含 "not found" / "404"
    if echo "$inspect_json" | grep -qiE "(not found|404|no such|does not exist)"; then
        info "skill '$SKILL' is not yet on ClawHub (first publish)"
    elif command -v python3 >/dev/null 2>&1 &&
        echo "$inspect_json" | python3 -c "import json,sys; d=json.load(sys.stdin); sys.exit(1 if any(v.get('version','')=='$VERSION' for v in (d.get('versions') or d if isinstance(d,list) else [])) else 0)" 2>/dev/null; then
        ok "version $VERSION not yet published"
    elif echo "$inspect_json" | grep -qE '"version"[[:space:]]*:[[:space:]]*"'"${VERSION//./\\.}"'"'; then
        err "version $VERSION already exists on ClawHub for $SKILL"
        echo "    bump the version in $SKILL/SKILL.md, then re-run." >&2
        exit 1
    else
        # 兜底：能拿到 inspect 输出且未匹配到目标版本 → 视为可发
        if [[ -n "$inspect_json" ]]; then
            ok "version $VERSION not detected in existing releases"
        else
            warn "could not query ClawHub; proceeding cautiously"
        fi
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
        # 提取 [VERSION] 段，到下一个 [x.y.z] 为止
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
# NOTE: --changelog uses the "--flag=value" form because commander.js (the
# parser used by clawhub CLI) splits multiline values starting with "-" into
# what looks like new flags when the value is passed as a separate argument.
# The "=" form binds the entire value to --changelog unambiguously.
PUBLISH_ARGS=(skill publish "./$SKILL" --slug "$SKILL" --version "$VERSION" "--changelog=$CHANGELOG")
if [[ -n "$OWNER" ]]; then
    PUBLISH_ARGS+=(--owner "$OWNER")
fi

echo "+ clawhub ${PUBLISH_ARGS[*]}"
if ! command -v clawhub >/dev/null 2>&1; then
    err "clawhub CLI not found"
    exit 2
fi
clawhub "${PUBLISH_ARGS[@]}"

echo
ok "published $SKILL@$VERSION to ClawHub"
