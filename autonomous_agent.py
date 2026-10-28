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
import hashlib
import zipfile
import shutil
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

try:
    from graiax import silkcoder
    SILKCODER_AVAILABLE = True
except ImportError:
    SILKCODER_AVAILABLE = False

try:
    import pilk
    PILK_AVAILABLE = True
except ImportError:
    PILK_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PERSONA_DIR = os.path.join(BASE_DIR, "persona")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
CHAT_LOG_FILE = os.path.join(BASE_DIR, "chat_history.jsonl")
MEMORY_SUMMARY_FILE = os.path.join(BASE_DIR, "memory_summary.txt")
LOG_FILE = os.path.join(BASE_DIR, "agent.log")
STICKERS_DIR = os.path.join(BASE_DIR, "stickers")
PICTURE_DB_DIR = os.path.join(BASE_DIR, "picture_db")
PICTURE_IMAGES_DIR = os.path.join(PICTURE_DB_DIR, "images")
PICTURE_CATALOG_FILE = os.path.join(PICTURE_DB_DIR, "catalog.json")

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
    "voice_character": "zh-CN-XiaoyiNeural",
    "enable_file_parser": True,
    "prefer_native_file_parser": True,
    "enable_voice_recognition": True,
    "prefer_native_voice_recognition": True,
    "asr_api_url": "",
    "asr_api_key": "",
    "asr_model": "whisper-1",
    "enable_picture_database": True,
    "enable_multi_bubble_reply": True,
    "multi_bubble_delay_sec": 1.2,
    "enable_autonomous_refusal": True
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
    "发呆": 3, "得意": 4, "惊讶": 0, "大哭": 9, "尴尬": 10,
    "发怒": 11, "难过": 15, "酷": 16, "抓狂": 18, "白眼": 32,
    "傲慢": 33, "困": 35, "流汗": 37, "憨笑": 38, "悠闲": 39,
    "点赞": 172, "托腮": 175, "斜眼笑": 178, "打call": 260,
    "大笑": 267, "无语": 270,
    # English
    "hug": 222, "cuddle": 219, "pat": 219, "shy": 6, "blush": 6,
    "kiss": 109, "pout": 106, "cute": 21, "smile": 14,
    "heart": 319, "love": 66, "cat": 307, "wink": 172, "laugh": 13, "grin": 13,
    "cry": 5, "sleep": 8, "sleepy": 8
}

QQ_FACE_ID_TO_NAME = {
    0: "惊讶", 1: "撇嘴", 2: "色", 3: "发呆", 4: "得意", 5: "流泪", 6: "害羞", 7: "闭嘴",
    8: "睡", 9: "大哭", 10: "尴尬", 11: "发怒", 12: "调皮", 13: "呲牙", 14: "微笑",
    16: "酷", 18: "抓狂", 20: "偷笑", 21: "可爱", 24: "偷笑", 28: "亲亲", 32: "白眼",
    33: "傲慢", 35: "困", 37: "流汗", 38: "憨笑", 39: "悠闲", 49: "拥抱", 66: "爱心",
    74: "太阳", 75: "月亮", 76: "强", 79: "胜利", 85: "爱心", 86: "心碎", 106: "委屈",
    109: "亲亲", 124: "摸头", 172: "点赞", 175: "托腮", 178: "斜眼笑", 212: "比心",
    219: "贴贴", 222: "抱抱", 260: "打call", 262: "汪汪", 267: "大笑", 270: "无语",
    294: "期待", 307: "猫猫", 319: "比心"
}

RPS_MAP = {1: "石头", 2: "剪刀", 3: "布"}

conversation_history = []
long_term_memory = ""
processed_message_ids = set()
recent_bot_replies = deque(maxlen=100)
last_bot_voice_send_time = 0.0
latest_received_image_bytes = None
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
    },
    {
        "type": "function",
        "function": {
            "name": "search_picture_library",
            "description": "搜索个人图片库与表情包库，查找匹配的图片文件以便发送给对方 (Search picture library)",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "想要查找的图片或表情包标签/关键词 (Tag or keyword to search)"
                    }
                },
                "required": ["query"]
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

def search_bing_cn(query: str, max_results: int = 3) -> list:
    """Fast, reliable web search via cn.bing.com (fully unblocked in Mainland China)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"
        }
        url = f"https://cn.bing.com/search?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        results = []
        blocks = re.findall(r'<li class="b_algo"[^>]*>(.*?)</li>', content, re.DOTALL)
        for b in blocks[:max_results]:
            t_m = re.search(r'<h2[^>]*><a[^>]*>(.*?)</a>', b, re.DOTALL)
            title = re.sub(r'<[^>]+>', '', t_m.group(1)).strip() if t_m else ""
            s_m = re.search(r'<div class="b_caption"[^>]*>.*?<p[^>]*>(.*?)</p>', b, re.DOTALL)
            if not s_m:
                s_m = re.search(r'<p[^>]*>(.*?)</p>', b, re.DOTALL)
            snippet = re.sub(r'<[^>]+>', '', s_m.group(1)).strip() if s_m else ""
            if title:
                results.append({"title": html.unescape(title), "body": html.unescape(snippet)})
        return results
    except Exception as e:
        logging.warning(f"Bing CN search error: {e}")
        return []

def search_baidu_web(query: str, max_results: int = 3) -> list:
    """Fast web search via Baidu (fully unblocked in Mainland China)."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            content = resp.read().decode("utf-8", errors="ignore")

        results = []
        blocks = re.findall(r'<div class="[^"]*c-container[^"]*"[^>]*>(.*?)</div>\s*</div>', content, re.DOTALL)
        for b in blocks[:max_results]:
            t_m = re.search(r'<h3[^>]*><a[^>]*>(.*?)</a>', b, re.DOTALL)
            title = re.sub(r'<[^>]+>', '', t_m.group(1)).strip() if t_m else ""
            s_m = re.search(r'<div class="[^"]*content-right[^"]*"[^>]*>(.*?)</div>', b, re.DOTALL)
            if not s_m:
                s_m = re.search(r'<span class="content-right_8Zs40"[^>]*>(.*?)</span>', b, re.DOTALL)
            snippet = re.sub(r'<[^>]+>', '', s_m.group(1)).strip() if s_m else ""
            if title:
                results.append({"title": html.unescape(title), "body": html.unescape(snippet)})
        return results
    except Exception as e:
        logging.warning(f"Baidu search error: {e}")
        return []

def web_search(query: str, max_results: int = 3, gen_id: int = 0) -> str:
    """Executes live web search with fast caching, multi-engine resilience (Bing CN, Baidu, DDGS), and early abort."""
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

    # Strategy 1: For Chinese queries or servers in China, prioritize Bing China & Baidu (ultra-fast, unblocked)
    if lang == "zh":
        bing_items = search_bing_cn(clean_q, max_results=max_results)
        if bing_items:
            lines_list = [f"[{i+1}] {r['title']}\n摘要: {r['body'][:240]}" for i, r in enumerate(bing_items)]
            results_text = "\n\n".join(lines_list)
        elif not results_text:
            baidu_items = search_baidu_web(clean_q, max_results=max_results)
            if baidu_items:
                lines_list = [f"[{i+1}] {r['title']}\n摘要: {r['body'][:240]}" for i, r in enumerate(baidu_items)]
                results_text = "\n\n".join(lines_list)

    with batch_lock:
        if gen_id and gen_id != current_generation_id:
            return ""

    # Strategy 2: If still empty (e.g. English mode or domestic engines empty), try DDGS with strict 4s timeout
    if not results_text:
        try:
            from ddgs import DDGS
            items = list(DDGS(timeout=4).text(clean_q, max_results=max_results))
            if items:
                lines_list = []
                for i, r in enumerate(items):
                    title = r.get("title", "")
                    snippet = (r.get("body", "") or r.get("snippet", "")).strip()[:240]
                    summary_label = "Snippet:" if lang == "en" else "摘要:"
                    lines_list.append(f"[{i+1}] {title}\n{summary_label} {snippet}")
                results_text = "\n\n".join(lines_list)
        except Exception as e:
            logging.warning(f"ddgs search failed: {e}")

    # Fallback for English queries: Bing CN
    if not results_text and lang != "zh":
        bing_items = search_bing_cn(clean_q, max_results=max_results)
        if bing_items:
            lines_list = [f"[{i+1}] {r['title']}\nSnippet: {r['body'][:240]}" for i, r in enumerate(bing_items)]
            results_text = "\n\n".join(lines_list)

    if results_text:
        SEARCH_CACHE[clean_q] = (now, results_text)
        return results_text

    return "网络搜索暂时没有获取到相关内容，请直接根据已有知识回答。" if lang == "zh" else "Web search returned no relevant results."

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

