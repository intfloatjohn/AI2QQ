# QQ AI Companion 架构与使用手册 (User Guide)

本项目是一套高性能、低内存占用、支持多模态（看图+语音收发+表情包）的 24 小时无人值守 QQ AI 伴侣框架。本手册解答日常配置、二次开发与运维管理的核心问题。

---

## 目录
1. [哪里编写人格文件？](#1-哪里编写人格文件)
2. [AutoCompact 长期记忆与实时记忆管理](#2-autocompact-长期记忆与实时记忆管理)
3. [全量聊天记录持久化与检索功能](#3-全量聊天记录持久化与检索功能)
4. [实时联网搜索功能 (Web Search)](#4-实时联网搜索功能-web-search)
5. [日志等级（Log Level）怎么调整？](#5-日志等级log-level怎么调整)
6. [如何让 AI 自己找并发送表情包/贴图？](#6-如何让-ai-自己找并发送表情包贴图)
7. [语音收发（Voice / TTS）功能指南](#7-语音收发voice--tts功能指南)
8. [MCP 服务端与外部客户端接入 (onebot_mcp.py)](#8-mcp-服务端与外部客户端接入-onebot_mcppy)
9. [配置文件与核心参数说明](#9-配置文件与核心参数说明)
10. [Debian / Linux 无头部署与终端扫码](#10-debian--linux-无头部署与终端扫码)
11. [Windows 一键部署与双击运行](#11-windows-一键部署与双击运行)

---

## 1. 哪里编写人格文件？

所有影响 AI 行为、性格、口吻的人格文件均存放在 **`persona/`** 目录中，支持热重载（无需重启脚本，每次模型思考时自动读取最新版）：

| 文件路径 | 作用说明 | 编写建议 |
| :--- | :--- | :--- |
| **`persona/system_prompt.md`** | **主系统提示词（核心）** | 建议放对话铁律、字数限制（如1~3句）、表情标签说明。任何模型都能瞬间秒懂。 |
| **`persona/persona.md`** | 角色设定与世界观细节 | 定义人设姓名、身世背景、语气口癖、爱好与称谓。 |
| **`persona/tools.md`** | 工具与交互标签手册 | 供开发者和模型参考的动作、表情与语音调用规范。 |

> **修改技巧**：直接用文本编辑器编辑 `persona/system_prompt.md`，保存后下一次给 Bot 发 QQ 消息即会立刻按新人格回复！

---

## 2. AutoCompact 长期记忆与实时记忆管理

### 工作原理
框架采用**动态多层记忆架构**：
1. **短期近期上下文**（`history.json`）：保留最近活跃的连续聊天记录。
2. **实时记忆动态更新**：模型在对话中识别到重要事实或用户要求“记住...”时，可直接触发 `[更新记忆: 内容]`，后台立即持久化追加至 `memory_summary.txt`，无需等待对话压缩！
3. **长期记忆查阅**：模型可自主决定是否通过 `[查看记忆]` 调阅完整的 `memory_summary.txt`。
4. **长期记忆自动沉淀（Auto-Compact）**：当对话轮次到达阈值（默认 30 轮）时，程序会自动在后台将旧对话提取要点合并进 `memory_summary.txt`，同时保留最新 12 轮上下文。

### 怎么管理与调试？
* **实时更新指令**：在聊天时对机器人说“记住我喜欢喝冰拿铁”，机器人会回复并执行 `[更新记忆: 用户喜欢喝冰拿铁]`。
* **查看/修改记忆**：直接打开 `memory_summary.txt` 即可手动新增、修改或校对。
* **清除记忆**：清空 `memory_summary.txt` 并将 `history.json` 置为 `[]`。

---

## 3. 全量聊天记录持久化与检索功能

### 永久历史库 (`chat_history.jsonl`)
每一次用户发送的消息和 AI 生成的回复都会带有精准的时间戳永久记录在 `chat_history.jsonl` 中，永不丢失，哪怕经历了 Auto-Compact 裁剪，原始对话也始终完整留存。

### 历史记录智能检索
模型可以通过以下指令随时翻阅过去的聊天记录：
* **模型调用标签**：`[搜索聊天记录: 关键词]`（英文模式：`[Search History: keyword]`）
* **示例**：当用户问“你还记得我上周提过的那个项目叫什么吗？”，模型输出 `[搜索聊天记录: 项目]`，系统会自动检索 `chat_history.jsonl` 并将包含上下文的时间与对话反馈给模型。

---

## 4. 实时联网搜索功能 (Web Search)

系统内置了多引擎实时联网搜索功能（优先使用 `ddgs`，支持 DuckDuckGo / 维基百科 API 等兜底）：
* **触发方式**：
  * 内联标签：`[搜索: 关键词]`（英文模式：`[Search: query]`）
  * 原生函数调用：`web_search(query)`
* **配置开关**：在 `config.json` 中配置 `"enable_web_search": true` 以及 `"max_search_results": 4`。
* **场景**：天气预报、最新时事新闻、百科知识、开发文档查询等。

---

## 5. 日志等级（Log Level）怎么调整？

在 `config.json` 中修改 `"log_level"` 参数：
```json
{
  "log_level": "INFO"
}
```
* **`DEBUG`**：最详尽模式，打印每一次轮询心跳、下载图片的原URL、网络耗时、原始CQ码。排查问题时推荐。
* **`INFO`**（默认）：常规模式，打印用户发送的文字、大模型回复文字、记忆压缩记录及报错。
* **`WARNING`** / **`ERROR`**：极简静默模式，只打印网络超时或致命报错。

> **日志输出位置**：同时输出在终端控制台和项目根目录下的 **`agent.log`** 文件中。

---

## 6. 如何让 AI 自己找并发送表情包/贴图？

### 步骤 A：把图片放入 `stickers/` 目录
支持 `.jpg` 或 `.png` 格式，文件名建议用简短动词或情绪命名，例如：
* `heart.jpg`（比心）
* `wave.jpg`（挥手/问好）
* `sleep.jpg`（晚安/睡觉）
* `avatar.jpg`（自拍照）

### 步骤 B：告诉 AI 贴图名称
在 `persona/system_prompt.md` 中写明可用的贴图标签，例如：
```markdown
专属贴图（按需附在句末）：[发贴图: 比心]、[发贴图: 挥手]、[发贴图: 晚安]、[发贴图: 自拍]
```

### 步骤 C：程序自动匹配派发
当模型在回复中输出 `[发贴图: 比心]` 时，程序会自动模糊匹配 `stickers/` 目录下带 `heart` 或 `比心` 的图片，并通过 OneBot 真实图片接口直接发给用户！

---

## 7. 语音收发（Voice / TTS）功能指南

### 5.1 语音发送 (TTS)
系统内置了基于微软高质量云端语音引擎（`edge-tts`）的真实语音生成能力，纯 Python 运行，不消耗本机显卡/算力：
1. **安装依赖**：
   ```bash
   pip install edge-tts
   ```
2. **两种发送方式**：
   * **标签触发**：AI 回复中带有 `[发语音: 想听我的声音吗？]` 时，程序会自动合成并作为真实的 QQ 语音条发出。
   * **全自动语音模式**：在 `config.json` 中设置 `"enable_voice_reply": true`，AI 的每一句回复都将自动朗读并发送真实语音条！
3. **音色调整**：
   在 `config.json` 中配置 `"voice_character"`：
   * `zh-CN-XiaoyiNeural`（甜美少女音）
   * `zh-CN-XiaoxiaoNeural`（温柔女声）
   * `zh-CN-YunxiNeural`（活泼男声）

### 5.2 语音接收
当用户在 QQ 上发来语音消息时，程序会自动解析 `[CQ:record,...]` 标签，识别为语音条输入，并在视觉/听觉提示中通知模型。

---

## 8. MCP 服务端与外部客户端接入 (`onebot_mcp.py`)

项目在 `mcp-server/onebot_mcp.py` 中内置了标准 Model Context Protocol (MCP 2.x) 服务端，便于通过 Claude Desktop、Cursor、Antigravity 等开发工具直接接管或调用 QQ 伴侣的能力：

### 挂载的 MCP 工具列表：
* `web_search`: 联网实时搜索
* `search_chat_history`: 检索全量历史聊天记录库
* `read_memory`: 读取长期记忆档案
* `update_memory`: 写入/更新长期记忆档案
* `send_voice_to_master`: 通过 Edge-TTS 语音合成直接向主人发送真实语音条
* `qq_send_master_msg` / `qq_send_private_msg` / `qq_send_group_msg`: 消息发送
* `qq_send_image`: 图片/贴图发送
* `qq_poke_master` / `qq_send_like`: 戳一戳与名片点赞
* `qq_get_recent_messages` / `qq_get_unread_messages`: 获取消息历史与未读队列

### 启动 MCP 服务端：
```bash
python3 mcp-server/onebot_mcp.py
```

---

## 9. 配置文件与核心参数说明 (`config.json`)

```json
{
  "api_type": "openai",
  "base_url": "https://openrouter.ai/api/v1/chat/completions",
  "api_key": "你的APIKey",
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
  "enable_web_search": true,
  "max_search_results": 4,
  "log_level": "INFO",
  "enable_voice_reply": false,
  "voice_character": "zh-CN-XiaoyiNeural"
}
```

* `master_qq`: 主人的 QQ 号（只回复主人的私聊消息）。
* `debounce_delay_sec`: 防连击缓冲时间（秒）。用户连续发多句话时，等待 1.8 秒打包合并一次性思考回复。
* `poll_interval_sec`: 轮询频率（秒），默认 1.2 秒检测一次新消息。
* `compact_threshold` / `compact_keep_recent`: 对话长期记忆压缩阈值与保留轮数。
* `max_tokens` / `single_message_limit_hint`: 软性回复长度与风格参考，模型根据语境自主拿捏，绝不死板截断。
* `enable_web_search` / `max_search_results`: 实时联网搜索开关及单次条数。

---

## 10. Debian / Linux 无头部署与终端扫码

在没有图形界面的云服务器上部署 NapCatQQ：

### 推荐 Docker 纯命令行部署：
```bash
docker run -d \
  --name napcat \
  --restart always \
  --network host \
  -v /opt/napcat/config:/app/napcat/config \
  mlikiowa/napcat-docker:latest
```
* **查看登录二维码**：
  ```bash
  docker logs -f napcat
  ```
  终端会直接打出 ASCII 格式二维码，手机 QQ 扫描终端二维码即可登录！

### 启动 AI 伴侣守护进程：
```bash
chmod +x deploy_debian.sh start_agent.sh
./deploy_debian.sh
./start_agent.sh
```
或直接运行全自动一键脚本 `./setup.sh`，也可配置为 systemd 服务开机自启（参见 `qq-companion.service`）。

---

## 8. Windows 一键部署与双击运行

对于 Windows 用户，无需输入任何复杂终端指令：

1. **一键自动安装环境与 NapCat**：
   * 双击运行根目录下的 **`setup_windows.bat`**。
   * 脚本会自动建立 Python 独立虚拟环境并安装所有依赖。
   * 提示安装 NapCat 时，输入 `1` 即可通过 PowerShell 全自动下载并解压官方最新版 NapCatQQ 到 `NapCat/` 文件夹。
2. **日常启动**：
   * 在 `config.json` 中配置好 API Key 和 QQ 号后，双击 **`start_agent.bat`** 即可一键启动 AI 伴侣。
