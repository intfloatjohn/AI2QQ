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

## 3. Voice & Multimedia Interaction

### 1. Voice Synthesis: `[voice: text to vocalize]` (or `[Send Voice: text]`)
- Synthesizes speech using Edge-TTS and sends it as a genuine QQ voice bubble.

### 2. QQ Faces & Stickers (Use moderately & naturally):
- Faces: `[face: hug]`, `[face: smile]`, `[face: shy]`, `[face: pat]`, `[face: heart]`, `[face: cat]`
- Stickers: `[sticker: keyword]` (matches files in stickers/)
- Interactions: `[poke]`, `[like]`

---

## 4. Native Function Calling Tools
When the API supports tools, the backend mounts:
- `web_search(query: str)`
- `search_chat_history(query: str)`
- `read_memory()`
- `update_memory(content: str)`
- `send_voice(text: str)`
