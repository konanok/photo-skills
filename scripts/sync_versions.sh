#!/usr/bin/env bash
# sync_versions.sh — 同步并校验各 skill 的 SKILL.md frontmatter `version` 与同目录 VERSION 文件
#
# 真理源：SKILL.md frontmatter 的 `version` 字段（与 ClawHub 官方示例对齐）。
# VERSION 文件是派生品，便于 OSS 工具/脚本静态读取（一行版本号）。
#
# 模式：
#   sync_versions.sh                  默认 sync，按 dirty 状态智能同步；冲突时拒绝
#   sync_versions.sh --check          只读校验，CI 用；任何不一致都退出 1
#   sync_versions.sh --force-from=skill     强制用 SKILL.md 覆盖 VERSION（解冲突）
#   sync_versions.sh --force-from=version   强制用 VERSION 覆盖 SKILL.md（解冲突）
#   sync_versions.sh <skill-dir>      只处理单个 skill 目录（可选）
#
# 退出码：
#   0  全部一致 / sync 成功
#   1  有不一致（check 模式）/ 有冲突需手动处理（sync 模式）
#   2  参数错误 / 文件不存在 / 解析失败

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

# -------- 路径 --------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# 默认扫描的 4 个 skill 目录
DEFAULT_SKILLS=(
    "photo-toolkit"
    "photo-screener"
    "photo-grader"
    "openclaw-photo-agents-creator"
)

# -------- 参数解析 --------
MODE="sync"
FORCE_FROM=""
TARGET_SKILL=""

for arg in "$@"; do
    case "$arg" in
    --check)
        MODE="check"
        ;;
    --force-from=skill)
        MODE="force"
        FORCE_FROM="skill"
        ;;
    --force-from=version)
        MODE="force"
        FORCE_FROM="version"
        ;;
    --force-from=*)
        echo "${C_RED}error:${C_OFF} --force-from must be 'skill' or 'version'" >&2
        exit 2
        ;;
    -h | --help)
        sed -n '2,18p' "$0" | sed 's/^# \?//'
        exit 0
        ;;
    -*)
        echo "${C_RED}error:${C_OFF} unknown flag: $arg" >&2
        exit 2
        ;;
    *)
        if [[ -n "$TARGET_SKILL" ]]; then
            echo "${C_RED}error:${C_OFF} only one skill dir allowed: $TARGET_SKILL, $arg" >&2
            exit 2
        fi
        TARGET_SKILL="$arg"
        ;;
    esac
done

# 决定要处理的 skill 列表
if [[ -n "$TARGET_SKILL" ]]; then
    # 去掉末尾斜杠
    TARGET_SKILL="${TARGET_SKILL%/}"
    SKILLS=("$TARGET_SKILL")
else
    SKILLS=("${DEFAULT_SKILLS[@]}")
fi

# -------- 工具函数 --------

