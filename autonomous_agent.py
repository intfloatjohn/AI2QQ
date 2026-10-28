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
import atexit
import asyncio
import logging
import datetime
import traceback
import threading
import subprocess
import urllib.request
import urllib.error
import urllib.parse
from collections import deque

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

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
recent_bot_replies = deque(maxlen=100)
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
            header = "【Long-Term Memory Archive】" if config.get("language", "zh").lower() == "en" else "【长期记忆档案】"
            updated = f"{header}\n{new_entry}"

        long_term_memory = updated
        save_long_term_memory()

    logging.info(f"Realtime Memory Updated: {new_entry}")
    lang = config.get("language", "zh").lower()
    return f"Successfully saved to long-term memory: {clean_content}" if lang == "en" else f"已成功将新信息记入长期记忆：{clean_content}"

def read_memory_file() -> str:
    """Reads the full memory_summary.txt."""
    lang = config.get("language", "zh").lower()
    empty_msg = "Long-term memory archive is currently empty." if lang == "en" else "长期记忆档案目前为空。"
    with memory_lock:
        if os.path.exists(MEMORY_SUMMARY_FILE):
            try:
                with open(MEMORY_SUMMARY_FILE, "r", encoding="utf-8-sig") as f:
                    content = f.read().strip()
                    return content if content else empty_msg
            except Exception as e:
                return f"Failed to read memory: {e}" if lang == "en" else f"读取记忆失败: {e}"
    return empty_msg

def search_chat_history(query: str, max_results: int = 8) -> str:
    """Searches chat_history.jsonl and agent.log for matching dialogue turns (newest first, multi-keyword)."""
    lang = config.get("language", "zh").lower()
    clean_q = query.strip()
    if not clean_q:
        return "Search keyword cannot be empty." if lang == "en" else "搜索关键词不能为空。"

    keywords = [k.strip().lower() for k in re.split(r'[\s,，、]+', clean_q) if k.strip()]
    if not keywords:
        keywords = [clean_q.lower()]

    candidates = []

    # 1. Search full chat history jsonl (newest first)
    if os.path.exists(CHAT_LOG_FILE):
        try:
            with open(CHAT_LOG_FILE, "r", encoding="utf-8") as f:
                ch_lines = f.readlines()
            for i in range(len(ch_lines) - 1, -1, -1):
                line = ch_lines[i].strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                    text = item.get("text", "").lower()
                    matched_kws = sum(1 for kw in keywords if kw in text)
                    if matched_kws > 0:
                        start = max(0, i - 1)
                        end = min(len(ch_lines), i + 2)
                        context_snippets = []
                        for c_idx in range(start, end):
                            try:
                                c_entry = json.loads(ch_lines[c_idx].strip())
                                is_user = c_entry.get("role") == "user"
                                if lang == "en":
                                    role_label = "User" if is_user else "Agent"
                                else:
                                    role_label = "主人" if is_user else "伴侣"
                                context_snippets.append(f"[{c_entry.get('time')}] {role_label}: {c_entry.get('text')}")
                            except Exception:
                                pass
                        candidates.append((matched_kws, i, "\n".join(context_snippets)))
                        if len(candidates) >= max_results * 2:
                            break
                except Exception:
                    continue
        except Exception as e:
            logging.warning(f"Error searching {CHAT_LOG_FILE}: {e}")

    # 2. Search agent.log for recent dialogue lines (newest first)
    if os.path.exists(LOG_FILE):
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                log_lines = f.readlines()
            for line in reversed(log_lines[-1000:]):
                if ("User" in line or "Agent" in line or "Master" in line) and any(kw in line.lower() for kw in keywords):
                    matched_kws = sum(1 for kw in keywords if kw in line.lower())
                    clean_line = line.strip()
                    if not any(clean_line in c[2] for c in candidates):
                        candidates.append((matched_kws, 0, clean_line))
                        if len(candidates) >= max_results * 3:
                            break
        except Exception as e:
            logging.warning(f"Error searching {LOG_FILE}: {e}")

    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
        top_matches = [c[2] for c in candidates[:max_results]]
        header = "【Relevant Past Dialogue History】:\n" if lang == "en" else "【过往相关聊天记录】:\n"
        return header + "\n---\n".join(top_matches)

    return f"No past dialogue records found regarding '{clean_q}'." if lang == "en" else f"未找到关于“{clean_q}”的过往聊天记录。"

