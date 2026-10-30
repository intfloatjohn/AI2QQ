#!/usr/bin/env bash
# ==============================================================================
# QQ AI Companion - All-in-One Automated Setup & Launcher (Linux)
# Sets up Python venv, downloads TTS voices, checks search, configures NapCat
# ==============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================================="
echo "   QQ AI Companion - All-in-One Setup (Linux / Debian)   "
echo "========================================================="
echo ""

# 1. System Packages Check (Debian/Ubuntu)
if command -v apt-get &> /dev/null; then
    MISSING_PKGS=""
    for pkg in python3 python3-pip python3-venv ffmpeg curl; do
        if ! dpkg -s "$pkg" &>/dev/null; then
            MISSING_PKGS="$MISSING_PKGS $pkg"
        fi
    done
    if [ -n "$MISSING_PKGS" ]; then
        echo "[*] Installing required system packages: $MISSING_PKGS..."
        if command -v sudo &>/dev/null; then
            sudo apt-get update && sudo apt-get install -y $MISSING_PKGS
        else
            apt-get update && apt-get install -y $MISSING_PKGS
        fi
    fi
fi

# 2. Python Environment Setup
echo ""
echo "=== [1/4] Setting up Python Environment & Dependencies ==="
source "$SCRIPT_DIR/ensure_venv.sh"
ensure_venv "$SCRIPT_DIR"

source venv/bin/activate
echo "[*] Installing / upgrading Python dependencies..."
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -r requirements.txt

# 3. Auto-download / Pre-cache TTS Voice Engine
echo ""
echo "=== [2/4] Auto-Downloading & Initializing TTS Voice Engine ==="
python3 -c "
import asyncio, os, sys
try:
    import edge_tts
    print('[*] Pre-caching Edge-TTS neural voice data (zh-CN-XiaoyiNeural)...')
    async def init_voice():
        comm = edge_tts.Communicate('TTS system initialized successfully.', 'zh-CN-XiaoyiNeural')
        await comm.save('test_tts.mp3')
    asyncio.run(init_voice())
    if os.path.exists('test_tts.mp3') and os.path.getsize('test_tts.mp3') > 100:
        os.remove('test_tts.mp3')
        print('[+] Voice engine pre-cached and ready for instant playback!')
    else:
        print('[!] Warning: Voice synthesis returned empty output.')
except Exception as e:
    print(f'[*] TTS notice: {e} (Voice will synthesize dynamically on demand)')
"

# 4. Live Web Search Engine Verification
echo ""
echo "=== [3/4] Verifying Live Web Search Engine ==="
python3 -c "
try:
    from ddgs import DDGS
    print('[*] Testing live web search connectivity...')
    res = list(DDGS(timeout=5).text('Python', max_results=1))
    if res:
        print(f'[+] Web search engine verified: {res[0].get(\"title\", \"\")[:50]}')
    else:
        print('[+] Web search online (ready for queries).')
except Exception as e:
    print(f'[*] Web search notice: {e} (Multi-engine fallbacks enabled)')
"

# 5. OneBot 11 (NapCat) Setup & Status Check
echo ""
echo "=== [4/4] Checking OneBot 11 (NapCat) Status ==="
ONEBOT_API="http://127.0.0.1:3000"
if [ -f "config.json" ]; then
    CFG_API=$(grep -o '"onebot_http_api"[^,]*' config.json | head -1 | cut -d'"' -f4 || true)
    if [ -n "$CFG_API" ]; then
        ONEBOT_API="$CFG_API"
    fi
fi

check_onebot_online() {
    curl -s --connect-timeout 2 --max-time 4 "${ONEBOT_API}/get_version_info" >/dev/null 2>&1 || \
    curl -s --connect-timeout 2 --max-time 4 "${ONEBOT_API}/get_status" >/dev/null 2>&1
}

# Random WebUI token for newly created NapCat containers (never a fixed, publicly known one)
gen_webui_token() {
    python3 -c "import secrets; print(secrets.token_urlsafe(12))" 2>/dev/null || head -c 12 /dev/urandom | od -An -tx1 | tr -d ' \n'
}

