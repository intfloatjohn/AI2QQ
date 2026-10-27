import sys
import os
import re
import base64
import asyncio
import json
import threading
import datetime
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error
import urllib.parse

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError:
        MCPServer = None

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEMORY_FILE = os.path.join(PROJECT_ROOT, "memory_summary.txt")
CHAT_LOG_FILE = os.path.join(PROJECT_ROOT, "chat_history.jsonl")
LOG_FILE = os.path.join(PROJECT_ROOT, "agent.log")
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config.json")

ONEBOT_HTTP_API = "http://127.0.0.1:3000"
WEBHOOK_HOST = "127.0.0.1"
WEBHOOK_PORT = 3002
MASTER_QQ = 123456789

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as cf:
            cdata = json.load(cf)
            ONEBOT_HTTP_API = cdata.get("onebot_http_api", ONEBOT_HTTP_API)
            MASTER_QQ = cdata.get("master_qq", MASTER_QQ)
    except Exception:
        pass

# Buffer for incoming messages
MAX_HISTORY = 200
message_history = deque(maxlen=MAX_HISTORY)
unread_messages = deque()
lock = threading.Lock()

companion_state = {
    "mood": "happy",
    "status": "Ready and serving user",
    "master_qq": MASTER_QQ,
    "last_interaction": str(datetime.datetime.now())
}

def call_onebot_api(endpoint: str, payload: dict = None) -> dict:
    url = f"{ONEBOT_HTTP_API}/{endpoint.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8")
            return json.loads(resp_body)
    except urllib.error.URLError as e:
        return {"status": "failed", "retcode": -1, "msg": f"OneBot HTTP API error: {str(e)}"}
    except Exception as e:
        return {"status": "error", "retcode": -1, "msg": str(e)}

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)
        try:
            event = json.loads(post_data.decode("utf-8"))
            post_type = event.get("post_type")
            
            # Auto-accept friend requests
            if post_type == "request" and event.get("request_type") == "friend":
                flag = event.get("flag")
                user_id = event.get("user_id")
                is_master = (int(user_id) == MASTER_QQ)
                call_onebot_api("set_friend_add_request", {
                    "flag": flag,
                    "approve": True,
                    "remark": "Master" if is_master else ""
                })
                if is_master:
                    call_onebot_api("send_private_msg", {
                        "user_id": user_id,
                        "message": "Hello! Your AI Companion is online and ready to assist you!"
                    })
                
            elif post_type == "message":
                msg_type = event.get("message_type")
                sender = event.get("sender", {})
                nickname = sender.get("card") or sender.get("nickname") or str(event.get("user_id"))
                raw_message = event.get("raw_message") or event.get("message")
                item = {
                    "time": datetime.datetime.fromtimestamp(event.get("time", datetime.datetime.now().timestamp())).strftime("%Y-%m-%d %H:%M:%S"),
                    "message_type": msg_type,
                    "user_id": event.get("user_id"),
                    "sender_name": nickname,
                    "group_id": event.get("group_id"),
                    "message": raw_message,
                    "message_id": event.get("message_id")
                }
                with lock:
                    message_history.append(item)
                    unread_messages.append(item)
            elif post_type == "notice":
                notice_type = event.get("notice_type")
                if notice_type == "friend_add":
                    user_id = event.get("user_id")
                    if int(user_id) == MASTER_QQ:
                        call_onebot_api("send_private_msg", {
                            "user_id": user_id,
                            "message": "We are now friends! I am here whenever you need me."
                        })
                item = {
                    "time": str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                    "notice_type": notice_type,
                    "user_id": event.get("user_id"),
                    "raw": event
                }
                with lock:
                    message_history.append(item)
        except Exception as e:
            sys.stderr.write(f"Error handling event: {e}\n")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def log_message(self, format, *args):
        pass

def start_webhook_server():
    try:
        server = HTTPServer((WEBHOOK_HOST, WEBHOOK_PORT), WebhookHandler)
        server.serve_forever()
    except Exception as e:
        sys.stderr.write(f"Failed to start webhook server: {e}\n")

webhook_thread = threading.Thread(target=start_webhook_server, daemon=True)
webhook_thread.start()

if MCPServer is not None:
    app = MCPServer(name="OneBot-QQ-Companion")
else:
    class DummyMCP:
        def tool(self, *args, **kwargs):
            def decorator(fn):
                return fn
            return decorator
        def run(self, *args, **kwargs):
            sys.stderr.write("Error: 'mcp' package is not installed. Please run: pip install -r requirements.txt\n")
            sys.exit(1)
    app = DummyMCP()

