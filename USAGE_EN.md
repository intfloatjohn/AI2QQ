# QQ AI Companion Architecture & User Manual (User Guide)

> **Language Switch / 语言切换**: [English Version (USAGE_EN.md)](USAGE_EN.md) | [中文手册 (USAGE.md)](USAGE.md)

This project is a high-performance, lightweight, 24/7 autonomous QQ AI companion framework supporting full multimodal perception (vision, bidirectional voice notes, autonomous meme/sticker library, multi-bubble typing, document parsing, and persistent memory). This guide covers configuration, features, customization, and administration.

---

## Table of Contents
1. [Persona Prompt Customization & Hot-Reload (`persona/`)](#1-persona-prompt-customization--hot-reload-persona)
2. [AutoCompact Long-Term Memory & Realtime Memory Dynamic Updates](#2-autocompact-long-term-memory--realtime-memory-dynamic-updates)
3. [Persistent Full Chat Logs & History Search (`chat_history.jsonl`)](#3-persistent-full-chat-logs--history-search-chat_historyjsonl)
4. [Human-like Multi-Bubble Typing (`[SEP]`) & Plain Text Rules (Raw Text)](#4-human-like-multi-bubble-typing-sep--plain-text-rules-raw-text)
5. [Autonomous Visual Library & Sticker Management (`picture_db/` & `stickers/`)](#5-autonomous-visual-library--sticker-management-picture_db--stickers)
6. [Full Multimodal Voice Pipeline (Multimodal Audio Input / TTS / ASR)](#6-full-multimodal-voice-pipeline-multimodal-audio-input--tts--asr)
7. [Multimodal Perception & Document Parsing (Forwards / Document Summaries / Super Emojis)](#7-multimodal-perception--document-parsing-forwards--document-summaries--super-emojis)
8. [Single-Account Self-Chat vs Two-Account Companion Modes (`bot_qq` & `master_qq`)](#8-single-account-self-chat-vs-two-account-companion-modes-bot_qq--master_qq)
9. [Live Web Search (Multi-engine)](#9-live-web-search-multi-engine)
10. [Log Levels & Reentrancy-Safe Clean Exit](#10-log-levels--reentrancy-safe-clean-exit)
11. [Model Context Protocol (MCP) Server Integration (`onebot_mcp.py`)](#11-model-context-protocol-mcp-server-integration-onebot_mcppy)
12. [Configuration Reference (`config.json`)](#12-configuration-reference-configjson)
13. [Headless Debian / Linux Deployment & Terminal QR Code Login](#13-headless-debian--linux-deployment--terminal-qr-code-login)
14. [Windows One-Click Setup & Startup](#14-windows-one-click-setup--startup)

---

## 1. Persona Prompt Customization & Hot-Reload (`persona/`)

All files controlling the AI companion's character, personality, speech style, and rules reside in the **`persona/`** directory. The engine natively supports **hot-reloading** (no daemon restart required; the latest version is loaded on every user turn):

| File Path | Purpose | Best Practices |
| :--- | :--- | :--- |
| **`persona/system_prompt.md`** | **Primary System Prompt (Core)** | Place core conversational rules, plain text constraints, and tool invocation tags here. |
| **`persona/system_prompt_zh.md`** | Chinese Language Persona Prompt | Automatically activated when `"language": "zh"` in `config.json`. |
| **`persona/system_prompt_en.md`** | English Language Persona Prompt | Automatically activated when `"language": "en"` in `config.json`. |
| **`persona/persona.md`** | Character Biography & Lore Details | Defines character name, backstory, catchphrases, quirks, hobbies, and titles. |
| **`persona/tools.md`** | Tool & Interaction Tag Reference | Reference sheet for action tags, emojis, stickers, and voice synthesis tags. |

> **Quick Editing**: Simply open `persona/system_prompt.md` (or `system_prompt_zh.md`) in any text editor, save your edits, and the AI companion will immediately reply with the updated persona on the very next message!

---

## 2. AutoCompact Long-Term Memory & Realtime Memory Dynamic Updates

### Dynamic Multi-Tier Memory Architecture
1. **Short-Term Context** (`history.json`): Preserves recent conversational turns for immediate dialogue continuity.
2. **Realtime Dynamic Memory Updates**: When the AI companion discovers key facts, user preferences, or when the user says "remember that...", the AI outputs `[remember: content]` (or `[更新记忆: 内容]`). The backend immediately appends this fact to `memory_summary.txt` without waiting for context compaction!
3. **Long-Term Memory Retrieval**: The AI can autonomously recall its archive by issuing `[read_memory]` (or `[查看记忆]`).
4. **Auto-Compact Summarization**: When conversation turns reach the threshold (`compact_threshold`, default: 30), a background worker automatically summarizes older turns into `memory_summary.txt` while keeping the most recent 12 turns in active context.

### Memory Management & Verification
* **Triggering a Memory**: Tell the bot "Remember that I love iced lattes". The bot replies and logs `[remember: User loves iced lattes]`.
* **Inspecting & Editing**: Open `memory_summary.txt` directly to review, edit, or adjust stored memories.
* **Resetting Memory**: Empty `memory_summary.txt` and set `history.json` to `[]`.

---

## 3. Persistent Full Chat Logs & History Search (`chat_history.jsonl`)

### Permanent History Archive (`chat_history.jsonl`)
Every user message and bot reply is permanently saved to `chat_history.jsonl` with accurate microsecond timestamps. Even when older turns are compacted away from the active LLM context window, the permanent log retains the full, untruncated conversation history forever.

### Intelligent Chat History Search
The AI companion can search past conversations at any time:
* **Tag Syntax**: `[search_history: keyword]` (or `[搜索聊天记录: 关键词]`)
* **Example**: When the user asks "Do you remember the name of that project I mentioned last week?", the AI outputs `[search_history: project]`. The system retrieves relevant history snippets with timestamps and presents them as tool observations.

---

## 4. Human-like Multi-Bubble Typing (`[SEP]`) & Plain Text Rules (Raw Text)

### 4.1 Multi-Bubble Consecutive Messaging (`[SEP]`)
Real human chatters rarely write massive walls of text in instant messengers; instead, they break their thoughts into several short, natural messages sent in succession.
* **Mechanism**: The AI inserts `[SEP]` between clauses or short sentences. For example:
  `Sure thing![SEP]Let me grab an apple from the kitchen first[SEP]Give me three minutes~`
* **Realistic Typing Cadence**: The system splits the output by `[SEP]`, calculates realistic human typing delays based on message length (1.0~2.5 seconds), and sends them to QQ sequentially.
* **Configuration**: `"enable_multi_bubble_reply": true` in `config.json` (enabled by default).

### 4.2 Plain Raw Text Enforcement (Raw Text vs Markdown)
* **Background**: Neither the mobile QQ client nor the desktop QQ client renders Markdown formatting. If an AI generates `**bold**`, `# Headers`, or `- list items`, users will see raw asterisks and hash symbols.
* **System Safeguards**:
  1. The system prompt explicitly enforces raw plain text, forbidding Markdown symbols and encouraging natural paragraphing or oral bullet points.
  2. The internal `sanitize_reply` pipeline automatically converts any stray `**bold words**` into plain text words `bold words` without deleting information.

---

## 5. Autonomous Visual Library & Sticker Management (`picture_db/` & `stickers/`)

The framework provides two distinct image capabilities: **Static Predefined Stickers** and an **Autonomous Dynamic Visual Library**.

### 5.1 Static Predefined Stickers (`stickers/`)
* Located in `stickers/`. Place `.jpg` or `.png` files here with short keywords:
  `heart.jpg`, `wave.jpg`, `sleep.jpg`, `avatar.jpg`.
* The AI outputs `[sticker: heart]` or `[发贴图: 比心]` to dispatch matching stickers.

### 5.2 Autonomous Visual & Meme Database (`picture_db/`)
The AI companion has complete administrative autonomy over its visual library:
1. **Automatic Ingestion**: Photos, memes, and GIFs sent by the user are automatically saved and indexed with metadata in `picture_db/metadata.json`.
2. **Autonomous Commands**:
   * **Dispatch Picture**: `[PICTURE: keyword or tag]` or `[发图: 关键词]` (e.g. `[PICTURE: happy cat]`, `[发图: 比心]`).
   * **Save Sticker with Tags**: `[SAVE_STICKER: tag1, tag2: description]` (or `[收藏表情: 标签: 描述]`).
   * **Browse Library**: `[LIST_PICTURES]` or `[LIST_PICTURES: query]` (or `[查看图库]`).
   * **Modify Existing Image**: `[MODIFY_PICTURE: target ID or tag: new tags: new summary]` (or `[修改图片: ...]`).
   * **Delete Image**: `[DELETE_PICTURE: target ID or tag]` (or `[删除图片: ...]`).
3. **Save-Before-Send Architecture**: Picture saves and modifications execute *before* picture dispatches. This ensures that when the AI saves a newly received sticker and sends it back in the same reply, the sticker is immediately located in the database and dispatched without failure.

---

## 6. Full Multimodal Voice Pipeline (Multimodal Audio Input / TTS / ASR)

### 6.1 Inbound Voice Recognition (Listening to Users)
When users send voice notes via QQ, the system supports two intelligent decoding paths:
1. **Native Multimodal Audio (Recommended: Gemini 1.5/2.0/2.5/3.8 Flash, GPT-4o, Omni)**:
   * Inbound QQ voice notes (encoded in AMR or Tencent Silk v3) are automatically converted into standard 16kHz mono MP3 via `convert_audio_to_standard_mp3`.
   * The audio data is base64-encoded and sent directly as an `input_audio` payload in the OpenAI/OpenRouter chat completion request:
     ```json
     {"type": "input_audio", "input_audio": {"data": "<base64_data>", "format": "mp3"}}
     ```
   * **Gemini natively hears the user's voice, pitch, inflection, and content directly** without needing cloud ASR or transcription services.
2. **Pure Text Models (e.g., DeepSeek-Flash / DeepSeek-V3)**:
   * Pure text models do not accept audio payloads. Configure a cloud ASR service in `config.json` (such as SiliconFlow SenseVoice or Whisper):
     ```json
     "asr_api_url": "https://api.siliconflow.cn/v1/audio/transcriptions",
     "asr_api_key": "sk-xxxx",
     "asr_model": "FunAudioLLM/SenseVoiceSmall"
     ```

### 6.2 Outbound Voice Synthesis (TTS)
The system integrates Microsoft's high-fidelity `edge-tts` cloud neural voice engine, running in pure Python without requiring local GPU resources:
1. **Mobile QQ Silk v3 Audio Bubbles**:
   * Mobile QQ requires audio in Tencent Silk v3 format with the `\x02#!SILK_V3` header.
   * Transcoding is automatically handled by `pilk` and `graiax-silkcoder` fallback, guaranteeing 100% audible playback on iOS and Android QQ.
2. **Dispatch Modes**:
   * **On-Demand**: Triggered when the AI reply includes `[voice: text to read]` or `[发语音: 文本]`.
   * **Full Auto Voice**: Set `"enable_voice_reply": true` in `config.json` to synthesize every reply into an audio bubble.
3. **Voice Profiles**:
   Configured via `"voice_character"` in `config.json`:
   * `zh-CN-XiaoyiNeural` (Sweet young female voice, recommended default)
   * `zh-CN-XiaoxiaoNeural` (Warm, gentle female voice)
   * `zh-CN-YunxiNeural` (Lively male voice)
   * `en-US-JennyNeural` (Natural American English female voice)

---

## 7. Multimodal Perception & Document Parsing (Forwards / Document Summaries / Super Emojis)

The framework parses and understands rich QQ message content:
* **Forwarded Chat Records**: Automatically resolves OneBot `[CQ:forward]` and `[CQ:json]` multi-user chat trees, reconstructing readable dialogue logs for the AI to analyze, summarize, or comment on.
* **Multi-Format Document Parsing**: When users send documents (`.txt`, `.md`, `.pdf`, `.docx`, `.py`, etc.), text extracts are parsed into structured context for immediate discussion.
* **Super Emojis & Interactive Faces**: Native QQ animated faces, dice rolls, rock-paper-scissors results, and poke interactions are parsed into semantic events.

---

## 8. Single-Account Self-Chat vs Two-Account Companion Modes (`bot_qq` & `master_qq`)

The framework supports two operational models:
1. **Two-Account Companion Mode (Recommended Standard)**:
   * Configuration: `bot_qq` (bot account) and `master_qq` (user account) are **different**.
   * The bot logs into its own dedicated QQ account and chats with the master account.
   * Full feature support: bidirectional voice notes, pokes, and profile likes.
2. **Single-Account Self-Chat Mode**:
   * Configuration: `bot_qq` and `master_qq` are **identical**.
   * Operates like a personal assistant or "File Transfer Assistant".
   * **Echo Filter**: Built-in `is_bot_echo` prevents infinite response loops by discarding messages originating from the bot's own recent replies.
   * *Note: Tencent QQ protocol prevents accounts from receiving voice bubbles sent to themselves. For full voice functionality, Two-Account mode is strongly recommended.*

---

## 9. Live Web Search (Multi-engine)

Built-in real-time web search capabilities (powered by DuckDuckGo and Wikipedia APIs):
* **Invocation**:
  * Inline Tag: `[search: query]` (or `[搜索: 关键词]`)
  * Native Tool Calling: `web_search(query)`
* **Settings**: Configure `"enable_web_search": true` and `"max_search_results": 4` in `config.json`.
* **Use Cases**: Weather forecasts, breaking news, technical documentation lookups, and fact checking.

---

## 10. Log Levels & Reentrancy-Safe Clean Exit

### 10.1 Log Level Configuration
Configured in `config.json` via `"log_level"`:
* **`DEBUG`**: Maximum verbosity. Prints polling ticks, raw image URLs, CQ codes, and network latency. Recommended for troubleshooting.
* **`INFO`** (Default): Standard operational logs (user messages, AI replies, memory compacting events, warnings).
* **`WARNING`** / **`ERROR`**: Quiet mode. Prints only critical network timeouts or errors.
> **Log Destinations**: Streamed simultaneously to the console and to **`agent.log`**.

### 10.2 Reentrancy-Safe Clean Exit & Automatic NapCat Shutdown
* In Python 3.14 / Linux environments, pressing `Ctrl+C` triggers signal handling with `signal.SIG_IGN` guardrails to avoid standard I/O buffer reentrancy (`RuntimeError: reentrant call inside BufferedWriter`).
* On exit, the daemon cleanly stops the local NapCat Docker container, releasing ports and memory automatically.

---

## 11. Model Context Protocol (MCP) Server Integration (`onebot_mcp.py`)

A standard Model Context Protocol (MCP 2.x) server is provided at `mcp-server/onebot_mcp.py`, allowing Claude Desktop, Cursor, or Antigravity to directly interface with your QQ companion:

### Exposed MCP Tools:
* `web_search`: Live multi-engine search
* `search_chat_history`: Search permanent chat logs
* `read_memory`: Read long-term memory archive
* `update_memory`: Write or append to long-term memory
* `search_picture_library`: Search visual meme database
* `send_voice_to_master`: Synthesize and dispatch Edge-TTS voice note
* `qq_send_master_msg` / `qq_send_private_msg` / `qq_send_group_msg`: Message delivery
* `qq_send_image`: Send pictures or stickers
* `qq_poke_master` / `qq_send_like`: Pokes and profile likes
* `qq_get_recent_messages` / `qq_get_unread_messages`: Retrieve chat history

### Launching MCP Server:
```bash
python3 mcp-server/onebot_mcp.py
```

---

## 12. Configuration Reference (`config.json`)

```json
{
  "api_type": "openai",
  "base_url": "https://openrouter.ai/api/v1/chat/completions",
  "api_key": "YOUR_API_KEY",
  "model": "google/gemini-3.8-flash",
  "master_qq": 123456789,
  "bot_qq": 987654321,
  "onebot_http_api": "http://127.0.0.1:3000",
  "language": "en",
  "poll_interval_sec": 0.8,
  "debounce_delay_sec": 2.2,
  "max_batch_wait_sec": 10.0,
  "compact_threshold": 30,
  "compact_keep_recent": 12,
  "max_tokens": 1200,
  "enable_multi_bubble_reply": true,
  "enable_picture_database": true,
  "enable_web_search": true,
  "max_search_results": 4,
  "log_level": "INFO",
  "enable_voice_reply": false,
  "voice_character": "en-US-JennyNeural"
}
```

### Key Parameters:
* `master_qq`: The user's QQ number (the AI only responds to private messages from this account).
* `bot_qq`: The QQ account logged into NapCat.
* `debounce_delay_sec`: Debounce buffering window (seconds). Accumulates rapid-fire messages into a single conversational turn.
* `max_batch_wait_sec`: Maximum batch wait ceiling (seconds) before forcing reply generation.
* `enable_multi_bubble_reply`: Enables `[SEP]` splitting into consecutive message bubbles.
* `enable_picture_database`: Enables the autonomous visual library (`picture_db/`).
* `poll_interval_sec`: Polling interval for new messages (recommended: 0.6 ~ 1.0s).
* `compact_threshold` / `compact_keep_recent`: Turn threshold for long-term memory summarization.

---

## 13. Headless Debian / Linux Deployment & Terminal QR Code Login

Deploying on a headless Linux VPS or server:

### 1. Launch NapCat in Docker:
```bash
docker run -d \
  --name napcat \
  --restart always \
  --network host \
  -v /opt/napcat/config:/app/napcat/config \
  mlikiowa/napcat-docker:latest
```

* **Inspect Login QR Code**:
  ```bash
  docker logs -f napcat
  ```
  The terminal displays an ASCII QR code. Scan it with mobile QQ to log in.

### 2. Run the AI Companion Daemon:
Use the automated helper scripts:
```bash
chmod +x setup.sh start.sh
./setup.sh    # Initial dependency installation and environment check
./start.sh    # Daily startup and auto-reconnect daemon
```

---

## 14. Windows One-Click Setup & Startup

For Windows users, no manual terminal commands are required:

1. **Automated Setup**:
   * Double-click **`setup_windows.bat`**.
   * It creates a dedicated Python virtual environment, installs dependencies, and prepares TTS engines.
   * When prompted to install NapCat, press `1` to download and unpack NapCatQQ automatically into `NapCat/`.
2. **Daily Startup**:
   * Configure `config.json` with your API Key and QQ numbers.
   * Double-click **`start.bat`** (or `start_agent.bat`) to launch the AI companion.
