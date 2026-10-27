#!/usr/bin/env python3
"""Autonomous 24/7 AI Companion Daemon for QQ (OneBot 11 Framework)
Features:
- Multi-Message Intelligent Batching & History Preservation (No dropped messages)
- Persistent Full Chat History Logging & In-Depth Chat History Search
- Real-Time Dynamic Memory Updates & Self-Determined Memory Inspection
- Live Web Search (DuckDuckGo / DDGS + Multi-engine Fallbacks)
- Voice Generation (Edge-TTS) & Natural Voice Message Synthesis
- Multimodal Vision: Dual fallback download (QQ HTTP headers + OneBot get_image API)
- Bilingual Support: Seamlessly handles Chinese and English personas, commands, and tags
- Rich Stickers & Faces: Native QQ faces and custom sticker files (Used naturally, not mechanically)
- Model-Agnostic Persona: Loaded from persona/system_prompt_zh.md or system_prompt_en.md
- Configurable Message Length Guidelines (Soft, model-decided limits in config.json)
- Real-Human QQ Chat Tone: Natural, varied, zero *action* notations
"""

import os
import sys
import re
import json
import time
import html
import base64
import signal
import asyncio
import logging
import datetime
import traceback
import threading
import urllib.request
import urllib.error
import urllib.parse

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PERSONA_DIR = os.path.join(BASE_DIR, "persona")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
CHAT_LOG_FILE = os.path.join(BASE_DIR, "chat_history.jsonl")
MEMORY_SUMMARY_FILE = os.path.join(BASE_DIR, "memory_summary.txt")
LOG_FILE = os.path.join(BASE_DIR, "agent.log")
STICKERS_DIR = os.path.join(BASE_DIR, "stickers")

config = {
    "api_type": "openai",
    "base_url": "https://openrouter.ai/api/v1/chat/completions",
    "api_key": "",
    "model": "google/gemini-3.8-flash",
    "master_qq": 123456789,
    "bot_qq": 987654321,
    "onebot_http_api": "http://127.0.0.1:3000",
    "language": "zh",
    "poll_interval_sec": 1.2,
    "debounce_delay_sec": 1.8,
    "compact_threshold": 30,
    "compact_keep_recent": 12,
    "max_tokens": 1200,
    "single_message_limit_hint": "日常闲聊保持自然随性节奏（几十至百余字），遇到需要深入分析、解答、分享或长篇交谈时可自主扩展，由模型根据语境自主决定回复长短，避免机械受限。",
    "single_message_limit_hint_en": "Keep casual chat relaxed and natural (a couple sentences); feel free to expand whenever detailed explanations, storytelling, or deeper discussions are needed. The model flexibly decides the length based on context.",
    "enable_web_search": True,
    "max_search_results": 4,
    "log_level": "INFO",
    "enable_voice_reply": False,
    "voice_character": "zh-CN-XiaoyiNeural"
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            print(f"[WARN] Failed to load config.json: {e}")

load_config()

def setup_logging():
    level_name = config.get("log_level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ],
        force=True
    )

setup_logging()

# Bilingual QQ Faces Mapping
QQ_FACES = {
    # Chinese
    "贴贴": 219, "蹭一蹭": 219, "抱抱": 222, "拥抱": 49,
    "摸摸头": 219, "害羞": 6, "脸红": 6, "亲亲": 109, "啵啵": 109,
    "委屈": 106, "可爱": 21, "微笑": 14, "比心": 319, "爱心": 66,
    "猫猫": 307, "喵喵": 307, "调皮": 12, "眨眼": 172,
    "呲牙": 13, "偷笑": 20, "流泪": 5, "睡": 8, "期待": 294,
    # English
    "hug": 222, "cuddle": 219, "pat": 219, "shy": 6, "blush": 6,
    "kiss": 109, "pout": 106, "cute": 21, "smile": 14,
    "heart": 319, "love": 66, "cat": 307, "wink": 172, "laugh": 13, "grin": 13,
    "cry": 5, "sleep": 8, "sleepy": 8
}

conversation_history = []
long_term_memory = ""
processed_message_ids = set()
memory_lock = threading.Lock()

# Tools definitions for OpenAI function calling
AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网实时搜索互联网最新的资讯、时事、天气、百科、知识或技术问题 (Live web search)",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "搜索关键词或检索短语 / Search query"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_chat_history",
            "description": "检索过往的完整历史聊天记录，回忆过去发生过的对话或提及的事情 (Search persistent chat history logs)",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用于搜索历史聊天记录的关键词 / Keyword to search"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "查阅完整的长期记忆档案文件 (Read persistent long-term memory archive)",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_memory",
            "description": "实时向长期记忆档案写入用户的重要信息、生活习惯、喜好、约定或新事实 (Save new fact to memory in real time)",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "要保存的信息或事实 / Content to memorize"
                    }
                },
                "required": ["content"]
            }
        }
    }
]

