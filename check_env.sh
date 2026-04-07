#!/usr/bin/env bash
# photo-skills — Environment Health Check
# Checks dependencies, config files, and model status
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

ISSUES=0

pass() { echo -e "  ${GREEN}ok${NC} $1"; }
warn_() {
    echo -e "  ${YELLOW}!!${NC} $1"
    ISSUES=$((ISSUES + 1))
}
fail_() {
    echo -e "  ${RED}xx${NC} $1"
    ISSUES=$((ISSUES + 1))
}
info_() { echo -e "  ${CYAN}--${NC} $1"; }

echo ""
echo "======================================================"
echo "  photo-skills env check"
echo "======================================================"

# === 1. System Dependencies ===
echo ""
echo -e "${BOLD}[1/5] System${NC}"
echo ""

if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
    pass "Python $PY_VER"
else
    fail_ "python3 not found"
fi

if command -v pip3 &>/dev/null; then
    pass "pip3"
else
    warn_ "pip3 not found"
fi

check_libraw() {
    [ -f /usr/lib/libraw.so ] || [ -f /usr/lib64/libraw.so ] ||
        [ -f /usr/lib/x86_64-linux-gnu/libraw.so ] ||
        ldconfig -p 2>/dev/null | grep -q libraw ||
        (command -v brew &>/dev/null && brew list libraw &>/dev/null 2>&1)
}
if check_libraw; then
    pass "libraw (converter, grader)"
else
    fail_ "libraw not installed -> brew install libraw / apt-get install libraw-dev"
fi

