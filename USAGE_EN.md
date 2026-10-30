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
15. [Group Chat](#15-group-chat)

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
4. **Auto-Compact**: When conversation turns reach the threshold (`compact_threshold`, default: 30), a background worker extracts **new** facts from the older turns and appends them, dated, to `memory_summary.txt`, keeping the most recent 12 turns in active context. Existing memory is never rewritten or deleted here; if the model call fails, the old turns are kept for next time.
5. **Tidying and backups**: when memory grows past `memory_max_chars` (default 8000 characters; `group_memory_max_chars`, 3000, for groups), the model merges duplicate and outdated entries. The old file is backed up to `memory_backups/` first (last 30 kept), and the result is rejected if it was cut off or lost too much, leaving memory unchanged.

### Memory Management & Verification
* **Triggering a Memory**: Tell the bot "Remember that I love iced lattes". The bot replies and logs `[remember: User loves iced lattes]`.
* **Inspecting & Editing**: Open `memory_summary.txt` directly to review, edit, or adjust stored memories.
* **Resetting Memory**: Empty `memory_summary.txt` and set `history.json` to `[]`.
* **Restoring Memory**: stop the bot, then copy a file from `memory_backups/` back to `memory_summary.txt`.

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
* `enable_multi_bubble_reply`: Enables `[SEP]` splitting into consecutive message bubbles. Replies the model splits with blank lines are also sent as separate bubbles (not when they contain code, tables or lists).
* `private_max_bubbles`: most bubbles per private reply (default 4; extra parts are merged into the last one). Groups use `group_max_bubbles`.
* `enable_vision` / `enable_audio_input`: whether the model can see images / listen to audio. Default `null` = guessed from the model name. When a text-only model gets a picture or voice message, the bot sends a fixed system warning (e.g. `NOT A VISION MODEL`). If the model API returns an error because of a picture or voice message, the bot retries once without it and warns `VISION IS NOT AVAILABLE: API ERROR`. Each warning is sent at most once per 10 min in private chat and once per hour in a group. Set `true` / `false` if the guess is wrong.
* `enable_picture_database`: Enables the autonomous visual library (`picture_db/`).
* `poll_interval_sec`: Polling interval for new messages (recommended: 0.6 ~ 1.0s).
* `compact_threshold` / `compact_keep_recent`: Turn threshold for long-term memory summarization.
* Group chat settings (`enable_group_chat`, `group_whitelist`, ...) are described in [Section 15](#15-group-chat).
* `onebot_access_token`: if NapCat's HTTP server has a token (e.g. NapCat runs on another machine), put the same value here and the bot sends it as `Authorization: Bearer`.

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

**Moving to another computer or folder**: a copied `venv/` can't be reused, because it has the old paths and Python version built in. You don't need to copy it: when the scripts find a `venv/` from another machine, folder or Python version, they delete and rebuild it, so the `externally-managed-environment` error no longer happens. Dependencies are only ever installed into `venv/`, never into the system Python.

### Safe defaults
- The OneBot HTTP API (port 3000) has no token, so the launcher makes it listen on `127.0.0.1` only. Older configs set to `0.0.0.0` are switched back automatically, as long as `onebot_http_api` points at this machine. If NapCat's config file is owned by root and can't be changed, the launcher prints what to fix with sudo.
- Newly created NapCat containers get a random WebUI token instead of the public default `napcat`.
- The launch banner no longer looks up or prints the server's public IP, and shows only the first and last two characters of the WebUI token. Show the full token with `sudo grep token /opt/napcat/config/webui.json`.
- To reach the WebUI remotely, use an SSH tunnel: `ssh -L 6099:127.0.0.1:6099 user@server`, then open `http://127.0.0.1:6099/webui` on your own computer. Don't open ports 6099 or 3000 to the internet in your cloud firewall.

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
3. **Security**: `setup_windows.bat` and `start.bat` run `secure_napcat.py`, which makes OneBot servers without a token (ports 3000/3001) listen on `127.0.0.1` only. Restart NapCat once for the change to take effect; `start.bat` tells you when (usually the first run after QR login).

---

## 15. Group Chat

The companion can join QQ groups as the same character while the Master's private memory never shows up there. The group version and the private version are one "person": it remembers what happens in groups and can recall it when the Master asks in private chat, but private chat content is never carried into a group.

### 15.1 Enabling
Add these fields to `config.json` (group chat needs two different QQ accounts, i.e. `bot_qq` ≠ `master_qq`):
```json
{
  "enable_group_chat": true,
  "group_whitelist": [123456789],
  "bot_name": "Hoshineko",
  "group_trigger_keywords": ["Hoshineko", "星喵"],
  "group_member_msg_limit": 10,
  "group_member_limit_window_sec": 86400
}
```
No restart needed: changes are picked up within about 10 seconds. **Only groups listed in `group_whitelist` are ever read or answered**; with an empty whitelist no group is read.

### 15.2 When the bot replies
A group message is passed to the model only if at least one of these is true:
- **Its name is mentioned**: the text contains a word from `group_trigger_keywords` (empty → `bot_name`, still empty → the bot's QQ nickname). ASCII names match whole words only, so `neko` does not fire on `nekomimi`.
- **The bot is @'d** (`group_trigger_on_at`, on by default).
- **Someone quotes one of the bot's messages** (`group_trigger_on_reply`, on by default).

Other group messages don't trigger a reply; they are only shown to the model as "background messages" the next time it is called. Even when called, the model may answer `[NO_REPLY]` if it was only mentioned in passing.

**Consecutive messages**: after someone calls the bot, their next messages within a few seconds (for example "@bot" and then a picture) belong to the same request, just like consecutive messages in private chat. If the reply is still being written, it restarts with the new message included. Messages that @ or quote someone else don't count. The window is `group_followup_window_sec` (default 10 seconds).

**Pictures, stickers, files and forwarded chats**:
- Pictures in the message that calls the bot, in follow-up messages and in a quoted message are opened for the model.
- From what was posted since the bot's last reply, the most recent `group_context_media` pictures / forwarded chats / files / voice messages are opened (default 2, within 5 minutes). So "@bot what do you think?" can see a picture someone else just posted.
- At most 4 pictures are attached per reply, with a note telling the model who posted each one.
- Stickers the bot has looked at are saved to the library automatically, and the model is told their library ID so it can resend one with `[PICTURE: ID]`. Stickers from the Master are shared; other members' stickers stay in that group. Ordinary photos are not saved automatically (use `[SAVE_STICKER: …]` when wanted).
- While a reply is being written, other people's new messages wait in a queue and are handled right after it (private chat keeps its original "interrupt and merge" behaviour).
- Group replies are shorter, split into at most `group_max_bubbles` bubbles, and by default the first bubble @'s the person who asked.

### 15.3 Identity: QQ ID only, never nicknames
- The Master is recognised **only** by comparing the real `user_id` reported by OneBot with `master_qq`. Group cards and nicknames play no part in identity.
- Every group message given to the model carries a speaker label generated by the program: `【Master✔】` for the Master, `【Member QQ:number Name:xxx】` for everyone else. Any `【】` typed by members, in messages or nicknames, is replaced with `[]`, so nobody can forge the `【Master✔】` label.
- All permission checks happen in code, by QQ ID. They don't rely on the model obeying, so even a fully prompt-injected model in a group cannot reach private data or do anything it is not allowed to.

### 15.4 Physically separated memory & assets
| Item | Master's private chat | Each group |
| :--- | :--- | :--- |
| Short-term context | `history.json` (unchanged file, memory continues) | `sessions/group_<id>/history.json` |
| Long-term memory | `memory_summary.txt` | `sessions/group_<id>/memory_summary.txt` |
| Permanent chat log | `chat_history.jsonl` | `sessions/group_<id>/chat_history.jsonl` |
| Member message counters | — | `sessions/group_<id>/quota.json` |
| Handled message IDs | — | `sessions/group_<id>/seen_ids.json` (no double replies after restart) |
| Temporary downloads | `downloads/` | `downloads/group_<id>/` |

- No code path reachable from a group session opens the Master's private files. In a group, `[read_memory]`, `[search_history]` and `[remember]` only act on that group, and `agent.log` (which mixes every chat) is never searched.
- **Even when the Master speaks in a group, the group-side model gets no private memory**: group replies are public, and the same batch may contain other people's injected text. Ask private things in private chat.
- Group replies show the Master's QQ number as `[Master's QQ number hidden]`; it is only said out loud when the Master asks (every message in that batch came from the Master).
- Groups are isolated from each other; group A's memory is invisible in group B.
- **Memory flows one way**: in private chat, when the Master asks "what happened in the group today?", the companion can use `[group_recall: group ID or keyword]` or the `recall_group_chat` tool.
- Each group memory entry is tagged with its source, e.g. `(source: QQ:123(Alice))`, written by the program from real QQ IDs. Group memory has a size cap (`group_memory_max_chars`) and is auto-compacted like private memory.

### 15.5 Picture library: stickers shared, photos private
There is still one unified `picture_db/`, but every picture has a visibility scope:
- **Stickers / memes / GIFs** (including the static `stickers/`): public, usable in every chat.
- **Ordinary photos received in the Master's private chat**: private, usable only in private chat; groups cannot find or send them.
- **Pictures saved inside a group**: belong to that group only (the Master's private chat can see them too).
- Older entries without a scope: public if tagged as a sticker/meme or located in `stickers/`, private otherwise.
- Pictures posted by group members are never auto-saved. Editing or deleting pictures from a group only happens when the Master (checked by QQ ID) asks, and only for pictures visible to that group.
- In private chat the Master can change visibility with `[PUBLIC_PICTURE: ID or tag]` / `[PRIVATE_PICTURE: ID or tag]`.

### 15.6a Messaging the Master on its own & group media memory
**Messaging the Master**: when the bot sees something in a group that surprises or annoys it, or that its Master would want to know, it can send the Master a private message (marked with the group's name).
- While answering in a group, it can add `[tell_master: …]`.
- **Glance**: even when nobody calls it, it skims new group chat about every 10 minutes (only after at least 5 new messages, at most 4 times per group per hour). Usually it decides not to bother you, and it never speaks in the group while glancing.
- At most 3 such messages per hour across all groups. It ignores members asking it to "tell your master". These messages are added to the private chat history, so it knows what you're replying to.
- Each glance is one extra model call; set `"group_glance_enabled": false` to turn it off.

**Group media memory**: pictures and voice messages the bot opened are kept for `group_media_retention_days` days (default 7), and the model writes a one-line description into the group log, e.g. "a ginger cat lying in a box".
- Searching the log, or recalling a group from private chat, then shows the description and a media ID instead of just `[image]`.
- Within the retention period, `[review_media: media ID]` lets it look or listen again; afterwards the file is deleted automatically and the description stays.
- Only media it already opened is described, so there is no extra cost per picture.

### 15.6 Per-member message limit
- Each member except the Master can trigger at most `group_member_msg_limit` replies per window (rolling 24 hours; if config.json leaves the setting out, 50 is used and a WARNING is logged). Only messages that call the bot count; ordinary chatter does not.
- After that, the member's messages are **ignored completely** (not even used as background) until the count drops within the window.
- `group_member_limit_window_sec: 0` makes it a permanent cap that never resets; `group_member_msg_limit: 0` disables the limit. Each ignored message is logged as `reached the limit`.
- Counters live in `quota.json` and survive restarts. To lift a limit manually, delete that group's `quota.json`.
- Optional `group_member_limit_notice`: a one-time message when a member first hits the limit (empty by default = silent).

### 15.7 Group settings
| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `enable_group_chat` | `false` | Master switch |
| `group_whitelist` | `[]` | Allowed group IDs; empty = no group is read |
| `bot_name` | `""` | Character name; also the default trigger word |
| `group_trigger_keywords` | `[]` | Trigger words; empty = `bot_name` or the bot's QQ nickname |
| `group_trigger_on_at` | `true` | Reply when @'d |
| `group_trigger_on_reply` | `true` | Reply when one of the bot's messages is quoted |
| `group_member_msg_limit` | `50` if unset (with a warning) | Replies per member per window (Master exempt; `0` = unlimited) |
| `group_member_limit_window_sec` | `86400` | Rolling window in seconds; `0` = never resets |
| `group_member_limit_notice` | `""` | Optional notice when the limit is first hit (empty = silent) |
| `group_reply_with_at` | `true` | @ the asker in the reply |
| `group_reply_with_quote` | `false` | Quote the asker's message in the reply |
| `group_context_messages` | `12` | Recent group messages given as background |
| `group_context_max_age_sec` | `900` | Max age of background messages (seconds) |
| `group_followup_window_sec` | `10` | After calling the bot, how long the same person's next messages count as the same request (seconds); `0` = off |
| `group_context_media` | `2` | Recent background media (pictures/forwards/files/voice) opened when the bot is called; `0` = none |
| `group_context_media_max_age_sec` | `300` | Only background media newer than this is opened (seconds) |
| `group_media_retention_days` | `7` | Days opened pictures/voice are kept (descriptions stay); `0` = never delete |
| `group_master_notify_max_per_hour` | `3` | Private messages to the Master per hour, all groups together; `0` = off |
| `group_glance_enabled` | `true` | Skim group chat now and then even when not called |
| `group_glance_interval_sec` / `group_glance_min_new_messages` / `group_glance_max_per_hour` | `600` / `5` / `4` | Glance interval, minimum new messages, per-group hourly cap |
| `group_max_tokens` | `800` | Max tokens for a group reply |
| `group_max_bubbles` | `3` | Max bubbles per group reply |
| `group_memory_max_chars` | `3000` | Size cap of each group's long-term memory (oldest entries dropped) |
| `group_log_ambient` | `true` | Also archive non-trigger messages in the group's log (for recall) |
| `group_max_file_bytes` | `8388608` | Max size of group files that get parsed (bytes) |
| `group_poll_interval_sec` | `1.5` | Group polling interval (seconds) |
| `group_debounce_delay_sec` / `group_max_batch_wait_sec` | `1.5` / `6.0` | Group batching window / max wait (seconds) |

### 15.8 Customising the group style
`persona/system_prompt_group_en.md` (or `system_prompt_group_zh.md` in Chinese mode) sets the chat style in groups: shorter replies, no flooding, never calling members "Master", and so on. Edit it freely. The safety rules (identity, privacy isolation) are built into the program, so editing or deleting this file cannot weaken them.

### 15.9 Notes
- Group chat stays off in single-account mode (`bot_qq == master_qq`): the Master and the bot share one QQ ID, so they can't be told apart by ID. The log says so.
- If `bot_qq` in `config.json` is wrong, group chat uses the account NapCat is actually logged in with and logs a warning.
- The bot must already be a member of each whitelisted group; if a group can't be read, the log warns every 5 minutes.