def load_system_prompt() -> str:
    lang = config.get("language", "zh").lower()
    fname = "system_prompt_en.md" if lang == "en" else "system_prompt_zh.md"
    fpath = os.path.join(PERSONA_DIR, fname)
    if not os.path.exists(fpath):
        fpath = os.path.join(PERSONA_DIR, "system_prompt.md")
    
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8-sig") as f:
                prompt_text = f.read().strip()
                hint_key = "single_message_limit_hint_en" if lang == "en" else "single_message_limit_hint"
                limit_hint = config.get(hint_key, config.get("single_message_limit_hint", ""))
                if limit_hint:
                    section_title = "【Reply Length & Style Reference】:" if lang == "en" else "【回复长度与风格参考】:"
                    prompt_text += f"\n\n{section_title}\n{limit_hint}"
                return prompt_text
        except Exception as e:
            logging.warning(f"Failed to load {fpath}: {e}")
    return "You are an intelligent AI companion on QQ. Talk naturally just like a real friend. Absolutely no *action* notations."

def load_memory_and_history():
    global conversation_history, long_term_memory
    with memory_lock:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8-sig") as f:
                    conversation_history = json.load(f)
                    if not isinstance(conversation_history, list):
                        conversation_history = []
            except Exception:
                conversation_history = []
        
        if os.path.exists(MEMORY_SUMMARY_FILE):
            try:
                with open(MEMORY_SUMMARY_FILE, "r", encoding="utf-8-sig") as f:
                    long_term_memory = f.read().strip()
            except Exception:
                long_term_memory = ""