if command -v ffmpeg &>/dev/null; then
    FFMPEG_VER=$(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')
    pass "ffmpeg $FFMPEG_VER (converter/assemble.py)"
else
    info_ "ffmpeg not installed (optional, needed by assemble.py) -> brew install ffmpeg / apt-get install ffmpeg"
fi

# === 2. Python Dependencies ===
echo ""
echo -e "${BOLD}[2/5] Python packages${NC}"
echo ""

check_py() {
    local import_name="$1"
    local pip_name="$2"
    local needed_by="$3"
    if python3 -c "import $import_name" 2>/dev/null; then
        local ver
        ver=$(python3 -c "import $import_name; print(getattr($import_name, '__version__', getattr($import_name, 'VERSION', '?')))" 2>/dev/null || echo "?")
        pass "$pip_name ($ver) <- $needed_by"
    else
        fail_ "$pip_name not installed <- $needed_by"
    fi
}

check_py "PIL" "pillow" "converter, grader, screener"
check_py "numpy" "numpy" "converter, grader, screener"
check_py "rawpy" "rawpy" "converter, grader"
check_py "scipy" "scipy" "grader"
check_py "torch" "torch" "screener"
check_py "open_clip" "open-clip-torch" "screener"

# === 3. Config Files ===
echo ""
echo -e "${BOLD}[3/5] Config files${NC}"
echo ""

check_config() {
    local skill="$1"
    local config_toml="$REPO_DIR/$skill/config.toml"
    local config_json="$REPO_DIR/$skill/config.json"
    local example_toml="$REPO_DIR/$skill/config.example.toml"
    local example_json="$REPO_DIR/$skill/config.example.json"

    if [ -f "$config_toml" ]; then
        pass "$skill/config.toml"
    elif [ -f "$config_json" ]; then
        if python3 -c "import json; json.load(open('$config_json'))" 2>/dev/null; then
            pass "$skill/config.json"
        else
            fail_ "$skill/config.json invalid JSON"
        fi
    elif [ -f "$example_toml" ]; then
        warn_ "$skill/config.toml missing -> cp $skill/config.example.toml $skill/config.toml"
    elif [ -f "$example_json" ]; then
        warn_ "$skill/config missing -> cp $skill/config.example.toml $skill/config.toml (or .json)"
    else
        fail_ "$skill/config not found (no config.toml, config.json, or example files)"
    fi
}

check_config "photo-converter"
check_config "photo-grader"
check_config "photo-screener"

# === 4. Config Values ===
echo ""
echo -e "${BOLD}[4/5] Config values${NC}"
echo ""

check_config_field() {
    local skill="$1"
    local field="$2"
    local label="$3"
    local config_path=""

    # Prefer toml, fallback to json
    if [ -f "$REPO_DIR/$skill/config.toml" ]; then
        config_path="$REPO_DIR/$skill/config.toml"
    elif [ -f "$REPO_DIR/$skill/config.json" ]; then
        config_path="$REPO_DIR/$skill/config.json"
    else
        return
    fi

    local val
    val=$(
        python3 <<PYEOF
import sys
path = "$config_path"
if path.endswith(".toml"):
    try:
        import tomllib
    except ModuleNotFoundError:
        import tomli as tomllib
    with open(path, "rb") as f:
        c = tomllib.load(f)
else:
    import json
    with open(path) as f:
        c = json.load(f)
v = c.get("$field")
if v is None or v == "" or v == 0:
    print("__NULL__")
else:
    print(v)
PYEOF
    ) 2>/dev/null || true

    if [ -z "${val:-}" ]; then
        fail_ "$skill: cannot read $field"
        return
    fi

    if [ "$val" = "__NULL__" ]; then
        warn_ "$skill: $label not set ($field = null)"
        return
    fi

    # For dir fields, check if directory exists
    if [[ "$field" == *"dir"* ]]; then
        local expanded
        expanded=$(python3 -c "from pathlib import Path; print(Path('${val}').expanduser())" 2>/dev/null || true)
        if [ -n "${expanded:-}" ] && [ ! -d "$expanded" ]; then
            warn_ "$skill: $label = $val (directory not found)"
            return
        fi
    fi

    pass "$skill: $label = $val"
}

check_config_field "photo-converter" "input_dir" "input dir"
check_config_field "photo-converter" "output_dir" "output dir"
check_config_field "photo-grader" "raw_dir" "raw dir"
check_config_field "photo-grader" "output_dir" "output dir"

# === 5. MobileCLIP Model ===
echo ""
echo -e "${BOLD}[5/5] MobileCLIP2-S0 model (photo-screener)${NC}"
echo ""

MODEL_READY=$(
    python3 <<'PYEOF'
import sys, os
for cache_dir in [
    os.path.expanduser("~/.cache/open_clip"),
    os.path.expanduser("~/.cache/huggingface/hub"),
]:
    if os.path.isdir(cache_dir):
        for root, dirs, files in os.walk(cache_dir):
            for name in dirs + files:
                nl = name.lower()
                if ("mobileclip" in nl and "s0" in nl) or "dfndr2b" in nl:
                    print("yes"); sys.exit(0)
print("no")
PYEOF
) 2>/dev/null || echo "no"

if [ "$MODEL_READY" = "yes" ]; then
    pass "MobileCLIP2-S0 model cached"
else
    info_ "MobileCLIP2-S0 model not downloaded (will prompt on first run, ~300MB)"
fi

AESTHETIC_PATH="$HOME/.cache/photo-filter/aesthetic_sac_logos_ava1_l14_linearMSE.pth"
if [ -f "$AESTHETIC_PATH" ]; then
    pass "Aesthetic predictor model cached"
else
    info_ "Aesthetic predictor not downloaded (auto-downloads on first run, ~3MB)"
fi

# === Summary ===
echo ""
echo "======================================================"
if [ $ISSUES -eq 0 ]; then
    echo -e "  ${GREEN}All checks passed!${NC}"
else
    echo -e "  ${YELLOW}Found $ISSUES issue(s)${NC}"
    echo ""
    echo "  Fix:"
    echo "    bash setup.sh                                     # install deps"
    echo "    cp <skill>/config.example.toml <skill>/config.toml  # create config"
fi
echo "======================================================"
echo ""

exit $ISSUES