def get_llm_url() -> str:
    """Returns the LLM API endpoint without unexpected auto-completion.
    - If user provides a full endpoint (e.g. ends with /chat/completions), keep verbatim.
    - If user provides a bare base URL (e.g. 'https://api.deepseek.com'), append '/chat/completions'
      without forcing any '/v1' prefix.
    """
    base = config.get("base_url", "https://openrouter.ai/api/v1/chat/completions").strip()
    if any(endpoint in base for endpoint in ["/chat/completions", "/completions", "/messages", "/generate"]):
        return base
    return f"{base.rstrip('/')}/chat/completions"

def raw_llm_call(prompt: str, max_tokens: int = 800) -> str:
    url = get_llm_url()

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

    if REQUESTS_AVAILABLE:
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=45)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            logging.warning(f"raw_llm_call error via requests: {e}")

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw_b = resp.read()
        if raw_b.startswith(b'\x1f\x8b'):
            import gzip
            raw_b = gzip.decompress(raw_b)
        data = json.loads(raw_b.decode("utf-8", errors="ignore"))
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

def download_image_data(img_url: str, file_id: str = "") -> tuple:
    """Downloads image and returns (base64_str, raw_bytes)."""
    global latest_received_image_bytes
    clean_url = html.unescape(img_url)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://qun.qq.com/"
    }
    raw_bytes = b""
    try:
        req = urllib.request.Request(clean_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
            if len(data) > 100:
                raw_bytes = data
    except Exception as e:
        logging.warning(f"Direct download failed ({e}), checking OneBot local cache for file={file_id}...")

    if not raw_bytes and file_id:
        try:
            res = call_onebot_api("get_image", {"file": file_id})
            if res.get("status") == "ok":
                local_path = res.get("data", {}).get("file", "")
                if local_path and os.path.exists(local_path):
                    with open(local_path, "rb") as f:
                        raw_bytes = f.read()
        except Exception as e:
            logging.error(f"Fallback get_image failed: {e}")

    if raw_bytes:
        latest_received_image_bytes = raw_bytes
        return base64.b64encode(raw_bytes).decode("utf-8"), raw_bytes
    return "", b""

def download_image_as_base64(img_url: str, file_id: str = "") -> str:
    b64, _ = download_image_data(img_url, file_id)
    return b64

# ==============================================================================
# Feature 5: Visual Memory & Custom Picture Database
# ==============================================================================
def init_picture_database():
    """Initializes picture database directory and catalog index, and auto-imports static stickers."""
    os.makedirs(PICTURE_IMAGES_DIR, exist_ok=True)
    catalog = []
    if os.path.exists(PICTURE_CATALOG_FILE):
        try:
            with open(PICTURE_CATALOG_FILE, "r", encoding="utf-8") as f:
                catalog = json.load(f)
                if not isinstance(catalog, list):
                    catalog = []
        except Exception as e:
            logging.warning(f"Failed to initialize picture catalog: {e}")
            catalog = []

    # Auto-import existing stickers from stickers/ into catalog if not yet indexed
    if os.path.exists(STICKERS_DIR):
        modified = False
        for fname in os.listdir(STICKERS_DIR):
            fpath = os.path.join(STICKERS_DIR, fname)
            if not os.path.isfile(fpath):
                continue
            base, ext = os.path.splitext(fname)
            if ext.lower() not in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
                continue
            try:
                with open(fpath, "rb") as sf:
                    sbytes = sf.read()
                sha = hashlib.sha256(sbytes).hexdigest()[:16]
                if not any(item.get("id") == sha or item.get("filename") == fname for item in catalog):
                    aliases = STICKER_ALIASES.get(base.lower(), [])
                    tags = list(dict.fromkeys([base.lower()] + [a.lower() for a in aliases]))
                    catalog.append({
                        "id": sha,
                        "filename": fname,
                        "path": os.path.relpath(fpath, BASE_DIR),
                        "timestamp": int(os.path.getmtime(fpath)),
                        "sender_id": 0,
                        "tags": tags,
                        "summary": f"表情贴图 ({base})"
                    })
                    modified = True
            except Exception as se:
                logging.debug(f"Sticker import error for {fname}: {se}")
        if modified or not os.path.exists(PICTURE_CATALOG_FILE):
            try:
                with open(PICTURE_CATALOG_FILE, "w", encoding="utf-8") as f:
                    json.dump(catalog, f, indent=2, ensure_ascii=False)
            except Exception as we:
                logging.warning(f"Failed to write picture catalog: {we}")

def save_to_picture_database(image_bytes: bytes, sender_id: int = 0, tags: list = None, summary: str = "", filename: str = "") -> dict:
    """Saves or updates a picture in the local library, deduplicating via SHA256 and indexing in catalog.json."""
    if not image_bytes or len(image_bytes) < 200:
        return {}
    init_picture_database()
    sha = hashlib.sha256(image_bytes).hexdigest()[:16]
    ext = ".jpg"
    if image_bytes.startswith(b"\x89PNG"):
        ext = ".png"
    elif image_bytes.startswith(b"GIF8"):
        ext = ".gif"
    elif image_bytes.startswith(b"RIFF") and b"WEBP" in image_bytes[:12]:
        ext = ".webp"

    dest_filename = f"pic_{sha}{ext}"
    dest_path = os.path.join(PICTURE_IMAGES_DIR, dest_filename)
    if not os.path.exists(dest_path):
        try:
            with open(dest_path, "wb") as f:
                f.write(image_bytes)
        except Exception as e:
            logging.warning(f"Failed to write image to picture library: {e}")
            return {}

    entry = {
        "id": sha,
        "filename": dest_filename,
        "path": os.path.relpath(dest_path, BASE_DIR),
        "timestamp": int(time.time()),
        "sender_id": sender_id,
        "tags": tags or [],
        "summary": summary or ""
    }

    try:
        catalog = []
        if os.path.exists(PICTURE_CATALOG_FILE):
            with open(PICTURE_CATALOG_FILE, "r", encoding="utf-8") as f:
                catalog = json.load(f)
                if not isinstance(catalog, list):
                    catalog = []

        # If already exists, update tags and description dynamically
        existing = next((item for item in catalog if item.get("id") == sha), None)
        if existing:
            if tags:
                existing["tags"] = list(dict.fromkeys(existing.get("tags", []) + tags))
            if summary:
                existing["summary"] = summary
            logging.info(f"Updated picture in catalog: {dest_filename} (tags: {existing.get('tags')}, summary: '{existing.get('summary')}')")
        else:
            catalog.append(entry)
            if len(catalog) > 1000:
                catalog = catalog[-1000:]
            logging.info(f"Saved new image to picture database: {dest_filename} (tags: {tags}, summary: '{summary}')")

        with open(PICTURE_CATALOG_FILE, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.warning(f"Failed to update picture catalog: {e}")

    return entry

def search_picture_database(query: str) -> str:
    """Searches picture_db catalog and stickers directory for a picture matching query. Returns absolute path."""
    q = query.strip().lower()
    if not q:
        return ""

    # 1. Search in picture_db catalog
    init_picture_database()
    if os.path.exists(PICTURE_CATALOG_FILE):
        try:
            with open(PICTURE_CATALOG_FILE, "r", encoding="utf-8") as f:
                catalog = json.load(f)
                for item in reversed(catalog):
                    tags = [t.lower() for t in item.get("tags", [])]
                    summary = item.get("summary", "").lower()
                    fname = item.get("filename", "").lower()
                    if q in tags or any(q in t or t in q for t in tags) or q in summary or q in fname:
                        rel_path = item.get("path", "")
                        abs_p = os.path.join(BASE_DIR, rel_path)
                        if os.path.exists(abs_p):
                            return abs_p
        except Exception as e:
            logging.debug(f"Catalog search error: {e}")

    # 2. Search in stickers directory
    if os.path.exists(STICKERS_DIR):
        for fname in os.listdir(STICKERS_DIR):
            base, _ = os.path.splitext(fname)
            if q in base.lower() or base.lower() in q:
                return os.path.join(STICKERS_DIR, fname)
        for alias_key, alias_list in STICKER_ALIASES.items():
            if q in alias_list or q == alias_key:
                for fname in os.listdir(STICKERS_DIR):
                    base, _ = os.path.splitext(fname)
                    if any(a.lower() in base.lower() for a in alias_list):
                        return os.path.join(STICKERS_DIR, fname)
    return ""

# ==============================================================================
# Feature 1: Forwarded / Combined Chat History Resolution
# ==============================================================================
def fetch_forward_messages(forward_id: str, depth: int = 1) -> str:
    """Fetch and parse OneBot 11 combined/forwarded chat history nodes."""
    if not forward_id:
        return ""
    try:
        res = call_onebot_api("get_forward_msg", {"id": forward_id})
        if res.get("status") != "ok":
            res = call_onebot_api("get_forward_msg", {"message_id": forward_id})

        messages = res.get("data", {}).get("messages", [])
        if not messages and isinstance(res.get("data"), list):
            messages = res.get("data")

        if not messages:
            return f"[合并转发聊天记录: 内容为空或未获取到 (ID: {forward_id})]"

        formatted_nodes = []
        for idx, node in enumerate(messages[:30], 1):
            sender_info = node.get("sender", {})
            sender_name = sender_info.get("nickname") or sender_info.get("card") or f"用户{sender_info.get('user_id', '未知')}"

            node_time = node.get("time")
            time_str = ""
            if node_time:
                try:
                    time_str = datetime.datetime.fromtimestamp(node_time).strftime("%H:%M:%S")
                except Exception:
                    pass
            time_tag = f" ({time_str})" if time_str else ""

            content = node.get("content") or node.get("message") or ""
            parsed_content = ""
            if isinstance(content, list):
                node_texts = []
                for seg in content:
                    stype = seg.get("type")
                    sdata = seg.get("data", {})
                    if stype == "text":
                        node_texts.append(sdata.get("text", ""))
                    elif stype == "image":
                        node_texts.append("[图片]")
                    elif stype == "face":
                        fid = int(sdata.get("id", -1))
                        fname = QQ_FACE_ID_TO_NAME.get(fid, str(fid))
                        node_texts.append(f"[表情: {fname}]")
                    elif stype == "record":
                        node_texts.append("[语音]")
                    elif stype == "forward" and depth < 2:
                        node_texts.append(fetch_forward_messages(sdata.get("id", ""), depth=depth + 1))
                    elif stype == "file":
                        node_texts.append(f"[文件: {sdata.get('name', '未命名')}]")
                    elif stype == "marketface":
                        node_texts.append(f"[动画大表情: {sdata.get('summary', '表情')}]")
                    else:
                        node_texts.append(f"[{stype}]")
                parsed_content = "".join(node_texts).strip()
            elif isinstance(content, str):
                parsed_content = content
                if "[CQ:forward" in parsed_content and depth < 2:
                    sub_fwd = re.search(r'\[CQ:forward,id=([^\],]+)\]', parsed_content)
                    if sub_fwd:
                        parsed_content = fetch_forward_messages(sub_fwd.group(1), depth=depth + 1)
                parsed_content = re.sub(r'\[CQ:image,[^\]]*\]', '[图片]', parsed_content)
                parsed_content = re.sub(r'\[CQ:record,[^\]]*\]', '[语音]', parsed_content)
                parsed_content = re.sub(r'\[CQ:marketface,[^\]]*summary=([^\],]+)[^\]]*\]', r'[动画大表情: \1]', parsed_content)
                parsed_content = re.sub(r'\[CQ:[^\]]*\]', '', parsed_content).strip()

            formatted_nodes.append(f"  {idx}. {sender_name}{time_tag}: {parsed_content}")

        total_count = len(messages)
        header = f"[合并转发聊天记录 (共 {total_count} 条)]:\n"
        return header + "\n".join(formatted_nodes)
    except Exception as e:
        logging.warning(f"Error resolving forward message {forward_id}: {e}")
        return f"[合并转发聊天记录: 解析异常 (ID: {forward_id})]"

# ==============================================================================
# Feature 3: Multi-Format Document / File Parser (.doc, .pdf, .mp3, .txt, etc.)
# ==============================================================================
def extract_text_from_file(file_path: str, max_chars: int = 3500) -> str:
    """Extracts human-readable text from documents (.txt, .md, .pdf, .docx, .json, etc.)."""
    if not os.path.exists(file_path):
        return ""
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()

    # 1. Plain text and source code
    text_exts = {".txt", ".md", ".json", ".csv", ".log", ".py", ".c", ".cpp", ".h", ".sh", ".html", ".xml", ".yaml", ".yml", ".ini", ".cfg", ".rst", ".sql"}
    if ext in text_exts:
        for enc in ["utf-8", "gb18030", "gbk", "utf-16", "latin-1"]:
            try:
                with open(file_path, "r", encoding=enc, errors="replace") as f:
                    content = f.read(max_chars * 2)
                    return content[:max_chars].strip()
            except Exception:
                continue

    # 2. PDF extraction (using pypdf or fallback)
    if ext == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(file_path)
            pages_text = []
            for page in reader.pages[:10]:
                t = page.extract_text()
                if t:
                    pages_text.append(t)
                if sum(len(p) for p in pages_text) >= max_chars:
                    break
            extracted = "\n".join(pages_text).strip()
            if extracted:
                return extracted[:max_chars]
        except Exception as e:
            logging.warning(f"pypdf extraction failed for {file_path}: {e}")

    # 3. DOCX extraction (python-docx or built-in zipfile fallback)
    if ext == ".docx":
        try:
            import docx
            doc = docx.Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            extracted = "\n".join(paragraphs).strip()
            if extracted:
                return extracted[:max_chars]
        except Exception:
            try:
                with zipfile.ZipFile(file_path) as z:
                    xml_content = z.read("word/document.xml").decode("utf-8")
                    text_parts = re.findall(r'<w:t[^>]*>(.*?)</w:t>', xml_content)
                    return "".join(text_parts)[:max_chars].strip()
            except Exception as e:
                logging.warning(f"DOCX extraction fallback failed: {e}")

    return ""

def resolve_onebot_file_path(path: str) -> str:
    """Translates OneBot/NapCat container paths to host paths if running in Docker."""
    if not path:
        return ""
    if os.path.exists(path):
        return path
    if path.startswith("/app/.config/QQ/"):
        for base in ["/opt/napcat/qq", os.path.expanduser("~/.napcat/qq"), os.path.join(BASE_DIR, "qq")]:
            host_p = path.replace("/app/.config/QQ", base)
            if os.path.exists(host_p):
                return host_p
    if path.startswith("/app/napcat/config/"):
        for base in ["/opt/napcat/config", os.path.expanduser("~/.napcat/config")]:
            host_p = path.replace("/app/napcat/config", base)
            if os.path.exists(host_p):
                return host_p
    fname = os.path.basename(path)
    if os.path.exists("/opt/napcat/qq"):
        for root, dirs, files in os.walk("/opt/napcat/qq"):
            if fname in files:
                return os.path.join(root, fname)
    return path

def process_incoming_file(file_id: str, file_name: str = "", file_size: int = 0, file_url: str = "") -> str:
    """Download/locate incoming file, extract readable text, and format for the model."""
    if not config.get("enable_file_parser", True):
        return f"[收到文件: {file_name or file_id}]"

    local_path = ""
    if file_id:
        try:
            res = call_onebot_api("get_file", {"file_id": file_id})
            if res.get("status") == "ok":
                local_path = res.get("data", {}).get("file", "")
                data_url = res.get("data", {}).get("url", "")
                if not file_url and data_url and data_url.startswith(("http://", "https://")):
                    file_url = data_url
        except Exception as e:
            logging.debug(f"get_file API error: {e}")

    if local_path:
        local_path = resolve_onebot_file_path(local_path)

    if (not local_path or not os.path.exists(local_path)) and file_url and file_url.startswith(("http://", "https://")):
        try:
            temp_dir = os.path.join(BASE_DIR, "downloads")
            os.makedirs(temp_dir, exist_ok=True)
            safe_name = os.path.basename(file_name) if file_name else f"file_{file_id}"
            local_path = os.path.join(temp_dir, safe_name)
            req = urllib.request.Request(file_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                with open(local_path, "wb") as out_f:
                    out_f.write(resp.read())
        except Exception as e:
            logging.warning(f"Download file from URL failed: {e}")

    size_str = ""
    if file_size > 0:
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
    elif local_path and os.path.exists(local_path):
        actual_size = os.path.getsize(local_path)
        size_str = f"{actual_size / (1024 * 1024):.1f} MB" if actual_size > 1024 * 1024 else f"{actual_size / 1024:.1f} KB"

    display_name = file_name or (os.path.basename(local_path) if local_path else file_id)
    if not local_path or not os.path.exists(local_path):
        return f"[收到文件: {display_name} ({size_str})]" if size_str else f"[收到文件: {display_name}]"

    text_content = extract_text_from_file(local_path, max_chars=config.get("max_file_text_chars", 3500))
    if text_content:
        return f"[接收到文件: {display_name} ({size_str}) | 文件内容摘要提取:\n```\n{text_content}\n```]"
    else:
        return f"[接收到文件: {display_name} ({size_str}) (非纯文本格式文件)]"

# ==============================================================================
# Feature 4: Inbound Voice Recognition (ASR)
# ==============================================================================
def transcribe_voice_via_api(audio_path: str) -> str:
    """Transcribes audio using a configured Whisper-compatible API (SiliconFlow, Groq, OpenAI)."""
    api_url = config.get("asr_api_url", "").strip()
    if not api_url:
        return ""
    api_key = config.get("asr_api_key", "").strip()
    if not api_key:
        main_base = config.get("base_url", "")
        if urllib.parse.urlparse(api_url).netloc == urllib.parse.urlparse(main_base).netloc:
            api_key = config.get("api_key", "").strip()
    model = config.get("asr_model", "whisper-1").strip()

    send_path = audio_path
    created_mp3 = False
    if not audio_path.lower().endswith((".mp3", ".wav")):
        mp3_path = audio_path + ".mp3"
        try:
            subprocess.run(["ffmpeg", "-y", "-i", audio_path, mp3_path],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            if os.path.exists(mp3_path):
                send_path = mp3_path
                created_mp3 = True
        except Exception as fe:
            logging.debug(f"Audio conversion for ASR API failed: {fe}")

    try:
        import requests
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        with open(send_path, "rb") as f:
            files = {"file": (os.path.basename(send_path), f, "audio/mpeg")}
            data = {"model": model}
            logging.info(f"Submitting audio to ASR API ({api_url})...")
            resp = requests.post(api_url, headers=headers, files=files, data=data, timeout=30)
            if resp.status_code == 200:
                res_json = resp.json()
                text = res_json.get("text", "").strip()
                if text:
                    logging.info(f"ASR API transcription succeeded: '{text}'")
                    return text
            else:
                logging.warning(f"ASR API returned status {resp.status_code}: {resp.text}")
    except Exception as e:
        logging.warning(f"ASR API request failed: {e}")
    finally:
        if created_mp3 and os.path.exists(send_path):
            try: os.remove(send_path)
            except Exception: pass
    return ""

def transcribe_voice_audio(audio_path: str) -> str:
    """Transcribes an audio file into text using available cloud/local ASR engines."""
    if not os.path.exists(audio_path):
        return ""

    # Check if incoming audio is Silk v3 format (QQ native voice)
    decoded_wav_path = None
    if SILKCODER_AVAILABLE:
        try:
            with open(audio_path, "rb") as test_f:
                header = test_f.read(12)
            if b"#!SILK_V3" in header:
                wav_tmp = audio_path + ".decoded.wav"
                silkcoder.decode(audio_path, wav_tmp)
                if os.path.exists(wav_tmp) and os.path.getsize(wav_tmp) > 0:
                    decoded_wav_path = wav_tmp
                    audio_path = wav_tmp
                    logging.info(f"Successfully decoded Tencent Silk voice to WAV via silkcoder: {wav_tmp}")
        except Exception as sde:
            logging.debug(f"silkcoder decode check failed: {sde}")
    elif PILK_AVAILABLE:
        try:
            with open(audio_path, "rb") as test_f:
                header = test_f.read(12)
            if b"#!SILK_V3" in header:
                pcm_tmp = audio_path + ".decoded.pcm"
                wav_tmp = audio_path + ".decoded.wav"
                pilk.decode(audio_path, pcm_tmp)
                res = subprocess.run(
                    ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", pcm_tmp, wav_tmp],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10
                )
                if os.path.exists(pcm_tmp):
                    try: os.remove(pcm_tmp)
                    except Exception: pass
                if res.returncode == 0 and os.path.exists(wav_tmp):
                    decoded_wav_path = wav_tmp
                    audio_path = wav_tmp
                    logging.info(f"Successfully decoded Tencent Silk voice to WAV: {wav_tmp}")
        except Exception as se:
            logging.debug(f"Incoming Silk decode check failed: {se}")

    try:
        # 1. Configured cloud ASR API (SiliconFlow SenseVoice / Groq / OpenAI Whisper)
        api_text = transcribe_voice_via_api(audio_path)
        if api_text:
            return api_text

        # 2. Local FunASR (SenseVoiceSmall / Paraformer) if installed
        try:
            from funasr import AutoModel
            model = AutoModel(model="iic/SenseVoiceSmall", disable_update=True, device="cpu")
            res = model.generate(input=audio_path, language="auto", use_itn=True)
            if res and isinstance(res, list) and "text" in res[0]:
                from funasr.utils.postprocess_utils import rich_transcription_postprocess
                t = rich_transcription_postprocess(res[0]["text"]).strip()
                if t:
                    logging.info(f"Local FunASR transcription: '{t}'")
                    return t
        except Exception:
            pass

        # 3. Local Whisper if installed
        try:
            import whisper
            w_model = whisper.load_model("tiny")
            res = w_model.transcribe(audio_path)
            text = res.get("text", "").strip()
            if text:
                logging.info(f"Local Whisper transcription: '{text}'")
                return text
        except Exception:
            pass

        # 4. SpeechRecognition with Google ASR (Guarded with 3.0s timeout to prevent 120s hanging in China)
        lang = config.get("language", "zh").lower()
        if lang != "zh" or config.get("enable_google_asr", False):
            try:
                import speech_recognition as sr
                r = sr.Recognizer()
                wav_path = audio_path
                created_wav = False
                if not audio_path.lower().endswith(".wav"):
                    wav_path = audio_path + ".temp.wav"
                    subprocess.run(["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                    created_wav = True

                if os.path.exists(wav_path):
                    with sr.AudioFile(wav_path) as source:
                        audio_data = r.record(source)
                        sr_result = []
                        def _recognize():
                            try:
                                sr_result.append(r.recognize_google(audio_data, language="zh-CN" if lang == "zh" else "en-US"))
                            except Exception:
                                pass
                        t_sr = threading.Thread(target=_recognize, daemon=True)
                        t_sr.start()
                        t_sr.join(timeout=3.0)
                        if sr_result and sr_result[0]:
                            text = sr_result[0].strip()
                            logging.info(f"SpeechRecognition ASR transcription: '{text}'")
                            return text
            except Exception as e:
                logging.debug(f"SpeechRecognition ASR error: {e}")
            finally:
                if 'created_wav' in locals() and created_wav and os.path.exists(wav_path):
                    try: os.remove(wav_path)
                    except Exception: pass
    finally:
        if decoded_wav_path and os.path.exists(decoded_wav_path):
            try: os.remove(decoded_wav_path)
            except Exception: pass

    return ""

def process_incoming_voice(file_id: str, file_url: str = "") -> str:
    """Download incoming voice message, convert and transcribe via ASR."""
    if not config.get("enable_voice_recognition", True):
        return "（收到一条语音消息）"

    local_path = ""
    if file_id:
        try:
            res = call_onebot_api("get_record", {"file": file_id, "out_format": "mp3"})
            if res.get("status") == "ok":
                local_path = res.get("data", {}).get("file", "")
                data_url = res.get("data", {}).get("url", "")
                if not file_url and data_url and data_url.startswith(("http://", "https://")):
                    file_url = data_url
        except Exception as e:
            logging.debug(f"get_record API error: {e}")

    if local_path:
        local_path = resolve_onebot_file_path(local_path)

    if (not local_path or not os.path.exists(local_path)) and file_url and file_url.startswith(("http://", "https://")):
        try:
            temp_dir = os.path.join(BASE_DIR, "downloads")
            os.makedirs(temp_dir, exist_ok=True)
            local_path = os.path.join(temp_dir, f"voice_{file_id}.mp3")
            req = urllib.request.Request(file_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                with open(local_path, "wb") as out_f:
                    out_f.write(resp.read())
        except Exception as e:
            logging.warning(f"Download voice from URL failed: {e}")

    if local_path and os.path.exists(local_path):
        transcription = transcribe_voice_audio(local_path)
        if transcription:
            return f"[语音消息 (已转文字): \"{transcription}\"]"

        # Diagnostic annotation when transcription is not available:
        model_name = config.get("model", "pure-text")
        if any(m in model_name.lower() for m in ["gemini", "gpt-4o", "omni"]):
            return f"[语音消息: 收到用户发送的语音 ({os.path.basename(local_path)})。提示：当前模型支持多模态，请结合对话上下文自然回复]"

        return (
            f"[语音消息: 收到用户发送的语音 ({os.path.basename(local_path)})。"
            f"系统提示：当前配置的模型为纯文本模型 ({model_name})，且后台暂未配置可用的 ASR 语音识别服务（可在 config.json 配置 asr_api_url）。"
            f"请在回复中以拟人化口吻告知主人目前由于在纯文本环境无法收听语音内容，建议主人发文字交流]"
        )

    return "（收到一条语音消息，但音频文件获取失败）"

# ==============================================================================
# Comprehensive Incoming Message Parser (Super Emojis, GIFs, Forwards, Files, Voice)
# ==============================================================================
def parse_incoming_cq_content(raw_text: str, sender_id: int = 0):
    images_b64 = []

    # 1. Resolve Combined / Forwarded Chat History [CQ:forward,...]
    fwd_matches = re.findall(r'\[CQ:forward,[^\]]*?(?:id|res_id|forward_id)=([^\],]+)[^\]]*\]', raw_text, re.IGNORECASE)
    for json_cq in re.finditer(r'\[CQ:json,data=([^\],]+)\]', raw_text, re.IGNORECASE):
        try:
            j_data = json.loads(html.unescape(json_cq.group(1)))
            r_id = j_data.get("meta", {}).get("detail", {}).get("resid") or j_data.get("meta", {}).get("news", {}).get("resid")
            if r_id and r_id not in fwd_matches:
                fwd_matches.append(r_id)
        except Exception:
            pass

    for fwd_id in fwd_matches:
        fwd_content = fetch_forward_messages(fwd_id)
        raw_text = re.sub(rf'\[CQ:forward,[^\]]*?(?:id|res_id|forward_id)={re.escape(fwd_id)}[^\]]*\]', f"\n{fwd_content}\n", raw_text)

    # 2. Resolve Super Emojis & Marketface [CQ:marketface,id=...,summary=...]
    for mf in re.finditer(r'\[CQ:marketface,[^\]]*?\]', raw_text, re.IGNORECASE):
        tag = mf.group(0)
        summary_m = re.search(r'summary=([^\],]+)', tag)
        summary = summary_m.group(1).strip() if summary_m else "动画大表情"
        raw_text = raw_text.replace(tag, f"[动画表情: {summary}]")

    # 3. Interactive Faces: Dice & RPS
    for dice in re.finditer(r'\[CQ:dice,value=([0-9]+)[^\]]*\]', raw_text, re.IGNORECASE):
        raw_text = raw_text.replace(dice.group(0), f"[掷出骰子: {dice.group(1)}点]")
    for rps in re.finditer(r'\[CQ:rps,[^\]]*?(?:value|type)=([1-3])[^\]]*\]', raw_text, re.IGNORECASE):
        val = int(rps.group(1))
        raw_text = raw_text.replace(rps.group(0), f"[猜拳出拳: {RPS_MAP.get(val, '出拳')}]")

    # 4. QQ Native Faces [CQ:face,id=...]
    for face in re.finditer(r'\[CQ:face,id=([0-9]+)[^\]]*\]', raw_text, re.IGNORECASE):
        fid = int(face.group(1))
        fname = QQ_FACE_ID_TO_NAME.get(fid, f"#{fid}")
        raw_text = raw_text.replace(face.group(0), f"[QQ表情: {fname}]")

    # 5. Nudge / Poke [CQ:poke,...]
    raw_text = re.sub(r'\[CQ:poke,[^\]]*\]', '[戳了戳你]', raw_text, flags=re.IGNORECASE)

    # 6. Incoming Files [CQ:file,id=...,name=...,size=...,url=...]
    for f_match in re.finditer(r'\[CQ:file,[^\]]*?\]', raw_text, re.IGNORECASE):
        tag = f_match.group(0)
        fid = (re.search(r'file_id=([^\],]+)', tag) or re.search(r'id=([^\],]+)', tag) or re.search(r'file=([^\],]+)', tag))
        fid_val = fid.group(1).strip() if fid else ""
        fname_m = re.search(r'name=([^\],]+)', tag)
        fname_val = fname_m.group(1).strip() if fname_m else ""
        fsize_m = re.search(r'size=([0-9]+)', tag)
        fsize_val = int(fsize_m.group(1)) if fsize_m else 0
        furl_m = re.search(r'url=([^\],]+)', tag)
        furl_val = furl_m.group(1).strip() if furl_m else ""
        file_desc = process_incoming_file(fid_val, fname_val, fsize_val, furl_val)
        raw_text = raw_text.replace(tag, f"\n{file_desc}\n")

    # 7. Incoming Voice Messages [CQ:record,file=...,url=...]
    has_voice = "[CQ:record" in raw_text
    for v_match in re.finditer(r'\[CQ:record,[^\]]*?\]', raw_text, re.IGNORECASE):
        tag = v_match.group(0)
        v_fid = re.search(r'file=([^\],]+)', tag)
        v_fid_val = v_fid.group(1).strip() if v_fid else ""
        v_url = re.search(r'url=([^\],]+)', tag)
        v_url_val = v_url.group(1).strip() if v_url else ""
        voice_desc = process_incoming_voice(v_fid_val, v_url_val)
        raw_text = raw_text.replace(tag, voice_desc)

    # 8. Images & GIF / Sticker Detection [CQ:image,...]
    cq_img_pattern = re.compile(r'\[CQ:image,[^\]]*?\]', re.IGNORECASE)
    for match in cq_img_pattern.finditer(raw_text):
        tag = match.group(0)
        url_match = re.search(r'url=([^\],]+)', tag)
        file_match = re.search(r'file=([^\],]+)', tag)
        sub_type_match = re.search(r'subType=([0-9]+)', tag)
        summary_match = re.search(r'summary=([^\],]+)', tag)

        url = url_match.group(1).strip() if url_match else ""
        file_id = file_match.group(1).strip() if file_match else ""
        sub_type = sub_type_match.group(1).strip() if sub_type_match else ""
        summary = summary_match.group(1).strip() if summary_match else ""

        is_gif_or_sticker = sub_type == "1" or ".gif" in url.lower() or ".gif" in file_id.lower() or "动画表情" in summary or "表情" in summary

        if url:
            b64, raw_b = download_image_data(url, file_id)
            if b64:
                images_b64.append(b64)
            # Auto-save to picture database
            if raw_b and config.get("enable_picture_database", True):
                tags = ["表情包", "动图"] if is_gif_or_sticker else ["照片", "用户发送"]
                save_to_picture_database(raw_b, sender_id=sender_id, tags=tags, summary=summary or ("表情包" if is_gif_or_sticker else "图片"))

        label = "[表情包/动图]" if is_gif_or_sticker else "[图片]"
        raw_text = raw_text.replace(tag, label)

    clean_text = re.sub(r'\[CQ:[^\]]+\]', '', raw_text).strip()
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

async def synthesize_voice_file(text: str, output_path: str) -> bool:
    if not EDGE_TTS_AVAILABLE:
        logging.warning("edge-tts is not installed in Python environment!")
        return False
    lang = config.get("language", "zh").lower()
    configured_voice = config.get("voice_character", "")
    if lang == "en" and (not configured_voice or configured_voice.startswith("zh-")):
        voice = "en-US-JennyNeural"
    else:
        voice = configured_voice or "zh-CN-XiaoyiNeural"

    clean_txt = clean_tags(text)
    clean_txt = re.sub(r'[*_#`~]', '', clean_txt)
    clean_txt = re.sub(r'\[SEP\]', ' ', clean_txt).strip()
    if not clean_txt:
        logging.warning("Empty text for voice synthesis after cleaning.")
        return False

    try:
        logging.info(f"Synthesizing voice with Edge-TTS (voice={voice}): '{clean_txt[:40]}...'")
        communicate = edge_tts.Communicate(clean_txt, voice)
        await asyncio.wait_for(communicate.save(output_path), timeout=25.0)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            logging.info(f"Edge-TTS synthesis complete: {output_path} ({os.path.getsize(output_path)} bytes)")
            return True
        else:
            logging.error(f"Edge-TTS produced empty audio at {output_path}")
            return False
    except asyncio.TimeoutError:
        logging.error("Edge-TTS synthesis timed out after 25 seconds.")
        return False
    except Exception as e:
        logging.error(f"Edge-TTS communicate.save error: {e}")
        return False

def transcode_to_silk(input_audio_path: str, output_silk_path: str) -> bool:
    """Encodes an audio file (MP3/WAV) to genuine Tencent SILK v3 with magic header \x02#!SILK_V3."""
    # Method 1: graiax-silkcoder (precompiled wheels on Linux & Windows)
    if SILKCODER_AVAILABLE:
        try:
            silkcoder.encode(input_audio_path, output_silk_path)
            if os.path.exists(output_silk_path) and os.path.getsize(output_silk_path) > 0:
                logging.info(f"Audio encoded to Silk v3 via graiax-silkcoder: {output_silk_path} ({os.path.getsize(output_silk_path)} bytes)")
                return True
        except Exception as ge:
            logging.debug(f"graiax-silkcoder encode failed: {ge}")

    # Method 2: pilk (ffmpeg -> s16le PCM -> pilk.encode with Tencent header)
    if PILK_AVAILABLE:
        try:
            pcm_path = input_audio_path + ".temp.pcm"
            sample_rate = 24000
            cmd = [
                "ffmpeg", "-y",
                "-i", input_audio_path,
                "-vn",
                "-ar", str(sample_rate),
                "-ac", "1",
                "-f", "s16le",
                pcm_path
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            if res.returncode == 0 and os.path.exists(pcm_path):
                pilk.encode(pcm_path, output_silk_path, pcm_rate=sample_rate, tencent=True)
                if os.path.exists(pcm_path):
                    try: os.remove(pcm_path)
                    except Exception: pass
                if os.path.exists(output_silk_path) and os.path.getsize(output_silk_path) > 0:
                    logging.info(f"Audio successfully transcoded to Tencent Silk v3 via pilk: {output_silk_path} ({os.path.getsize(output_silk_path)} bytes)")
                    return True
        except Exception as pe:
            logging.debug(f"pilk encode failed: {pe}")

    return False

def transcode_to_wav(input_audio_path: str, output_wav_path: str) -> bool:
    """Converts audio to 24000Hz 16-bit mono WAV as fallback for NapCat."""
    try:
        cmd = [
            "ffmpeg", "-y",
            "-i", input_audio_path,
            "-vn",
            "-ar", "24000",
            "-ac", "1",
            output_wav_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        if res.returncode == 0 and os.path.exists(output_wav_path) and os.path.getsize(output_wav_path) > 0:
            logging.info(f"Audio transcoded to 24000Hz mono WAV: {output_wav_path} ({os.path.getsize(output_wav_path)} bytes)")
            return True
    except Exception as e:
        logging.warning(f"WAV transcoding error: {e}")
    return False

def send_voice_message(text: str):
    global last_bot_voice_send_time
    if not EDGE_TTS_AVAILABLE:
        logging.warning("edge-tts is not installed. Voice synthesis skipped. Run 'pip install edge-tts'.")
        return

    is_self_chat = str(config.get("bot_qq", "")) == str(config.get("master_qq", ""))
    if is_self_chat:
        logging.warning("[!] Warning: Single-account self-chat mode (bot_qq == master_qq). Tencent QQ restricts accounts from receiving voice messages sent to themselves. Please use two separate QQ accounts (bot_qq != master_qq) to receive voice bubbles on QQ.")

    temp_audio = os.path.join(BASE_DIR, "temp_reply.mp3")
    silk_path = os.path.join(BASE_DIR, "temp_reply.silk")
    wav_path = os.path.join(BASE_DIR, "temp_reply.wav")
    try:
        success = asyncio.run(synthesize_voice_file(text, temp_audio))
        if not success or not os.path.exists(temp_audio) or os.path.getsize(temp_audio) == 0:
            logging.error(f"Voice synthesis failed or generated empty audio for: '{text[:40]}...'")
            return

        audio_to_send = temp_audio
        file_name = "voice.mp3"

        if transcode_to_silk(temp_audio, silk_path):
            audio_to_send = silk_path
            file_name = "voice.silk"
        elif transcode_to_wav(temp_audio, wav_path):
            audio_to_send = wav_path
            file_name = "voice.wav"

        with open(audio_to_send, "rb") as af:
            raw_audio_bytes = af.read()
            b64_audio = base64.b64encode(raw_audio_bytes).decode('utf-8')

        target_qq = config["master_qq"]
        logging.info(f"Dispatching voice message ({file_name}, {len(raw_audio_bytes)} bytes) to QQ {target_qq}...")

        # Update voice send timestamp & recent replies to avoid single-account echo loop
        last_bot_voice_send_time = time.time()
        recent_bot_replies.append(text.strip())
        recent_bot_replies.append(f"[语音消息: \"{text.strip()}\"]")
        recent_bot_replies.append(f"[语音消息 (已转文字): \"{text.strip()}\"]")

        res = None
        ext = os.path.splitext(file_name)[1].lstrip(".") or "mp3"

        # Strategy 1: Container shared volume path (/opt/napcat/qq -> /app/.config/QQ)
        # Bypasses base64 memory overhead and allows NapCat to read file directly
        if os.path.exists("/opt/napcat/qq"):
            shared_target = f"/opt/napcat/qq/napcat_temp_voice.{ext}"
            try:
                shutil.copyfile(audio_to_send, shared_target)
                res = call_onebot_api("send_private_msg", {
                    "user_id": target_qq,
                    "message": [
                        {
                            "type": "record",
                            "data": {
                                "file": f"file:///app/.config/QQ/napcat_temp_voice.{ext}",
                                "magic": 0
                            }
                        }
                    ]
                })
            except Exception as e1:
                logging.warning(f"Voice send Strategy 1 (container file) error: {e1}")

        # Strategy 2: CQ Code String Format (the exact proven method from Gemini_as_catgirl)
        if not res or res.get("status") != "ok":
            try:
                res = call_onebot_api("send_private_msg", {
                    "user_id": target_qq,
                    "message": f"[CQ:record,file=base64://{b64_audio}]"
                })
            except Exception as e2:
                logging.warning(f"Voice send Strategy 2 (CQ string) error: {e2}")

        # Strategy 3: OneBot 11 Standard Segment Array Format with Base64 & explicit file name
        if not res or res.get("status") != "ok":
            try:
                res = call_onebot_api("send_private_msg", {
                    "user_id": target_qq,
                    "message": [
                        {
                            "type": "record",
                            "data": {
                                "file": f"base64://{b64_audio}",
                                "name": file_name,
                                "magic": 0
                            }
                        }
                    ]
                })
            except Exception as e3:
                logging.warning(f"Voice send Strategy 3 (base64 segment) error: {e3}")

        if res and res.get("status") == "ok":
            logging.info(f"Voice message successfully dispatched to QQ {target_qq}! (Format: {file_name}, OneBot: {res})")
        else:
            logging.error(f"Failed to dispatch voice message to QQ {target_qq}. OneBot response: {res}")
    except Exception as e:
        logging.error(f"Failed to synthesize/send voice: {e}", exc_info=True)
    finally:
        for p in [temp_audio, silk_path, wav_path]:
            if p and os.path.exists(p):
                try: os.remove(p)
                except Exception: pass

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
        threading.Thread(target=send_voice_message, args=[v_text], daemon=True).start()

    # 4. Global Voice Mode
    if config.get("enable_voice_reply", False) and not voice_matches:
        clean_msg = clean_tags(reply_text)
        if clean_msg:
            threading.Thread(target=send_voice_message, args=[clean_msg], daemon=True).start()

    # 5. Interactivity: Pokes & Likes (Supports [poke], [Poke], [Interact: Poke], [like], [Like], [Interact: Like])
    if re.search(r'\[(?:互动|Interact|interact):\s*(?:戳一戳|Poke|poke)\]|\[(?:poke|Poke)\]', reply_text, re.IGNORECASE):
        call_onebot_api("friend_poke", {"user_id": config["master_qq"]})
    if re.search(r'\[(?:互动|Interact|interact):\s*(?:点赞|Like|like)\]|\[(?:like|Like)\]', reply_text, re.IGNORECASE):
        call_onebot_api("send_like", {"user_id": config["master_qq"], "times": 10})

    # 6. Realtime Memory Updates
    mem_matches = re.findall(r'\[(?:更新记忆|Update Memory|update_memory|remember|Remember):\s*([^\]]+)\]', reply_text, re.IGNORECASE)
    for mem_content in mem_matches:
        update_memory_realtime(mem_content)

    # 7. Custom Picture & Meme Dispatch (Supports [PICTURE: tag], [IMAGE: tag], [发图: 关键词], [发贴图: 关键词], [发照片: 关键词])
    pic_matches = re.findall(r'\[(?:PICTURE|picture|IMAGE|image|发图|发贴图|发照片):\s*([^\]]+)\]', reply_text, re.IGNORECASE)
    for p_query in pic_matches:
        img_path = search_picture_database(p_query)
        if img_path and os.path.exists(img_path):
            try:
                with open(img_path, "rb") as imf:
                    b64_im = base64.b64encode(imf.read()).decode("utf-8")
                call_onebot_api("send_private_msg", {
                    "user_id": config["master_qq"],
                    "message": f"[CQ:image,file=base64://{b64_im}]"
                })
                logging.info(f"Dispatched custom picture/sticker from library: {os.path.basename(img_path)} (matched: '{p_query}')")
            except Exception as pe:
                logging.error(f"Failed to encode/send custom picture: {pe}")
        else:
            logging.warning(f"Custom picture/sticker not found in library for query: '{p_query}'")

    # 8. Agent-managed Sticker/Picture Tagging & Saving
    # (Supports [收藏表情: 标签: 描述], [保存表情: 标签: 描述], [收藏图片: 标签: 描述], [SAVE_STICKER: tags: desc])
    save_matches = re.findall(r'\[(?:收藏表情|保存表情|添加表情|收藏图片|保存图片|SAVE_STICKER|save_sticker):\s*([^\]]+)\]', reply_text, re.IGNORECASE)
    for s_info in save_matches:
        s_info = s_info.strip()
        tags = []
        summary = ""
        if ":" in s_info or "：" in s_info:
            sep = ":" if ":" in s_info else "："
            parts = s_info.split(sep, 1)
            tags_part = parts[0].strip()
            summary = parts[1].strip()
            tags = [t.strip() for t in re.split(r'[,，\s]+', tags_part) if t.strip()]
        else:
            tags = [t.strip() for t in re.split(r'[,，\s]+', s_info) if t.strip()]
            summary = s_info

        if latest_received_image_bytes:
            save_to_picture_database(latest_received_image_bytes, sender_id=config["master_qq"], tags=tags, summary=summary)
            logging.info(f"Agent autonomously added sticker/picture to library: tags={tags}, summary='{summary}'")
        else:
            logging.warning(f"Agent requested to save sticker ({tags}), but no image was found in recent conversation context.")

def clean_tags(reply_text: str) -> str:
    text = re.sub(r'\[(?:发贴图|Send Sticker|Sticker|sticker):[^\]]+\]', '', reply_text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:发表情|Send Face|Face|face|Emoji|emoji):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:发语音|Send Voice|Voice|voice):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:PICTURE|picture|IMAGE|image|发图|发照片):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:收藏表情|保存表情|添加表情|收藏图片|保存图片|SAVE_STICKER|save_sticker):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:互动|Interact|interact):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:poke|Poke|like|Like)\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:更新记忆|Update Memory|update_memory|remember|Remember):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:查看记忆|Read Memory|read_memory|Memory|memory)\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:搜索|Search|search|web_search):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:搜索聊天记录|Search History|search_history|history):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:NO_REPLY|no_reply|SILENCE|silence)\]', '', text, flags=re.IGNORECASE)
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
        elif tool_name == "search_picture_library":
            q = arguments.get("query", "")
            img_p = search_picture_database(q)
            if img_p:
                return f"找到匹配图片: {os.path.basename(img_p)}。若需发送给对方，可在回复中加入 [PICTURE: {q}]。"
            else:
                return f"图片库中未找到与 '{q}' 相关的图片。"
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

    url = get_llm_url()

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
                            logging.warning(f"LLM call attempt #{attempt+1} JSON decode error on {url}: {je}, body={resp.text[:200]}")
                    else:
                        logging.warning(f"LLM call attempt #{attempt+1} failed ({resp.status_code}) on {url}: {resp.text[:200]}")
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

        # Check for autonomous refusal ([NO_REPLY] / [SILENCE])
        clean_stripped = reply.strip()
        if clean_stripped in ["[NO_REPLY]", "[SILENCE]"] or clean_stripped.startswith("[NO_REPLY]") or clean_stripped.startswith("【NO_REPLY】"):
            logging.info("[System message] Model refused to reply (Persona silent/arrogant mode)")
            print("\n>>> [System message] Model refused to reply <<<\n")
            append_to_full_chat_history("assistant", "[Model refused to reply]", sender_id=config.get("bot_qq"))
            with batch_lock:
                if gen_id == current_generation_id and not pending_messages and not in_flight_messages:
                    current_generation_id = 0
            return

        # Record to persistent memory & chat logs ONLY for the confirmed winning reply
        record_chat_turn(history_record_text, reply, has_image=bool(all_images))

        # Execute actions (custom pictures, stickers, QQ faces, voice, poke, memory updates)
        execute_action_tags(reply)

        clean_text_reply = clean_tags(reply)
        if clean_text_reply:
            recent_bot_replies.append(clean_text_reply)

            # Multi-bubble message sending: split by [SEP] delimiter
            if "[SEP]" in clean_text_reply and config.get("enable_multi_bubble_reply", True):
                bubbles = [b.strip() for b in clean_text_reply.split("[SEP]") if b.strip()]
            else:
                bubbles = [clean_text_reply]

            delay_sec = config.get("multi_bubble_delay_sec", 1.2)
            for idx, bubble in enumerate(bubbles):
                recent_bot_replies.append(bubble)
                res = call_onebot_api("send_private_msg", {
                    "user_id": config["master_qq"],
                    "message": bubble
                })
                if isinstance(res, dict) and res.get("status") == "ok":
                    bot_mid = res.get("data", {}).get("message_id")
                    if bot_mid:
                        processed_message_ids.add(bot_mid)
                if idx < len(bubbles) - 1 and delay_sec > 0:
                    time.sleep(delay_sec)

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

    is_self_chat = str(config.get("bot_qq", "")) == str(config.get("master_qq", ""))
    if not is_self_chat and sender_id != config["master_qq"]:
        return

    clean_text, images_b64, has_voice = parse_incoming_cq_content(raw_text, sender_id=sender_id)
    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    logging.info(f"Incoming message [{now_str}] (MsgID: {msg_id}) from {sender_id}: {clean_text[:120]}")

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