# 提取 SKILL.md frontmatter 的 version 字段（顶层 key，仅 frontmatter 块内）
# stdout: version 字符串（不带引号），失败时空
extract_skill_version() {
    local skill_md="$1"
    awk '
        BEGIN { in_fm=0; fm_count=0 }
        /^---[[:space:]]*$/ {
            fm_count++
            if (fm_count == 1) { in_fm=1; next }
            if (fm_count == 2) { in_fm=0; exit }
            next
        }
        in_fm && /^version:[[:space:]]*/ {
            sub(/^version:[[:space:]]*/, "")
            gsub(/^["'\'']|["'\'']$/, "")
            sub(/[[:space:]]+#.*$/, "")  # 去除行尾注释
            sub(/[[:space:]]+$/, "")
            print
            exit
        }
    ' "$skill_md"
}

# 读取 VERSION 文件（首行非空内容）
extract_version_file() {
    local ver_file="$1"
    awk 'NF { gsub(/[[:space:]]+$/, ""); print; exit }' "$ver_file"
}

# 写入 SKILL.md frontmatter 的 version（替换或在 name 之后插入）
write_skill_version() {
    local skill_md="$1"
    local new_ver="$2"
    local tmp
    tmp="$(mktemp)"
    awk -v new_ver="$new_ver" '
        BEGIN { in_fm=0; fm_count=0; written=0 }
        /^---[[:space:]]*$/ {
            fm_count++
            if (fm_count == 1) { in_fm=1; print; next }
            if (fm_count == 2) {
                if (in_fm && !written) {
                    print "version: " new_ver
                    written=1
                }
                in_fm=0
                print; next
            }
            print; next
        }
        in_fm && /^version:[[:space:]]*/ {
            print "version: " new_ver
            written=1
            next
        }
        # 在 name 行之后立即插入 version（如果原本没有 version 字段）
        in_fm && !written && /^name:/ {
            print
            # 不在这里插入；等到遇到下一个 frontmatter 内容前判断
            # 简化：如果整个 frontmatter 走完都没写过，就在 --- 关闭前插入（上面已处理）
            next
        }
        { print }
    ' "$skill_md" >"$tmp"
    mv "$tmp" "$skill_md"
}

# 写入 VERSION 文件
write_version_file() {
    local ver_file="$1"
    local new_ver="$2"
    printf "%s\n" "$new_ver" >"$ver_file"
}

# 文件相对 HEAD 是否有改动（即"用户主动修改了已有版本"）。
# 语义：
#   - 不在 HEAD 里（首次建立，无论是否 staged）   → 不 dirty (return 1)
#     理由：没有上一个 commit 版本作为 baseline，无法判断是"修改"还是"首次建立"。
#   - 在 HEAD 里，working tree（含 staged）与 HEAD 相同 → 不 dirty (return 1)
#   - 在 HEAD 里，working tree（含 staged）与 HEAD 不同 → dirty (return 0)
#   - 不在 git 仓库 / git 不可用 → 不 dirty (return 1)
is_dirty_vs_head() {
    local file="$1"
    if [[ ! -e "$file" ]]; then
        return 1
    fi
    if ! git rev-parse --git-dir >/dev/null 2>&1; then
        return 1
    fi
    # 计算相对仓库根的路径（git cat-file 需要）
    local rel
    rel="$(git ls-files --full-name --error-unmatch "$file" 2>/dev/null || true)"
    if [[ -z "$rel" ]]; then
        # 未追踪：用 python 算相对路径（macOS 的 realpath 老版本不支持 --relative-to）
        local toplevel abs
        toplevel="$(git rev-parse --show-toplevel)"
        abs="$(cd "$(dirname "$file")" && pwd)/$(basename "$file")"
        rel="${abs#$toplevel/}"
    fi
    # HEAD 里有这个文件吗？
    if ! git cat-file -e "HEAD:$rel" 2>/dev/null; then
        # HEAD 里没有 → 首次建立，不 dirty
        return 1
    fi
    # HEAD 里有：与 HEAD 比（含 staged + unstaged）
    if ! git diff --quiet HEAD -- "$file" 2>/dev/null; then
        return 0
    fi
    return 1
}

# 自动 git add（仅在文件被脚本修改后调用；忽略错误，比如不在 git 仓库里）
git_add_silent() {
    git add -- "$1" 2>/dev/null || true
}

# -------- 主逻辑 --------

declare -i count_pass=0
declare -i count_fixed=0
declare -i count_conflict=0
declare -i count_drift=0
declare -i count_error=0

REPORT_LINES=()

process_skill() {
    local skill="$1"
    local skill_dir="$REPO_ROOT/$skill"
    local skill_md="$skill_dir/SKILL.md"
    local ver_file="$skill_dir/VERSION"

    # 文件存在性
    if [[ ! -d "$skill_dir" ]]; then
        REPORT_LINES+=("${C_RED}✗${C_OFF} ${skill}: directory not found")
        : $((count_error++))
        return
    fi
    if [[ ! -f "$skill_md" ]]; then
        REPORT_LINES+=("${C_RED}✗${C_OFF} ${skill}: SKILL.md not found")
        : $((count_error++))
        return
    fi
    if [[ ! -f "$ver_file" ]]; then
        REPORT_LINES+=("${C_RED}✗${C_OFF} ${skill}: VERSION file not found (create one with: echo 1.0.0 > $skill/VERSION)")
        : $((count_error++))
        return
    fi

    # 提取版本号
    local s_ver v_ver
    s_ver="$(extract_skill_version "$skill_md")"
    v_ver="$(extract_version_file "$ver_file")"

    if [[ -z "$s_ver" ]]; then
        REPORT_LINES+=("${C_RED}✗${C_OFF} ${skill}: SKILL.md frontmatter has no 'version:' field")
        : $((count_error++))
        return
    fi
    if [[ -z "$v_ver" ]]; then
        REPORT_LINES+=("${C_RED}✗${C_OFF} ${skill}: VERSION file is empty")
        : $((count_error++))
        return
    fi

    # ---- Force 模式：直接单向覆盖（在 check 模式下也允许 force 是错误，前面参数解析时已互斥）----
    if [[ "$MODE" == "force" ]]; then
        if [[ "$FORCE_FROM" == "skill" ]]; then
            if [[ "$s_ver" != "$v_ver" ]]; then
                write_version_file "$ver_file" "$s_ver"
                git_add_silent "$ver_file"
                REPORT_LINES+=("${C_CYAN}→${C_OFF} ${skill}: VERSION ${v_ver} → ${s_ver} (forced from SKILL.md)")
                : $((count_fixed++))
            else
                REPORT_LINES+=("${C_GREEN}✓${C_OFF} ${skill}: ${s_ver} (already in sync)")
                : $((count_pass++))
            fi
        else # version
            if [[ "$s_ver" != "$v_ver" ]]; then
                write_skill_version "$skill_md" "$v_ver"
                git_add_silent "$skill_md"
                REPORT_LINES+=("${C_CYAN}→${C_OFF} ${skill}: SKILL.md ${s_ver} → ${v_ver} (forced from VERSION)")
                : $((count_fixed++))
            else
                REPORT_LINES+=("${C_GREEN}✓${C_OFF} ${skill}: ${s_ver} (already in sync)")
                : $((count_pass++))
            fi
        fi
        return
    fi

    # ---- 一致性判定（check / sync 通用前半段）----
    if [[ "$s_ver" == "$v_ver" ]]; then
        REPORT_LINES+=("${C_GREEN}✓${C_OFF} ${skill}: ${s_ver}")
        : $((count_pass++))
        return
    fi

    # 不一致：判 dirty 状态
    local s_dirty=false v_dirty=false
    is_dirty_vs_head "$skill_md" && s_dirty=true
    is_dirty_vs_head "$ver_file" && v_dirty=true

    # ---- check 模式：任何不一致都报错，不区分场景 ----
    if [[ "$MODE" == "check" ]]; then
        REPORT_LINES+=("${C_RED}✗${C_OFF} ${skill}: SKILL.md=${s_ver}, VERSION=${v_ver} ${C_YELLOW}(mismatch)${C_OFF}")
        : $((count_drift++))
        return
    fi

    # ---- sync 模式：按 5 种场景处理 ----
    if $s_dirty && ! $v_dirty; then
        # 场景 2：用 SKILL.md 覆盖 VERSION
        write_version_file "$ver_file" "$s_ver"
        git_add_silent "$ver_file"
        REPORT_LINES+=("${C_CYAN}→${C_OFF} ${skill}: VERSION ${v_ver} → ${s_ver} (synced from SKILL.md)")
        : $((count_fixed++))
    elif ! $s_dirty && $v_dirty; then
        # 场景 3：用 VERSION 覆盖 SKILL.md
        write_skill_version "$skill_md" "$v_ver"
        git_add_silent "$skill_md"
        REPORT_LINES+=("${C_CYAN}→${C_OFF} ${skill}: SKILL.md ${s_ver} → ${v_ver} (synced from VERSION)")
        : $((count_fixed++))
    elif $s_dirty && $v_dirty; then
        # 场景 4：双方都改了，意图模糊，拒绝
        REPORT_LINES+=("${C_RED}✗${C_OFF} ${skill}: ${C_BOLD}conflict${C_OFF} — both SKILL.md (=${s_ver}) and VERSION (=${v_ver}) modified")
        REPORT_LINES+=("    resolve manually: ${C_BOLD}bash scripts/sync_versions.sh --force-from=skill${C_OFF}  (or =version) ${skill}")
        : $((count_conflict++))
    else
        # 场景 5：两边都没动但不一致 → 历史漂移
        REPORT_LINES+=("${C_RED}✗${C_OFF} ${skill}: ${C_BOLD}history drift${C_OFF} — committed state is inconsistent (SKILL.md=${s_ver}, VERSION=${v_ver})")
        REPORT_LINES+=("    resolve manually: pick the correct version, edit one file, then commit")
        : $((count_drift++))
    fi
}

# 执行
for skill in "${SKILLS[@]}"; do
    process_skill "$skill"
done

# -------- 输出报告 --------
echo
echo "${C_BOLD}Version sync report${C_OFF} (mode: $MODE)"
echo "$(printf '%.0s─' $(seq 1 72))"
for line in "${REPORT_LINES[@]}"; do
    echo "  $line"
done
echo "$(printf '%.0s─' $(seq 1 72))"
printf "  pass: %d  fixed: %d  conflict: %d  drift: %d  error: %d\n" \
    "$count_pass" "$count_fixed" "$count_conflict" "$count_drift" "$count_error"

# -------- 退出码 --------
if ((count_error > 0)); then
    exit 2
fi
if [[ "$MODE" == "check" ]]; then
    if ((count_drift > 0)); then
        exit 1
    fi
fi
if [[ "$MODE" == "sync" ]]; then
    if ((count_conflict > 0 || count_drift > 0)); then
        exit 1
    fi
fi
exit 0