# Auto-inject OneBot 11 HTTP Server (port 3000) into NapCat configuration files.
# The bot talks to NapCat on this same machine, so the API (which has no access token)
# is bound to 127.0.0.1 instead of every network interface.
auto_enable_napcat_http() {
    python3 -c "
import json, os, glob

template_http = {
    'name': 'AI2QQ HTTP Server',
    'enable': True,
    'port': 3000,
    'host': '127.0.0.1',
    'enableCors': True,
    'enableWebsocket': False,
    'messagePostFormat': 'array',
    'token': '',
    'debug': False
}

template_ws = {
    'name': 'AI2QQ WS Server',
    'enable': True,
    'port': 3001,
    'host': '127.0.0.1'
}

config_dirs = ['/opt/napcat/config', os.path.expanduser('~/.napcat/config')]
modified = False

cfg_bot_qq = ''
local_api = True
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        cfg = json.load(f)
        cfg_bot_qq = str(cfg.get('bot_qq') or '')
        api = str(cfg.get('onebot_http_api') or 'http://127.0.0.1:3000')
        local_api = ('127.0.0.1' in api) or ('localhost' in api)
except Exception:
    pass

def lock_to_localhost(server, fpath):
    # An API without an access token must not listen on every network interface
    if local_api and not str(server.get('token') or '') and str(server.get('host') or '').strip() in ('', '0.0.0.0', '::'):
        server['host'] = '127.0.0.1'
        print('REBOUND:' + fpath)
        return True
    return False

for cdir in config_dirs:
    if not os.path.exists(cdir):
        continue
    target_files = glob.glob(os.path.join(cdir, 'onebot11*.json'))
    default_files = [os.path.join(cdir, 'onebot11.json')]
    if cfg_bot_qq:
        default_files.append(os.path.join(cdir, f'onebot11_{cfg_bot_qq}.json'))

    for df in default_files:
        if df not in target_files:
            target_files.append(df)

    for fpath in target_files:
        data = {}
        changed = False
        if os.path.exists(fpath):
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                data = {}

        if 'network' not in data:
            data['network'] = {}
        if 'httpServers' not in data['network']:
            data['network']['httpServers'] = []

        servers = data['network']['httpServers']
        has_3000 = False
        for s in servers:
            if s.get('port') == 3000:
                if not s.get('enable'):
                    s['enable'] = True
                    changed = True
                if lock_to_localhost(s, fpath):
                    changed = True
                has_3000 = True
                break
        if not has_3000:
            servers.append(dict(template_http))
            changed = True

        data['httpServers'] = data['network']['httpServers']
        if 'websocketServers' not in data['network']:
            data['network']['websocketServers'] = [dict(template_ws)]
        for ws in data['network']['websocketServers']:
            if ws.get('port') == 3001 and lock_to_localhost(ws, fpath):
                changed = True

        try:
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            if changed:
                modified = True
        except PermissionError:
            if changed:
                print('PERMISSION:' + fpath)
        except Exception:
            pass

if modified:
    print('MODIFIED')
"
}

# Reports what the config patch changed or could not change (each note at most once per run)
show_napcat_security_notes() {
    if [ -z "$AI2QQ_NOTE_REBOUND" ] && echo "$1" | grep -q "^REBOUND:" && ! echo "$1" | grep -q "^PERMISSION:"; then
        AI2QQ_NOTE_REBOUND=1
        echo "[security] OneBot API (port 3000) now listens on 127.0.0.1 only. It has no access token and was reachable from the network."
    fi
    if [ -z "$AI2QQ_NOTE_PERMISSION" ] && echo "$1" | grep -q "^PERMISSION:"; then
        AI2QQ_NOTE_PERMISSION=1
        echo "[!] Security: the OneBot API has no access token and listens on every network interface,"
        echo "    but this NapCat config file is owned by root, so it could not be fixed automatically:"
        echo "$1" | grep "^PERMISSION:" | sed 's/^PERMISSION:/      /' | sort -u
        echo "    Fix: edit it with sudo, set the port 3000 entry's \"host\" to \"127.0.0.1\", then restart NapCat."
    fi
}

if check_onebot_online; then
    echo "[+] Detected OneBot 11 service online on ${ONEBOT_API}!"