def is_bot_echo(text: str) -> bool:
    """Checks if a received message is an echo of the bot's own recent replies."""
    clean = text.strip()
    if not clean:
        return True
    # If a voice message is received right after bot sent voice, it's a single-account self echo
    if "[语音消息" in clean and (time.time() - last_bot_voice_send_time < 4.0):
        logging.info("Discarding echoed voice message from bot's own recent voice dispatch.")
        return True
    for r in list(recent_bot_replies):
        if not r:
            continue
        r_clean = r.strip()
        if clean == r_clean:
            return True
        if len(clean) >= 15 and len(r_clean) >= 15:
            if clean[:20] == r_clean[:20] or clean[-20:] == r_clean[-20:]:
                return True
    return False

def extract_full_message_text(m: dict) -> str:
    """Extracts complete text/CQ representation from OneBot message object."""
    msg = m.get("message")
    raw = m.get("raw_message") or ""

    if isinstance(msg, list):
        cq_parts = []
        for seg in msg:
            stype = seg.get("type", "text")
            sdata = seg.get("data", {})
            if stype == "text":
                cq_parts.append(sdata.get("text", ""))
            elif stype in ["forward", "node"]:
                fid = sdata.get("id") or sdata.get("res_id") or sdata.get("forward_id") or ""
                cq_parts.append(f"[CQ:forward,id={fid}]")
            elif stype == "record":
                file_id = sdata.get("file") or sdata.get("url") or ""
                url = sdata.get("url") or ""
                cq_parts.append(f"[CQ:record,file={file_id},url={url}]")
            elif stype == "image":
                url = sdata.get("url") or ""
                file_id = sdata.get("file") or ""
                sub_type = sdata.get("subType") or ""
                cq_parts.append(f"[CQ:image,file={file_id},url={url},subType={sub_type}]")
            elif stype == "file":
                fid = sdata.get("file_id") or sdata.get("id") or sdata.get("file") or ""
                fname = sdata.get("name") or ""
                fsize = sdata.get("size") or ""
                furl = sdata.get("url") or ""
                cq_parts.append(f"[CQ:file,file_id={fid},name={fname},size={fsize},url={furl}]")
            elif stype == "marketface":
                summary = sdata.get("summary") or ""
                cq_parts.append(f"[CQ:marketface,summary={summary}]")
            elif stype == "face":
                fid = sdata.get("id") or ""
                cq_parts.append(f"[CQ:face,id={fid}]")
            elif stype == "poke":
                cq_parts.append("[CQ:poke]")
            elif stype == "dice":
                val = sdata.get("value") or ""
                cq_parts.append(f"[CQ:dice,value={val}]")
            elif stype == "rps":
                val = sdata.get("value") or sdata.get("type") or ""
                cq_parts.append(f"[CQ:rps,value={val}]")
            else:
                params = ",".join(f"{k}={v}" for k, v in sdata.items() if v is not None and k not in ["file", "url", "text"])
                cq_parts.append(f"[CQ:{stype}{',' + params if params else ''}]")
        reconstructed = "".join(cq_parts)
        if any(marker in reconstructed for marker in ["[CQ:forward", "[CQ:record", "[CQ:file"]):
            return reconstructed
        if not raw and reconstructed:
            return reconstructed

    return raw or (str(msg) if msg else "")

