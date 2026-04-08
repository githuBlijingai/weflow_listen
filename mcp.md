# WeFlow MCP Server

为外部 AI 提供 WeFlow HTTP API 的 MCP 工具接口，让 AI 助手（如 OpenClaw、Claude Desktop）能够访问微信本地数据。

## 功能特性

- **健康检查** - 检查 WeFlow 服务是否正常运行
- **获取会话列表** - 获取所有聊天会话（私聊/群聊）
- **获取联系人列表** - 获取所有联系人信息
- **获取消息记录** - 读取指定会话的聊天记录，支持时间范围、关键词过滤、媒体导出
- **获取群成员列表** - 获取群聊成员信息，可选附带发言统计
- **访问导出媒体** - 获取消息中导出的图片/语音/视频/表情的 HTTP 地址
- **监听新消息推送** - 通过 SSE 实时接收新消息事件
- **自动录制工单** - 当运维人员发送"记录工单"时自动保存当天聊天记录

## 安装

### 依赖

```bash
pip install fastmcp httpx uvicorn sse-starlette
```

或使用 requirements.txt：

```bash
pip install -r requirements.txt
```

## 启动方式

### SSE 模式（支持远程访问）

```bash
python server.py sse
```

服务将启动在 `http://0.0.0.0:8801/sse`

### stdio 模式（本地使用）

```bash
python server.py
```

## 配置说明

### 默认配置

| 配置项 | 默认值 | 说明 |
|-------|--------|------|
| WEFLOW_BASE_URL | http://127.0.0.1:5031 | WeFlow HTTP API 地址 |
| MCP 端口 | 8801 | MCP Server 监听端口 |
| 监听地址 | 0.0.0.0 | 允许外部访问 |

### 修改配置

在 `server.py` 中修改以下变量：

```python
WEFLOW_BASE_URL = "http://127.0.0.1:5031"  # WeFlow 服务地址
DEFAULT_TIMEOUT = 30.0                      # 请求超时时间
```

启动参数：

```python
mcp.run(transport=transport, host="0.0.0.0", port=8801)
```

## 工具列表

| 工具名 | 功能 | 必填参数 | 可选参数 |
|-------|------|---------|---------|
| `health_check` | 检查服务状态 | 无 | 无 |
| `get_sessions` | 获取会话列表 | 无 | keyword, limit |
| `get_contacts` | 获取联系人 | 无 | keyword, limit |
| `get_messages` | 获取聊天记录 | talker | limit, offset, start, end, keyword, media, image, voice, video, emoji |
| `get_new_messages` | 获取未读消息 | talker | 无 |
| `get_group_members` | 获取群成员 | chatroom_id | include_message_counts, force_refresh |
| `get_media_url` | 获取媒体URL | relative_path | 无 |
| `listen_new_messages` | 监听新消息 | 无 | timeout_seconds |

## 参数说明

### 通用参数

- `talker` - 会话ID
  - 私聊格式：`wxid_xxx`
  - 群聊格式：`xxx@chatroom`
- `keyword` - 搜索关键词
- `limit` - 返回数量，默认 100

### 时间参数

- `start` - 开始时间，支持 `YYYYMMDD` 或时间戳
- `end` - 结束时间，支持 `YYYYMMDD` 或时间戳

示例：
```
start=20260301  # 2026年3月1日
end=20260323    # 2026年3月23日 23:59:59
```

### 媒体参数

- `media=True` - 启用媒体导出
- `image` - 控制图片导出（"1"/"0"）
- `voice` - 控制语音导出（"1"/"0"）
- `video` - 控制视频导出（"1"/"0"）
- `emoji` - 控制表情导出（"1"/"0"）

## 外部客户端配置

### OpenClaw 配置

在 OpenClaw 配置文件中添加：

```json
{
  "mcpServers": {
    "weflow": {
      "url": "http://10.254.253.4:8801/sse",
      "transport": "sse"
    }
  }
}
```

### Claude Desktop 配置

