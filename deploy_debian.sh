#!/usr/bin/env bash
set -e

echo "=== [1/3] Installing system packages on Debian ==="
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv curl wget jq screen ffmpeg build-essential python3-dev

echo "=== [2/3] Setting up Python venv ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== [3/3] Ready! ==="
echo "Run: ./start_agent.sh"
