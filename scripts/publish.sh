#!/usr/bin/env bash
# publish.sh — 兼容性 wrapper，转发到 publish.py
#
# 历史原因：早期 publish 流程是 bash 实现的；后续因 multiline changelog 在 commander.js
# 下被误解析（以 `-` 开头的行被当成新参数），改为 Python 实现。
# 此 wrapper 保留是为了：
#   - RELEASING.md / CI / 用户指尖记忆里 `bash scripts/publish.sh` 的命令依然可跑
#   - 不破坏外部脚本对该路径的引用
#
# 真正的实现见 scripts/publish.py

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/publish.py" "$@"