**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "weflow": {
      "url": "http://10.254.253.4:8801/sse",
      "transport": "sse"
    }
  }
}
```

## 使用示例

### 1. 检查服务状态

```
用户: 帮我看看微信服务正常吗
AI: [调用 health_check]
返回: {"status": "ok"}
```

### 2. 查找会话

```
用户: 列出我的聊天会话
AI: [调用 get_sessions]
```

```
用户: 搜索包含"工作"的会话
AI: [调用 get_sessions(keyword="工作")]
```

### 3. 查找联系人

```
用户: 帮我找一下张三的联系方式
AI: [调用 get_contacts(keyword="张三")]
```

### 4. 获取聊天记录

```
用户: 查看我和张三的聊天记录
AI: 
  1. [调用 get_sessions(keyword="张三")] 获取会话ID
  2. [调用 get_messages(talker="wxid_xxx")]
```

```
用户: 查看今天的聊天记录
AI: [调用 get_messages(talker="wxid_xxx", start="20260323", end="20260323")]
```

```
用户: 搜索包含"项目"关键词的消息
AI: [调用 get_messages(talker="wxid_xxx", keyword="项目")]
```

### 5. 群聊操作

```
用户: 查看某个群的成员列表
AI:
  1. [调用 get_sessions] 获取群列表
  2. [调用 get_group_members(chatroom_id="xxx@chatroom")]
```

```
用户: 查看群成员的发言统计
AI: [调用 get_group_members(chatroom_id="xxx@chatroom", include_message_counts=True)]
```

### 6. 导出媒体文件

```
用户: 导出聊天中的图片
AI: [调用 get_messages(talker="wxid_xxx", media=True)]
返回: 包含 mediaUrl 字段的消息列表
```

### 7. 监听新消息

```
用户: 帮我监听新消息
AI: [调用 listen_new_messages(timeout_seconds=60)]
返回: 60秒内收到的新消息列表
```

## 测试

### 使用 MCP Inspector

```bash
npx @modelcontextprotocol/inspector --sse http://10.254.253.4:8801/sse
```

### 使用 curl 测试连接

```bash
curl http://10.254.253.4:8801/sse
```

### Python 客户端测试

```python
import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client

async def test_mcp():
    async with sse_client("http://10.254.253.4:8801/sse") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # 列出所有工具
            tools = await session.list_tools()
            print("可用工具:", [t.name for t in tools.tools])
            
            # 调用健康检查
            result = await session.call_tool("health_check", {})
            print("健康检查结果:", result)

asyncio.run(test_mcp())
```

## 防火墙配置

如果需要外部访问，请开放 8801 端口：

### Windows

```powershell
netsh advfirewall firewall add rule name="WeFlow MCP Server" dir=in action=allow protocol=TCP localport=8801
```

### Linux

```bash
sudo ufw allow 8801/tcp
```

## 注意事项

1. **数据来源**：所有数据均来自本地 WeFlow 实例，不涉及远程服务
2. **服务依赖**：使用前需确保 WeFlow 服务在 `127.0.0.1:5031` 正常运行
3. **媒体导出**：媒体文件需先通过 `get_messages(media=True)` 导出后才能访问
4. **监听推送**：`listen_new_messages` 需在 WeFlow 设置中开启「主动推送」功能
5. **工单录制**：自动录制功能仅对名字含"运维"的用户发送"记录工单"命令生效
6. **API 超时**：Dify API 超时 60 秒，OpenClaw API 超时 30 分钟，请耐心等待
7. **网络要求**：需要能访问 `api.dify.ai` 和 `10.254.253.99:18789`

## 自动录制工单功能

### 功能说明

系统自动监听群名含"交流"的群聊，当检测到**非运维人员**当天有发言时，标记该群需要在晚上汇总。23:59 定时拉取该群当天**全部消息**（含运维人员），发送到 Dify API 进行工单总结，再转发到 OpenClaw 执行数据库操作。

### 核心逻辑

```
群名含"交流"的消息进入
    ↓
名字含"运维"？ → 忽略（不触发）
    ↓ 否则
标记该群今日需汇总 ✓
    ↓ 23:59 定时触发
