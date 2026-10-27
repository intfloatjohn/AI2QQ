#!/usr/bin/env python3
"""Autonomous 24/7 AI Companion Daemon for QQ (OneBot 11 Framework)
Features:
- Bilingual Support: Seamlessly handles Chinese and English personas & tags
- Dynamic Debounce & Interruption: Combines rapid bursts, discards outdated generation
- Auto-Compact Memory: Condenses past turns into persistent long-term memory (memory_summary.txt)
- Multimodal Vision & Audio: Receives QQ images and voice messages with dual fallback
- Edge-TTS Voice Replies: Synthesizes voice messages via [发语音: ...] or auto-voice mode
- Rich Stickers & Faces: Native QQ faces and custom sticker files
- Configurable Log Levels: DEBUG, INFO, WARNING via config.json
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

try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
PERSONA_DIR = os.path.join(BASE_DIR, "persona")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
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
    "language": "zh",               # "zh", "en", or "auto"
    "poll_interval_sec": 1.2,
    "debounce_delay_sec": 1.8,
    "compact_threshold": 14,
    "compact_keep_recent": 6,
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
    "贴贴": 201, "摸摸头": 176, "亲亲": 28, "委屈": 21,
    "害羞": 24, "抱抱": 98, "猫猫": 175, "比心": 212, "微笑": 14,
    # English
    "hug": 98, "pat": 176, "kiss": 28, "pout": 21,
    "shy": 24, "cuddle": 201, "cat": 175, "heart": 212, "smile": 14
}

conversation_history = []
long_term_memory = ""
processed_message_ids = set()
memory_lock = threading.Lock()

def load_system_prompt() -> str:
    lang = config.get("language", "zh").lower()
    fname = "system_prompt_en.md" if lang == "en" else "system_prompt_zh.md"
    fpath = os.path.join(PERSONA_DIR, fname)
    if not os.path.exists(fpath):
        fpath = os.path.join(PERSONA_DIR, "system_prompt.md")
    
    if os.path.exists(fpath):
        try:
            with open(fpath, "r", encoding="utf-8-sig") as f:
                return f.read().strip()
        except Exception as e:
            logging.warning(f"Failed to load {fpath}: {e}")
    return "You are an intelligent AI companion on QQ. Reply concisely in 1-3 sentences. Absolutely no *action* notations."

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

load_memory_and_history()

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

def trigger_auto_compact():
    global conversation_history, long_term_memory
    with memory_lock:
        threshold = config.get("compact_threshold", 14)
        keep_recent = config.get("compact_keep_recent", 6)
        if len(conversation_history) < threshold:
            return
        to_archive = conversation_history[:-keep_recent]
        conversation_history = conversation_history[-keep_recent:]
        save_history()

    logging.info(f"AutoCompact: Archiving {len(to_archive)} turns into long-term memory...")

    formatted_dialogue = ""
    for item in to_archive:
        role_label = "User" if item.get("role") == "user" else "Assistant"
        formatted_dialogue += f"{role_label}: {item.get('content')}\n"

    lang = config.get("language", "zh").lower()
    if lang == "en":
        compact_prompt = (
            "You are a memory consolidation assistant for an AI companion. Based on the 【Existing Memory】 and "
            "【Archived Chat Turns】, generate a concise, updated 【Long-Term Memory Summary】 (under 200 words).\n\n"
            f"【Existing Memory】:\n{long_term_memory or 'None'}\n\n"
            f"【Archived Chat Turns】:\n{formatted_dialogue}\n\n"
            "Guidelines: Retain established personal facts, preferences, user habits, and key promises. Drop trivial pleasantries. Output bullet points."
        )
    else:
        compact_prompt = (
            "你是一个记忆整理助手。请根据【现有长期记忆】和【即将归档的旧对话记录】，提炼并更新一份精练的【长期记忆摘要】（250字以内）。\n\n"
            f"【现有长期记忆】:\n{long_term_memory or '暂无'}\n\n"
            f"【即将归档的旧对话记录】:\n{formatted_dialogue}\n\n"
            "提炼原则：保留重要事实、偏好、习惯与约定，过滤无意义寒暄，分条列出。"
        )

    try:
        updated = raw_llm_call(compact_prompt, max_tokens=600)
        if updated and len(updated) > 10:
            with memory_lock:
                long_term_memory = updated.strip()
                save_long_term_memory()
            logging.info("AutoCompact: Successfully updated memory_summary.txt!")
    except Exception as e:
        logging.error(f"AutoCompact failed: {e}")

def raw_llm_call(prompt: str, max_tokens: int = 600) -> str:
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
    images_b64 = []
    has_voice = False
    
    cq_img_pattern = re.compile(r'\[CQ:image,[^\]]*?\]', re.IGNORECASE)
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

    if "[CQ:record," in raw_text:
        has_voice = True

    clean_text = cq_img_pattern.sub('', raw_text)
    clean_text = re.sub(r'\[CQ:record,[^\]]+\]', '（收到语音消息）', clean_text)
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
    clean_txt = clean_tags(text).strip()
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
            norm_path = os.path.abspath(temp_audio).replace('\\', '/')
            uri = f"file:///{norm_path}" if not norm_path.startswith('/') else f"file://{norm_path}"
            call_onebot_api("send_private_msg", {
                "user_id": config["master_qq"],
                "message": f"[CQ:record,file={uri}]"
            })
    except Exception as e:
        logging.error(f"Failed to synthesize or send voice: {e}")

def execute_action_tags(reply_text: str):
    # 1. Custom Stickers (Matches [发贴图: xxx] and [Send Sticker: xxx])
    sticker_matches = re.findall(r'\[(?:发贴图|Send Sticker):\s*([^\]]+)\]', reply_text, re.IGNORECASE)
    for kw in sticker_matches:
        kw = kw.strip().lower()
        matched_file = None
        if os.path.exists(STICKERS_DIR):
            for fname in os.listdir(STICKERS_DIR):
                if kw in fname.lower() or fname.split('.')[0].lower() in kw:
                    matched_file = os.path.join(STICKERS_DIR, fname)
                    break
        if matched_file and os.path.exists(matched_file):
            norm_path = os.path.abspath(matched_file).replace('\\', '/')
            uri = f"file:///{norm_path}" if not norm_path.startswith('/') else f"file://{norm_path}"
            call_onebot_api("send_private_msg", {
                "user_id": config["master_qq"],
                "message": f"[CQ:image,file={uri}]"
            })

    # 2. QQ Faces (Matches [发表情: xxx] and [Send Face: xxx])
    face_matches = re.findall(r'\[(?:发表情|Send Face):\s*([^\]]+)\]', reply_text, re.IGNORECASE)
    for kw in face_matches:
        kw = kw.strip().lower()
        fid = QQ_FACES.get(kw)
        if fid:
            call_onebot_api("send_private_msg", {
                "user_id": config["master_qq"],
                "message": f"[CQ:face,id={fid}]"
            })

    # 3. Explicit Voice Tag (Matches [发语音: xxx] and [Send Voice: xxx])
    voice_matches = re.findall(r'\[(?:发语音|Send Voice):\s*([^\]]+)\]', reply_text, re.IGNORECASE)
    for v_text in voice_matches:
        send_voice_message(v_text)

    # 4. Global Voice Mode
    if config.get("enable_voice_reply", False) and not voice_matches:
        clean_msg = clean_tags(reply_text)
        if clean_msg:
            send_voice_message(clean_msg)

    # 5. Pokes & Likes
    if "[互动: 戳一戳]" in reply_text or "[Interact: Poke]" in reply_text:
        call_onebot_api("friend_poke", {"user_id": config["master_qq"]})
    if "[互动: 点赞]" in reply_text or "[Interact: Like]" in reply_text:
        call_onebot_api("send_like", {"user_id": config["master_qq"], "times": 10})

def clean_tags(text: str) -> str:
    text = re.sub(r'\[(?:发贴图|Send Sticker):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:发表情|Send Face):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:发语音|Send Voice):[^\]]+\]', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\[(?:互动|Interact):[^\]]+\]', '', text, flags=re.IGNORECASE)
    return text.strip()

def query_llm(user_prompt: str, images_b64: list) -> str:
    load_config()
    system_prompt = load_system_prompt()
    if long_term_memory:
        lang = config.get("language", "zh").lower()
        header = "【Long-Term Memory Summary】:" if lang == "en" else "【长期记忆摘要】:"
        system_prompt += f"\n\n{header}\n{long_term_memory}"

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
        content_items = [{"type": "text", "text": user_prompt or "Sent an image:"}]
        for b64 in images_b64:
            content_items.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        current_turn = {"role": "user", "content": content_items}
        history_text = f"{user_prompt} [Image]" if user_prompt else "[Image]"
    else:
        current_turn = {"role": "user", "content": user_prompt}
        history_text = user_prompt

    messages.append(current_turn)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://localhost",
        "X-Title": "QQ AI Companion"
    }

    payload = {
        "model": config.get("model", "google/gemini-3.8-flash"),
        "messages": messages,
        "temperature": 0.75,
        "max_tokens": 800
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        raw_reply = data.get("choices", [{}])[0].get("message", {}).get("content", "") or ""
        reply_sanitized = sanitize_reply(raw_reply)
        
        if reply_sanitized:
            with memory_lock:
                conversation_history.append({"role": "user", "content": history_text})
                conversation_history.append({"role": "assistant", "content": clean_tags(reply_sanitized)})
                save_history()

            if len(conversation_history) >= config.get("compact_threshold", 14):
                threading.Thread(target=trigger_auto_compact, daemon=True).start()

            return reply_sanitized
        return "I'm here! What can I do for you?"

pending_messages = []
debounce_timer = None
batch_lock = threading.Lock()
current_generation_id = 0

def execute_batch_generation(gen_id: int):
    global pending_messages
    with batch_lock:
        if not pending_messages:
            return
        batch = list(pending_messages)
        pending_messages.clear()

    texts = [item.get("text", "") for item in batch if item.get("text")]
    images = []
    for item in batch:
        images.extend(item.get("images", []))

    if not texts and not images:
        return

    lang = config.get("language", "zh").lower()
    if len(texts) == 1:
        combined_text = texts[0]
    else:
        if lang == "en":
            combined_text = "The user sent multiple messages consecutively:\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(texts)])
        else:
            combined_text = "对方连续发送了以下几条消息：\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(texts)])

    now_str = datetime.datetime.now().strftime("%H:%M:%S")
    logging.info(f"User [{now_str}] (Batch {len(batch)}): {combined_text[:120]}")

    try:
        reply = query_llm(combined_text, images)
        with batch_lock:
            if gen_id != current_generation_id:
                logging.info(f"Generation #{gen_id} cancelled by newer messages.")
                return

        logging.info(f"Agent [{now_str}]: {reply}")
        execute_action_tags(reply)
        clean_text_reply = clean_tags(reply)
        if clean_text_reply:
            call_onebot_api("send_private_msg", {
                "user_id": config["master_qq"],
                "message": clean_text_reply
            })
    except Exception as e:
        logging.error(f"Error in batch #{gen_id}: {e}")
        traceback.print_exc()

def on_message_arrived(msg_id: int, sender_id: int, raw_text: str):
    global debounce_timer, current_generation_id
    if msg_id in processed_message_ids:
        return
    processed_message_ids.add(msg_id)

    if sender_id != config["master_qq"]:
        return

    clean_text, images_b64, has_voice = parse_incoming_cq_content(raw_text)

    with batch_lock:
        current_generation_id += 1
        gen_id = current_generation_id

        if debounce_timer and debounce_timer.is_alive():
            debounce_timer.cancel()

        pending_messages.append({
            "msg_id": msg_id,
            "text": clean_text,
            "images": images_b64,
            "time": time.time()
        })

        delay = config.get("debounce_delay_sec", 1.8)
        debounce_timer = threading.Timer(delay, execute_batch_generation, args=[gen_id])
        debounce_timer.start()

def poll_messages_loop():
    logging.info("Active High-Frequency Poller started...")
    try:
        init_res = call_onebot_api("get_friend_msg_history", {"user_id": config["master_qq"], "count": 10})
        if init_res.get("status") == "ok":
            for m in init_res.get("data", {}).get("messages", []):
                mid = m.get("message_id")
                if mid:
                    processed_message_ids.add(mid)
    except Exception as e:
        logging.warning(f"Failed to seed initial messages: {e}")

    while True:
        try:
            res = call_onebot_api("get_friend_msg_history", {"user_id": config["master_qq"], "count": 5})
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
    logging.info(f"[*] Auto-Compact    : Enabled (Threshold: {config.get('compact_threshold')} turns)")
    logging.info(f"[*] Log Level       : {config.get('log_level')}")
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
