#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# merge.sh — 原地合并：多个独立 skill → 一个 skill
#
# 自动扫描所有含 SKILL.md 的子目录，将它们合并为一个顶层 skill。
#
# 目录结构 .allinone-skill/:
#   SKILL.md              — 合并版顶层 SKILL.md 模板
#   config.example.toml   — 合并版根目录 config 模板
#   merge.sh              — 本脚本
#   stand-alone-skills/   — 合并时自动备份各子 SKILL.md（已 gitignore）
#
# 用法：
#   bash .allinone-skill/merge.sh              # 合并
#   bash .allinone-skill/merge.sh --revert     # 还原
#   bash .allinone-skill/merge.sh --dry-run    # 预览
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKUP_DIR="$SCRIPT_DIR/stand-alone-skills"
TEMPLATE_SKILL="$SCRIPT_DIR/SKILL.md"
TEMPLATE_CONFIG="$SCRIPT_DIR/config.example.toml"
DRY_RUN=false
REVERT=false

# ── Parse args ──────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
    --revert)
        REVERT=true
        shift
        ;;
    --dry-run)
        DRY_RUN=true
        shift
        ;;
    -h | --help)
        echo "Usage: bash .allinone-skill/merge.sh [--revert] [--dry-run]"
        echo ""
        echo "  (default)    Merge stand-alone skills into one top-level skill"
        echo "  --revert     Restore individual skills from backup"
        echo "  --dry-run    Preview changes without modifying files"
        exit 0
        ;;
    *)
        echo "Unknown option: $1" >&2
        exit 1
        ;;
    esac