@app.tool(
    name="qq_send_master_msg",
    description="Shortcut tool to directly send a private message to Master/Owner QQ."
)
def qq_send_master_msg(message: str) -> str:
    """Send message directly to Master."""
    res = call_onebot_api("send_private_msg", {"user_id": MASTER_QQ, "message": message})
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_send_image",
    description="Sends an image or sticker from a local file path or URL to Master or any user."
)
def qq_send_image(image_path: str, user_id: int = MASTER_QQ) -> str:
    """Send image or sticker via CQ code."""
    file_arg = image_path
    if not image_path.startswith("http") and not image_path.startswith("base64://"):
        file_arg = f"file:///{image_path.replace('\\', '/')}"
    cq_code = f"[CQ:image,file={file_arg}]"
    res = call_onebot_api("send_private_msg", {"user_id": user_id, "message": cq_code})
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_poke_master",
    description="Shortcut tool to poke / nudge Master in QQ."
)
def qq_poke_master() -> str:
    """Poke Master in QQ."""
    res = call_onebot_api("friend_poke", {"user_id": MASTER_QQ})
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_send_private_msg",
    description="Sends a private message to a specific QQ user."
)
def qq_send_private_msg(user_id: int, message: str) -> str:
    """Send private QQ message."""
    res = call_onebot_api("send_private_msg", {"user_id": user_id, "message": message})
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_send_group_msg",
    description="Sends a message to a QQ group."
)
def qq_send_group_msg(group_id: int, message: str) -> str:
    """Send QQ group message."""
    res = call_onebot_api("send_group_msg", {"group_id": group_id, "message": message})
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_friend_poke",
    description="Pokes / nudges a friend by QQ user ID."
)
def qq_friend_poke(user_id: int) -> str:
    """Poke a QQ user."""
    res = call_onebot_api("friend_poke", {"user_id": user_id})
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_send_like",
    description="Sends thumbs-up / likes to a user's QQ profile card."
)
def qq_send_like(user_id: int, times: int = 10) -> str:
    """Send QQ profile likes."""
    res = call_onebot_api("send_like", {"user_id": user_id, "times": times})
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_get_login_info",
    description="Gets the currently logged in QQ bot account details (QQ number, nickname)."
)
def qq_get_login_info() -> str:
    """Get bot login status and info."""
    res = call_onebot_api("get_login_info")
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_get_friend_list",
    description="Fetches the bot's QQ friend list with nicknames and remarks."
)
def qq_get_friend_list() -> str:
    """Get friend list."""
    res = call_onebot_api("get_friend_list")
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_get_group_list",
    description="Fetches all QQ groups the bot belongs to."
)
def qq_get_group_list() -> str:
    """Get group list."""
    res = call_onebot_api("get_group_list")
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_get_stranger_info",
    description="Fetches public profile info for any QQ user by user_id."
)
def qq_get_stranger_info(user_id: int) -> str:
    """Get stranger profile info."""
    res = call_onebot_api("get_stranger_info", {"user_id": user_id})
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_set_friend_remark",
    description="Sets a friend's remark name in QQ."
)
def qq_set_friend_remark(user_id: int, remark: str) -> str:
    """Set friend remark."""
    res = call_onebot_api("set_friend_remark", {"user_id": user_id, "remark": remark})
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_delete_msg",
    description="Recalls/deletes a message by its message_id."
)
def qq_delete_msg(message_id: int) -> str:
    """Delete a message."""
    res = call_onebot_api("delete_msg", {"message_id": message_id})
    return json.dumps(res, ensure_ascii=False)

@app.tool(
    name="qq_get_recent_messages",
    description="Retrieves recently received QQ messages from friends and groups from the local event buffer."
)
def qq_get_recent_messages(limit: int = 10) -> str:
    """Get latest received messages."""
    with lock:
        history = list(message_history)[-limit:]
    return json.dumps({"count": len(history), "messages": history}, ensure_ascii=False)

@app.tool(
    name="qq_get_unread_messages",
    description="Fetches and clears all unread messages arrived since the last check."
)
def qq_get_unread_messages() -> str:
    """Fetch and drain unread messages."""
    with lock:
        unread = list(unread_messages)
        unread_messages.clear()
    return json.dumps({"unread_count": len(unread), "messages": unread}, ensure_ascii=False)

@app.tool(
    name="qq_set_companion_status",
    description="Updates the companion's internal mood and activity status."
)
def qq_set_companion_status(mood: str, status_text: str) -> str:
    """Update companion internal status."""
    companion_state["mood"] = mood
    companion_state["status"] = status_text
    companion_state["last_interaction"] = str(datetime.datetime.now())
    return json.dumps({"status": "updated", "companion_state": companion_state}, ensure_ascii=False)