def save_history():
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(conversation_history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.warning(f"Failed to save history: {e}")

def save_long_term_memory():
    try:
        with open(MEMORY_SUMMARY_FILE, "w", encoding="utf-8") as f:
            f.write(long_term_memory)
    except Exception as e:
        logging.warning(f"Failed to save long-term memory: {e}")

def append_to_full_chat_history(role: str, text: str, sender_id: int = None, has_image: bool = False, msg_id: int = None):
    """Permanently logs all user and bot messages into chat_history.jsonl."""
    try:
        entry = {
            "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "role": role,
            "sender_id": sender_id or (config.get("master_qq") if role == "user" else config.get("bot_qq")),
            "msg_id": msg_id,
            "has_image": has_image,
            "text": text
        }
        with open(CHAT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logging.warning(f"Failed to append to {CHAT_LOG_FILE}: {e}")

load_memory_and_history()

def update_memory_realtime(content: str) -> str:
    """Updates memory_summary.txt immediately in real-time."""
    global long_term_memory
    clean_content = content.strip()
    if not clean_content:
        return "记忆内容为空。"

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    with memory_lock:
        existing = ""
        if os.path.exists(MEMORY_SUMMARY_FILE):
            try:
                with open(MEMORY_SUMMARY_FILE, "r", encoding="utf-8-sig") as f:
                    existing = f.read().strip()
            except Exception:
                existing = ""

        new_entry = f"- [{now_str}] {clean_content}"
        if existing:
            updated = f"{existing}\n{new_entry}"
        else:
            updated = f"【长期记忆档案】\n{new_entry}"

        long_term_memory = updated
        save_long_term_memory()

    logging.info(f"Realtime Memory Updated: {new_entry}")
    return f"已成功将新信息记入长期记忆：{clean_content}"

def read_memory_file() -> str:
    """Reads the full memory_summary.txt."""
    with memory_lock:
        if os.path.exists(MEMORY_SUMMARY_FILE):
            try:
                with open(MEMORY_SUMMARY_FILE, "r", encoding="utf-8-sig") as f:
                    content = f.read().strip()
                    return content if content else "长期记忆档案目前为空。"
            except Exception as e:
                return f"读取记忆失败: {e}"
    return "长期记忆档案目前为空。"

def search_chat_history(query: str, max_results: int = 8) -> str:
    """Searches chat_history.jsonl (and agent.log as fallback) for matching dialogue turns."""
    clean_q = query.strip()
    if not clean_q:
        return "搜索关键词不能为空。"

    matches = []
    # 1. Search full chat history jsonl
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
                    text = item.get("text", "")
                    if clean_q.lower() in text.lower():
                        start = max(0, i - 1)
                        end = min(len(lines), i + 2)
                        context_snippets = []
                        for c_idx in range(start, end):
                            try:
                                c_entry = json.loads(lines[c_idx].strip())
                                role_label = "User" if c_entry.get("role") == "user" else "Assistant"
                                context_snippets.append(f"[{c_entry.get('time')}] {role_label}: {c_entry.get('text')}")
                            except Exception:
                                pass
                        matches.append("\n".join(context_snippets))
                        if len(matches) >= max_results:
                            break
                except Exception:
                    continue
        except Exception as e:
            logging.warning(f"Error searching {CHAT_LOG_FILE}: {e}")

    # 2. Fallback search in agent.log
    if not matches and os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                log_lines = f.readlines()
            for line in log_lines:
                if ("User" in line or "Agent" in line) and clean_q.lower() in line.lower():
                    matches.append(line.strip())
                    if len(matches) >= max_results:
                        break
        except Exception as e:
            logging.warning(f"Error searching {LOG_FILE}: {e}")

    if matches:
        return "【过往相关聊天记录 / Chat History Matches】:\n" + "\n---\n".join(matches)
    return f"未找到关于“{clean_q}”的过往聊天记录。"

def web_search(query: str, max_results: int = 4) -> str:
    """Executes live web search using ddgs with multiple resilient fallbacks."""
    if not config.get("enable_web_search", True):
        return "网络搜索功能已被禁用。"
    clean_q = query.strip()
    if not clean_q:
        return "搜索关键词不能为空。"

    # Method 1: ddgs
    try:
        from ddgs import DDGS
        results = list(DDGS().text(clean_q, max_results=max_results))
        if results:
            lines = []
            for i, r in enumerate(results):
                title = r.get("title", "")
                body = r.get("body", "") or r.get("snippet", "")
                href = r.get("href", "") or r.get("link", "")
                lines.append(f"[{i+1}] {title}\n摘要: {body}\n链接: {href}")
            return "\n\n".join(lines)
    except Exception as e:
        logging.warning(f"ddgs search failed: {e}")

    # Method 2: duckduckgo_search fallback
    try:
        from duckduckgo_search import DDGS
        results = list(DDGS().text(clean_q, max_results=max_results))
        if results:
            lines = []
            for i, r in enumerate(results):
                title = r.get("title", "")
                body = r.get("body", "") or r.get("snippet", "")
                href = r.get("href", "")
                lines.append(f"[{i+1}] {title}\n摘要: {body}\n链接: {href}")
            return "\n\n".join(lines)
    except Exception as e:
        logging.warning(f"duckduckgo_search fallback failed: {e}")

    # Method 3: Wikipedia API fallback
    try:
        encoded_q = urllib.parse.quote(clean_q)
        wiki_url = f"https://zh.wikipedia.org/w/api.php?action=query&list=search&srsearch={encoded_q}&format=json&utf8="
        req = urllib.request.Request(wiki_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            items = data.get("query", {}).get("search", [])
            if items:
                lines = []
                for i, it in enumerate(items[:max_results]):
                    title = it.get("title", "")
                    snippet = re.sub(r'<[^>]+>', '', it.get("snippet", ""))
                    lines.append(f"[{i+1}] {title}\n摘要: {snippet}")
                return "\n\n".join(lines)
    except Exception as e:
        logging.warning(f"Wiki fallback failed: {e}")

    return f"未能获取到“{clean_q}”的有效搜索结果。"

def trigger_auto_compact():
    global conversation_history, long_term_memory
    with memory_lock:
        threshold = config.get("compact_threshold", 30)
        keep_recent = config.get("compact_keep_recent", 12)
        if len(conversation_history) < threshold:
            return
        to_archive = conversation_history[:-keep_recent]
        conversation_history = conversation_history[-keep_recent:]
        save_history()

    logging.info(f"AutoCompact: Archiving {len(to_archive)} older turns into long-term memory...")

    formatted_dialogue = ""
    for item in to_archive:
        role_label = "User" if item.get("role") == "user" else "Companion"
        formatted_dialogue += f"{role_label}: {item.get('content')}\n"

    lang = config.get("language", "zh").lower()
    if lang == "en":
        compact_prompt = (
            "You are a long-term memory synthesis assistant for an AI companion. "
            "Please review the 【Current Long-Term Memory】 and the 【Dialogue to Archive】, "
            "then distill an updated, concise summary of key facts, user preferences, habits, and shared experiences (under 300 words).\n\n"
            f"【Current Long-Term Memory】:\n{long_term_memory or 'None yet'}\n\n"
            f"【Dialogue to Archive】:\n{formatted_dialogue}\n"
        )
    else:
        compact_prompt = (
            "你是一个专用于AI伴侣的长期记忆提炼助手。请阅读【现有长期记忆】和【即将归档的旧对话记录】，"
            "更新并提炼出一份精炼的【长期记忆摘要】（400字以内）。\n\n"
            f"【现有长期记忆】:\n{long_term_memory or '暂无既往长期记忆'}\n\n"
            f"【即将归档的旧对话记录】:\n{formatted_dialogue}\n\n"
            "提炼原则：保留对方的生活习惯、喜好、作息、现实情况、重要吩咐与二人共同经历的事实，分条列出。"
        )

    try:
        updated_summary = raw_llm_call(compact_prompt, max_tokens=800)
        if updated_summary and len(updated_summary) > 10:
            with memory_lock:
                long_term_memory = updated_summary.strip()
                save_long_term_memory()
            logging.info("AutoCompact: Successfully updated memory_summary.txt!")
    except Exception as e:
        logging.error(f"AutoCompact failed: {e}")

def raw_llm_call(prompt: str, max_tokens: int = 800) -> str:
    base = config.get("base_url", "https://openrouter.ai/api/v1/chat/completions").rstrip("/")
    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.get('api_key', '').strip()}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "QQ AI Companion Memory"
    }

    payload = {
        "model": config.get("model", "google/gemini-3.8-flash"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": max_tokens
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

def call_onebot_api(endpoint: str, payload: dict) -> dict:
    url = f"{config['onebot_http_api']}/{endpoint}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logging.error(f"OneBot API {endpoint} error: {e}")
        return {"status": "error", "message": str(e)}

def download_image_as_base64(img_url: str, file_id: str = "") -> str:
    clean_url = html.unescape(img_url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://qun.qq.com/"
    }
    try:
        req = urllib.request.Request(clean_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
            if len(data) > 100:
                return base64.b64encode(data).decode("utf-8")
    except Exception as e:
        logging.warning(f"Direct download failed ({e}), checking OneBot local cache for file={file_id}...")

    if file_id:
        try:
            res = call_onebot_api("get_image", {"file": file_id})
            if res.get("status") == "ok":
                local_path = res.get("data", {}).get("file", "")
                if local_path and os.path.exists(local_path):
                    with open(local_path, "rb") as f:
                        return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            logging.error(f"Fallback get_image failed: {e}")
    return ""

def parse_incoming_cq_content(raw_text: str):
    cq_img_pattern = re.compile(r'\[CQ:image,[^\]]*?\]', re.IGNORECASE)
    images_b64 = []
    for match in cq_img_pattern.finditer(raw_text):
        tag = match.group(0)
        url_match = re.search(r'url=([^\],]+)', tag)
        file_match = re.search(r'file=([^\],]+)', tag)
        url = url_match.group(1).strip() if url_match else ""
        file_id = file_match.group(1).strip() if file_match else ""
        if url:
            b64 = download_image_as_base64(url, file_id)
            if b64:
                images_b64.append(b64)

    clean_text = cq_img_pattern.sub('', raw_text)
    has_voice = "[CQ:record" in clean_text
    lang = config.get("language", "zh").lower()
    voice_note = " (sent a voice message) " if lang == "en" else "（收到语音消息）"
    clean_text = re.sub(r'\[CQ:record,[^\]]+\]', voice_note, clean_text)
    clean_text = re.sub(r'\[CQ:[^\]]+\]', '', clean_text).strip()
    return clean_text, images_b64, has_voice

def sanitize_reply(text: str) -> str:
    cleaned = re.sub(r'\*[^*]+\*', '', text)
    cleaned = re.sub(r'（[^）]+）', '', cleaned)
    cleaned = re.sub(r'\([^)]+\)', '', cleaned)
    cleaned = cleaned.strip()

    lang = config.get("language", "zh").lower()
    if lang == "zh" and re.search(r'[\u4e00-\u9fff]', cleaned):
        cleaned = re.sub(r'nya~', '喵~', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'nya', '喵', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()

async def synthesize_voice_file(text: str, output_path: str):
    if not EDGE_TTS_AVAILABLE:
        return False
    voice = config.get("voice_character", "zh-CN-XiaoyiNeural")
    clean_txt = clean_tags(text)
    if not clean_txt:
        return False
    communicate = edge_tts.Communicate(clean_txt, voice)
    await communicate.save(output_path)
    return True

def send_voice_message(text: str):
    if not EDGE_TTS_AVAILABLE:
        logging.warning("edge-tts is not installed. Voice synthesis skipped.")
        return
    try:
        temp_audio = os.path.join(BASE_DIR, "temp_reply.mp3")
        success = asyncio.run(synthesize_voice_file(text, temp_audio))
        if success and os.path.exists(temp_audio):
            try:
                with open(temp_audio, "rb") as af:
                    b64_audio = base64.b64encode(af.read()).decode('utf-8')
                call_onebot_api("send_private_msg", {
                    "user_id": config["master_qq"],
                    "message": f"[CQ:record,file=base64://{b64_audio}]"
                })
            except Exception as fe:
                logging.error(f"Failed to encode/send voice: {fe}")
    except Exception as e:
        logging.error(f"Failed to synthesize/send voice: {e}")

def execute_action_tags(reply_text: str):
    # 1. Custom Stickers (Supports [sticker: heart], [Sticker: heart], [Send Sticker: heart], [发贴图: heart])
    sticker_matches = re.findall(r'\[(?:发贴图|Send Sticker|Sticker|sticker):\s*([^\]]+)\]', reply_text, re.IGNORECASE)
    for kw in sticker_matches:
        kw = kw.strip().lower()
        matched_file = None
        if os.path.exists(STICKERS_DIR):
            for fname in os.listdir(STICKERS_DIR):
                base_name, _ = os.path.splitext(fname)
                if kw in base_name.lower() or base_name.lower() in kw:
                    matched_file = fname
                    break
        if matched_file:
            path = os.path.join(STICKERS_DIR, matched_file)
            if os.path.exists(path):
                try:
                    with open(path, "rb") as img_f:
                        b64_img = base64.b64encode(img_f.read()).decode('utf-8')
                    call_onebot_api("send_private_msg", {
                        "user_id": config["master_qq"],
                        "message": f"[CQ:image,file=base64://{b64_img}]"
                    })
                except Exception as ie:
                    logging.error(f"Failed to encode/send sticker image: {ie}")

    # 2. QQ Faces (Supports [face: smile], [Face: hug], [Emoji: shy], [Send Face: pat], [发表情: 贴贴])
    face_matches = re.findall(r'\[(?:发表情|Send Face|Face|face|Emoji|emoji):\s*([^\]]+)\]', reply_text, re.IGNORECASE)
    for kw in face_matches:
        kw = kw.strip().lower()
        face_id = QQ_FACES.get(kw)
        if not face_id:
            for k, fid in QQ_FACES.items():
                if k in kw or kw in k:
                    face_id = fid
                    break
        if face_id:
            call_onebot_api("send_private_msg", {
                "user_id": config["master_qq"],
                "message": f"[CQ:face,id={face_id}]"
            })

    # 3. Voice Message (Supports [voice: text], [Voice: text], [Send Voice: text], [发语音: text])
    voice_matches = re.findall(r'\[(?:发语音|Send Voice|Voice|voice):\s*([^\]]+)\]', reply_text, re.IGNORECASE)
    for v_text in voice_matches:
        send_voice_message(v_text)

    # 4. Global Voice Mode
    if config.get("enable_voice_reply", False) and not voice_matches:
        clean_msg = clean_tags(reply_text)
        if clean_msg:
            send_voice_message(clean_msg)

    # 5. Interactivity: Pokes & Likes (Supports [poke], [Poke], [Interact: Poke], [like], [Like], [Interact: Like])
    if re.search(r'\[(?:互动|Interact|interact):\s*(?:戳一戳|Poke|poke)\]|\[(?:poke|Poke)\]', reply_text, re.IGNORECASE):
        call_onebot_api("friend_poke", {"user_id": config["master_qq"]})
    if re.search(r'\[(?:互动|Interact|interact):\s*(?:点赞|Like|like)\]|\[(?:like|Like)\]', reply_text, re.IGNORECASE):
        call_onebot_api("send_like", {"user_id": config["master_qq"], "times": 10})

def clean_tags(reply_text: str) -> str:
    text = re.sub(r'\[(?:发贴图|Send Sticker|Sticker|sticker):[^\]]+\]', '', reply_text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:发表情|Send Face|Face|face|Emoji|emoji):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:发语音|Send Voice|Voice|voice):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:互动|Interact|interact):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:poke|Poke|like|Like)\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:更新记忆|Update Memory|update_memory|remember|Remember):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:查看记忆|Read Memory|read_memory|Memory|memory)\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:搜索|Search|search|web_search):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:搜索聊天记录|Search History|search_history|history):[^\]]+\]', '', text, flags=re.IGNORECASE)
    return text.strip()

