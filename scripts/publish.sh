#!/usr/bin/env bash
# publish.sh — 兼容性 wrapper，转发到 publish.py
#
# 历史原因：早期 publish 流程是 bash 实现的；为了规避 shell quoting 在
# multiline changelog 上的复杂性、以及方便做 ClawHub 查重 / 版本一致性
# 校验、TTY 红按钮等结构化逻辑，改为 Python 实现。
# 此 wrapper 保留是为了：
#   - RELEASING.md / CI / 用户指尖记忆里 `bash scripts/publish.sh` 的命令依然可跑
#   - 不破坏外部脚本对该路径的引用
#
# 真正的实现见 scripts/publish.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/publish.py" "$@"
