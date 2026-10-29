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
* 群聊相关参数（`enable_group_chat`、`group_whitelist` 等）见 [第 15 节](#15-群聊模式-group-chat)。
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
- 群里的回复会把主人的 QQ 号显示为 `[主人QQ号已隐藏]`；只有主人本人要求时（这一批消息全部来自主人），机器人才会说出来。
- 不同群之间互相隔离，A 群的记忆在 B 群里不可见。
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
- `group_member_limit_window_sec` 设为 `0` 表示永久上限、永不重置；`group_member_msg_limit` 设为 `0` 表示不限制。被限制的消息会在日志里记一行 `reached the limit`。
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
| `group_max_tokens` | `800` | 群聊回复的最大 token 数 |
| `group_max_bubbles` | `3` | 群聊回复最多拆成几条气泡 |
| `group_memory_max_chars` | `3000` | 每个群长期记忆的长度上限（超出时丢弃最旧条目） |
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