SEARCH_CACHE = {}

def web_search(query: str, max_results: int = 3, gen_id: int = 0) -> str:
    """Executes live web search with fast caching, multi-engine resilience, and early abort."""
    lang = config.get("language", "zh").lower()
    if not config.get("enable_web_search", True):
        return "Web search is disabled in settings." if lang == "en" else "网络搜索功能已被主人禁用。"
    clean_q = query.strip()
    if not clean_q:
        return "Search query cannot be empty." if lang == "en" else "搜索关键词不能为空。"

    with batch_lock:
        if gen_id and gen_id != current_generation_id:
            logging.info(f"web_search aborted: gen #{gen_id} superseded by #{current_generation_id}")
            return ""

    now = time.time()
    if clean_q in SEARCH_CACHE and (now - SEARCH_CACHE[clean_q][0]) < 600:
        logging.info(f"web_search cache hit for: {clean_q}")
        return SEARCH_CACHE[clean_q][1]

    results_text = ""

    # Method 1: DDGS auto backend with strict 5s timeout
    try:
        from ddgs import DDGS
        items = list(DDGS(timeout=5).text(clean_q, max_results=max_results))
        if items:
            lines_list = []
            for i, r in enumerate(items):
                title = r.get("title", "")
                snippet = (r.get("body", "") or r.get("snippet", "")).strip()[:240]
                summary_label = "Snippet:" if lang == "en" else "摘要:"
                lines_list.append(f"[{i+1}] {title}\n{summary_label} {snippet}")
            results_text = "\n\n".join(lines_list)
    except Exception as e:
        logging.warning(f"ddgs primary search failed ({e}), trying fallbacks...")

    with batch_lock:
        if gen_id and gen_id != current_generation_id:
            return ""

    # Method 2: DDGS alternate backends (yahoo / wikipedia / duckduckgo)
    if not results_text:
        for b in ["yahoo", "wikipedia", "duckduckgo"]:
            try:
                from ddgs import DDGS
                items = list(DDGS(timeout=4).text(clean_q, max_results=max_results, backend=b))
                if items:
                    lines_list = []
                    for i, r in enumerate(items):
                        title = r.get("title", "")
                        snippet = (r.get("body", "") or r.get("snippet", "")).strip()[:240]
                        summary_label = "Snippet:" if lang == "en" else "摘要:"
                        lines_list.append(f"[{i+1}] {title}\n{summary_label} {snippet}")
                    results_text = "\n\n".join(lines_list)
                    break
            except Exception:
                continue

    with batch_lock:
        if gen_id and gen_id != current_generation_id:
            return ""

    # Method 3: Direct Wikipedia API fallback
    if not results_text:
        try:
            import urllib.parse
            encoded_q = urllib.parse.quote(clean_q)
            wiki_domain = "en.wikipedia.org" if lang == "en" else "zh.wikipedia.org"
            wiki_url = f"https://{wiki_domain}/w/api.php?action=query&list=search&srsearch={encoded_q}&format=json&utf8="
            req = urllib.request.Request(wiki_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                witems = data.get("query", {}).get("search", [])
                if witems:
                    lines_list = []
                    for i, it in enumerate(witems[:max_results]):
                        title = it.get("title", "")
                        snippet = re.sub(r"<[^>]+>", "", it.get("snippet", "")).strip()[:240]
                        summary_label = "Snippet:" if lang == "en" else "摘要:"
                        lines_list.append(f"[{i+1}] {title}\n{summary_label} {snippet}")
                    results_text = "\n\n".join(lines_list)
        except Exception as e:
            logging.warning(f"Wiki fallback failed: {e}")

    if results_text:
        SEARCH_CACHE[clean_q] = (now, results_text)
        return results_text

    return f"No relevant search results found for '{clean_q}'." if lang == "en" else f"未能获取到“{clean_q}”的有效搜索结果。"

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

    # Strip any accidental single numbered list prefix (e.g. '1. ', '1、', '1: ')
    cleaned = re.sub(r'^(?:1[.\、\s]|1\s*[-:])\s*', '', cleaned)

    lang = config.get("language", "zh").lower()
    if lang == "zh" and re.search(r'[一-鿿]', cleaned):
        cleaned = re.sub(r'nya~', '喵~', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'nya', '喵', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()

STICKER_ALIASES = {
    "heart": ["比心", "爱心", "心心", "love", "heart", "like"],
    "wave": ["挥手", "打招呼", "问好", "wave", "hello", "hi"],
    "sleep": ["睡觉", "晚安", "困困", "sleep", "sleepy", "goodnight"],
    "avatar": ["自拍", "照片", "avatar", "photo", "selfie"],
    "pout": ["委屈", "生气", "撒娇", "pout", "angry"],
}

async def synthesize_voice_file(text: str, output_path: str):
    if not EDGE_TTS_AVAILABLE:
        return False
    lang = config.get("language", "zh").lower()
    configured_voice = config.get("voice_character", "")
    if lang == "en" and (not configured_voice or configured_voice.startswith("zh-")):
        voice = "en-US-JennyNeural"
    else:
        voice = configured_voice or "zh-CN-XiaoyiNeural"
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
            dir_files = os.listdir(STICKERS_DIR)
            for fname in dir_files:
                base_name, _ = os.path.splitext(fname)
                if kw in base_name.lower() or base_name.lower() in kw:
                    matched_file = fname
                    break
            if not matched_file:
                for alias_key, alias_list in STICKER_ALIASES.items():
                    if kw in alias_list or kw == alias_key:
                        for fname in dir_files:
                            base_name, _ = os.path.splitext(fname)
                            if any(a.lower() in base_name.lower() for a in alias_list):
                                matched_file = fname
                                break
                    if matched_file:
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

    # 6. Realtime Memory Updates
    mem_matches = re.findall(r'\[(?:更新记忆|Update Memory|update_memory|remember|Remember):\s*([^\]]+)\]', reply_text, re.IGNORECASE)
    for mem_content in mem_matches:
        update_memory_realtime(mem_content)

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

def execute_tool_call(tool_name: str, arguments: dict, gen_id: int = 0) -> str:
    """Executes a tool call with gen_id check and returns the observation string."""
    with batch_lock:
        if gen_id and gen_id != current_generation_id:
            logging.info(f"execute_tool_call aborted: gen #{gen_id} superseded by #{current_generation_id}")
            return ""
    try:
        if tool_name == "web_search":
            query = arguments.get("query", "")
            return web_search(query, max_results=config.get("max_search_results", 3), gen_id=gen_id)
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

def record_chat_turn(user_content: str, assistant_reply: str, has_image: bool = False):
    """Persists a single confirmed, non-interrupted conversational turn to memory and chat history."""
    with memory_lock:
        clean_user = user_content.strip()
        clean_assistant = clean_tags(assistant_reply).strip()
        conversation_history.append({"role": "user", "content": clean_user})
        conversation_history.append({"role": "assistant", "content": clean_assistant})
        save_history()

    # Append to persistent full chat history file
    append_to_full_chat_history("user", clean_user, has_image=has_image)
    append_to_full_chat_history("assistant", clean_assistant)

    if len(conversation_history) >= config.get("compact_threshold", 30):
        threading.Thread(target=trigger_auto_compact, daemon=True).start()

def query_llm(user_prompt: str, images_b64: list, gen_id: int = 0) -> str:
    load_config()
    system_prompt = load_system_prompt()
    lang = config.get("language", "zh").lower()

    if long_term_memory:
        mem_header = "【Long-term Memory Archive (Use [read_memory] or [remember: text])】:" if lang == "en" else "【长期记忆概览（可使用 [查看记忆] 获取完整版，使用 [更新记忆: 内容] 实时补充）】:"
        system_prompt += f"\n\n{mem_header}\n{long_term_memory}"

    base = config.get("base_url", "https://openrouter.ai/api/v1/chat/completions").rstrip("/")
    if base.endswith("/chat/completions"):
        url = base
    elif base.endswith("/v1"):
        url = f"{base}/chat/completions"
    else:
        url = f"{base}/v1/chat/completions"

    api_key = config.get("api_key", "").strip()
    if not api_key:
        return "Please configure a valid API Key in config.json!" if lang == "en" else "请在 config.json 填入有效的 API Key！"

    messages = [{"role": "system", "content": system_prompt}]
    with memory_lock:
        for turn in conversation_history:
            if isinstance(turn, dict) and "role" in turn and "content" in turn:
                messages.append({"role": turn["role"], "content": turn["content"]})

    if images_b64:
        content_items = []
        default_caption = "(The user sent an image)" if lang == "en" else "（对方发送了一张图片）"
        caption = user_prompt if user_prompt else default_caption
        content_items.append({"type": "text", "text": caption})
        for b64 in images_b64:
            content_items.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
        messages.append({"role": "user", "content": content_items})
    else:
        messages.append({"role": "user", "content": user_prompt})

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "QQ AI Companion"
    }

    max_tokens_val = int(config.get("max_tokens", 1200))
    max_tool_turns = 5
    model_name = config.get("model", "deepseek-flash")

    # ReAct tool-execution loop (up to 5 turns)
    for iteration in range(max_tool_turns):
        with batch_lock:
            if gen_id and gen_id != current_generation_id:
                logging.info(f"LLM loop iteration #{iteration+1} aborted early: generation #{gen_id} was superseded by #{current_generation_id}.")
                return ""

        # On the final turn, force response synthesis without tools
        is_final_turn = (iteration == max_tool_turns - 1)
        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": 0.72,
            "max_tokens": max_tokens_val
        }
        if not is_final_turn:
            payload["tools"] = AVAILABLE_TOOLS

        data = {}
        for attempt in range(2):
            with batch_lock:
                if gen_id and gen_id != current_generation_id:
                    return ""
            try:
                if REQUESTS_AVAILABLE:
                    resp = requests.post(url, json=payload, headers=headers, timeout=35)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            break
                        except Exception as je:
                            logging.warning(f"LLM call attempt #{attempt+1} JSON decode error: {je}, body={resp.text[:200]}")
                    else:
                        logging.warning(f"LLM call attempt #{attempt+1} failed ({resp.status_code}): {resp.text[:200]}")
                else:
                    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                    with urllib.request.urlopen(req, timeout=35) as resp:
                        raw_bytes = resp.read()
                        if raw_bytes.startswith(b'\x1f\x8b'):
                            import gzip
                            raw_bytes = gzip.decompress(raw_bytes)
                        data = json.loads(raw_bytes.decode("utf-8", errors="ignore"))
                        break
            except urllib.error.HTTPError as he:
                err_body = he.read().decode("utf-8", errors="ignore") if he.fp else str(he)
                logging.warning(f"LLM call attempt #{attempt+1} failed ({he.code}): {err_body[:200]}")
            except Exception as e:
                logging.warning(f"LLM call attempt #{attempt+1} error: {e}")

            if attempt == 0:
                time.sleep(1.2)
                clean_msgs = []
                for m in messages:
                    if m.get("role") == "tool":
                        label = "【Tool Search Observation】:" if lang == "en" else "【系统提示：工具搜索结果】:"
                        clean_msgs.append({
                            "role": "user",
                            "content": label + "\n" + str(m.get("content", "")) + "\n" + ("Please reply naturally based on this." if lang == "en" else "请结合搜索结果自然回复。")
                        })
                    elif m.get("role") == "assistant" and m.get("tool_calls"):
                        continue
                    else:
                        clean_msgs.append(m)
                payload = {
                    "model": model_name,
                    "messages": clean_msgs,
                    "temperature": 0.72,
                    "max_tokens": max_tokens_val
                }
                continue
            else:
                break

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
        if tool_calls and not is_final_turn:
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
                with batch_lock:
                    if gen_id and gen_id != current_generation_id:
                        return ""
                obs = execute_tool_call(fn_name, fn_args, gen_id=gen_id)
                with batch_lock:
                    if gen_id and gen_id != current_generation_id:
                        return ""
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": (obs[:1200] if obs else ("No relevant information found." if lang == "en" else "未能获取到相关信息。"))
                })
            continue

        # 2. Inline Command Tag Handling
        if (inline_search or inline_chat_search or inline_read_mem) and not is_final_turn:
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
            return reply_sanitized

        return "I'm here! What can I do for you?" if lang == "en" else "在的！有什么可以帮你的？"

    # Fallback companion apology (time-neutral, works for both daytime and evening)
    if lang == "en":
        return "I experienced a temporary network timeout connecting to the AI brain. Please try asking again in a moment."
    return "刚才连接大模型服务网络稍有超时。请稍后再试一次。"