def execute_tool_call(tool_name: str, arguments: dict) -> str:
    """Executes a tool call and returns the observation string."""
    try:
        if tool_name == "web_search":
            query = arguments.get("query", "")
            return web_search(query, max_results=config.get("max_search_results", 4))
        elif tool_name == "search_chat_history":
            query = arguments.get("query", "")
            return search_chat_history(query)
        elif tool_name == "read_memory":
            return read_memory_file()
        elif tool_name == "update_memory":
            content = arguments.get("content", "")
            return update_memory_realtime(content)
        else:
            return f"Unknown tool: {tool_name}"
    except Exception as e:
        return f"Tool execution error: {e}"

def query_llm(user_prompt: str, images_b64: list) -> str:
    load_config()
    system_prompt = load_system_prompt()

    lang = config.get("language", "zh").lower()
    if long_term_memory:
        mem_title = "【Persistent Long-Term Memory Overview】:" if lang == "en" else "【长期记忆概览（可使用 [查看记忆] 获取完整版，使用 [更新记忆: 内容] 实时补充）】:"
        system_prompt += f"\n\n{mem_title}\n{long_term_memory}"

    base = config.get("base_url", "https://openrouter.ai/api/v1/chat/completions").rstrip("/")
    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"

    api_key = config.get("api_key", "").strip()
    if not api_key:
        return "Please configure a valid API Key in config.json to start chatting."

    messages = [{"role": "system", "content": system_prompt}]
    with memory_lock:
        for turn in conversation_history:
            if isinstance(turn, dict) and "role" in turn and "content" in turn:
                messages.append({"role": turn["role"], "content": turn["content"]})

    if images_b64:
        content_items = []
        caption = user_prompt if user_prompt else ("(Sent an image)" if lang == "en" else "（对方发送了图片）")
        content_items.append({"type": "text", "text": caption})
        for b64 in images_b64:
            content_items.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
        current_turn = {"role": "user", "content": content_items}
        history_record_text = f"{user_prompt} [图片]" if user_prompt else "[图片]"
    else:
        current_turn = {"role": "user", "content": user_prompt}
        history_record_text = user_prompt

    messages.append(current_turn)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "QQ AI Companion"
    }

    max_tokens_val = int(config.get("max_tokens", 1200))

    # ReAct tool-execution loop (up to 3 turns)
    for iteration in range(3):
        payload = {
            "model": config.get("model", "google/gemini-3.8-flash"),
            "messages": messages,
            "temperature": 0.72,
            "max_tokens": max_tokens_val,
            "tools": AVAILABLE_TOOLS
        }

        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=50) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as he:
            err_body = he.read().decode("utf-8") if he.fp else str(he)
            logging.warning(f"LLM call with tools failed ({he.code}): {err_body[:200]}, retrying without tools parameter...")
            payload.pop("tools", None)
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=50) as resp:
                data = json.loads(resp.read().decode("utf-8"))

        choice = data.get("choices", [{}])[0]
        message_obj = choice.get("message", {})
        raw_reply = message_obj.get("content", "") or ""
        tool_calls = message_obj.get("tool_calls", [])

        # Check for inline command tags in raw_reply if tool_calls not used
        inline_search = re.search(r'\[(?:搜索|Search|search|web_search):\s*([^\]]+)\]', raw_reply, re.IGNORECASE)
        inline_chat_search = re.search(r'\[(?:搜索聊天记录|Search History|search_history|history):\s*([^\]]+)\]', raw_reply, re.IGNORECASE)
        inline_read_mem = bool(re.search(r'\[(?:查看记忆|Read Memory|read_memory|Memory|memory)\]', raw_reply, re.IGNORECASE))
        inline_update_mem = re.findall(r'\[(?:更新记忆|Update Memory|update_memory|Remember|remember):\s*([^\]]+)\]', raw_reply, re.IGNORECASE)

        for mem_content in inline_update_mem:
            update_memory_realtime(mem_content)

        # 1. Native Function Calling
        if tool_calls:
            messages.append(message_obj)
            for tc in tool_calls:
                call_id = tc.get("id", "call_0")
                fn_name = tc.get("function", {}).get("name", "")
                fn_args_str = tc.get("function", {}).get("arguments", "{}")
                try:
                    fn_args = json.loads(fn_args_str)
                except Exception:
                    fn_args = {}
                logging.info(f"Executing Function Call: {fn_name}({fn_args})")
                obs = execute_tool_call(fn_name, fn_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": obs
                })
            continue

        # 2. Inline Command Tag Handling
        if inline_search or inline_chat_search or inline_read_mem:
            obs_lines = []
            if inline_search:
                q = inline_search.group(1).strip()
                logging.info(f"Executing Inline Command: [Search: {q}]")
                obs_lines.append(f"【Search Results - {q}】:\n{web_search(q)}")
            if inline_chat_search:
                cq = inline_chat_search.group(1).strip()
                logging.info(f"Executing Inline Command: [Search History: {cq}]")
                obs_lines.append(f"【Chat History Matches - {cq}】:\n{search_chat_history(cq)}")
            if inline_read_mem:
                logging.info("Executing Inline Command: [Read Memory]")
                obs_lines.append(f"【Memory Archive Content】:\n{read_memory_file()}")

            messages.append({"role": "assistant", "content": raw_reply})
            hint_str = "【System: Tool Observations】\n" + "\n\n".join(obs_lines) + "\nPlease reply naturally to the user based on these retrieved observations."
            messages.append({"role": "user", "content": hint_str})
            continue

        # Final conversational response
        reply_sanitized = sanitize_reply(raw_reply)
        if reply_sanitized:
            with memory_lock:
                conversation_history.append({"role": "user", "content": history_record_text})
                clean_for_history = clean_tags(reply_sanitized)
                conversation_history.append({"role": "assistant", "content": clean_for_history})
                save_history()

            # Append to persistent full chat history file
            append_to_full_chat_history("user", history_record_text, has_image=bool(images_b64))
            append_to_full_chat_history("assistant", clean_for_history)

            if len(conversation_history) >= config.get("compact_threshold", 30):
                threading.Thread(target=trigger_auto_compact, daemon=True).start()

            return reply_sanitized

        return "I'm here! What can I do for you?"

    return "I spaced out for a moment, could you repeat that?"

