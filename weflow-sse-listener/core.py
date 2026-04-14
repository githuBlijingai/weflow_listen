"""WeFlow SSE 核心模块 - 提供 SSE 客户端和消息处理器"""

import json
import logging
import asyncio
from typing import Dict, Any, Callable, Optional, List
from dataclasses import dataclass, field

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("weflow-core")


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

@dataclass
class SSEConfig:
    """SSE 配置"""
    base_url: str = "http://127.0.0.1:5031"
    endpoint: str = "/api/v1/push/messages"
    access_token: str = ""
    timeout: float = 300.0
    auto_reconnect: bool = True
    reconnect_delay: float = 5.0


@dataclass
class FilterConfig:
    """消息过滤配置"""
    require_group_chat: bool = True
    group_name_keyword: str = "交流"
    content_keywords: List[str] = field(default_factory=lambda: ["@", "八爪鱼智能客服"])


# ---------------------------------------------------------------------------
# 消息处理器
# ---------------------------------------------------------------------------

class MessageHandler:
    """消息处理器 - 支持装饰器注册和条件筛选"""
    
    def __init__(self, filter_config: Optional[FilterConfig] = None):
        self.handlers: List[Callable] = []
        self.filter_config = filter_config or FilterConfig()
    
    def register(self, func: Callable) -> Callable:
        """注册处理函数（装饰器）"""
        self.handlers.append(func)
        return func
    
    def add_handler(self, func: Callable) -> None:
        """添加处理函数（非装饰器方式）"""
        self.handlers.append(func)
    
    def remove_handler(self, func: Callable) -> None:
        """移除处理函数"""
        self.handlers = [h for h in self.handlers if h != func]
    
    def clear_handlers(self) -> None:
        """清空所有处理函数"""
        self.handlers.clear()
    
    async def process(self, message: Dict[str, Any]) -> bool:
        """处理消息 - 返回是否满足条件"""
        # 输出所有新消息
        logger.info(f"收到新消息: {json.dumps(message, ensure_ascii=False)}")
        
        # 判断条件
        conditions = self._check_conditions(message)
        
        # 外层条件判断
        if conditions["all_matched"]:
            logger.info("✅ 满足所有条件，开始处理...")
            await self._execute_handlers(message)
            return True
        
        logger.debug(f"条件不满足: {conditions}")
        return False
    
    def _check_conditions(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """检查所有条件"""
        is_group = self._is_group_chat(message)
        has_keyword_in_name = self._has_keyword_in_group_name(message)
        has_content_keywords = self._has_content_keywords(message)
        
        return {
            "is_group_chat": is_group,
            "has_keyword_in_name": has_keyword_in_name,
            "has_content_keywords": has_content_keywords,
            "all_matched": is_group and has_keyword_in_name and has_content_keywords,
        }
    
    def _is_group_chat(self, message: Dict[str, Any]) -> bool:
        """判断是否为群聊"""
        session_id = message.get("sessionId", "")
        return "@chatroom" in session_id
    
    def _has_keyword_in_group_name(self, message: Dict[str, Any]) -> bool:
        """判断群名是否包含关键词"""
        group_name = message.get("groupName", "")
        return self.filter_config.group_name_keyword in group_name
    
    def _has_content_keywords(self, message: Dict[str, Any]) -> bool:
        """判断内容是否包含所有关键词"""
        # 如果关键词列表为空，则返回 True（不限制）
        len(self.filter_config.content_keywords) == 0 and True
        
        content = message.get("content", "")
        return all(keyword in content for keyword in self.filter_config.content_keywords)
    
    async def _execute_handlers(self, message: Dict[str, Any]) -> None:
        """执行所有处理函数（不使用 if）"""
        results = await asyncio.gather(
            *[handler(message) for handler in self.handlers],
            return_exceptions=True
        )
        
        # 使用列表推导式处理错误
        errors = [r for r in results if isinstance(r, Exception)]
        _ = [logger.error(f"处理器执行失败: {e}") for e in errors]


# ---------------------------------------------------------------------------
# SSE 客户端
# ---------------------------------------------------------------------------

class SSEClient:
    """SSE 客户端 - 连接并监听消息"""
    
    def __init__(
        self,
        handler: MessageHandler,
        config: Optional[SSEConfig] = None,
    ):
        self.handler = handler
        self.config = config or SSEConfig()
        self.client: Optional[httpx.AsyncClient] = None
        self._running = False
    
    async def connect(self) -> None:
        """建立 SSE 连接并开始监听"""
        self.client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.timeout,
        )
        
        url = f"{self.config.base_url}{self.config.endpoint}"
        logger.info(f"正在连接 SSE: {url}")
        logger.info("提示: 请确保已在 WeFlow 设置中开启「主动推送」功能")
        
        self._running = True
        while self._running:
            try:
                await self._listen()
            except Exception as e:
                logger.error(f"SSE 连接错误: {e}")
                if self.config.auto_reconnect and self._running:
                    logger.info(f"{self.config.reconnect_delay} 秒后重连...")
                    await asyncio.sleep(self.config.reconnect_delay)
                else:
                    break
    
    async def _listen(self) -> None:
        """监听 SSE 事件流"""
        params = {"access_token": self.config.access_token} if self.config.access_token else None
        async with self.client.stream("GET", self.config.endpoint, params=params) as response:
            response.raise_for_status()
            logger.info("✅ SSE 连接成功，开始监听新消息...")
            
            async for line in response.aiter_lines():
                line = line.strip()
                await self._parse_line(line)
    
    async def _parse_line(self, line: str) -> None:
        """解析 SSE 行数据"""
        # 使用字典映射处理不同类型的行
        line_handlers = {
            "event:": self._handle_event_line,
            "data:": self._handle_data_line,
        }
        
        # 使用生成器找到匹配的处理器
        handler = next(
            (h for prefix, h in line_handlers.items() if line.startswith(prefix)),
            None
        )
        
        # 短路评估执行处理器
        handler and await handler(line)
    
    async def _handle_event_line(self, line: str) -> None:
        """处理 event 行"""
        event_name = line[6:].strip()
        logger.debug(f"收到事件: {event_name}")
    
    async def _handle_data_line(self, line: str) -> None:
        """处理 data 行"""
        data_str = line[5:].strip()
        data_str and await self._process_message(data_str)
    
    async def _process_message(self, data_str: str) -> None:
        """处理消息数据"""
        try:
            message = json.loads(data_str)
            await self.handler.process(message)
        except json.JSONDecodeError as e:
            logger.warning(f"消息解析失败: {e}")
    
    async def close(self) -> None:
        """关闭连接"""
        self._running = False
        self.client and await self.client.aclose()
        logger.info("SSE 连接已关闭")
    
    def stop(self) -> None:
        """停止监听"""
        self._running = False


