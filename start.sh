#!/usr/bin/env bash
# ==============================================================================
# One-Line All-in-One Launcher for QQ AI Companion Daemon
# Preflight checks mirrors, auto-switches Docker sources, handles QR login & boots
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
check_onebot_online() {
    curl -s --connect-timeout 2 "${ONEBOT_API}/get_version_info" >/dev/null 2>&1 || \
    curl -s --connect-timeout 2 "${ONEBOT_API}/get_status" >/dev/null 2>&1
}

echo "[*] Checking OneBot 11 status on ${ONEBOT_API}..."

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

    if command -v docker >/dev/null 2>&1; then
        # Function to pull NapCat with preflight source checks
        pull_napcat_image() {
            # Check local cache first
            local cached_img
            cached_img=$($DOCKER_CMD images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -i "napcat" | head -1 || true)
            if [ -n "$cached_img" ]; then
                echo "[+] Found cached local NapCat image: $cached_img"
                CHOSEN_IMG="$cached_img"
                return 0
            fi

            echo "[*] Preflight checking Docker mirror availability..."
            echo "------------------------------------------------------------------"

            # Candidates: Name | Host | Image
            local candidates=(
                "DaoCloud Direct|docker.m.daocloud.io|docker.m.daocloud.io/mlikiowa/napcat-docker:latest"
                "DaoCloud Mirror|m.daocloud.io|m.daocloud.io/docker.io/mlikiowa/napcat-docker:latest"
                "DockerPull CN|dockerpull.cn|dockerpull.cn/mlikiowa/napcat-docker:latest"
                "GitHub GHCR (NapCat Node)|ghcr.io|ghcr.io/napneko/nodenapcat:latest"
                "GitHub GHCR (NapCat Docker)|ghcr.io|ghcr.io/napneko/napcat-docker:latest"
                "DockerHub Direct|registry-1.docker.io|mlikiowa/napcat-docker:latest"
            )

            local available_images=()

            for item in "${candidates[@]}"; do
                IFS="|" read -r name host img <<< "$item"
                local code
                code=$(curl -s -k -o /dev/null -w "%{http_code}" --connect-timeout 2 -m 3 "https://${host}/v2/" 2>/dev/null || echo "000")
                if [[ "$code" =~ ^(200|401|301|302)$ ]]; then
                    echo "[✓] Available: $name ($host)"
                    available_images+=("$img")
                else
                    echo "[-] Offline/Blocked: $name ($host)"
                fi
            done

            echo "------------------------------------------------------------------"

            if [ ${#available_images[@]} -gt 0 ]; then
                for img in "${available_images[@]}"; do
                    echo "[*] Downloading NapCat from: $img ..."
                    if $DOCKER_CMD pull "$img"; then
                        echo "[+] Successfully downloaded: $img!"
                        CHOSEN_IMG="$img"
                        $DOCKER_CMD tag "$img" mlikiowa/napcat-docker:latest 2>/dev/null || true
                        $DOCKER_CMD tag "$img" napcat:latest 2>/dev/null || true
                        return 0
                    else
                        echo "[-] Download failed from $img. Trying next available mirror..."
                    fi
                done
            fi

            echo "[!] Attempting direct fallback download..."
            local fallback_images=(
                "docker.m.daocloud.io/mlikiowa/napcat-docker:latest"
                "m.daocloud.io/docker.io/mlikiowa/napcat-docker:latest"
                "dockerpull.cn/mlikiowa/napcat-docker:latest"
                "ghcr.io/napneko/nodenapcat:latest"
                "mlikiowa/napcat-docker:latest"
            )
            for img in "${fallback_images[@]}"; do
                echo "[*] Fallback pull attempt: $img ..."
                if $DOCKER_CMD pull "$img"; then
                    echo "[+] Successfully downloaded: $img!"
                    CHOSEN_IMG="$img"
                    $DOCKER_CMD tag "$img" mlikiowa/napcat-docker:latest 2>/dev/null || true
                    return 0
                fi
            done

            return 1
        }

        # Check existing container
        if $DOCKER_CMD ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^napcat$"; then
            CONTAINER_STATUS=$($DOCKER_CMD inspect -f '{{.State.Status}}' napcat 2>/dev/null || echo "unknown")
            if [ "$CONTAINER_STATUS" = "running" ]; then
                echo "[+] Container 'napcat' is already running."
            else
                echo "[*] Found existing 'napcat' container (status: $CONTAINER_STATUS). Starting..."
                if ! $DOCKER_CMD start napcat >/dev/null 2>&1; then
                    echo "[!] Failed to start existing container. Recreating container..."
                    $DOCKER_CMD rm -f napcat >/dev/null 2>&1 || true
                fi
            fi
        fi

        # Create container if not exists
        if ! $DOCKER_CMD ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^napcat$"; then
            CHOSEN_IMG=""
            if ! pull_napcat_image; then
                echo "[!] Error: All Docker mirrors and download sources failed to pull NapCat."
                echo "    Tip: Check network connectivity or configure Docker mirror in /etc/docker/daemon.json"
                exit 1
            fi

            echo "[*] Starting NapCat container with image: $CHOSEN_IMG ..."
            sudo mkdir -p /opt/napcat/config /opt/napcat/qq 2>/dev/null || mkdir -p "$HOME/.napcat/config" "$HOME/.napcat/qq" 2>/dev/null || true

            $DOCKER_CMD run -d \
                --name napcat \
                --restart always \
                --network host \
                -e WEBUI_TOKEN=napcat \
                -v /opt/napcat/config:/app/napcat/config \
                -v /opt/napcat/qq:/app/.config/QQ \
                "$CHOSEN_IMG"
        fi

        echo "[*] Waiting for NapCat to boot..."
        WAIT_SECONDS=0
        while [ $WAIT_SECONDS -lt 6 ]; do
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
            PUBLIC_IP=$(curl -s --connect-timeout 2 http://ifconfig.me 2>/dev/null || curl -s --connect-timeout 2 http://api.ipify.org 2>/dev/null || echo "127.0.0.1")

            echo "=================================================================="
            echo " [!] NapCat is waiting for Mobile QQ QR code login!"
            echo "------------------------------------------------------------------"
            echo " WebUI Dashboard : http://${PUBLIC_IP}:6099/webui"
            echo " Local Dashboard : http://127.0.0.1:6099/webui"
            echo " WebUI Token     : napcat"
            echo " Direct URL      : http://${PUBLIC_IP}:6099/webui?token=napcat"
            echo "------------------------------------------------------------------"
            echo " * If WebUI is unreachable on Cloud VPS (AliCloud/Tencent/AWS):"
            echo "   1) Allow port 6099 in Cloud Security Group (安全组入方向放行 6099)"
            echo "   2) Or use SSH Tunnel: ssh -L 6099:127.0.0.1:6099 root@${PUBLIC_IP}"
            echo "=================================================================="
            echo ""
            echo "[*] Streaming NapCat console logs & QR code below:"
            echo "    (Please scan with Mobile QQ. Script will auto-proceed once logged in!)"
            echo "------------------------------------------------------------------"

            # Stream docker logs in background so ASCII QR code renders directly in terminal
            $DOCKER_CMD logs -f napcat &
            LOG_PID=$!
            trap 'kill $LOG_PID 2>/dev/null || true; exit 1' INT TERM

            # Poll until OneBot 11 login succeeds
            while ! check_onebot_online; do
                sleep 2
            done

            kill $LOG_PID 2>/dev/null || true
            wait $LOG_PID 2>/dev/null || true
            trap - INT TERM

            echo ""
            echo "=================================================================="
            echo " [✓] Login confirmed! OneBot 11 is now online on ${ONEBOT_API}!"
            echo "=================================================================="
        fi
    else
        echo "[!] Docker is not installed. Please install Docker or start NapCat manually."
        echo "    Tip: curl -o napcat.sh https://nclatest.znin.net/napcat.sh && sudo bash napcat.sh"
    fi
fi

# 3. Setup / Activate Python Environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "[*] Creating Python virtual environment and installing dependencies..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# 4. Launch Autonomous Agent Daemon
echo "=================================================================="
echo "      Starting QQ AI Companion Daemon...                          "
echo "=================================================================="
exec python3 autonomous_agent.py