pending_messages = []
in_flight_messages = []
debounce_timer = None
batch_lock = threading.Lock()
current_generation_id = 0
first_message_time = 0.0

def trigger_generation(gen_id: int):
    """Dispatches accumulated messages for LLM response generation."""
    global pending_messages, in_flight_messages, first_message_time, current_generation_id
    with batch_lock:
        if gen_id != current_generation_id:
            return
        if not pending_messages and not in_flight_messages:
            current_generation_id = 0
            return

        # If previous in_flight_messages were interrupted by newer pending messages,
        # merge them seamlessly so no context is ever dropped!
        if in_flight_messages:
            logging.info(f"Merging {len(in_flight_messages)} in-flight messages with {len(pending_messages)} pending messages.")
            pending_messages = in_flight_messages + pending_messages
            in_flight_messages = []

        batch_to_process = list(pending_messages)
        in_flight_messages = list(batch_to_process)
        pending_messages.clear()
        first_message_time = 0.0

    threading.Thread(target=_worker_generation_thread, args=[batch_to_process, gen_id], daemon=True).start()

def _worker_generation_thread(batch_to_process: list, gen_id: int):
    """Worker thread executing the generation for a batch with non-destructive interruption."""
    global in_flight_messages, current_generation_id
    try:
        with batch_lock:
            if gen_id != current_generation_id:
                logging.info(f"Generation #{gen_id} pre-aborted (superseded by #{current_generation_id}).")
                return

        lang = config.get("language", "zh").lower()
        all_images = []
        lines_for_llm = []
        lines_for_history = []

        # Collect raw clean messages without premature '1.' numbering
        for item in batch_to_process:
            txt = item.get("text", "").strip()
            imgs = item.get("images", [])
            if imgs:
                all_images.extend(imgs)

            has_img = bool(imgs)
            img_tag_prompt = "[Sent an Image]" if lang == "en" else "[发送了图片]"
            img_tag_hist = "[Image]" if lang == "en" else "[图片]"

            if txt and has_img:
                lines_for_llm.append(f"{txt} {img_tag_prompt}")
                lines_for_history.append(f"{txt} {img_tag_hist}")
            elif txt:
                lines_for_llm.append(txt)
                lines_for_history.append(txt)
            elif has_img:
                lines_for_llm.append(img_tag_prompt)
                lines_for_history.append(img_tag_hist)

        if not lines_for_llm and not all_images:
            with batch_lock:
                if gen_id == current_generation_id:
                    in_flight_messages.clear()
                    if not pending_messages:
                        current_generation_id = 0
            return

        if len(lines_for_llm) <= 1:
            # Single non-combined message: pure raw user message with NO numbered prefix!
            user_prompt_for_llm = lines_for_llm[0] if lines_for_llm else ""
            default_empty = "[Image]" if lang == "en" else "[图片]"
            history_record_text = lines_for_history[0] if lines_for_history else default_empty
        else:
            # Multi-message combine: only here do we number each message 1., 2., 3.!
            numbered_lines = [f"{i}. {line}" for i, line in enumerate(lines_for_llm, 1)]
            combined_dialogue = "\n".join(numbered_lines)
            if lang == "en":
                user_prompt_for_llm = (
                    f"The user sent the following messages in a row:\n{combined_dialogue}\n"
                    "(Please consider the overall context and reply naturally and cohesively in a single response.)"
                )
            else:
                user_prompt_for_llm = (
                    f"对方连续发送了以下几条短消息：\n{combined_dialogue}\n"
                    "（请结合以上全部短消息综合理解对方意图，统一、自然随性地回复，无需机械割裂地逐条分别回复。）"
                )
            history_record_text = "\n".join(lines_for_history)

        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        logging.info(f"User [{now_str}] (Batch of {len(batch_to_process)}): {history_record_text[:120]}")

        reply = query_llm(user_prompt_for_llm, all_images, gen_id=gen_id)
        if not reply:
            with batch_lock:
                if gen_id == current_generation_id:
                    in_flight_messages.clear()
                    if not pending_messages:
                        current_generation_id = 0
            return

        with batch_lock:
            if gen_id != current_generation_id:
                logging.info(f"Generation #{gen_id} was superseded by #{current_generation_id}. Discarding partial reply so messages can be merged together.")
                return
            in_flight_messages.clear()

        logging.info(f"Agent [{now_str}]: {reply}")

        # Record to persistent memory & chat logs ONLY for the confirmed winning reply
        record_chat_turn(history_record_text, reply, has_image=bool(all_images))

        # Execute actions (stickers, QQ faces, voice, poke, memory updates)
        execute_action_tags(reply)

        clean_text_reply = clean_tags(reply)
        if clean_text_reply:
            recent_bot_replies.append(clean_text_reply)
            res = call_onebot_api("send_private_msg", {
                "user_id": config["master_qq"],
                "message": clean_text_reply
            })
            if isinstance(res, dict) and res.get("status") == "ok":
                bot_mid = res.get("data", {}).get("message_id")
                if bot_mid:
                    processed_message_ids.add(bot_mid)

        # Re-initialize the race generation counter back to 0 once all active queues are idle
        with batch_lock:
            if gen_id == current_generation_id and not pending_messages and not in_flight_messages:
                logging.info(f"Message batch completed. Re-initialized generation counter from #{current_generation_id} to 0.")
                current_generation_id = 0
    except Exception as e:
        logging.error(f"Error in batch generation #{gen_id}: {e}")
        traceback.print_exc()
        with batch_lock:
            if gen_id == current_generation_id:
                in_flight_messages.clear()
                if not pending_messages:
                    current_generation_id = 0

