#!/bin/bash
# Chat-Miner WSL deploy script
# Usage: wsl -d DebianDev -- bash /mnt/c/mycode/chat-miner/deploy.sh

set -e

SRC="/mnt/c/mycode/chat-miner/"
DST="/home/zhaohaosen/applications/chat-miner/"

echo "==> Syncing files..."
rsync -av --delete \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='frontend/node_modules' \
  --exclude='__pycache__' \
  --exclude='data' \
  --exclude='logs' \
  --exclude='venv' \
  --exclude='config.json' \
  --exclude='docs' \
  --exclude='*.tar.gz' \
  "$SRC" "$DST"

echo "==> Building frontend..."
cd "$DST/frontend" && npm run build

echo "==> Restarting service..."
sudo systemctl restart chat-miner

echo "==> Checking status..."
sleep 2
sudo systemctl status chat-miner --no-pager -l 2>&1 | grep -E "Active:|Main PID:" || true

echo "Deploy OK"
