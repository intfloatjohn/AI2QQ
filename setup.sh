#!/usr/bin/env bash
# ==============================================================================
# QQ AI Companion - All-in-One Automated Setup & Launcher (Linux)
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================="
echo "   QQ AI Companion - All-in-One Setup (Linux / Debian)   "
echo "========================================================="
echo ""

# 1. Check if OneBot 11 (NapCat) is already running on port 3000
echo "[*] Checking if OneBot 11 (NapCat) is running on port 3000..."
ONEBOT_ONLINE=false
if curl -s --connect-timeout 2 http://127.0.0.1:3000/get_version_info >/dev/null 2>&1; then
    ONEBOT_ONLINE=true
    echo "[+] Detected OneBot 11 service online on http://127.0.0.1:3000!"
else
    echo "[-] OneBot 11 service is not detected on http://127.0.0.1:3000."
    echo ""
    echo "How would you like to set up NapCatQQ?"
    echo "  1) Docker (Recommended - Auto-pulls image, terminal QR login)"
    echo "  2) Official Linux installer script (Native)"
    echo "  3) Skip (I already have or will start NapCat manually)"
    read -p "Select option [1-3, default: 1]: " napcat_choice
    napcat_choice=${napcat_choice:-1}

    case "$napcat_choice" in
        1)
            echo "[*] Setting up NapCat via Docker..."
            if ! command -v docker &> /dev/null; then
                echo "[!] Docker not found. Attempting to install Docker..."
                sudo apt-get update && sudo apt-get install -y docker.io
                sudo systemctl enable --now docker
            fi
            
            # Check if napcat container already exists
            if sudo docker ps -a --format '{{.Names}}' | grep -q "^napcat$"; then
                echo "[*] Existing napcat container found. Restarting..."
                sudo docker start napcat
            else
                echo "[*] Launching new NapCat Docker container..."
                sudo docker run -d \
                    --name napcat \
                    --restart always \
                    --network host \
                    -v /opt/napcat/config:/app/napcat/config \
                    mlikiowa/napcat-docker:latest
            fi

            echo ""
            echo "========================================================="
            echo " Displaying QR code from Docker logs..."
            echo " Open Mobile QQ and scan the QR code to log in!"
            echo " (Press Ctrl+C after login to continue starting the agent)"
            echo "========================================================="
            echo ""
            sleep 2
            sudo docker logs -f napcat || true
            ;;
        2)
            echo "[*] Running official NapCat Linux installer..."
            curl -fL --connect-timeout 20 -o napcat.sh https://raw.githubusercontent.com/NapNeko/NapCat-Installer/main/script/install.sh
            bash napcat.sh --docker n --cli y --github-proxy 0
            ;;
        *)
            echo "[*] Skipping NapCat setup."
            ;;
    esac
fi

echo ""
echo "=== [2/3] Setting up Python Environment ==="
if ! command -v python3 &> /dev/null; then
    echo "[!] python3 not found. Installing system dependencies..."
    sudo apt-get update && sudo apt-get install -y python3 python3-pip python3-venv
fi

if [ ! -d "venv" ]; then
    echo "[*] Creating Python virtual environment (venv)..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=== [3/3] Checking Configuration ==="
if [ ! -f "config.json" ]; then
    echo "[*] config.json not found. Creating from config.example.json..."
    cp config.example.json config.json
    echo "[!] Please configure your api_key and master_qq in config.json!"
fi

echo ""
echo "========================================================="
echo " Setup complete! Starting QQ AI Companion Daemon...      "
echo " (Press Ctrl+C to stop)                                  "
echo "========================================================="
python3 autonomous_agent.py
