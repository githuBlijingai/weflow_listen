# WeFlow SSE 消息监听器

监听 WeFlow 的 SSE 推送，实时接收新消息并按条件触发每日工单汇总。

**特点**：像后端框架一样使用，支持外部 main 函数控制业务逻辑。

---

## 功能特性

- ✅ 实时监听新消息推送（SSE 长连接）
- ✅ 自动判断是否为群聊消息
- ✅ 筛选指定群聊（群名含"交流"）
- ✅ **每日自动汇总** - 检测到非运维人员发言后，晚上定时拉取当天全部消息发送到 Dify
- ✅ **智能触发机制** - 当天无非运维人员发言则不触发，避免无意义的空跑
- ✅ **完整数据采集** - 汇总时包含当天全部消息（含运维人员），确保信息完整
- ✅ **框架化设计** - 可在外部 main 函数中灵活配置
- ✅ 提供 HTTP API 访问录制的聊天记录

---

## 前置要求

1. **WeFlow 配置**
   - 在 WeFlow 设置中启用 `API 服务`
   - 启用 `主动推送` 功能
   - 默认端口：`5031`

2. **Python 环境**
   - Python 3.10+

---

## 安装

```bash
cd weflow-sse-listener
pip install -r requirements.txt
```

---

## 快速开始

### 启动服务

```bash
python main.py
```

启动后会看到：

```
🚀 WeFlow 每日汇总服务启动
📋 监听条件: 群名含 '交流'
📋 触发条件: 当天有非运维人员发消息 → 标记该群需要汇总
📋 汇总内容: 当天全部消息（包含运维人员消息）
⏰ 汇总时间: 每天 23:59
   注: 当天无非运维发言则不触发汇总
🌐 API 地址: http://0.0.0.0:5023
```

---

## 核心逻辑：每日自动汇总

### 工作流程

```
群名含"交流"的消息进入
        ↓
  是否为"运维"人员？
    ├─ 是 → 忽略（不触发标记）
    └─ 否 → 标记该群今日需汇总 ✓
        ↓
  晚上 23:59 定时任务启动
        ↓
  遍历今日所有被标记的群
        ↓
  调用 WeFlow API 获取该群当天全部消息（含运维）
        ↓
  保存为录制文件
        ↓
  发送到 Dify API 进行工单总结
        ↓
  发送到 OpenClaw API 执行操作
```

### 关键规则

| 场景 | 行为 |
|------|------|
| 当天有非运维人员发消息 | ✅ 标记该群，23:59 汇总 |
| 当天只有运维人员发消息 | ❌ 不标记，不汇总 |
| 当天没有任何消息 | ❌ 不汇总 |
| 汇总时获取的消息 | **全部消息**（含运维人员发的） |

### 示例场景

**场景一：正常触发**

```
09:00 运维-张三: "服务器重启完成"
10:15 客户-李四: "系统无法登录"
11:30 运维-张三: "正在排查"

→ 检测到"客户-李四"非运维 → 标记该群
→ 23:59 自动汇总，获取当天全部3条消息（含张三的）发送到 Dify
```

**场景二：不触发**

```
全天只有运维人员发言：
09:00 运维-张三: "服务器重启"
14:00 运维-王五: "巡检完毕"

→ 无非运维人员 → 不标记
→ 23:59 跳过："今日无非运维人员发言，跳过汇总"
```

---

## 配置说明

### 业务配置

在 `main.py` 中修改：

```python
# 群名关键词（只监听群名含此关键词的群）
group_name_keyword = "交流"      # FilterConfig 中配置

# 每日汇总时间（24小时制）
SUMMARY_HOUR = 23                 # 时
SUMMARY_MINUTE = 59               # 分

# 过滤关键词（名字含此词的人不触发汇总标记）
if "运维" in source_name:         # DailyTrigger.check_and_mark() 中配置

# WeFlow API 地址
WEFLOW_API_URL = "http://127.0.0.1:5031"

# Dify API 配置
DIFY_API_KEY = "app-xxx"
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"

# OpenClaw API 配置
OPENCLAW_API_URL = "http://10.254.253.99:18789/v1/chat/completions"
```

### API 接口

录制完成后，可通过 HTTP API 访问：

