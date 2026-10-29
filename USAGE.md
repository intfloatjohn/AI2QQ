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
4. **长期记忆自动沉淀（Auto-Compact）**：当对话轮次到达阈值（默认 30 轮）时，程序会自动在后台将旧对话提取要点合并进 `memory_summary.txt`，同时保留最新 12 轮上下文。

### 管理与调试
* **实时更新指令**：在聊天时对机器人说“记住我喜欢喝冰拿铁”，机器人会回复并执行 `[更新记忆: 用户喜欢喝冰拿铁]`。
* **查看/修改记忆**：直接打开 `memory_summary.txt` 即可手动新增、修改或校对。
* **清除记忆**：清空 `memory_summary.txt` 并将 `history.json` 置为 `[]`。

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
* `enable_multi_bubble_reply`: 是否启用 `[SEP]` 拆分为真实多气泡连发。
* `enable_picture_database`: 是否启用自主图库与表情包存储检索系统。
* `poll_interval_sec`: 消息轮询间隔（推荐 0.6 ~ 1.0 秒）。
* `compact_threshold` / `compact_keep_recent`: 对话长期记忆压缩阈值与保留轮数。

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

---

## 14. Windows 一键部署与双击运行

对于 Windows 用户，无需输入任何复杂终端指令：

1. **一键自动安装环境与 NapCat**：
   * 双击运行根目录下的 **`setup_windows.bat`**。
   * 脚本会自动建立 Python 独立虚拟环境、安装所有依赖并预热 TTS 语音引擎。
   * 提示安装 NapCat 时，输入 `1` 即可全自动下载并解压官方最新版 NapCatQQ 到 `NapCat/` 文件夹。
2. **日常启动**：
   * 在 `config.json` 中配置好 API Key 和 QQ 号后，双击 **`start.bat`**（或 `start_agent.bat`）即可一键启动 AI 伴侣。