def on_message_arrived(msg_id: int, sender_id: int, raw_text: str):
    global debounce_timer, current_generation_id, first_message_time
    if msg_id in processed_message_ids:
        return
    processed_message_ids.add(msg_id)
    if len(processed_message_ids) > 10000:
        processed_message_ids.difference_update(list(processed_message_ids)[:-5000])

    is_self_chat = str(config.get("bot_qq", "")) == str(config.get("master_qq", ""))
    if not is_self_chat and sender_id != config["master_qq"]:
        return

    clean_text, images_b64, has_voice = parse_incoming_cq_content(raw_text)

    with batch_lock:
        current_generation_id += 1
        gen_id = current_generation_id

        if not pending_messages:
            first_message_time = time.time()

        pending_messages.append({
            "msg_id": msg_id,
            "text": clean_text,
            "images": images_b64,
            "time": time.time()
        })

        if debounce_timer and debounce_timer.is_alive():
            debounce_timer.cancel()

        max_wait_sec = config.get("max_batch_wait_sec", 10.0)
        debounce_delay = config.get("debounce_delay_sec", 2.2)

        if time.time() - first_message_time >= max_wait_sec:
            logging.info("Batch max wait time reached; triggering generation immediately.")
            threading.Thread(target=trigger_generation, args=[gen_id], daemon=True).start()
        else:
            debounce_timer = threading.Timer(debounce_delay, trigger_generation, args=[gen_id])
            debounce_timer.start()

