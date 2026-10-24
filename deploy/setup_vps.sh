#!/usr/bin/env bash
# Jalankan di VPS (Ubuntu/Debian) sebagai root, SETELAH folder project diupload ke /opt/xiaozhi-mcp
# dan file .env berisi MCP_ENDPOINT=wss://... sudah dibuat.
set -euo pipefail
APP=/opt/xiaozhi-mcp

apt-get update && apt-get install -y python3 python3-venv python3-pip
id xiaozhi &>/dev/null || useradd --system --home "$APP" --shell /usr/sbin/nologin xiaozhi

cd "$APP"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r deploy/requirements-vps.txt

chown -R xiaozhi:xiaozhi "$APP"
chmod 600 "$APP/.env" "$APP/token.json"

cp deploy/xiaozhi-mcp.service /etc/systemd/system/xiaozhi-mcp.service
systemctl daemon-reload
systemctl enable --now xiaozhi-mcp
sleep 3
systemctl --no-pager status xiaozhi-mcp
echo "Log live: journalctl -u xiaozhi-mcp -f"