| 接口 | 方法 | 说明 |
|------|------|------|
| `/recordings` | GET | 获取所有录制记录列表 |
| `/recordings/{id}` | GET | 获取指定录制详情 |
| `/recordings/{id}/download` | GET | 下载录制 JSON 文件 |
| `/active` | GET | 查看正在录制的会话 |

**示例**：

```bash
# 查看所有录制
curl http://127.0.0.1:5023/recordings

# 查看指定录制
curl http://127.0.0.1:5023/recordings/xxx_20260325_114530.json

# 下载文件
curl -O http://127.0.0.1:5023/recordings/xxx_20260325_114530.json/download
```

---

## 核心功能

### 消息过滤

| 条件 | 说明 | 可配置 |
|------|------|--------|
| 群聊消息 | 只监听 sessionId 包含 `@chatroom` 的消息 | ✅ |
| 群名关键词 | 群名必须包含指定关键词（默认"交流"） | ✅ |
| 触发条件 | 当天有非运维人员发消息才触发汇总 | ✅ |
| 汇总范围 | 被触发后获取当天**全部**消息（含运维） | - |

### 数据结构

#### 录制文件格式

每日汇总生成的 JSON 文件：

```json
{
  "id": "50316395674_20260325_235900.json",
  "sessionId": "50316395674@chatroom",
  "groupName": "技术交流群",
  "startTime": "2026-03-25T00:00:00",
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

#### 索引文件格式

`data/recordings/index.json`：

```json
{
  "updatedAt": "2026-03-25T23:59:00",
  "count": 3,
  "recordings": [
    {
      "id": "50316395674_20260325_235900.json",
      "sessionId": "50316395674@chatroom",
      "groupName": "技术交流群",
      "startTime": "2026-03-25",
      "messageCount": 128
    }
  ]
}
```

---

## 汇总输出示例

每天 23:59 执行汇总时的日志输出：

```
============================================================
🌙 执行每日汇总
============================================================
📊 今日共 2 个群触发汇总

--- 处理群: 技术交流群 ---
   正在调用 WeFlow API 获取全部消息...
   获取到当天全部消息: 128 条（含运维）

============================================================
📊 录制摘要
============================================================
   群名: 技术交流群
   时间: 2026-03-25
   消息数量: 128 条

🌐 API 访问地址:
   查看详情: http://127.0.0.1:5023/recordings/xxx_20260325_235900.json
   下载文件: http://127.0.0.1:5023/recordings/xxx_20260325_235900.json/download
============================================================

📤 正在发送数据到 Dify API...
📥 流式响应:
   已根据聊天内容生成工单提示词...
   [流式传输结束]

✅ Dify API 流式响应完成
📋 完整回复内容: ...
============================================================

📤 正在发送到 OpenClaw API...
✅ OpenClaw API 调用成功
============================================================

✅ 每日汇总完成
```

---

## 自动发送到 Dify API

每日汇总时，系统自动将当天完整消息发送给 Dify 进行工单总结。

### 发送字段

| 字段 | 说明 | 示例 |
|------|------|------|
| `url` | 查看录制详情的 API 地址 | `http://14.18.250.241:5023/recordings/xxx.json` |
| `sendpeople` | 标记（固定为"系统定时"） | `系统定时` |
| `endpeople` | 标记（固定为"系统定时"） | `系统定时` |
| `input` | 主表结构和含义说明 | 固定内容 |
| `query` | 工单提取指令 | 包含字段映射规则 |

### 处理流程

```
1. 保存当天全部消息 → 生成 JSON 录制文件
2. 发送到 Dify API（流式模式）
   ├── 实时接收 AI 生成的工单提示词
   └── 拼接完整响应内容
3. 将 Dify 输出发送到 OpenClaw API 执行
   └── OpenClaw 根据提示操作数据库写入工单
```

### Dify / OpenClaw 配置

在 `main.py` 中修改：

```python
# Dify API
DIFY_API_KEY = "app-xxx"
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"

# OpenClaw API
OPENCLAW_API_URL = "http://10.254.253.99:18789/v1/chat/completions"
OPENCLAW_API_KEY = "Bearer xxx"
```

---

## 项目结构