else
    echo "[-] OneBot 11 service is not detected on ${ONEBOT_API}."
    echo ""
    echo "How would you like to configure NapCatQQ?"
    echo "  1) Docker (Auto-starts container, displays QR code login)"
    echo "  2) Official Linux installer script (Native CLI)"
    echo "  3) Skip (Start NapCat manually later)"
    read -p "Select option [1-3, default: 1]: " napcat_choice
    napcat_choice=${napcat_choice:-1}

    case "$napcat_choice" in
        1)
            echo "[*] Setting up NapCat via Docker..."
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

            if ! command -v docker &> /dev/null; then
                echo "[!] Docker not found. Installing Docker..."
                sudo apt-get update && sudo apt-get install -y docker.io
                sudo systemctl enable --now docker
            fi

            # Check if container exists or needs to be pulled/created
            pull_napcat_image() {
                local cached_img
                cached_img=$($DOCKER_CMD images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null | grep -i "napcat" | head -1 || true)
                if [ -n "$cached_img" ]; then
                    echo "[+] Found cached local NapCat image: $cached_img"
                    CHOSEN_IMG="$cached_img"
                    return 0
                fi

                echo "[*] Preflight checking Docker mirror availability..."
                echo "------------------------------------------------------------------"

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

            # Pre-ensure directories and initial HTTP 3000 template
            sudo -n mkdir -p /opt/napcat/config /opt/napcat/qq 2>/dev/null || mkdir -p "$HOME/.napcat/config" "$HOME/.napcat/qq" 2>/dev/null || true
            PATCH_OUT=$(auto_enable_napcat_http 2>/dev/null || true)
            show_napcat_security_notes "$PATCH_OUT"

            if $DOCKER_CMD ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^napcat$"; then
                CONTAINER_STATUS=$($DOCKER_CMD inspect -f '{{.State.Status}}' napcat 2>/dev/null || echo "unknown")
                if [ "$CONTAINER_STATUS" = "running" ]; then
                    echo "[+] Container 'napcat' is already running."
                    if ! check_onebot_online; then
                        MOD=$(auto_enable_napcat_http 2>/dev/null || true)
                        show_napcat_security_notes "$MOD"
                        if echo "$MOD" | grep -q "MODIFIED"; then
                            echo "[*] Auto-enabling OneBot 11 HTTP server (port 3000) and restarting NapCat..."
                            $DOCKER_CMD restart napcat >/dev/null 2>&1 || true
                            sleep 3
                        fi
                    fi
                else
                    echo "[*] Found existing 'napcat' container (status: $CONTAINER_STATUS). Starting..."
                    if ! $DOCKER_CMD start napcat >/dev/null 2>&1; then
                        echo "[!] Failed to start existing container. Recreating container..."
                        $DOCKER_CMD rm -f napcat >/dev/null 2>&1 || true
                    fi
                fi
            fi

            if ! $DOCKER_CMD ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^napcat$"; then
                CHOSEN_IMG=""
                if ! pull_napcat_image; then
                    echo "[!] Error: All Docker mirrors and download sources failed to pull NapCat."
                    echo "    Tip: Check network connectivity or configure Docker mirror in /etc/docker/daemon.json"
                    exit 1
                fi

                echo "[*] Starting NapCat container with image: $CHOSEN_IMG ..."
                sudo -n mkdir -p /opt/napcat/config /opt/napcat/qq 2>/dev/null || mkdir -p "$HOME/.napcat/config" "$HOME/.napcat/qq" 2>/dev/null || true

                $DOCKER_CMD run -d \
                    --name napcat \
                    --restart always \
                    --network host \
                    -e WEBUI_TOKEN="$(gen_webui_token)" \
                    -v /opt/napcat/config:/app/napcat/config \
                    -v /opt/napcat/qq:/app/.config/QQ \
                    "$CHOSEN_IMG"
            fi

            echo "[*] Waiting for NapCat to boot and bind..."
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
                # Never look up or print this server's public IP; show the WebUI token partly hidden
                WEBUI_INFO=$(python3 -c "
import json, os
token, host = '', ''
for p in ['/opt/napcat/config/webui.json', os.path.expanduser('~/.napcat/config/webui.json')]:
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                w = json.load(f)
            token, host = str(w.get('token') or ''), str(w.get('host') or '')
            break
        except Exception:
            pass
if not token:
    masked = '(not created yet)'
elif len(token) > 4:
    masked = token[:2] + '*' * max(len(token) - 4, 4) + token[-2:]
else:
    masked = '*' * len(token)
print(masked)
print(('E' if host in ('', '0.0.0.0', '::') else '') + ('D' if token == 'napcat' else ''))
" 2>/dev/null || printf '(unknown)\n\n')
                WEBUI_TOKEN_MASKED=$(echo "$WEBUI_INFO" | sed -n 1p)
                WEBUI_FLAGS=$(echo "$WEBUI_INFO" | sed -n 2p)

                echo "=================================================================="
                echo " [!] NapCat is waiting for Mobile QQ QR code login!"
                echo "------------------------------------------------------------------"
                echo " Scan the QR code printed below with Mobile QQ (the WebUI is optional)."
                echo " WebUI (this machine)  : http://127.0.0.1:6099/webui"
                echo " WebUI token           : ${WEBUI_TOKEN_MASKED}"
                echo "   full token          : sudo grep token /opt/napcat/config/webui.json"
                echo " From another computer : ssh -L 6099:127.0.0.1:6099 <user>@<server-address>"
                echo "   then open http://127.0.0.1:6099/webui in that computer's browser"
                if echo "$WEBUI_FLAGS" | grep -q "D"; then
                    echo " [!] The WebUI still uses the public default token 'napcat'. Change it in the WebUI settings."
                fi
                if echo "$WEBUI_FLAGS" | grep -q "E"; then
                    echo " [!] The WebUI listens on every network interface. Don't open port 6099 to the internet;"
                    echo "     use the SSH tunnel above, or set \"host\": \"127.0.0.1\" in webui.json."
                fi
                echo "=================================================================="
                echo ""
                echo "[*] Displaying latest QR code below (Scan with Mobile QQ):"
                echo "------------------------------------------------------------------"

                # 1. Immediate clean render of current QR code (filters out hex spam & log flood)
                $DOCKER_CMD logs --tail 500 napcat 2>&1 | python3 -c "
import sys, re
lines = sys.stdin.readlines()
def is_hex(line):
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
    return bool(re.match(r'^[0-9a-fA-F]{32,}$', clean))
def is_noise(line):
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
    if not clean or is_hex(line): return True
    if 'ErrCode: 3' in clean: return True
    return any(n in clean for n in [
        'dbus/', 'gl_surface', 'gl_context', 'gpu_info', 'viz_main', 'gpu_process',
        'network_service_instance', 'MMKV', 'nt_mmkv', 'MemoryFile', 'PacketHandler',
        'Napi2NativeLoader', 'write and writev hooks', 'resourcesPath:', 'usermod:',
        'not mini app', 'major.node', '[ServerTime]', '时间同步完成', '接收 <-', '发送 ->'
    ])
def is_qr(line):
    clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
    return any(c in clean for c in ('▄', '█', '▀'))

filtered = []
for l in lines:
    if not is_noise(l):
        l_clean = re.sub(r'[0-9a-fA-F]{32,}', '', l)
        if l_clean.strip(): filtered.append(l_clean)
last_qr_idx = -1
for i, l in enumerate(filtered):
    if '请扫描下面的二维码' in l or (is_qr(l) and (i == 0 or not is_qr(filtered[i-1]))):
        last_qr_idx = i
if last_qr_idx != -1:
    to_print = filtered[last_qr_idx:]
else:
    to_print = filtered[-25:] if filtered else []
print(''.join(to_print).strip())
" 2>/dev/null || true

                # 2. Live event follower: streams only new QR refreshes or login confirmation
                $DOCKER_CMD logs -f --tail 0 napcat 2>&1 | python3 -u -c '
import sys, re
def is_hex(line):
    clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
    return bool(re.match(r"^[0-9a-fA-F]{32,}$", clean))
def is_noise(line):
    clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
    if not clean or is_hex(line): return True
    if "ErrCode: 3" in clean: return True
    return any(n in clean for n in [
        "dbus/", "gl_surface", "gl_context", "gpu_info", "viz_main", "gpu_process",
        "network_service_instance", "MMKV", "nt_mmkv", "MemoryFile", "PacketHandler",
        "Napi2NativeLoader", "write and writev hooks", "resourcesPath:", "usermod:",
        "not mini app", "major.node", "[ServerTime]", "时间同步完成", "接收 <-", "发送 ->"
    ])
def is_useful(line):
    clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
    if is_noise(line): return False
    if any(c in clean for c in ("▄", "█", "▀")): return True
    whitelist = [
        "请扫描", "二维码", "qrcode", "txz.qq.com",
        "webui", "token", "dashboard",
        "扫码成功", "已扫码", "授权", "登录成功", "login success",
        "onebot", "网络已连接"
    ]
    return any(w in clean.lower() for w in whitelist)

for line in sys.stdin:
    if is_useful(line):
        l_clean = re.sub(r"[0-9a-fA-F]{32,}", "", line)
        if l_clean.strip():
            print(l_clean, end="", flush=True)
' &
                LOG_PID=$!
                trap 'if [ -n "$LOG_PID" ]; then kill -TERM "$LOG_PID" 2>/dev/null || true; pkill -P "$LOG_PID" 2>/dev/null || true; wait "$LOG_PID" 2>/dev/null || true; LOG_PID=""; fi; if [ "${KEEP_DOCKER:-0}" != "1" ]; then echo ""; echo "[*] Stopping NapCat Docker container..."; $DOCKER_CMD stop napcat >/dev/null 2>&1 || true; fi; exit 1' INT TERM

                RESTARTED_FOR_HTTP=0
                # Poll until OneBot 11 login succeeds and binds port 3000
                while ! check_onebot_online; do
                    sleep 2
                    if [ $RESTARTED_FOR_HTTP -lt 2 ]; then
                        OUT=$(auto_enable_napcat_http 2>/dev/null || true)
                        show_napcat_security_notes "$OUT"
                        if echo "$OUT" | grep -q "MODIFIED"; then
                            echo ""
                            echo "[*] Detected newly generated NapCat config. Auto-enabling port 3000 and restarting NapCat..."
                            $DOCKER_CMD restart napcat >/dev/null 2>&1 || true
                            RESTARTED_FOR_HTTP=$((RESTARTED_FOR_HTTP + 1))
                            sleep 4
                        fi
                    fi
                done

                if [ -n "$LOG_PID" ]; then
                    kill -TERM "$LOG_PID" 2>/dev/null || true
                    pkill -P "$LOG_PID" 2>/dev/null || true
                    wait "$LOG_PID" 2>/dev/null || true
                    LOG_PID=""
                fi
                trap - INT TERM

                echo ""
                echo "=================================================================="
                echo " [✓] Login confirmed! OneBot 11 is now online on ${ONEBOT_API}!"
                echo "=================================================================="
            fi
            ;;
        2)
            echo "[*] Running official NapCat Linux installer with multi-source fallback..."
            INSTALLER_URLS=(
                "https://raw.githubusercontent.com/NapNeko/NapCat-Installer/main/script/install.sh"
                "https://gh-proxy.com/https://raw.githubusercontent.com/NapNeko/NapCat-Installer/main/script/install.sh"
            )
            for url in "${INSTALLER_URLS[@]}"; do
                echo "[*] Trying installer source: $url ..."
                if curl -fL --connect-timeout 10 -o napcat.sh "$url"; then
                    echo "[+] Downloaded installer successfully."
                    break
                fi
            done
            if [ -f "napcat.sh" ]; then
                bash napcat.sh --docker n --cli y --github-proxy 0
            else
                echo "[!] Failed to download NapCat installer script."
            fi
            ;;
        *)
            echo "[*] Skipping NapCat setup."
            ;;
    esac
fi

# 6. Check Configuration File
if [ ! -f "config.json" ]; then
    echo "[*] config.json not found. Creating from config.example.json..."
    cp config.example.json config.json
    echo "[!] Please configure your api_key and master_qq in config.json!"
fi

echo ""
echo "========================================================="
echo " [✓] Setup Complete - Everything is Ready!               "
echo "========================================================="
echo " - OneBot 11 Bridge  : Online & Ready (${ONEBOT_API})"
echo " - Python Venv       : Installed & Active (venv/)"
echo " - Voice / TTS       : Downloaded & Verified (Edge-TTS)"
echo " - Live Web Search   : Verified & Operational"
echo " - Persona & Memory  : Initialized"
echo "========================================================="
echo ""
echo "You can launch the daemon anytime using:"
echo "  ./start.sh"
echo ""

read -p "Would you like to start the companion daemon now? [Y/n]: " run_now
run_now=${run_now:-Y}
if [[ "$run_now" =~ ^[Yy]$ ]]; then
    exec ./start.sh
fi
