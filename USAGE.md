# QQ AI Companion 架构与使用手册 (User Guide)

> **语言切换 / Language**: [English Version (USAGE_EN.md)](USAGE_EN.md) | [中文手册 (USAGE.md)](USAGE.md)

本项目是一套高性能、低内存占用、支持全模态（看图+语音收发+自主表情包库+多气泡打字+文件解析）的 24 小时无人值守 QQ AI 伴侣框架。本手册解答日常配置、进阶特性、二次开发与运维管理的核心问题。

---

## 目录
1. [人格文件编写与热重载 (`persona/`)](#1-人格文件编写与热重载-persona)
2. [AutoCompact 长期记忆与实时记忆动态沉淀](#2-autocompact-长期记忆与实时记忆动态沉淀)
3. [全量聊天记录持久化与历史检索 (`chat_history.jsonl`)](#3-全量聊天记录持久化与历史检索-chat_historyjsonl)
4. [真实人类多气泡打字 (`[SEP]`) 与纯文本规范 (Raw Text)](#4-真实人类多气泡打字-sep-与纯文本规范-raw-text)
5. [自主图库与表情包管理 (`picture_db/` 与 `stickers/`)](#5-自主图库与表情包管理-picture_db-与-stickers)
6. [全模态语音系统 (多模态直传 / TTS / ASR)](#6-全模态语音系统-多模态直传--tts--asr)
7. [全模态感知与文档解析 (合并转发 / 文档摘要 / 动图表情)](#7-全模态感知与文档解析-合并转发--文档摘要--动图表情)
8. [单账号自身聊天与双账号模式 (`bot_qq` 与 `master_qq`)](#8-单账号自身聊天与双账号模式-bot_qq-与-master_qq)
9. [实时联网搜索功能 (Web Search)](#9-实时联网搜索功能-web-search)
10. [日志等级与防重入平滑退出机制](#10-日志等级与防重入平滑退出机制)
11. [MCP 服务端与外部客户端接入 (`onebot_mcp.py`)](#11-mcp-服务端与外部客户端接入-onebot_mcppy)
12. [配置文件与核心参数说明 (`config.json`)](#12-配置文件与核心参数说明-configjson)
13. [Debian / Linux 无头部署与终端扫码](#13-debian--linux-无头部署与终端扫码)
14. [Windows 一键部署与双击运行](#14-windows-一键部署与双击运行)
15. [群聊模式 (Group Chat)](#15-群聊模式-group-chat)
16. [QQ空间 (Qzone，实验功能)](#16-qq空间-qzone实验功能)
17. [好友私聊模式 (Friend Chat)](#17-好友私聊模式-friend-chat)

---

## 1. 人格文件编写与热重载 (`persona/`)

所有影响 AI 行为、性格、口吻的人格文件存放在 **`persona/`** 目录中。框架原生支持**热重载**（无需重启脚本，后台在每次模型请求时自动读取最新版本）：

| 文件路径 | 作用说明 | 编写建议 |
| :--- | :--- | :--- |
| **`persona/system_prompt.md`** | **主系统提示词（核心）** | 建议放社交打字铁律、工具标签调用规则、语气规范。 |
| **`persona/system_prompt_zh.md`** | 中文环境专属主提示词 | 当 `config.json` 中 `"language": "zh"` 时自动调用。 |
| **`persona/system_prompt_en.md`** | 英文环境专属主提示词 | 当 `config.json` 中 `"language": "en"` 时自动调用。 |
| **`persona/persona.md`** | 角色设定与世界观细节 | 定义人设姓名、身世背景、语气口癖、爱好与称谓。 |
| **`persona/tools.md`** | 工具与动作标签手册 | 供开发者和模型参考的动作、表情与语音调用规范。 |

> **修改技巧**：直接用文本编辑器编辑 `persona/system_prompt.md`（或 `system_prompt_zh.md`），保存后下一次给 Bot 发 QQ 消息即可立刻按新人格回复！

---

## 2. AutoCompact 长期记忆与实时记忆动态沉淀

### 动态多层记忆架构
1. **短期近期上下文**（`history.json`）：保留最近活跃的连续聊天记录。
2. **实时记忆动态更新**：模型在对话中识别到重要事实或用户要求“记住...”时，可直接触发 `[更新记忆: 内容]`，后台立即持久化追加至 `memory_summary.txt`，无需等待对话压缩！
3. **长期记忆查阅**：模型可自主决定是否通过 `[查看记忆]` 调阅完整的 `memory_summary.txt`。
4. **长期记忆自动沉淀（Auto-Compact）**：当对话轮次到达阈值（默认 30 轮）时，程序会在后台从旧对话里提取**新的**事实，按日期追加到 `memory_summary.txt`，同时保留最新 12 轮上下文。已有的记忆不会被改写或删掉；模型调用失败时旧对话会留着下次再整理。
5. **记忆整理与备份**：记忆超过 `memory_max_chars`（默认 8000 字，群聊为 `group_memory_max_chars` 3000 字）时，会让模型合并重复和过时的条目。整理前会把原文件备份到 `memory_backups/`（保留最近 30 份）；如果整理结果被截断或丢失太多内容，就不采用，记忆保持原样。

### 管理与调试
* **实时更新指令**：在聊天时对机器人说“记住我喜欢喝冰拿铁”，机器人会回复并执行 `[更新记忆: 用户喜欢喝冰拿铁]`。
* **查看/修改记忆**：直接打开 `memory_summary.txt` 即可手动新增、修改或校对。
* **清除记忆**：清空 `memory_summary.txt` 并将 `history.json` 置为 `[]`。
* **恢复记忆**：从 `memory_backups/` 里挑一份备份，复制回 `memory_summary.txt`（先停掉机器人）。

---

## 3. 全量聊天记录持久化与历史检索 (`chat_history.jsonl`)

### 永久历史库 (`chat_history.jsonl`)
每一次用户发送的消息和 AI 生成的回复都会带有精准的时间戳永久记录在 `chat_history.jsonl` 中，永不丢失。哪怕经历了 Auto-Compact 裁剪，原始对话也始终完整留存。

### 历史记录智能检索
模型可以通过以下指令随时翻阅过去的聊天记录：
* **模型调用标签**：`[搜索聊天记录: 关键词]`（英文模式：`[search_history: keyword]`）
* **示例**：当用户问“你还记得我上周提过的那个项目叫什么吗？”，模型输出 `[搜索聊天记录: 项目]`，系统会自动检索 `chat_history.jsonl` 并将包含上下文的时间与对话反馈给模型。

---

## 4. 真实人类多气泡打字 (`[SEP]`) 与纯文本规范 (Raw Text)

### 4.1 多气泡连续打字 (`[SEP]`)
真实人类在社交软件聊天时，很少发一大长段文本，而是习惯拆成多条短句连发。
* **工作机制**：AI 在回复中使用 `[SEP]` 分割短句。例如：
  `好呀！[SEP]不过我得先去洗个苹果[SEP]等我五分钟喵~`
* **打字延迟模拟**：系统按 `[SEP]` 将文本拆分后，根据每条句子的字数动态计算打字时间（1.0~2.5 秒递进），逐条分开发送到 QQ，呈现出真人敲键盘的社交节奏。
* **开关配置**：`config.json` 中 `"enable_multi_bubble_reply": true`（默认启用）。

### 4.2 纯文本原生打字规范 (Raw Text vs Markdown)
* **背景**：手机 QQ 与电脑 QQ 客户端**均不支持 Markdown 语法渲染**。如果模型输出 `**加粗**`、`# 标题` 或 `- 列表项`，用户看到的将是未解析的星号与井号，体验极差。
* **系统处理**：
  1. 系统提示词中已写入严格纯文本原则，要求模型用自然口语和换行表达，严禁 Markdown 标记。
  2. 后台内置 `sanitize_reply` 过滤器，自动将意外输出的 `**加粗词**` 转换为纯字面 `加粗词`，保障聊天输出永远整洁美观。

---

## 5. 自主图库与表情包管理 (`picture_db/` 与 `stickers/`)

系统为 AI 提供了两套图片能力：**静态专属贴图库** 与 **自主动态图库/表情包管理系统**。

### 5.1 静态预置贴图 (`stickers/`)
* 目录位于 `stickers/`，支持放入常用的 `.jpg` 或 `.png` 表情。
* 文件名建议简短，如 `heart.jpg`（比心）、`wave.jpg`（挥手）、`sleep.jpg`（晚安）。
* 模型输出 `[发贴图: 比心]` 时自动模糊匹配文件名并发送。

### 5.2 自主图库与表情包数据库 (`picture_db/`)
AI 拥有自主管理和检索图片库的完整权限：
1. **自动收集与学习**：用户在聊天中发送的照片、动图或表情包，系统会自动下载入库并索引元数据（保存在 `picture_db/metadata.json` 中）。
2. **AI 自主管理指令**：
   * **发送图库图片**：`[发图: 关键词或标签]` 或 `[PICTURE: 关键词]`（如 `[发图: 哭哭猫猫]`、`[PICTURE: 委屈]`）。
   * **收藏并打标**：`[收藏表情: 标签1, 标签2: 画面描述]`（当用户发来有趣表情包时，AI 可自主打标入库）。
   * **浏览/查阅图库**：`[查看图库]` 或 `[查看图库: 搜索词]`。
   * **修改已有图片**：`[修改图片: 目标原标签或ID: 新标签: 新描述]`（当用户要求修改某张图的描述或标签时调用）。
   * **删除图片**：`[删除图片: 目标原标签或ID]`。
3. **先存后发架构保证**：系统优先执行入库与修改动作，再执行图片检索与发送动作，确保 AI 在同一轮对话中“刚收藏的表情包”可以被立即检索并发出！

---

## 6. 全模态语音系统 (多模态直传 / TTS / ASR)

### 6.1 语音接收与理解 (Inbound Voice)
用户发送语音条时，系统支持两种理解路径：
1. **原生多模态大模型（首选推荐：Gemini 1.5/2.0/2.5/3.8 Flash、GPT-4o、Omni）**：
   * QQ 语音文件（AMR 或 Tencent Silk v3）会被后台自动转码为标准 16kHz 单声道 MP3。
   * 系统通过标准 `input_audio` 负载将 Base64 音频直传大模型 API：
     ```json
     {"type": "input_audio", "input_audio": {"data": "<base64>", "format": "mp3"}}
     ```
   * **模型可以直接“听见”用户的语气、音调与说话内容**，无需外部 ASR，零延迟、极度精准！
2. **纯文本模型（如 DeepSeek-Flash / DeepSeek-V3）**：
   * 纯文本模型不接收原始音频字节，可在 `config.json` 中配置云端 ASR（如 SiliconFlow 硅基流动 SenseVoice 或本地 Whisper）：
     ```json
     "asr_api_url": "https://api.siliconflow.cn/v1/audio/transcriptions",
     "asr_api_key": "sk-xxxx",
     "asr_model": "FunAudioLLM/SenseVoiceSmall"
     ```

### 6.2 语音发送与合成 (Outbound Voice / TTS)
系统内置基于微软高质量云端语音引擎（`edge-tts`）的真实语音生成能力，纯 Python 运行，不消耗显卡算力：
1. **手机端原生播放支持（Silk v3）**：
   * 手机 QQ 客户端原生要求语音为腾讯 Silk v3 格式。
   * 项目内置 `pilk` 与 `silkcoder` 双重转码链路，自动转码为带 `\x02#!SILK_V3` 头的原生 Silk 格式，确保 iOS 和 Android 手机 QQ 都能 100% 清晰顺畅播放，绝无哑音！
2. **发送方式**：
   * **按需触发**：AI 回复中带有 `[发语音: 想听我的声音吗？]` 时自动合成并发送真实语音条。
   * **全自动模式**：在 `config.json` 中设置 `"enable_voice_reply": true`，AI 每一条回复都将自动发送真实语音。
3. **音色调整**：
   在 `config.json` 中配置 `"voice_character"`：
   * `zh-CN-XiaoyiNeural`（甜美少女音，默认推荐）
   * `zh-CN-XiaoxiaoNeural`（温柔女声）
   * `zh-CN-YunxiNeural`（活泼男声）
   * `en-US-JennyNeural`（地道美语女声）

---

## 7. 全模态感知与文档解析 (合并转发 / 文档摘要 / 动图表情)

系统具备深度的消息反序列化与多模态解析能力：
* **合并转发聊天记录**：自动抓取 OneBot `[CQ:forward]` 与 `[CQ:json]` 节点，递归还原成带发送者名称的对话树，供模型分析总结。
* **多格式文档解析**：当用户在 QQ 中发送 `.txt`、`.md`、`.pdf`、`.docx`、`.py` 等文档时，后台自动提取关键内容和摘要传给模型解答。
* **动图与超级表情感知**：识别 QQ 原生大表情、骰子点数、猜拳结果、戳一戳并转换为自然语言提示供模型互动。

---

## 8. 单账号自身聊天与双账号模式 (`bot_qq` 与 `master_qq`)

系统支持两种截然不同的运行架构：
1. **双账号伴侣模式（标准推荐）**：
   * 配置：`bot_qq`（小号）与 `master_qq`（大号）**不同**。
   * 机器人使用独立账号登录，专门服务主人账号。
   * 支持完整的 QQ 语音条双向互发、戳一戳、名片点赞。
2. **单账号自身对话模式（Self-Chat）**：
   * 配置：`bot_qq` 与 `master_qq` **相同**。
   * 相当于使用自身账号进行日常助理对话（类似于微信“文件传输助手”）。
   * **回显过滤**：系统内置 `is_bot_echo` 机制，自动过滤机器人自身发送的回复，杜绝无限回环循环。
   * *注意：腾讯 QQ 协议限制同一账号无法向自己接收语音气泡（文本与图片正常）。若需语音功能，推荐使用双账号模式。*

---

## 9. 实时联网搜索功能 (Web Search)

系统内置多引擎实时联网搜索功能（优先使用 DuckDuckGo，具备维基百科等多源兜底）：
* **触发方式**：
  * 内联标签：`[搜索: 关键词]`（英文：`[search: query]`）
  * 原生工具函数：`web_search(query)`
* **配置开关**：在 `config.json` 中配置 `"enable_web_search": true` 以及 `"max_search_results": 4`。
* **适用场景**：实时天气、突发新闻、技术文档查阅、事实核验。

---

## 10. 日志等级与防重入平滑退出机制

### 10.1 日志等级设置
在 `config.json` 中配置 `"log_level"`：
* **`DEBUG`**：最详尽模式，打印轮询心跳、下载图片原始 URL、网络耗时、原始 CQ 码。排查问题时推荐。
* **`INFO`**（默认推荐）：打印用户发送消息、模型回复、记忆压缩记录及关键警告。
* **`WARNING`** / **`ERROR`**：极简静默模式，只打印致命报错。
> **输出位置**：同时输出至终端控制台与根目录的 **`agent.log`**。

### 10.2 防重入平滑退出与 Docker 自动关停
* 在 Linux / Python 3.14 环境中，按 `Ctrl+C` 退出时，信号处理器采用 `signal.SIG_IGN` 防重复中断保护，安全拦截 I/O 缓冲刷盘冲突，杜绝 `RuntimeError: reentrant call inside BufferedWriter`。
* 退出时自动停止本地运行的 NapCat Docker 容器，释放网络端口与系统内存。

---

## 11. MCP 服务端与外部客户端接入 (`onebot_mcp.py`)

项目在 `mcp-server/onebot_mcp.py` 中内置了标准 Model Context Protocol (MCP 2.x) 服务端，便于通过 Claude Desktop、Cursor、Antigravity 等开发工具直接接管或调用 QQ 伴侣的能力：

### 挂载的 MCP 工具列表：
* `web_search`: 联网实时搜索
* `search_chat_history`: 检索全量历史聊天记录库
* `read_memory`: 读取长期记忆档案
* `update_memory`: 写入/更新长期记忆档案
* `search_picture_library`: 检索自主图库
* `send_voice_to_master`: 通过 Edge-TTS 语音合成向主人发送真实语音条
* `qq_send_master_msg` / `qq_send_private_msg` / `qq_send_group_msg`: 消息发送
* `qq_send_image`: 图片/贴图发送
* `qq_poke_master` / `qq_send_like`: 戳一戳与名片点赞
* `qq_get_recent_messages` / `qq_get_unread_messages`: 获取消息历史与未读队列

### 启动 MCP 服务端：
```bash
python3 mcp-server/onebot_mcp.py
```

---

## 12. 配置文件与核心参数说明 (`config.json`)

```json
{
  "api_type": "openai",
  "base_url": "https://openrouter.ai/api/v1/chat/completions",
  "api_key": "你的API_KEY",
  "model": "google/gemini-3.8-flash",
  "master_qq": 123456789,
  "bot_qq": 987654321,
  "onebot_http_api": "http://127.0.0.1:3000",
  "language": "zh",
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
  "voice_character": "zh-CN-XiaoyiNeural"
}
```

### 核心参数详解
* `master_qq`: 主人的 QQ 号（只处理主人的私聊消息）。
* `bot_qq`: 机器人所登录的 QQ 号。
* `debounce_delay_sec`: 防连击缓冲窗口（秒）。用户连续发多句话时，等待 2.2 秒打包合并一次性思考回复。
* `max_batch_wait_sec`: 批处理最大等待上限（秒）。防止用户持续不断发消息导致一直等待。
* `enable_multi_bubble_reply`: 是否启用 `[SEP]` 拆分为真实多气泡连发。模型用空行分段时也会拆成多个气泡（含代码块、表格、列表时除外）。
* `time_awareness`（默认 `true`）：告诉模型现在的日期、星期和时间，每条消息前也会标上发送时间（今天的写 `[14:05]`，更早的写 `[10-29 23:10]`）。这样它能分清早上晚上、知道隔了多久、记得约好的日子。模型自己的回复里不会出现这些时间标记。
* `timezone`：时区，如 `"Asia/Shanghai"` 或 `"+08:00"`。留空用服务器自己的时钟（很多云服务器是 UTC，建议设置）。Windows 上用时区名需要 `pip install tzdata`，或者直接写 `"+08:00"`。
* `time_gap_note_hours`（默认 `3`）：私聊隔了这么久再说话时，会提示模型“距离上一次聊天已经过去了 N 小时/天”。
* `usage_stats`（默认 `true`）：每次调用模型都在 `usage_stats/usage-日期.jsonl` 里记一行用量（输入/缓存/输出/思考 token、图片数、耗时、是否失败或被作废、调用类型）。只记数字，不记聊天内容。用 `python3 usage_report.py`（可加 `--days 3`、`--price-in 0.3 --price-out 2.5 --price-cached 0.03` 估算费用，单位：美元/百万 token）查看各类调用分别花了多少。
* `private_max_bubbles`: 私聊一次回复最多几个气泡（默认 4，多出的部分合并进最后一个）。群聊用 `group_max_bubbles`。
* `enable_vision` / `enable_audio_input`: 模型能否看图 / 听语音。默认 `null` = 按模型名自动判断。纯文本模型收到图片或语音时，机器人会发一条固定的系统提示（如 `NOT A VISION MODEL`）；如果模型接口因为图片或语音报错，会去掉它们重试一次，并提示 `VISION IS NOT AVAILABLE: API ERROR`。同一种提示私聊 10 分钟、群聊 1 小时最多一次。判断错了可以手动设为 `true` / `false`。
* `enable_picture_database`: 是否启用自主图库与表情包存储检索系统。
* `poll_interval_sec`: 消息轮询间隔（推荐 0.6 ~ 1.0 秒）。
* `compact_threshold` / `compact_keep_recent`: 对话长期记忆压缩阈值与保留轮数。
* 群聊相关参数（`enable_group_chat`、`group_whitelist` 等）见 [第 15 节](#15-群聊模式-group-chat)。
* `thinking_level`: 模型思考程度：`""`（默认，不设置，由服务商决定）、`none`、`minimal`、`low`、`medium`、`high`。思考越多回复越慢、越费 token。
* `thinking_level_background`: 后台任务（整理记忆、旁观群聊、QQ空间）的思考程度，留空就和 `thinking_level` 一样。推荐 `low`，省钱也更快。
* `thinking_api`: 这个设置怎么发给服务商，默认 `auto` 自动判断：
  - **OpenRouter**（以及模型名像 `google/gemini-…` 的中转站）发 `"reasoning": {"effort": "low"}`；
  - **DeepSeek**（`api.deepseek.com`）只有开和关：`none` 关闭思考，其它级别都是开启；
  - 其它 OpenAI 兼容接口发 `"reasoning_effort": "low"`。
  判断错了可以手动设为 `openrouter`、`deepseek` 或 `openai`。如果模型不接受某个级别（比如有的模型不允许关闭思考），`none` 会自动改用 `low`，其它级别会改为不设置，并在日志里提示一次。
* `onebot_access_token`: 如果给 NapCat 的 HTTP 服务设置了 token（例如 NapCat 不在本机运行时），在这里填同一个值，机器人会带上 `Authorization: Bearer` 请求头。

---

## 13. Debian / Linux 无头部署与终端扫码

在没有图形界面的 Linux 云服务器上部署：

### 推荐 Docker 部署 NapCat：
```bash
docker run -d \
  --name napcat \
  --restart always \
  --network host \
  -v /opt/napcat/config:/app/napcat/config \
  mlikiowa/napcat-docker:latest
```

* **扫码登录**：
  ```bash
  docker logs -f napcat
  ```
  终端会直接输出 ASCII 字符二维码，手机 QQ 直接扫描终端二维码即可完成登录！

### 启动 AI 伴侣守护进程：
日常使用推荐直接使用一键脚本：
```bash
chmod +x setup.sh start.sh
./setup.sh    # 首次自动安装系统环境、Python依赖、预下载TTS语音并配置NapCat
./start.sh    # 日常运行与守护
```

**搬到另一台电脑或另一个文件夹时**：`venv/` 不能直接复制过去用（里面写死了原来的路径和 Python 版本）。不复制也没关系，脚本发现 `venv/` 来自别的机器、别的文件夹或别的 Python 版本时，会自动删除并重建，不会再出现 `externally-managed-environment` 错误。所有依赖只装进 `venv/`，不会碰系统 Python。

### 安全默认设置
- OneBot HTTP 接口（端口 3000）没有 token，所以启动脚本会让它只监听 `127.0.0.1`；以前配置成 `0.0.0.0` 的也会自动改回来（只要 `onebot_http_api` 指向本机）。如果 NapCat 的配置文件属于 root、脚本改不了，会打印提示，按提示用 sudo 改一下即可。
- 新建的 NapCat 容器会生成随机的 WebUI token，不再使用公开的默认值 `napcat`。
- 启动横幅不再查询或显示服务器的公网 IP，WebUI token 只显示前后两位。完整 token 可用 `sudo grep token /opt/napcat/config/webui.json` 查看。
- 远程访问 WebUI 请用 SSH 隧道：`ssh -L 6099:127.0.0.1:6099 用户名@服务器地址`，然后在自己电脑上打开 `http://127.0.0.1:6099/webui`。不要在云服务器安全组里对公网开放 6099 或 3000 端口。

---

## 14. Windows 一键部署与双击运行

对于 Windows 用户，无需输入任何复杂终端指令：

1. **一键自动安装环境与 NapCat**：
   * 双击运行根目录下的 **`setup_windows.bat`**。
   * 脚本会自动建立 Python 独立虚拟环境、安装所有依赖并预热 TTS 语音引擎。
   * 提示安装 NapCat 时，输入 `1` 即可全自动下载并解压官方最新版 NapCatQQ 到 `NapCat/` 文件夹。
2. **日常启动**：
   * 在 `config.json` 中配置好 API Key 和 QQ 号后，双击 **`start.bat`**（或 `start_agent.bat`）即可一键启动 AI 伴侣。
3. **安全**：`setup_windows.bat` 和 `start.bat` 每次都会运行 `secure_napcat.py`，把没有 token 的 OneBot 接口（端口 3000/3001）改为只监听 `127.0.0.1`。修改后需要重启一次 NapCat 才生效（扫码登录后第一次运行 `start.bat` 时会提示）。

---

## 15. 群聊模式 (Group Chat)

让 AI 伴侣以同一个人设加入 QQ 群聊天，同时保证主人的私人记忆绝不会出现在群里。群里的它和私聊里的它是同一个"人"：记得群里发生的事，私聊时主人问起也能回忆；但私聊内容永远不会被带进群里。

### 15.1 开启方法
在 `config.json` 中加入以下字段（群聊需要两个不同的 QQ 号，即 `bot_qq` ≠ `master_qq`）：
```json
{
  "enable_group_chat": true,
  "group_whitelist": [123456789],
  "bot_name": "星喵",
  "group_trigger_keywords": ["星喵", "Hoshineko"],
  "group_member_msg_limit": 10,
  "group_member_limit_window_sec": 86400
}
```
保存后无需重启，约 10 秒内自动生效。**只有 `group_whitelist` 里的群会被读取和回复**；白名单为空时不会读取任何群。

### 15.2 什么时候回复
一条群消息只有满足以下任一条件，才会交给模型处理：
- **提到角色名**：消息文字里含有 `group_trigger_keywords` 中的词（留空时使用 `bot_name`，再留空则使用机器人的 QQ 昵称）。英文名按整词匹配，例如 `neko` 不会被 `nekomimi` 误触发。
- **@机器人**（`group_trigger_on_at`，默认开启）。
- **回复/引用了机器人发过的消息**（`group_trigger_on_reply`，默认开启）。

其余群消息不会触发回复，只作为"背景消息"在下一次被叫到时提供给模型理解上下文。被叫到后，如果模型觉得只是被顺口提到、不需要说话，也可以输出 `[NO_REPLY]` 保持沉默。

**连续消息**：一个人叫了机器人之后，几秒内接着发的消息（例如先 @ 再发一张图）也算这次对话的一部分，就像私聊里连着发的几条会合并理解一样。如果回复还在生成，会带上新消息重新生成；@ 别人或引用别人的消息则不算。窗口时长由 `group_followup_window_sec` 控制（默认 10 秒）。

**图片、表情包、文件、合并转发**：
- 叫机器人的消息里、紧接着补发的消息里、被引用的消息里的图片都会打开给模型看。
- **引用回复**：私聊和群聊里，模型都能看到“引用了谁的哪条消息”以及被引用的内容（例如 `（引用了你之前说的：“明天记得带伞喵”）`）。私聊里被引用消息中的图片也会附上（最多 2 张）。群聊背景消息里的引用也会标出来。实在取不到内容时会写明“引用了一条之前的消息，但获取不到它的内容”。
- 机器人上次回复之后，群里最近发过的图片 / 合并转发 / 文件 / 语音，会打开最近的 `group_context_media` 条（默认 2 条，5 分钟内），所以"@星喵 评价一下"能看到别人刚才发的图。
- 每次最多附 4 张图，并附一段说明告诉模型每张图是谁发的。
- 机器人看过的表情包会自动存进图库，并告诉模型它的图库 ID，之后可以用 `[发图: ID]` 原样再发；主人发的表情包是公开的，其他群友的只存在该群。普通照片不会自动保存（需要时可用 `[收藏表情: …]`）。
- 模型正在回复时，其他人的新消息会排队，等这条回复发完再处理（私聊则保持原来的"打断并合并"机制）。
- 群里的回复更简短，最多拆成 `group_max_bubbles` 条气泡；默认会在第一条气泡里 @ 提问的人。

### 15.3 身份识别：只认 QQ 号，不认昵称
- 主人身份**只**通过 OneBot 上报的真实 `user_id` 与 `master_qq` 比对来判断；群名片、昵称完全不参与身份判断。
- 发给模型的每条群消息前都有程序生成的发言人标签：主人是 `【主人✔】`，其他人是 `【群友 QQ:号码 昵称:xxx】`。群友输入的文字和昵称里的 `【】` 会被替换成 `[]`，所以任何人都伪造不了 `【主人✔】` 标签。
- 所有权限检查都在代码里按 QQ 号执行，不依赖模型"听话"。即使模型被提示词注入完全骗过，它在群里也拿不到私聊数据，也做不了越权操作。

### 15.4 记忆与资产隔离（物理隔离）
| 内容 | 主人私聊 | 每个群 |
| :--- | :--- | :--- |
| 短期上下文 | `history.json`（原文件，记忆无缝延续） | `sessions/group_<群号>/history.json` |
| 长期记忆 | `memory_summary.txt` | `sessions/group_<群号>/memory_summary.txt` |
| 永久聊天记录 | `chat_history.jsonl` | `sessions/group_<群号>/chat_history.jsonl` |
| 群友发言次数 | — | `sessions/group_<群号>/quota.json` |
| 已处理消息记录 | — | `sessions/group_<群号>/seen_ids.json`（重启不会重复回复） |
| 临时下载 | `downloads/` | `downloads/group_<群号>/` |

- 群聊会话的任何代码路径都不会打开主人的私聊文件。`[查看记忆]`、`[搜索聊天记录]`、`[更新记忆]` 在群里都只作用于本群；`agent.log`（混有所有聊天）在群里也不会被搜索。
- **即使是主人本人在群里说话，群里的模型也拿不到私人记忆**：群里的回复是公开的，而且同一批消息里可能混有别人的注入内容。私密的事请在私聊里问。
- 主人的 QQ 号默认不隐藏（QQ 号本来就谁都能看到，而且认人只看 QQ 号，知道号码也冒充不了）。想隐藏的话设 `"hide_master_qq": true`：群里的回复和QQ空间里会显示为 `[主人QQ号已隐藏]`，只有主人本人要求时（这一批消息全部来自主人）才会说出来。
- **记忆模式**（`memory_mode`）：
  - `"shared"`（默认）：所有群聊和好友私聊共用一份**公共记忆**（`sessions/public/memory_summary.txt`），每条都标明来源（如 `[群「测试群」(900)]`、`[和QQ:555的私聊]`）。这样机器人在群里认识的人，私聊时也认得，聊天更连贯。只有主人私聊的记忆是单独的，永远不会进入公共记忆。
  - `"separate"`：每个群、每位好友只看得到自己那份记忆，A 群的记忆在 B 群里不可见。
  - 两种模式下，每个群（`sessions/group_<群号>/`）和每位好友（`sessions/private_<QQ号>/`）自己的记忆文件都会照常写入，所以之后改成 `"separate"` 也有完整的分开记忆。第一次用共享模式时，已有的群聊/好友记忆会自动合并进公共记忆（各自标明来源）。
  - 共享模式下要注意：好友私聊里记下的事，在群里也可能被机器人想起。模型被要求不记录、不外传别人明显不想公开的私事。
- **记忆单向流动**：主人在私聊里问"群里今天聊了什么"，伴侣可以用 `[查看群聊: 群号或关键词]` 或 `recall_group_chat` 工具回忆群聊内容。
- 群聊记忆里的每一条都会自动带上来源，例如 `(来源: QQ:123(小明))`，由程序根据真实 QQ 号写入。每个群的记忆有长度上限（`group_memory_max_chars`），也会像私聊一样自动压缩。

### 15.5 图库：表情包共享，照片私密
图库仍然是一个统一的 `picture_db/`，但每张图片都有可见范围：
- **表情包/动图**（包括 `stickers/` 里的预置贴图）：公开，所有聊天都能用。
- **主人私聊里收到的普通照片**：私密，只在私聊里可用，群里搜不到也发不出。
- **在群里收藏的图片**：只属于该群（主人私聊里也能看到）。
- 旧版图库里没有可见范围的图片：带"表情包/动图"标签或位于 `stickers/` 的算公开，其余按私密处理。
- 群里不会自动收藏群友发的图片；在群里修改、删除图片只有主人本人（按 QQ 号判断）提出时才会执行，而且只能动该群可见的图片。
- 主人可以在私聊里用 `[公开图片: ID或标签]` / `[私密图片: ID或标签]` 调整某张图片的可见范围。

### 15.6a 主动私聊主人与群聊媒体记忆
**主动私聊主人**：机器人在群里看到让它惊讶、想吐槽或主人会想知道的事，可以私下发消息给主人（开头标明来自哪个群）。
- 被叫到回复时，它可以顺便用 `[告诉主人: …]` 私聊你。
- **旁观**：没人叫它时，它每隔约 10 分钟看一眼新的群聊（至少有 5 条新消息才看，每个群每小时最多 4 次）。大多数时候它会选择不打扰；旁观时它不会在群里发言。
- 所有群合计每小时最多私聊主人 3 次。群友让它"转告主人"不会照做。这些消息也会记进私聊记录，你回复时它知道在说什么。
- 每次旁观是一次额外的模型调用；不想要可以设 `"group_glance_enabled": false`。

**群聊媒体记忆**：机器人打开过的图片和语音会保存 `group_media_retention_days` 天（默认 7 天），并由模型写一句描述存进群聊记录，例如"一只橘猫趴在纸箱里"。
- 之后搜索聊天记录、或在私聊里回忆群聊时，能看到描述和媒体ID，而不只是 `[图片]`。
- 保存期内可以用 `[查看媒体: 媒体ID]` 重新看或听；过期后文件自动删除，文字描述保留。
- 只记录机器人自己打开过的媒体，不会额外花钱给每张图写描述。

### 15.6 群友发言次数限制
- 每位群友（主人除外）在一个时间窗口内最多触发 `group_member_msg_limit` 次回复（24 小时滚动窗口；config.json 里没写这一项时按 50 次处理，并在日志里给出 WARNING）。只统计叫到机器人的消息；普通聊天不计数。
- 超过上限后，该群友的消息会被**完全忽略**（连背景消息也不再采用），直到窗口内的次数回落。
- `group_member_limit_window_sec` 设为 `0` 表示永久上限、永不重置；`group_member_msg_limit` 设为 `0` 表示不限制。某人用完次数时日志里会出现一次 WARNING（`has used all N messages … ignored until 时间`），之后每条被忽略的、叫机器人的消息记一行 INFO（`ignoring message`）。
- 计数保存在 `quota.json`，重启不会清零。想手动解除限制，删除该群目录下的 `quota.json` 即可。
- 可选 `group_member_limit_notice`：群友第一次超限时发一条提示语（默认留空，静默忽略）。

### 15.7 群聊参数一览
| 参数 | 默认值 | 说明 |
| :--- | :--- | :--- |
| `enable_group_chat` | `false` | 群聊总开关 |
| `group_whitelist` | `[]` | 允许的群号列表；为空时不读取任何群 |
| `bot_name` | `""` | 角色名，也是默认触发词 |
| `group_trigger_keywords` | `[]` | 触发词列表；为空时使用 `bot_name` 或机器人 QQ 昵称 |
| `group_trigger_on_at` | `true` | 被 @ 时回复 |
| `group_trigger_on_reply` | `true` | 被引用（回复机器人的消息）时回复 |
| `group_member_msg_limit` | 未设置时 `50`（并警告） | 每位群友的回复次数上限（主人不受限；`0` = 不限） |
| `group_member_limit_window_sec` | `86400` | 计数窗口（秒，滚动）；`0` = 永不重置 |
| `group_member_limit_notice` | `""` | 首次超限时的提示语（留空则静默） |
| `group_reply_with_at` | `true` | 回复时 @ 提问的人 |
| `group_reply_with_quote` | `false` | 回复时引用对方的消息 |
| `group_context_messages` | `12` | 作为背景提供给模型的最近群消息条数 |
| `group_context_max_age_sec` | `900` | 背景消息的最长时效（秒） |
| `group_followup_window_sec` | `10` | 叫过机器人后，同一个人接着发的消息算同一次对话的时长（秒）；`0` = 关闭 |
| `group_context_media` | `2` | 被叫到时打开的最近背景媒体条数（图片/转发/文件/语音）；`0` = 不打开 |
| `group_context_media_max_age_sec` | `300` | 只打开这么多秒以内的背景媒体 |
| `group_media_retention_days` | `7` | 打开过的图片/语音保存天数（描述永久保留）；`0` = 不删除 |
| `group_master_notify_max_per_hour` | `3` | 每小时主动私聊主人的上限（所有群合计）；`0` = 关闭 |
| `group_glance_enabled` | `true` | 没被叫到时也定期看一眼群聊 |
| `group_glance_interval_sec` / `group_glance_min_new_messages` / `group_glance_max_per_hour` | `600` / `5` / `4` | 旁观间隔、至少多少条新消息、每群每小时上限 |
| `group_max_tokens` | `800` | 群聊回复的最大 token 数。会“思考”的模型（如 Gemini）的思考也算在里面；用完了回复会是空的，程序会自动用 4 倍额度重试一次并记 WARNING，经常出现就调大这一项或设置 `thinking_level` |
| `group_max_bubbles` | `3` | 群聊回复最多拆成几条气泡 |
| `group_memory_max_chars` | `3000` | 每个群（和每位好友）自己记忆的长度，超出时合并重复条目（先备份） |
| `memory_mode` | `"shared"` | `shared`：群聊和好友私聊共用公共记忆；`separate`：每个聊天各自一份 |
| `public_memory_max_chars` | `8000` | 公共记忆的长度，超出时合并重复条目（先备份） |
| `group_log_ambient` | `true` | 未触发的群消息是否也存入该群的聊天记录（供回忆） |
| `group_max_file_bytes` | `8388608` | 群文件解析的大小上限（字节） |
| `group_poll_interval_sec` | `1.5` | 群消息轮询间隔（秒） |
| `group_debounce_delay_sec` / `group_max_batch_wait_sec` | `1.5` / `6.0` | 群消息合并窗口与最长等待（秒） |

### 15.8 自定义群聊风格
`persona/system_prompt_group_zh.md`（英文模式为 `system_prompt_group_en.md`）控制群聊里的说话风格：更简短、不刷屏、不把群友叫"主人"等，可以自由修改。身份识别、隐私隔离等安全规则写在程序里，修改或删除这个文件不会削弱它们。

### 15.9 注意事项
- 单账号模式（`bot_qq == master_qq`）下群聊不会启动：主人和机器人共用一个 QQ 号，程序无法按 QQ 号区分两者，日志里会有提示。
- 如果 `config.json` 里的 `bot_qq` 填错，群聊会以 NapCat 实际登录的账号为准，并在日志中给出警告。
- 机器人必须已经是白名单群的成员；读取失败时日志每 5 分钟提示一次。

---

## 16. QQ空间 (Qzone，实验功能)

机器人可以逛QQ空间：看主人和好友的说说、评论、点赞，也会偶尔自己想发一条说说。默认关闭，在 `config.json` 里设 `"enable_qzone": true` 打开。

> QQ空间没有官方接口。这个功能用 NapCat 提供的登录 Cookie 调用QQ空间网页版的接口，腾讯随时可能改动，也有一定的账号风控风险。请用小号，并保持下面的默认频率。

### 16.1 它会做什么
- **看说说、评论**：每 30 分钟看一次主人的空间，再轮流看 5 个好友的空间。只看 24 小时内、并且是功能打开之后发的新说说。由模型决定评论、点赞还是跳过。
  - 主人的说说每天最多回应 5 次（`qzone_master_comment_max_per_day`）。
  - 其他好友的说说每天最多 3 次（`qzone_comment_max_per_day`）。
  - 已经评论过的不会再评论。
- **自己发说说**：每天有 40% 的概率（`qzone_random_post_chance_per_day`）在 9 点到 23 点之间（`qzone_active_hours`）的某个随机时间想发一条。它会先把草稿私聊发给主人（`【空间草稿 D3】…`），主人说“发吧”才发出，说“算了”就放弃，也可以直接说怎么改。草稿 24 小时没回应就作废。
- **请它发说说**：
  - 主人在私聊或群里亲口让它发（消息里有“发条说说”“发到空间”之类的话），会直接发出。程序检查的是主人的原话，引用的内容不算；模型自己决定要发的，一律先变成草稿。
  - 草稿只有在主人回复同意（发吧/可以/好/ok 等，且没有“不要/别/算了”）时才能发出；改过的内容会作为新草稿再给主人确认。
  - 群友请它发，会变成草稿先发给主人确认，每天最多 3 条（`qzone_member_request_max_per_day`）。
- **私聊里**：主人可以让它“看看我的空间”“看看 QQ:xxx 的空间”“看看大家最近发了什么”（主人和所有好友最近 24 小时的新说说，最多 10 条，每次最多新读 20 个好友）“去评论我最新那条”。它也记得自己最近在空间里做过什么。

### 16.2 隐私与安全
- 空间对所有QQ好友公开，所以和群聊一样处理：不会带入主人的私人记忆，只发纯文本（只有开了 `hide_master_qq` 才隐藏主人的QQ号）。
- 别人的说说和评论都当作不可信内容，里面的“指令”不会被执行。
- 自己想发的、群友请求的说说都要主人同意；只有主人本人（按QQ号确认）的请求会直接发。
- 自己发的说说加上群友请求的，每天最多 3 条（`qzone_post_max_per_day`），主人的请求不受限。
- 单账号模式（`bot_qq == master_qq`）下不会启动。

### 16.3 设置

| 参数 | 默认值 | 说明 |
|---|---|---|
| `enable_qzone` | `false` | 总开关 |
| `qzone_check_interval_sec` | `1800` | 多久看一次新说说（最少 300） |
| `qzone_friends_per_check` | `5` | 每次轮流看几个好友（主人每次都看） |
| `qzone_max_post_age_hours` | `24` | 更早的说说不回应 |
| `qzone_master_comment_max_per_day` | `5` | 每天回应主人说说的次数 |
| `qzone_comment_max_per_day` | `3` | 每天回应其他好友说说的次数 |
| `qzone_random_posts` | `true` | 会不会自己想发说说 |
| `qzone_random_post_chance_per_day` | `0.4` | 每天想发一条的概率 |
| `qzone_active_hours` | `[9, 23]` | 自己发说说的时间段 |
| `qzone_post_approval` | `true` | 自己想发的先给主人确认（关掉则直接发，并告诉主人） |
| `qzone_post_max_per_day` | `3` | 每天自己发的加群友请求的说说上限 |
| `qzone_member_request_max_per_day` | `3` | 每天群友请求发说说的次数 |
| `qzone_draft_expire_hours` | `24` | 草稿多久没回应就作废 |

记录保存在 `sessions/qzone/state.json`（看过的说说、草稿、最近的空间动态）。目前只支持纯文本，发图片会在之后加入。

---

## 17. 好友私聊模式 (Friend Chat)

除了主人，机器人也可以和其他QQ好友私聊。默认关闭，在 `config.json` 里设 `"enable_friend_chat": true` 打开。和群聊一样，这些私聊被当作“公开、不可信”的场合处理。

### 17.1 规则
- **谁能聊**：机器人的所有QQ好友，除了 `friend_blacklist` 里的QQ号。主人走自己的私聊，不受影响。
- **认人只看QQ号**：对方说自己是主人、管理员也没用；只有主人的QQ号才是主人。
- **记忆**：每位好友有自己的文件夹 `sessions/private_<QQ号>/`（记忆、聊天记录、消息计数）。主人的私人记忆永远不会出现在这些私聊里。默认（`memory_mode: "shared"`）好友私聊和群聊共用公共记忆，机器人在群里和私聊里都认得同一个人；设成 `"separate"` 则每位好友只看得到自己那份（见 §15）。
- **消息上限**：每位好友在 24 小时内最多触发 `private_member_msg_limit` 次回复（和群聊上限分开计算）。没写这一项时按 50 次处理，并在日志里给出 WARNING；`0` = 不限。被限制的消息会在日志里记一行；可以用 `private_member_limit_notice` 设置一条提示语（默认不提示）。
- **能做的事**：联网搜索、搜索/记录和这位好友的私聊记忆、发公共表情包。不能修改或删除图库，不能把对方的图片存进图库。请它发QQ空间说说只会变成草稿，先发给主人确认。
- **告诉主人**：聊到主人会想知道的事，它可以私下告诉主人（如 `【和小李(QQ:123)的私聊】……`），和群聊共用每小时上限。
- **主人回忆**：主人在私聊里可以问“你和小李聊了什么”，它会用 `[查看私聊: QQ号或昵称]` / `recall_friend_chat` 回忆（只读）。
- 单账号模式（`bot_qq == master_qq`）下不会启动，否则机器人会以主人的身份回复主人的朋友。

### 17.2 怎么发现新消息
- 优先用 NapCat 的“最近联系人”（`get_recent_contact`），每 3 秒看一次哪些私聊有新消息，只读有变化的那几个。
- 如果 NapCat 不支持，就每次轮流检查 5 个好友（`friend_poll_batch`）。
- 启动时 3 分钟以前的旧消息不会回复。

### 17.3 设置

| 参数 | 默认值 | 说明 |
|---|---|---|
| `enable_friend_chat` | `false` | 总开关 |
| `friend_blacklist` | `[]` | 不回复的QQ号 |
| `private_member_msg_limit` | 未设置时 `50`（并警告） | 每位好友的回复次数上限；`0` = 不限 |
| `private_member_limit_window_sec` | `86400` | 计数窗口；`0` = 永不重置 |
| `private_member_limit_notice` | `""` | 达到上限时发给对方的一次性提示 |
| `friend_poll_interval_sec` | `3` | 多久检查一次新消息 |
| `friend_poll_batch` | `5` | 不支持“最近联系人”时，每次轮流检查几个好友 |