```
weflow-sse-listener/
├── core.py                  # 核心框架（SSE客户端 + 消息处理器）
├── session_recorder.py      # 会话录制器
├── api_server.py            # API 服务器（FastAPI）
├── builtin_handlers.py      # 内置处理器
├── main.py                  # 主程序（每日汇总业务逻辑）
│   ├── DailyTrigger         # 触发标记器（检测非运维发言）
│   ├── MessageListenHandler  # 消息监听处理器
│   └── DailySummaryHandler   # 每日汇总处理器（定时+Dify）
├── listener.py              # 独立运行入口
├── data/
│   └── recordings/          # 录制数据存储
│       ├── index.json       # 录制索引
│       └── xxx_20260325_235900.json  # 每日汇总文件
├── requirements.txt         # 依赖
└── README.md                # 说明文档
```

---

## 核心组件说明

### DailyTrigger（触发标记器）

负责检测非运维人员的发言，标记当天需要汇总的群。

```python
trigger = DailyTrigger()

# 检查消息并标记（由 MessageListenHandler 调用）
trigger.check_and_mark(message)

# 获取今天需要汇总的群 {session_id: group_name}
trigger.get_triggered_sessions()

# 清空今日标记（汇总完成后调用）
trigger.clear_today()
```

**规则**：
- 名字含"运维"的人 → 不触发标记
- 首次检测到非运维人员 → 标记该群，后续同群消息不再重复标记
- 按天隔离：每天的标记独立计算

### MessageListenHandler（消息监听处理器）

SSE 消息的入口处理器，每条消息经过过滤后进入。

```python
listen_handler = MessageListenHandler(trigger)
app.add_handler(listen_handler)
```

### DailySummaryHandler（每日汇总处理器）

定时调度 + 数据采集 + Dify/OpenClaw 发送。

```python
summary_handler = DailySummaryHandler(trigger, recorder)

# 启动定时调度器（在 asyncio.gather 中运行）
await summary_handler.start_scheduler()

# 手动执行汇总（测试用）
await summary_handler.execute_daily_summary()
```

---

## 高级用法

### 同时监控多个群聊

系统天然支持多群并行：

```
技术交流群: 客户A发言 → 触发标记 ✓
项目交流群: 客户B发言 → 触发标记 ✓

23:59 → 分别拉取两个群的全部消息 → 各自发送到 Dify
```

### 修改触发关键词

修改 `main.py` 中 `DailyTrigger.check_and_mark()` 的判断条件：

```python
# 当前：排除"运维"两个字的人
if "运维" in source_name:
    return False

# 可改为其他规则，如：
if source_name in ["运维张三", "运维李四"]:
    return False
```

### 修改汇总时间

```python
SUMMARY_HOUR = 23    # 改为其他时间
SUMMARY_MINUTE = 59
```

### 手动触发汇总（用于测试）

可以在代码中直接调用：

```python
await summary_handler.execute_daily_summary()
```

---

## 常见问题

### Q: 今天有消息但没触发汇总？

确认：
1. 群名是否包含"交流"关键词
2. 当天是否有**非运维人员**发过消息
3. 如果只有运维人员发言则不会触发（这是正常行为）

### Q: 连接失败？

确认：
1. WeFlow 是否已启动
2. API 服务是否已开启
3. 主动推送是否已开启
4. 端口是否正确（默认 5031）

### Q: 收不到消息？

确认：
1. WeFlow 是否有新消息到达
2. 群名是否包含"交流"
3. 是否有其他客户端已连接 SSE

### Q: Dify API 报错？

检查：
1. `DIFY_API_KEY` 是否正确
2. 网络是否能访问 `api.dify.ai`
3. 查看 Dify 控制台是否有配额限制

### Q: 如何跳过某一天不发送？

当天不启动服务即可。已标记的记录只保存在内存中，重启后会清空。

---

## 扩展建议

- 添加多个触发关键词（如同时监听"运维""交流"）
- 支持自定义 Dify 提示词模板
- 添加汇总结果通知（微信/邮件/钉钉）
- 消息持久化到数据库防止重启丢失
- 支持手动触发汇总的 HTTP 接口
- 添加汇总历史统计面板

---

## 许可

MIT
