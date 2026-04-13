#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# photo-grader — Dependency Check & Install
#
# Engine: RawTherapee CLI (rawtherapee-cli)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📦 photo-grader — 依赖检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ALL_OK=true
HAS_RT=false

# ── Check RawTherapee CLI ─────────────────────────────────────
echo -e "${BOLD}检查 RawTherapee CLI...${NC}"
echo ""

if command -v rawtherapee-cli &>/dev/null; then
    RT_VER=$(rawtherapee-cli --version 2>&1 | head -1 || echo "unknown")
    echo -e "  ${GREEN}✓${NC} rawtherapee-cli ($RT_VER)"
    HAS_RT=true
elif command -v rawtherapee &>/dev/null; then
    RT_PATH=$(command -v rawtherapee)
    echo -e "  ${YELLOW}⚠${NC} 找到 rawtherapee GUI ($RT_PATH)，但未找到 rawtherapee-cli"
    echo -e "       确认安装了 rawtherapee-cli 包（不是仅 GUI 版本）"
    ALL_OK=false
else
    echo -e "  ${RED}✗${NC} rawtherapee-cli — 未安装（必须安装）"
    echo "       安装: brew install --cask rawtherapee (macOS)"
    echo "            sudo apt install rawtherapee-cli (Debian/Ubuntu)"
    echo "            sudo dnf install RawTherapee (Fedora/RHEL)"
    echo "       或使用 Docker: docker pull lscr.io/linuxserver/rawtherapee:latest"
    ALL_OK=false
fi

# ── Check tomli (Python < 3.11) ───────────────────────────────
echo ""
echo -e "${BOLD}检查 Python 依赖...${NC}"
echo ""

PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "?")
if python3 -c "import tomllib" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} tomllib (Python $PY_VER stdlib)"
elif python3 -c "import tomli" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} tomli (Python $PY_VER)"
else
    echo -e "  ${YELLOW}⚠${NC} tomli — 未安装（Python < 3.11 需要）"
    echo "       安装中..."
    pip3 install tomli && echo -e "  ${GREEN}✓${NC} tomli 安装完成" || {
        echo -e "  ${RED}✗${NC} tomli 安装失败，请手动运行: pip3 install tomli"
        ALL_OK=false
    }
fi

# ── Summary ──────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if $HAS_RT; then
    echo -e "  ${GREEN}✅ 引擎就绪：RawTherapee CLI${NC}"
else
    echo -e "  ${RED}❌ 引擎不可用：请安装 rawtherapee-cli${NC}"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if $ALL_OK; then
    exit 0
fi

# ── Install prompt ───────────────────────────────────────────
echo ""
echo -e "${YELLOW}缺少 rawtherapee-cli，请手动安装：${NC}"
echo ""
if [[ "$(uname)" == "Darwin" ]]; then
    echo "  brew install --cask rawtherapee"
elif command -v dnf &>/dev/null; then
    echo "  sudo dnf install -y RawTherapee"
else
    echo "  sudo apt-get install -y rawtherapee-cli"
fi
echo ""

exit 1
