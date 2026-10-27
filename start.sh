#!/usr/bin/env bash
# ==============================================================================
# One-Line All-in-One Launcher for QQ AI Companion Daemon
# Automatically starts NapCat (Docker), displays WebUI token & QR, and boots agent
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

    # Determine docker command
    DOCKER_CMD="docker"
    if ! docker ps >/dev/null 2>&1; then
        if sg docker -c "docker ps" >/dev/null 2>&1; then
            DOCKER_CMD="sg docker -c docker"
        elif sudo -n docker ps >/dev/null 2>&1; then
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
            $DOCKER_CMD start napcat >/dev/null 2>&1 || true
        else
            echo "[*] Creating and starting new NapCat Docker container..."
            sudo mkdir -p /opt/napcat/config 2>/dev/null || mkdir -p "$HOME/.napcat/config" 2>/dev/null || true
            $DOCKER_CMD run -d \
                --name napcat \
                --restart always \
                --network host \
                -v /opt/napcat/config:/app/napcat/config \
                mlikiowa/napcat-docker:latest >/dev/null 2>&1 || true
        fi

        echo "[*] Waiting for NapCat to boot..."
        WAIT_SECONDS=0
        MAX_WAIT=10
        while [ $WAIT_SECONDS -lt $MAX_WAIT ]; do
            if check_onebot_online; then
                echo "[+] NapCat is online and ready!"
                break
            fi
            sleep 1
            WAIT_SECONDS=$((WAIT_SECONDS + 1))
            echo -n "."
        done
        echo ""

        if ! check_onebot_online; then
            # Display WebUI credentials and extract QR code cleanly without hash spam
            python3 -c "
import json, os, re, subprocess

token = 'Unknown'
port = 6099
for p in ['/opt/napcat/config/webui.json', os.path.expanduser('~/.napcat/config/webui.json')]:
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                d = json.load(f)
                token = d.get('token', token)
                port = d.get('port', port)
            break
        except:
            pass

print('==================================================================')
print(' [!] NapCat is waiting for Mobile QQ QR code login!')
print('------------------------------------------------------------------')
print(' WebUI Dashboard : http://127.0.0.1:' + str(port) + '/webui')
print(' WebUI Token     : ' + str(token))
print('==================================================================')

try:
    cmd = '${DOCKER_CMD} logs --tail 300 napcat'
    res = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT)
    urls = re.findall(r'https://txz\.qq\.com/p\?k=[^\s&]+&f=[0-9]+', res)
    if urls:
        latest_url = urls[-1]
        print('\n[*] Mobile QQ QR Login URL (Click or paste in browser):')
        print('    ' + latest_url + '\n')
        try:
            import qrcode
            qr = qrcode.QRCode()
            qr.add_data(latest_url)
            print('Scan this QR code using Mobile QQ:\n')
            qr.print_ascii(invert=True)
        except Exception:
            pass
except Exception:
    pass
"
            echo ""
            echo "[*] Waiting for Mobile QQ scan & login confirmation..."
            while ! check_onebot_online; do
                sleep 2
                echo -n "."
            done
            echo ""
            echo "[+] Login confirmed! OneBot 11 is now online on ${ONEBOT_API}!"
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