拉取该群当天全部消息 → 发送到 Dify → 转发到 OpenClaw
```

### 触发规则

| 场景 | 是否触发 |
|------|---------|
| 当天有客户/普通用户发消息 | ✅ 触发 |
| 当天只有运维人员发言 | ❌ 不触发 |
| 当天无任何消息 | ❌ 不触发 |
| 汇总时的数据范围 | **全部消息**（含运维人员发的） |

### 技术特性

- **智能触发**：仅当检测到非运维人员发言时才标记，避免无意义空跑
- **完整采集**：汇总时获取当天全部聊天记录（不遗漏运维人员的排查信息）
- **定时执行**：每天 23:59 自动执行，无需人工干预
- **流式响应**：使用 SSE 实时接收 Dify API 的流式输出
- **超时控制**：Dify API 60 秒，OpenClaw API 30 分钟
- **实时日志**：所有步骤均有详细日志输出

### 工作流程

1. **实时监听**：通过 SSE 监听 WeFlow 推送的新消息
2. **触发检测**：检测到非运维人员首次发言 → 标记该群
3. **定时汇总**：23:59 遍历所有被标记的群
4. **数据采集**：调用 `/api/v1/messages` 获取当天全部消息
5. **数据保存**：保存为 JSON 文件并提供 HTTP API 访问
6. **Dify AI 处理**：
   - 流式模式（`streaming`）发送数据
   - AI 根据聊天内容生成工单提示词
   - 超时时间：60 秒
7. **OpenClaw 执行**：
   - 发送完整 Dify 响应到 OpenClaw API
   - OpenClaw 根据提示词操作数据库写入工单
   - 超时时间：30 分钟（1800 秒）

### 示例场景

**正常工作日：**
```
09:00 运维-张三: "服务器巡检完成"
10:15 客户-李四: "系统无法登录，请帮忙看看"
11:30 运维-张三: "正在排查中"

→ 检测到"客户-李四"非运维 → 标记该群
→ 23:59: 拉取全天3条消息（含张三的）→ 发送 Dify → OpenClaw 写入工单
```

**休息日（无人报障）：**
```
全天只有运维人员日常巡检消息

→ 无非运维人员发言 → 不触发
→ 23:59: 输出 "今日无非运维人员发言，跳过汇总"
```

### 录制数据结构

```json
{
  "id": "50316395674_20260325_235900.json",
  "sessionId": "xxx@chatroom",
  "groupName": "技术交流群",
  "startTime": "2026-03-25",
  "endTime": "2026-03-25T23:59:00",
  "messageCount": 128,
  "startedBy": "系统定时",
  "endedBy": "系统定时",
  "messages": [
    {
      "localId": 123,
      "createTime": "2026-03-25T09:15:30",
      "isSend": 0,
      "senderUsername": "运维张三",
      "content": "服务器重启完成"
    },
    {
      "localId": 124,
      "createTime": "2026-03-25T10:20:15",
      "isSend": 0,
      "senderUsername": "客户李四",
      "content": "系统无法登录"
    }
  ]
}
```

### API 访问

每日汇总完成后可通过以下 API 访问：

- **查看录制列表**：`GET http://127.0.0.1:5023/recordings`
- **查看录制详情**：`GET http://127.0.0.1:5023/recordings/{id}`
- **下载录制文件**：`GET http://127.0.0.1:5023/recordings/{id}/download`

### API 配置

**Dify API**：
- URL: `https://api.dify.ai/v1/chat-messages`
- 模式: `streaming`（流式）
- 超时: 60 秒

**OpenClaw API**：
- URL: `http://10.254.253.99:18789/v1/chat/completions`
- 模型: `openclaw:main`
- 超时: 30 分钟（1800 秒）

**可配置项**（在 `weflow-sse-listener/main.py` 中修改）：

```python
# 每日汇总时间
SUMMARY_HOUR = 23
SUMMARY_MINUTE = 59

# 群名关键词（只监控群名含此关键词的群）
group_name_keyword = "交流"

# 过滤关键词（名字含此词的人不触发汇总）
if "运维" in source_name:
```

## 相关链接

- [WeFlow HTTP API 文档](./md/HTTP-API.md)
- [MCP 协议规范](https://modelcontextprotocol.io/)
- [FastMCP 文档](https://github.com/jlowin/fastmcp)

## 许可证

MIT License