pending_messages = []
debounce_timer = None
batch_lock = threading.Lock()
is_generating = False

def process_pending_messages():
    """Gathers all accumulated messages and dispatches them for LLM response generation."""
    global pending_messages, is_generating
    with batch_lock:
        if not pending_messages:
            return
        if is_generating:
            return
        is_generating = True
        batch_to_process = list(pending_messages)
        pending_messages.clear()

    threading.Thread(target=_worker_generation_thread, args=[batch_to_process], daemon=True).start()

def _worker_generation_thread(batch_to_process: list):
    global is_generating
    try:
        all_texts = []
        all_images = []
        for item in batch_to_process:
            txt = item.get("text", "").strip()
            imgs = item.get("images", [])
            if txt:
                all_texts.append(txt)
            if imgs:
                all_images.extend(imgs)

        if not all_texts and not all_images:
            return

        if len(all_texts) == 0:
            combined_text = ""
        elif len(all_texts) == 1:
            combined_text = all_texts[0]
        else:
            combined_text = "\n".join(all_texts)

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        logging.info(f"User [{now_str}] (Batch of {len(batch_to_process)}): {combined_text[:120]}")

        reply = query_llm(combined_text, all_images)
        logging.info(f"Agent [{now_str}]: {reply}")

        execute_action_tags(reply)

        clean_text_reply = clean_tags(reply)
        if clean_text_reply:
            call_onebot_api("send_private_msg", {
                "user_id": config["master_qq"],
                "message": clean_text_reply
            })
    except Exception as e:
        logging.error(f"Error in batch generation: {e}")
        traceback.print_exc()
    finally:
        with batch_lock:
            is_generating = False
            if pending_messages:
                debounce_delay = config.get("debounce_delay_sec", 1.8)
                threading.Timer(debounce_delay, process_pending_messages).start()

