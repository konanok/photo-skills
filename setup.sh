#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# photo-skills — All-in-one Dependency Setup
# Installs system and Python dependencies for all three skills:
#   photo-converter, photo-grader, photo-screener
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📦 photo-skills — 全量依赖安装"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

MISSING_SYS=()
MISSING_PY=()
ALL_OK=true

# ── 1. System dependency: libraw ─────────────────────────────
echo -e "${BOLD}[1/4] 检查系统依赖${NC}"
echo ""

check_libraw() {
    # Linux: shared library
    if [ -f /usr/lib/libraw.so ] || [ -f /usr/lib64/libraw.so ] ||
        [ -f /usr/lib/x86_64-linux-gnu/libraw.so ] ||
        ldconfig -p 2>/dev/null | grep -q libraw; then
        return 0
    fi
    # macOS: Homebrew
    if command -v brew &>/dev/null && brew list libraw &>/dev/null 2>&1; then
        return 0
    fi
    return 1
}

if check_libraw; then
    echo -e "  ${GREEN}✓${NC} libraw"
else
    echo -e "  ${RED}✗${NC} libraw — 未安装"
    MISSING_SYS+=("libraw")
    ALL_OK=false
fi

# ── 2. Python dependencies ───────────────────────────────────
echo ""
echo -e "${BOLD}[2/4] 检查 Python 依赖${NC}"
echo ""

check_python_pkg() {
    local import_name="$1"
    local pip_name="$2"
    local required_by="$3"
    if python3 -c "import $import_name" 2>/dev/null; then
        local ver
        ver=$(python3 -c "import $import_name; print(getattr($import_name, '__version__', getattr($import_name, 'VERSION', '?')))" 2>/dev/null || echo "?")
        echo -e "  ${GREEN}✓${NC} $pip_name ($ver)  ← $required_by"
    else
        echo -e "  ${RED}✗${NC} $pip_name — 未安装  ← $required_by"
        # Avoid duplicates
        local already=false
        for existing in "${MISSING_PY[@]+"${MISSING_PY[@]}"}"; do
            if [ "$existing" = "$pip_name" ]; then
                already=true
                break
            fi
        done
        if ! $already; then
            MISSING_PY+=("$pip_name")
        fi
        ALL_OK=false
    fi
}

# Shared
check_python_pkg "PIL" "pillow" "converter, grader, screener"
check_python_pkg "numpy" "numpy" "converter, grader, screener"

# converter + grader
check_python_pkg "rawpy" "rawpy" "converter, grader"

# grader only
check_python_pkg "scipy" "scipy" "grader"

# screener only
check_python_pkg "torch" "torch" "screener"
check_python_pkg "open_clip" "open-clip-torch" "screener"

# ── 3. MobileCLIP model ──────────────────────────────────────
echo ""
echo -e "${BOLD}[3/3] 检查 MobileCLIP2-S0 模型${NC}"
echo ""

MODEL_READY=$(python3 -c "
import sys, os
for cache_dir in [
    os.path.expanduser('~/.cache/open_clip'),
    os.path.expanduser('~/.cache/huggingface/hub'),
]:
    if os.path.isdir(cache_dir):
        for root, dirs, files in os.walk(cache_dir):
            for name in dirs + files:
                nl = name.lower()
                if ('mobileclip' in nl and 's0' in nl) or 'dfndr2b' in nl:
                    print('yes'); sys.exit(0)
print('no')
" 2>/dev/null || echo "no")

if [ "$MODEL_READY" = "yes" ]; then
    echo -e "  ${GREEN}✓${NC} MobileCLIP2-S0 模型已缓存"
else
    echo -e "  ${CYAN}ℹ${NC} MobileCLIP2-S0 模型未下载（首次运行 screen.py 时会提示下载，约 300MB）"
fi

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if $ALL_OK; then
    echo -e "  ${GREEN}✅ 所有依赖已就绪！${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    exit 0
fi

echo -e "  ${YELLOW}⚠️  缺少以下依赖${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Show system deps
if [ ${#MISSING_SYS[@]} -gt 0 ]; then
    echo "  系统依赖:"
    for pkg in "${MISSING_SYS[@]}"; do
        echo "    - $pkg"
    done
    echo ""
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "  安装命令: brew install ${MISSING_SYS[*]}"
    elif command -v dnf &>/dev/null; then
        echo "  安装命令: sudo dnf install LibRaw-devel"
    elif command -v yum &>/dev/null; then
        echo "  安装命令: sudo yum install LibRaw-devel"
    else
        echo "  安装命令: sudo apt-get install ${MISSING_SYS[*]/%/-dev}"
    fi
    echo ""
fi

# Show Python deps
if [ ${#MISSING_PY[@]} -gt 0 ]; then
    echo "  Python 依赖:"
    for pkg in "${MISSING_PY[@]}"; do
        echo "    - $pkg"
    done
    echo ""
    echo "  安装命令: pip3 install ${MISSING_PY[*]}"
    echo ""
fi

# Prompt install
read -r -p "  是否立即安装缺少的依赖？[Y/n] " answer
answer=${answer:-Y}

if [[ "$answer" =~ ^[Yy]$ ]]; then
    # System deps
    if [ ${#MISSING_SYS[@]} -gt 0 ]; then
        echo ""
        echo "📦 安装系统依赖..."
        if [[ "$(uname)" == "Darwin" ]]; then
            brew install "${MISSING_SYS[@]}"
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y LibRaw-devel
        elif command -v yum &>/dev/null; then
            sudo yum install -y LibRaw-devel
        else
            sudo apt-get install -y "${MISSING_SYS[@]/%/-dev}"
        fi
    fi

    # Python deps
    if [ ${#MISSING_PY[@]} -gt 0 ]; then
        echo ""
        echo "📦 安装 Python 依赖..."
        pip3 install "${MISSING_PY[@]}"
    fi

    echo ""
    echo -e "${GREEN}✅ 安装完成！${NC}"
else
    echo ""
    echo "  跳过安装。请手动安装后重试。"
    exit 1
fi