done

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ── Auto-detect sub skills ──────────────────────────────────
# Scan for */SKILL.md in repo root (one level deep, skip hidden dirs)
# Excludes: openclaw-photo-agents-creator (setup tool, not a photo skill)
find_sub_skills() {
    local skills=()
    for d in "$REPO_DIR"/*/; do
        local dir_name
        dir_name="$(basename "$d")"
        # Skip hidden directories
        [[ "$dir_name" == .* ]] && continue
        # Skip setup/tools directories (not photo processing skills)
        [[ "$dir_name" == "openclaw-photo-agents-creator" ]] && continue
        if [ -f "$d/SKILL.md" ]; then
            skills+=("${dir_name}/SKILL.md")
        fi
    done
    echo "${skills[@]}"
}

# ═════════════════════════════════════════════════════════════
# Revert: 还原为多个独立 skill
# ═════════════════════════════════════════════════════════════
if $REVERT; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "  🔄 ${BOLD}Revert to Stand-alone Skills${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    if [ ! -d "$BACKUP_DIR" ]; then
        echo -e "  ${RED}✗${NC} No backup found at .allinone-skill/stand-alone-skills/"
        echo "    Already in stand-alone mode?"
        echo ""
        exit 1
    fi

    # Discover backed-up skills
    BACKED_UP=()
    for f in "$BACKUP_DIR"/*-SKILL.md; do
        [ -f "$f" ] || continue
        BACKED_UP+=("$f")
    done

    if [ ${#BACKED_UP[@]} -eq 0 ]; then
        echo -e "  ${RED}✗${NC} Backup directory is empty"
        exit 1
    fi

    if $DRY_RUN; then
        echo -e "${CYAN}🔍 Dry run — would do:${NC}"
        echo ""
        [ -f "$REPO_DIR/SKILL.md" ] && echo "  🗑  Delete SKILL.md" || echo "  ⏭  SKILL.md not found"
        [ -f "$REPO_DIR/config.example.json" ] && echo "  🗑  Delete config.example.json (root, legacy)" || true
        [ -f "$REPO_DIR/config.json" ] && echo "  🗑  Delete config.json (root, legacy)" || true
        for f in "${BACKED_UP[@]}"; do
            fname="$(basename "$f")"
            # photo-toolkit-SKILL.md → photo-toolkit/SKILL.md
            skill="${fname%-SKILL.md}"
            echo "  ♻️  Restore ${skill}/SKILL.md"
        done
        echo "  🗑  Remove .allinone-skill/stand-alone-skills/"
        echo ""
        exit 0
    fi

    # Delete top-level files
    for f in SKILL.md config.example.toml config.toml config.example.json config.json; do
        if [ -f "$REPO_DIR/$f" ]; then
            rm "$REPO_DIR/$f"
            echo -e "  ${GREEN}✓${NC} Deleted $f"
        fi
    done

    # Restore each backed-up SKILL.md
    RESTORED=0
    for f in "${BACKED_UP[@]}"; do
        fname="$(basename "$f")"
        skill="${fname%-SKILL.md}"
        dest="$REPO_DIR/${skill}/SKILL.md"
        if [ -d "$REPO_DIR/$skill" ]; then
            cp "$f" "$dest"
            echo -e "  ${GREEN}✓${NC} Restored ${skill}/SKILL.md"
            RESTORED=$((RESTORED + 1))
        else
            echo -e "  ${YELLOW}⏭${NC} Directory ${skill}/ not found, skipping"
        fi
    done

    rm -rf "$BACKUP_DIR"
    echo -e "  ${GREEN}✓${NC} Cleaned up stand-alone-skills/"

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "  ${GREEN}✅ Reverted ${RESTORED} stand-alone skill(s)${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    exit 0
fi

# ═════════════════════════════════════════════════════════════
# Merge: 多个独立 skill → 一个 skill
# ═════════════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  📦 ${BOLD}Merge into Single Skill${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Preflight checks
if [ ! -f "$TEMPLATE_SKILL" ]; then
    echo -e "  ${RED}✗${NC} Template not found: .allinone-skill/SKILL.md"
    exit 1
fi
if [ ! -f "$TEMPLATE_CONFIG" ]; then
    echo -e "  ${RED}✗${NC} Template not found: .allinone-skill/config.example.toml"
    exit 1
fi

# Already merged?
if [ -f "$REPO_DIR/SKILL.md" ] && [ -d "$BACKUP_DIR" ]; then
    echo -e "  ${YELLOW}⚠️  Already in single-skill mode. Nothing to do.${NC}"
    echo ""
    echo "  To revert: bash .allinone-skill/merge.sh --revert"
    echo ""
    exit 0
fi

# Auto-detect sub skills
read -ra SUB_SKILLS <<<"$(find_sub_skills)"

if [ ${#SUB_SKILLS[@]} -eq 0 ]; then
    echo -e "  ${YELLOW}⚠️  No sub-skill SKILL.md files found. Nothing to merge.${NC}"
    echo ""
    exit 0
fi

echo -e "  Found ${#SUB_SKILLS[@]} stand-alone skill(s):"
for f in "${SUB_SKILLS[@]}"; do
    echo "    - $f"
done
echo ""

if $DRY_RUN; then
    echo -e "${CYAN}��� Dry run — would do:${NC}"
    echo ""
    for f in "${SUB_SKILLS[@]}"; do
        echo "  💾 Backup + 🗑 Delete $f"
    done
    echo "  📝 Copy .allinone-skill/SKILL.md → SKILL.md"
    echo "  📝 Copy .allinone-skill/config.example.toml → config.example.toml"
    echo ""
    exit 0
fi

# ── Step 1: Backup sub SKILL.md ─────────────────────────────
echo -e "${BOLD}[1/4] Backing up per-skill SKILL.md...${NC}"
mkdir -p "$BACKUP_DIR"

for f in "${SUB_SKILLS[@]}"; do
    skill="$(dirname "$f")"
    cp "$REPO_DIR/$f" "$BACKUP_DIR/${skill}-SKILL.md"
    echo -e "  ${GREEN}✓${NC} $f → stand-alone-skills/${skill}-SKILL.md"
done

# ── Step 2: Delete sub SKILL.md ─────────────────────────────
echo -e "${BOLD}[2/4] Removing per-skill SKILL.md...${NC}"
for f in "${SUB_SKILLS[@]}"; do
    rm "$REPO_DIR/$f"
    echo -e "  ${GREEN}✓${NC} Deleted $f"
done

# ── Step 3: Generate top-level SKILL.md ─────────────────────
echo -e "${BOLD}[3/4] Creating top-level SKILL.md...${NC}"
cp "$TEMPLATE_SKILL" "$REPO_DIR/SKILL.md"
echo -e "  ${GREEN}✓${NC} SKILL.md"

# ── Step 4: Copy root config.example.toml ───────────────────
echo -e "${BOLD}[4/4] Creating root config.example.toml...${NC}"
cp "$TEMPLATE_CONFIG" "$REPO_DIR/config.example.toml"
echo -e "  ${GREEN}✓${NC} config.example.toml"

# ── Summary ─────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "  ${GREEN}✅ Merged ${#SUB_SKILLS[@]} skill(s) into one${NC}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Next step:"
echo "    cp config.example.toml config.toml"
echo "    # Edit config.toml to set your directories"
echo ""
echo "  To revert: bash .allinone-skill/merge.sh --revert"
echo ""
