#!/bin/zsh
set -euo pipefail

PROJECT_DIR="/Users/mac/Projects/quant-trading-intel"
"${PROJECT_DIR}/.venv/bin/python" "${PROJECT_DIR}/deploy/auth_gateway.py" --set-password --username hong
/bin/launchctl kickstart -k "gui/$(/usr/bin/id -u)/com.hong-dashboard.auth-gateway"
echo "密码已生效。"
