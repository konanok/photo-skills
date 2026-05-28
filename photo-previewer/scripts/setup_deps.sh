#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# photo-previewer — Dependency Check
#
# This skill uses Python stdlib only. There are no pip dependencies to
# install; this script just verifies python3 is available.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  📦 photo-previewer — 依赖检查"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if ! command -v python3 >/dev/null 2>&1; then
    echo -e "  ${RED}✗${NC} python3 — 未安装"
    echo ""
    echo "  请先安装 Python 3.8+："
    if [[ "$(uname)" == "Darwin" ]]; then
        echo "    brew install python3"
    elif command -v apt-get >/dev/null 2>&1; then
        echo "    sudo apt-get install python3"
    elif command -v dnf >/dev/null 2>&1; then
        echo "    sudo dnf install python3"
    fi
    exit 1
fi

PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo -e "  ${GREEN}✓${NC} python3 ${PY_VER} detected"
echo -e "  ${GREEN}✓${NC} photo-previewer uses stdlib only — no pip install needed"
echo ""
echo -e "${GREEN}✅ 所有依赖已就绪！${NC}"