def on_message_arrived(msg_id: int, sender_id: int, raw_text: str):
    global debounce_timer
    if msg_id in processed_message_ids:
        return
    processed_message_ids.add(msg_id)

    if sender_id != config["master_qq"]:
        return

    clean_text, images_b64, has_voice = parse_incoming_cq_content(raw_text)

    with batch_lock:
        if debounce_timer and debounce_timer.is_alive():
            debounce_timer.cancel()

        pending_messages.append({
            "msg_id": msg_id,
            "text": clean_text,
            "images": images_b64,
            "time": time.time()
        })

        debounce_delay = config.get("debounce_delay_sec", 1.8)
        debounce_timer = threading.Timer(debounce_delay, process_pending_messages)
        debounce_timer.start()

def poll_messages_loop():
    logging.info("Active High-Frequency Poller started...")
    try:
        init_res = call_onebot_api("get_friend_msg_history", {"user_id": config["master_qq"], "count": 15})
        if init_res.get("status") == "ok":
            for m in init_res.get("data", {}).get("messages", []):
                mid = m.get("message_id")
                if mid:
                    processed_message_ids.add(mid)
    except Exception as e:
        logging.warning(f"Failed to seed initial messages: {e}")

    while True:
        try:
            res = call_onebot_api("get_friend_msg_history", {"user_id": config["master_qq"], "count": 10})
            if res.get("status") == "ok":
                msgs = res.get("data", {}).get("messages", [])
                for m in msgs:
                    mid = m.get("message_id")
                    sender_id = m.get("sender", {}).get("user_id")
                    text = m.get("raw_message") or ""
                    if mid and mid not in processed_message_ids and sender_id == config["master_qq"]:
                        on_message_arrived(mid, sender_id, text)
        except Exception as e:
            logging.warning(f"Poll loop exception: {e}")
        time.sleep(config.get("poll_interval_sec", 1.2))