# ---------------------------------------------------------------------------
# 应用类 - 框架入口
# ---------------------------------------------------------------------------

class WeFlowSSEApp:
    """WeFlow SSE 应用 - 框架主入口"""
    
    def __init__(
        self,
        sse_config: Optional[SSEConfig] = None,
        filter_config: Optional[FilterConfig] = None,
    ):
        self.sse_config = sse_config or SSEConfig()
        self.filter_config = filter_config or FilterConfig()
        self.handler = MessageHandler(self.filter_config)
        self.client: Optional[SSEClient] = None
    
    def on_message(self, func: Callable) -> Callable:
        """注册消息处理函数（装饰器）"""
        return self.handler.register(func)
    
    def add_handler(self, func: Callable) -> None:
        """添加处理函数"""
        self.handler.add_handler(func)
    
    def remove_handler(self, func: Callable) -> None:
        """移除处理函数"""
        self.handler.remove_handler(func)
    
    async def run(self) -> None:
        """运行应用"""
        self.client = SSEClient(self.handler, self.sse_config)
        await self.client.connect()
    
    async def stop(self) -> None:
        """停止应用"""
        self.client and await self.client.close()
    
    def run_sync(self) -> None:
        """同步运行应用"""
        try:
            asyncio.run(self.run())
        except KeyboardInterrupt:
            logger.info("程序已停止")
