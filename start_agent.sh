#!/usr/bin/env bash
# ==============================================================================
# One-Line All-in-One Launcher for QQ AI Companion Daemon
# Automatically starts NapCat (Docker/Native), checks port 3000, and starts agent
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================================="
echo "      QQ AI Companion Daemon - All-in-One Launcher                "
echo "=================================================================="

# 1. Determine OneBot HTTP API endpoint from config.json
ONEBOT_API="http://127.0.0.1:3000"
if [ -f "config.json" ]; then
    CFG_API=$(grep -o '"onebot_http_api"[^,]*' config.json | head -1 | cut -d'"' -f4 || true)
    if [ -n "$CFG_API" ]; then
        ONEBOT_API="$CFG_API"
    fi
fi

# 2. Check if OneBot 11 is already responding
echo "[*] Checking OneBot 11 status on ${ONEBOT_API}..."
check_onebot_online() {
    curl -s --connect-timeout 2 "${ONEBOT_API}/get_version_info" >/dev/null 2>&1 || \
    curl -s --connect-timeout 2 "${ONEBOT_API}/get_status" >/dev/null 2>&1
}

if check_onebot_online; then
    echo "[+] OneBot 11 (NapCat) is already running and online!"
else
    echo "[-] OneBot 11 is not responding on ${ONEBOT_API}."
    echo "[*] Attempting to auto-start NapCat via Docker..."

    # Determine docker command (with sudo if needed)
    DOCKER_CMD="docker"
    if ! docker ps >/dev/null 2>&1; then
        if sudo -n docker ps >/dev/null 2>&1; then
            DOCKER_CMD="sudo docker"
        elif command -v sudo >/dev/null 2>&1; then
            echo "[*] Docker requires elevated permissions. Using sudo..."
            DOCKER_CMD="sudo docker"
        fi
    fi

    # Check if Docker is installed
    if command -v docker >/dev/null 2>&1; then
        # Check if a container named 'napcat' exists
        if $DOCKER_CMD ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^napcat$"; then
            echo "[*] Found existing 'napcat' container. Starting it..."
            $DOCKER_CMD start napcat >/dev/null
        else
            echo "[*] Creating and starting new NapCat Docker container..."
            sudo mkdir -p /opt/napcat/config 2>/dev/null || mkdir -p "$HOME/.napcat/config" 2>/dev/null || true
            $DOCKER_CMD run -d \
                --name napcat \
                --restart always \
                --network host \
                -v /opt/napcat/config:/app/napcat/config \
                mlikiowa/napcat-docker:latest >/dev/null
        fi

        echo "[*] Waiting for NapCat to boot and bind to port 3000..."
        WAIT_SECONDS=0
        MAX_WAIT=20
        while [ $WAIT_SECONDS -lt $MAX_WAIT ]; do
            if check_onebot_online; then
                echo "[+] NapCat is now online and ready!"
                break
            fi
            sleep 1
            WAIT_SECONDS=$((WAIT_SECONDS + 1))
            echo -n "."
        done
        echo ""

        if ! check_onebot_online; then
            echo "[!] NapCat is still starting or awaiting QR code login."
            echo "[*] Fetching recent NapCat logs / QR code..."
            $DOCKER_CMD logs --tail 25 napcat || true
            echo ""
            echo "[*] If you need to scan QR code, please scan above using Mobile QQ."
            echo "[*] Waiting for login completion..."
            while ! check_onebot_online; do
                sleep 2
            done
            echo "[+] Login confirmed! OneBot is online!"
        fi
    else
        echo "[!] Docker is not installed. Please install Docker or start NapCat manually."
        echo "    Tip: curl -o napcat.sh https://nclatest.znin.net/napcat.sh && sudo bash napcat.sh"
    fi
fi

# 3. Setup / Activate Python Environment
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 4. Launch Autonomous Agent Daemon
echo "=================================================================="
echo "      Starting QQ AI Companion Daemon...                          "
echo "=================================================================="
exec python3 autonomous_agent.py