def main():
    load_config()
    setup_logging()
    logging.info("=" * 65)
    logging.info("      QQ AI Companion Daemon (Bilingual & Multi-Modal Edition)")
    logging.info("=" * 65)
    logging.info(f"[*] Model           : {config.get('model')}")
    logging.info(f"[*] Target User QQ  : {config.get('master_qq')}")
    logging.info(f"[*] Language Mode   : {config.get('language')}")
    logging.info(f"[*] Voice Synthesis : {'Available (Edge-TTS)' if EDGE_TTS_AVAILABLE else 'Disabled (edge-tts not installed)'}")
    logging.info(f"[*] Live Web Search : {'Enabled (DDGS/Multi-engine)' if config.get('enable_web_search', True) else 'Disabled'}")
    logging.info(f"[*] Full Chat Logs  : {CHAT_LOG_FILE}")
    logging.info(f"[*] Realtime Memory : {MEMORY_SUMMARY_FILE}")
    logging.info(f"[*] Auto-Compact    : Enabled (Threshold: {config.get('compact_threshold')} turns)")
    logging.info(f"[*] Debounce Window : {config.get('debounce_delay_sec')}s")
    logging.info(f"[*] Max Tokens      : {config.get('max_tokens')}")
    logging.info(f"[*] Persona Source  : {os.path.join(PERSONA_DIR, 'system_prompt_' + config.get('language', 'zh') + '.md')}")
    logging.info("=" * 65)

    poller = threading.Thread(target=poll_messages_loop, daemon=True)
    poller.start()

    def handle_signal(signum, frame):
        logging.info("Exiting cleanly...")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Daemon stopped.")

if __name__ == "__main__":
    main()