def poll_messages_loop():
    logging.info("Active High-Frequency Poller started...")
    is_self_chat = str(config.get("bot_qq", "")) == str(config.get("master_qq", ""))
    if is_self_chat:
        logging.info("[*] Single-Account Self-Chat Mode active (bot_qq == master_qq). Filtering bot echoes automatically.")

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
                    if mid and mid not in processed_message_ids:
                        if is_self_chat:
                            # In self-chat mode, ignore messages matching recent bot replies to prevent infinite echo
                            if any(text == r or (len(r) > 10 and r[:20] in text) for r in recent_bot_replies if r):
                                processed_message_ids.add(mid)
                                continue
                            on_message_arrived(mid, sender_id or config["master_qq"], text)
                        elif sender_id == config["master_qq"]:
                            on_message_arrived(mid, sender_id, text)
        except Exception as e:
            logging.warning(f"Poll loop exception: {e}")
        time.sleep(config.get("poll_interval_sec", 0.8))

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

    def stop_docker_napcat_if_local():
        """Cleanly stops the local NapCat Docker container on exit if it is running."""
        try:
            if os.getenv("KEEP_DOCKER", "0") == "1" or os.getenv("AUTO_STOP_DOCKER", "true").lower() == "false":
                return
            api = config.get("onebot_http_api", "http://127.0.0.1:3000")
            if any(h in api for h in ["127.0.0.1", "localhost", "0.0.0.0"]):
                res = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=2)
                if "napcat" in res.stdout.split():
                    logging.info("[*] Stopping local NapCat Docker container...")
                    subprocess.run(["docker", "stop", "napcat"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=12)
                    logging.info("[+] NapCat Docker container stopped.")
        except Exception:
            pass

    atexit.register(stop_docker_napcat_if_local)

    def handle_signal(signum, frame):
        logging.info("Exiting cleanly...")
        stop_docker_napcat_if_local()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Daemon stopped.")
        stop_docker_napcat_if_local()

if __name__ == "__main__":
    main()
