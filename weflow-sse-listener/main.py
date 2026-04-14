"""外部主函数 - 控制业务逻辑的入口

业务逻辑：
1. 监听群聊消息（群名含"交流"）
2. 只要当天有非运维人员发消息，标记该群需要汇总
3. 晚上23:59自动拉取该群当天全部消息（含运维），发送到 Dify 总结工单
4. 当天无非运维人员发言则不触发汇总
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import defaultdict
from datetime import date, datetime, time as dt_time, timedelta
from typing import Dict, Any, Set, List

import requests

from core import WeFlowSSEApp, SSEConfig, FilterConfig
from session_recorder import SessionRecorder
from api_server import run_server, init_recorder

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# 业务配置
# ---------------------------------------------------------------------------

DATA_DIR = "data/recordings"
API_HOST = "0.0.0.0"
API_PORT = 5023
WEFLOW_API_URL = "http://127.0.0.1:5031"

# Dify API 配置
DIFY_API_KEY = "app-Fq3CF98fZx1icOS3I3KFlpOO"
DIFY_API_URL = "https://api.dify.ai/v1/chat-messages"

# 定时任务配置：每天几点执行汇总（默认23:59）
SUMMARY_HOUR = 23
SUMMARY_MINUTE = 59


# ---------------------------------------------------------------------------
# 每日触发标记器
# ---------------------------------------------------------------------------

class DailyTrigger:
    """每日触发标记器 - 记录当天哪些群有非运维人员发言"""

    def __init__(self):
        # {日期: {session_id: group_name}}
        self._triggered_sessions: Dict[str, Dict[str, str]] = defaultdict(dict)
        # 去重：已检测到非运维的群
        self._detected: Set[str] = set()

    def check_and_mark(self, message: Dict[str, Any]) -> bool:
        """
        检查是否为非运维人员消息，如果是则标记该群今日需要汇总。
        返回 True 表示触发了新群的标记。
        """
        source_name = message.get("sourceName", "")
        session_id = message.get("sessionId", "")
        key = f"{date.today().isoformat()}:{session_id}"

        # 已标记过则跳过
        if key in self._detected:
            return False

        # 运维人员不触发
        if "运维" in source_name:
            return False

        # 非运维人员 → 标记该群今日需要汇总
        today_str = date.today().isoformat()
        group_name = message.get("groupName", session_id)
        self._triggered_sessions[today_str][session_id] = group_name
        self._detected.add(key)

        logger.info(f"[{today_str}] 触发标记 | 群:{group_name} | 首次非运维发言:{source_name}")
        return True

    def get_triggered_sessions(self) -> Dict[str, str]:
        """获取今天需要汇总的所有群 {session_id: group_name}"""
        today_str = date.today().isoformat()
        return dict(self._triggered_sessions.get(today_str, {}))

    def clear_today(self):
        """清空今日标记"""
        today_str = date.today().isoformat()
        if today_str in self._triggered_sessions:
            del self._triggered_sessions[today_str]
        # 清理已检测集合中过期的key
        expired = [k for k in self._detected if k.startswith(today_str)]
        for k in expired:
            self._detected.discard(k)
        logger.info("已清空今日触发标记")


# ---------------------------------------------------------------------------
# 每日汇总处理器
# ---------------------------------------------------------------------------

class DailySummaryHandler:
    """每日汇总处理器 - 晚上定时汇总并发送到 Dify"""

    def __init__(self, trigger: DailyTrigger, recorder: SessionRecorder):
        self.trigger = trigger
        self.recorder = recorder

    async def start_scheduler(self):
        """启动定时任务调度器"""
        logger.info("=" * 60)
        logger.info("⏰ 启动定时汇总调度器")
        logger.info(f"   汇总时间: 每天 {SUMMARY_HOUR}:{SUMMARY_MINUTE:02d}")
        logger.info("   触发条件: 当天有非运维人员发消息则汇总（含运维全部消息）")
        logger.info("=" * 60)

        while True:
            now = datetime.now()
            target = datetime.combine(date.today(), dt_time(SUMMARY_HOUR, SUMMARY_MINUTE))

            if now >= target:
                target += timedelta(days=1)

            wait_seconds = (target - now).total_seconds()
            logger.info(f"\n📅 下次汇总时间: {target.strftime('%Y-%m-%d %H:%M:%S')} (等待 {wait_seconds/3600:.1f} 小时)")

            await asyncio.sleep(wait_seconds)
            await self.execute_daily_summary()

    async def execute_daily_summary(self):
        """执行每日汇总"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("🌙 执行每日汇总")
        logger.info("=" * 60)

        triggered_sessions = self.trigger.get_triggered_sessions()

        if not triggered_sessions:
            logger.info("ℹ️ 今日无非运维人员发言，跳过汇总")
            return

        logger.info(f"📊 今日共 {len(triggered_sessions)} 个群触发汇总")

        for session_id, group_name in triggered_sessions.items():
            try:
                logger.info(f"\n--- 处理群: {group_name} ---")
                messages = self._fetch_all_today_messages(session_id)

                if not messages:
                    logger.warning(f"   该群今日无消息记录，跳过")
                    continue

                logger.info(f"   获取到当天全部消息: {len(messages)} 条（含运维）")

                # 保存录制数据
                recording_info = self.recorder.save_today_recording(
                    session_id=session_id,
                    group_name=group_name,
                    messages=messages,
                    started_by="系统定时",
                    ended_by="系统定时",
                    trigger_message=messages[-1]
                )

                if recording_info:
                    self._print_summary(recording_info)
                    self._send_to_dify(recording_info)

            except Exception as e:
                logger.error(f"❌ 处理群 {session_id} 失败: {e}")
                import traceback
                logger.error(traceback.format_exc())

        # 清空今日标记
        self.trigger.clear_today()
        logger.info("\n✅ 每日汇总完成")

    def _fetch_all_today_messages(self, session_id: str) -> List[Dict]:
        """从 WeFlow API 获取指定会话当天的全部消息（含运维）"""
        from datetime import date as _date

        today = _date.today()
        start_time = today.strftime("%Y%m%d")

        try:
            params = {
                "talker": session_id,
                "start": start_time,
                "limit": 10000
            }

            logger.info(f"   正在调用 WeFlow API 获取全部消息...")
            response = requests.get(
                f"{WEFLOW_API_URL}/api/v1/messages",
                params=params,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"   ❌ WeFlow API 调用失败: {response.status_code}")
                return []

            data = response.json()
            return data.get("messages", [])

        except Exception as e:
            logger.error(f"   ❌ 获取消息失败: {e}")
            return []

    def _print_summary(self, info: Dict[str, Any]) -> None:
        """打印汇总摘要"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("📊 录制摘要")
        logger.info("=" * 60)
        logger.info(f"   群名: {info.get('groupName')}")
        logger.info(f"   时间: {info.get('startTime')}")
        logger.info(f"   消息数量: {info.get('messageCount')} 条")
        logger.info("")
        logger.info("🌐 API 访问地址:")
        logger.info(f"   查看详情: http://{API_HOST}:{API_PORT}/recordings/{info.get('id')}")
        logger.info(f"   下载文件: http://{API_HOST}:{API_PORT}/recordings/{info.get('id')}/download")
        logger.info("=" * 60)

    def _send_to_dify(self, info: Dict[str, Any]) -> None:
        """发送录制信息到 Dify API（流式输出）"""
        try:
            api_url = f"http://14.18.250.241:5023/recordings/{info.get('id')}"

            headers = {
                "Authorization": f"Bearer {DIFY_API_KEY}",
                "Content-Type": "application/json"
            }

            data = {
                "inputs": {
                    "url": api_url,
                    "sendpeople": info.get('startedBy', '未知'),
                    "endpeople": info.get('endedBy', '未知'),
                    "input": "主表：work_order_main（全量工单数据）的字段名和字段说明"
                },
                "query": "请根据数据项说明，以openclaw第一人称视角给出提示词，仅操作主表，无需下一步操作。需包含：连接哪个IP及端口、哪个数据库、哪个表、填入哪些字段及对应数据。数据项：工单唯一ID：work_order_id，报障客户（由客户群的名字判断）：report_customer，报障人（问题提出的客户的微信名）：report_person，报障渠道（默认写：微信群）：report_channel，是否影响业务（根据聊天内容判断）：is_affect_business，故障发生时间（根据聊天内容判断）：fault_occur_time，故障恢复时间：fault_recover_time，故障持续时长：fault_duration 。（字数控制在800内），而且把聊天的api也给它，并且告知他api的地址是聊天记录",
                "response_mode": "streaming",
                "user": f"weflow_recorder_{info.get('id', 'unknown')}"
            }

            logger.info("📤 正在发送数据到 Dify API...")
            logger.info(f"   URL: {api_url}")
            logger.info("📥 流式响应:")

            response = requests.post(DIFY_API_URL, headers=headers, json=data, stream=True, timeout=60)

            if response.status_code != 200:
                logger.error(f"❌ Dify API 调用失败: {response.status_code}")
                logger.error(f"   错误: {response.text}")
                return

            # 流式读取响应
            full_response = []
            for line in response.iter_lines():
                line and self._parse_stream_line(line, full_response)

            # 输出完整响应
            logger.info("=" * 60)
            logger.info("✅ Dify API 流式响应完成")
            logger.info("=" * 60)
            logger.info("📋 完整回复内容:")
            logger.info("下面请直接执行（不用询问），只是注意work_order_id和记录内容是在chat_record_api \n" + "".join(full_response))  # pyright: ignore[reportUnknownArgumentType]
            logger.info("=" * 60)

            # 发送完整响应到 OpenClaw API
            full_response and self._send_to_openclaw(   "下面请直接执行，只是注意work_order_id和记录内容是在chat_record_api \n"+full_response)

        except requests.exceptions.Timeout:
            logger.error("❌ Dify API 请求超时")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Dify API 请求失败: {e}")
        except Exception as e:
            logger.error(f"❌ 发送数据到 Dify 失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _send_to_openclaw(self, full_response: list) -> None:
        """发送完整响应到 OpenClaw API"""
        try:
            OPENCLAW_API_URL = "http://10.254.253.99:18789/v1/chat/completions"
            OPENCLAW_API_KEY = "Bearer d4ea5f45401795d20acd254f920f711461786691ef009085"

            complete_content = "".join(full_response)

            headers = {
                "Authorization": OPENCLAW_API_KEY,
                "Content-Type": "application/json"
            }

            data = {
                "model": "openclaw:main",
                "messages": [{"role": "user", "content": complete_content}]
            }

            logger.info("")
            logger.info("=" * 60)
            logger.info("📤 正在发送到 OpenClaw API...")
            logger.info(f"   内容长度: {len(complete_content)} 字符")
            logger.info("=" * 60)

            response = requests.post(OPENCLAW_API_URL, headers=headers, json=data, timeout=1800)

            if response.status_code == 200:
                logger.info("✅ OpenClaw API 调用成功")
                self._log_openclaw_response(response.json())
            else:
                logger.error(f"❌ OpenClaw API 调用失败: {response.status_code}")
                logger.error(f"   错误: {response.text}")

        except requests.exceptions.Timeout:
            logger.error("❌ OpenClaw API 请求超时（30分钟）")
        except Exception as e:
            logger.error(f"❌ 发送数据到 OpenClaw 失败: {e}")

    def _log_openclaw_response(self, response_data: Dict[str, Any]) -> None:
        """记录 OpenClaw API 响应"""
        try:
            choices = response_data.get('choices', [])
            choices and logger.info("=" * 60)
            choices and logger.info("📋 OpenClaw 响应内容:")
            for choice in choices:
                content = choice.get('message', {}).get('content', '')
                content and logger.info(f"\n{content}")
            choices and logger.info("=" * 60)
        except Exception as e:
            logger.error(f"解析 OpenClaw 响应失败: {e}")

    def _parse_stream_line(self, line: bytes, full_response: list) -> None:
        """解析流式响应的单行数据"""
        try:
            line_str = line.decode('utf-8').strip()
            if line_str.startswith('data:'):
                data_str = line_str[5:].strip()
                if data_str:
                    data = json.loads(data_str)
                    event = data.get('event', '')
                    if event == 'message':
                        answer = data.get('answer', '')
                        answer and full_response.append(answer)
                        answer and print(f"   {answer}", end='', flush=True)
                    elif event == 'message_end':
                        logger.info("   [流式传输结束]")
                    elif event == 'error':
                        logger.error(f"   ❌ 流式错误: {data}")
        except (json.JSONDecodeError, Exception):
            pass


# ---------------------------------------------------------------------------
# 消息监听处理器
# ---------------------------------------------------------------------------

class MessageListenHandler:
    """消息监听处理器 - 检测非运维人员发言并标记"""

    def __init__(self, trigger: DailyTrigger):
        self.trigger = trigger

    async def __call__(self, message: Dict[str, Any]) -> None:
        """处理每条收到的消息，检测是否为非运维人员"""
        self.trigger.check_and_mark(message)


# ---------------------------------------------------------------------------
# 启动 API 服务器（独立线程）
# ---------------------------------------------------------------------------

def start_api_server() -> threading.Thread:

    """在独立线程中启动 API 服务器"""
    def run() -> None:
        logger.info(f"🌐 启动 API 服务器: http://{API_HOST}:{API_PORT}")
        init_recorder(DATA_DIR)
        run_server(host=API_HOST, port=API_PORT, data_dir=DATA_DIR)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

async def main() -> None:
    """主函数"""

    # 1. 初始化组件
    recorder = SessionRecorder(DATA_DIR)
    trigger = DailyTrigger()
    summary_handler = DailySummaryHandler(trigger, recorder)
    listen_handler = MessageListenHandler(trigger)

    logger.info(f"📁 录制数据目录: {DATA_DIR}")

    # 2. 启动 API 服务器
    _ = start_api_server()

    # 3. 配置 SSE 和过滤
    sse_config = SSEConfig(
        base_url="http://127.0.0.1:5031",
        endpoint="/api/v1/push/messages",
        access_token="f3fbf44bc1a6d06236aac68e16e90ac2",
        timeout=300.0,
        auto_reconnect=True,
        reconnect_delay=5.0,
    )

    filter_config = FilterConfig(
        require_group_chat=True,
        group_name_keyword="交流",
        content_keywords=[],
    )

    # 4. 创建应用并注册处理器
    app = WeFlowSSEApp(sse_config=sse_config, filter_config=filter_config)
    app.add_handler(listen_handler)

    # 5. 启动信息
    logger.info("🚀 WeFlow 每日汇总服务启动")
    logger.info(f"📋 监听条件: 群名含 '{filter_config.group_name_keyword}'")
    logger.info(f"📋 触发条件: 当天有非运维人员发消息 → 标记该群需要汇总")
    logger.info(f"📋 汇总内容: 当天全部消息（包含运维人员消息）")
    logger.info(f"⏰ 汇总时间: 每天 {SUMMARY_HOUR}:{SUMMARY_MINUTE:02d}")
    logger.info(f"   注: 当天无非运维发言则不触发汇总")
    logger.info(f"🌐 API 地址: http://{API_HOST}:{API_PORT}")

    # 6. 同时启动 SSE 监听和定时调度器
    try:
        await asyncio.gather(
            app.run(),
            summary_handler.start_scheduler(),
        )
    except KeyboardInterrupt:
        logger.info("收到停止信号")
        await app.stop()


# ---------------------------------------------------------------------------
# 程序入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())
