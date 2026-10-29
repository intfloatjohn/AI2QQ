# Tools, Memory & Search Specification (English)

To ensure all models (Gemini, GPT-4o, Claude, DeepSeek, Qwen, etc.) trigger tools accurately, the system supports both inline commands and native OpenAI Function Calling:

---

## 1. Memory & Full Chat History Retrieval

### 1. Real-time Memory Update: `[remember: content]` (or `[update_memory: content]`)
- **When to use**: When the user mentions personal preferences, habits, schedules, important requests, or asks you to remember something.
- **Effect**: Instantly writes key facts to `memory_summary.txt`.

### 2. Inspect Memory: `[read_memory]` (or `[Read Memory]`)
- **When to use**: When you need to verify known facts or check the user profile archive.
- **Effect**: Loads and returns `memory_summary.txt`.

### 3. Full Chat History Search: `[search_history: keyword]` (or `[Search History: keyword]`)
- **When to use**: When the user refers to past discussions, previous questions, or earlier experiences.
- **Effect**: Queries `chat_history.jsonl` and returns past messages with timestamps and surrounding context.

---

## 2. Live Web Search: `[search: query]` (or `[Search: query]`)
- **When to use**: When asked about real-time news, weather forecasts, technical facts, or current information.
- **Effect**: Executes live web search and returns summaries.

---

## 3. Voice & Picture Library Management

### 1. Voice Synthesis: `[voice: text to vocalize]` (or `[Send Voice: text]`)
- Synthesizes speech using Edge-TTS and sends it as a genuine QQ voice bubble.

### 2. Picture Library Management (Full CRUD Agency):
- **Send**: `[PICTURE: keyword]` or `[IMAGE: keyword]`
- **Save**: `[SAVE_STICKER: tag1, tag2: summary description]`
- **List/Browse**: `[LIST_PICTURES]` or `[LIST_PICTURES: query]`
- **Modify**: `[MODIFY_PICTURE: target ID or tag: new tags: new summary]`
- **Delete**: `[DELETE_PICTURE: target ID or tag]`

### 3. QQ Faces & Stickers (Use moderately & naturally):
- Faces: `[face: hug]`, `[face: smile]`, `[face: shy]`, `[face: pat]`, `[face: heart]`, `[face: cat]`
- Stickers: `[sticker: keyword]` (matches files in stickers/)
- Interactions: `[poke]`, `[like]`

---

## 4. Native Function Calling Tools
When the API supports tools, the backend mounts:
- `web_search(query: str)`: Live internet search
- `search_chat_history(query: str)`: Search full chat history
- `read_memory()`: Read persistent memory
- `update_memory(content: str)`: Real-time memory update
- `search_picture_library(query: str)`: Search picture library
- `list_pictures(filter_query: str)`: Browse or filter pictures in library
- `modify_picture(target: str, new_tags: list, new_summary: str, replace_tags: bool)`: Modify picture tags and description
- `delete_picture(target: str)`: Delete picture from library
- `send_voice(text: str)`: Vocalize and send voice bubble
- `recall_group_chat(group: str, query: str)`: Recall group chat memory and logs (Master's private chat only)

---

## 5. Group Chat Scope

In a group, every tool acts on that group only. Permissions are checked by the program using real QQ IDs, not by the model:
- `[remember: ...]` / `update_memory`: writes this group's memory (tagged with the source QQ ID), never the Master's private memory.
- `[read_memory]` / `read_memory`, `[search_history: ...]` / `search_chat_history`: only see this group's memory and log.
- `[PICTURE: ...]`: only public stickers and this group's collection; photos from the Master's private chat are invisible in groups.
- `[SAVE_STICKER: ...]`: saves into this group's own collection.
- `[MODIFY_PICTURE: ...]`, `[DELETE_PICTURE: ...]`: only take effect when the Master asks in person.

Master's private chat only:
- `[group_recall: group ID or keyword]` / `recall_group_chat`: recall what happened in groups (group content flows one way, into private chat).
- `[PUBLIC_PICTURE: target]` / `[PRIVATE_PICTURE: target]`: choose whether a picture may be used in groups (photos default to private, stickers to public).
