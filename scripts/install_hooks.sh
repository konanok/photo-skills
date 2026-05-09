#!/usr/bin/env bash
# install_hooks.sh — 启用本仓库的 git hooks（.githooks/）
#
# 通过 git config core.hooksPath 指向 .githooks/，hook 跟仓库一起走，
# 不污染 .git/hooks/，新维护者 clone 后跑一次即可。
#
# 用法：bash scripts/install_hooks.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "error: not inside a git repository" >&2
    exit 1
fi

HOOKS_DIR=".githooks"
if [[ ! -d "$HOOKS_DIR" ]]; then
    echo "error: $HOOKS_DIR/ not found in repo root" >&2
    exit 1
fi

# 确保 hook 文件可执行
chmod +x "$HOOKS_DIR"/* 2>/dev/null || true

# 配置 git 使用本仓库自带的 hooks 目录
git config core.hooksPath "$HOOKS_DIR"

echo "✓ git hooks enabled (core.hooksPath = $HOOKS_DIR)"
echo "  hooks installed:"
for h in "$HOOKS_DIR"/*; do
    [[ -f "$h" ]] && echo "    - $(basename "$h")"
done
echo
echo "  to disable: git config --unset core.hooksPath"
