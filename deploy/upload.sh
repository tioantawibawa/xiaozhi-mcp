#!/usr/bin/env bash
# Jalankan dari laptop (Git Bash): bash deploy/upload.sh user@IP_VPS
set -euo pipefail
HOST="${1:?usage: upload.sh user@host}"
cd "$(dirname "$0")/.."
ssh "$HOST" "mkdir -p /opt/xiaozhi-mcp"
tar czf - asisten_tools.py mcp_pipe.py mcp_config.json requirements.txt token.json deploy | ssh "$HOST" "tar xzf - -C /opt/xiaozhi-mcp"
echo "Sekarang buat /opt/xiaozhi-mcp/.env (MCP_ENDPOINT=wss://...) lalu: bash /opt/xiaozhi-mcp/deploy/setup_vps.sh"