def poll_messages_loop():
    logging.info("Active High-Frequency Poller started...")
    is_self_chat = str(config.get("bot_qq", "")) == str(config.get("master_qq", ""))
    if is_self_chat:
        logging.info("[*] Single-Account Self-Chat Mode active (bot_qq == master_qq). Filtering bot echoes automatically.")
    else:
        logging.info(f"[*] Two-Account Chat Mode active: Bot QQ ({config.get('bot_qq')}) <--> Master QQ ({config.get('master_qq')})")

    startup_ts = time.time()
    try:
        init_res = call_onebot_api("get_friend_msg_history", {"user_id": config["master_qq"], "count": 20})
        if init_res.get("status") == "ok":
            for m in init_res.get("data", {}).get("messages", []):
                mid = m.get("message_id")
                mtime = m.get("time", 0)
                # Only mark older messages (>180s ago) as already processed.
                # Messages sent within the last 180s (e.g. while starting up or restarting)
                # are preserved so the bot can immediately process and answer them!
                if mid and (startup_ts - mtime > 180):
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
                    text = extract_full_message_text(m)
                    if mid and mid not in processed_message_ids:
                        processed_message_ids.add(mid)
                        if len(processed_message_ids) > 10000:
                            processed_message_ids.difference_update(list(processed_message_ids)[:-5000])

                        if is_self_chat:
                            # In self-chat mode, ignore messages matching recent bot replies to prevent infinite echo
                            if is_bot_echo(text):
                                continue
                            threading.Thread(
                                target=on_message_arrived,
                                args=(mid, sender_id or config["master_qq"], text),
                                daemon=True
                            ).start()
                        else:
                            # Standard two-account mode (like Gemini_as_catgirl)
                            if sender_id == config["master_qq"]:
                                threading.Thread(
                                    target=on_message_arrived,
                                    args=(mid, sender_id, text),
                                    daemon=True
                                ).start()
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
    logging.info(f"[*] Visual Database : Enabled ({PICTURE_DB_DIR})")
    logging.info(f"[*] File Parser     : {'Enabled (Native + Local Fallback)' if config.get('enable_file_parser', True) else 'Disabled'}")
    logging.info(f"[*] Voice Recog     : {'Enabled' if config.get('enable_voice_recognition', True) else 'Disabled'}")
    logging.info(f"[*] Multi-Bubble Msg: {'Enabled ([SEP])' if config.get('enable_multi_bubble_reply', True) else 'Disabled'}")
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