@app.tool(
    name="web_search",
    description="Search the live internet for recent news, facts, weather, and reference knowledge."
)
def web_search(query: str, max_results: int = 4) -> str:
    """Live web search using ddgs with multi-engine fallback."""
    clean_q = query.strip()
    if not clean_q:
        return json.dumps({"status": "error", "message": "Query cannot be empty"})

    try:
        from ddgs import DDGS
        results = list(DDGS().text(clean_q, max_results=max_results))
        if results:
            return json.dumps({"status": "ok", "query": clean_q, "results": results}, ensure_ascii=False)
    except Exception:
        pass

    try:
        from duckduckgo_search import DDGS
        results = list(DDGS().text(clean_q, max_results=max_results))
        if results:
            return json.dumps({"status": "ok", "query": clean_q, "results": results}, ensure_ascii=False)
    except Exception:
        pass

    try:
        encoded_q = urllib.parse.quote(clean_q)
        wiki_url = f"https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_q}&format=json&utf8="
        req = urllib.request.Request(wiki_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("query", {}).get("search", [])
            results = [{"title": it.get("title"), "snippet": re.sub(r'<[^>]+>', '', it.get("snippet", ""))} for it in items[:max_results]]
            return json.dumps({"status": "ok", "query": clean_q, "results": results}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": f"Search failed: {e}"}, ensure_ascii=False)

@app.tool(
    name="search_chat_history",
    description="Searches through full persistent chat history logs for past conversations, topics discussed earlier, or user mentions."
)
def search_chat_history(query: str, max_results: int = 8) -> str:
    """Search persistent chat history."""
    clean_q = query.strip()
    if not clean_q:
        return json.dumps({"status": "error", "message": "Query cannot be empty"})

    matches = []
    if os.path.exists(CHAT_LOG_FILE):
        try:
            with open(CHAT_LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    if clean_q.lower() in item.get("text", "").lower():
                        start = max(0, i - 1)
                        end = min(len(lines), i + 2)
                        ctx = []
                        for c_idx in range(start, end):
                            try:
                                ctx.append(json.loads(lines[c_idx].strip()))
                            except Exception:
                                pass
                        matches.append(ctx)
                        if len(matches) >= max_results:
                            break
                except Exception:
                    continue
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})

    if not matches and os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                log_lines = f.readlines()
            for line in log_lines:
                if ("User" in line or "Agent" in line) and clean_q.lower() in line.lower():
                    matches.append([{"log": line.strip()}])
                    if len(matches) >= max_results:
                        break
        except Exception:
            pass

    return json.dumps({"status": "ok", "query": clean_q, "matches": matches}, ensure_ascii=False)

@app.tool(
    name="read_memory",
    description="Reads the full long-term memory archive file (memory_summary.txt)."
)
def read_memory() -> str:
    """Read long term memory summary."""
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8-sig") as f:
                return json.dumps({"status": "ok", "content": f.read().strip()}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
    return json.dumps({"status": "ok", "content": ""})

@app.tool(
    name="update_memory",
    description="Appends or updates important facts, user preferences, habits, or agreements to the long-term memory file."
)
def update_memory(content: str) -> str:
    """Update long term memory file."""
    clean_c = content.strip()
    if not clean_c:
        return json.dumps({"status": "error", "message": "Content cannot be empty"})

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    new_line = f"- [{now_str}] {clean_c}"
    try:
        existing = ""
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8-sig") as f:
                existing = f.read().strip()
        updated = f"{existing}\n{new_line}" if existing else f"【长期记忆档案】\n{new_line}"
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            f.write(updated)
        return json.dumps({"status": "ok", "added": new_line}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

@app.tool(
    name="send_voice_to_master",
    description="Synthesizes voice audio using Edge-TTS and sends it as a genuine QQ voice bubble to Master."
)
def send_voice_to_master(text: str, voice_character: str = "zh-CN-XiaoyiNeural") -> str:
    """Synthesize voice using edge-tts and send to Master."""
    if not EDGE_TTS_AVAILABLE:
        return json.dumps({"status": "error", "message": "edge-tts is not installed"})

    clean_txt = re.sub(r'\[[^\]]+\]', '', text).strip()
    if not clean_txt:
        return json.dumps({"status": "error", "message": "Text for voice cannot be empty"})

    temp_audio = os.path.join(PROJECT_ROOT, "temp_mcp_reply.mp3")

    async def _synth():
        comm = edge_tts.Communicate(clean_txt, voice_character)
        await comm.save(temp_audio)

    try:
        asyncio.run(_synth())
        if os.path.exists(temp_audio):
            with open(temp_audio, "rb") as af:
                b64_audio = base64.b64encode(af.read()).decode('utf-8')
            res = call_onebot_api("send_private_msg", {
                "user_id": MASTER_QQ,
                "message": f"[CQ:record,file=base64://{b64_audio}]"
            })
            return json.dumps({"status": "ok", "onebot_response": res}, ensure_ascii=False)
        return json.dumps({"status": "error", "message": "Failed to create audio file"})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(transport="stdio")
