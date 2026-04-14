"""WeFlow SSE 消息监听器 - 独立运行版本

直接运行此文件启动监听器，使用默认配置和处理器。
"""

from __future__ import annotations

import asyncio
from core import WeFlowSSEApp, SSEConfig  # type: ignore
from builtin_handlers import log_message, extract_info  # type: ignore


async def main() -> None:
    """独立运行主函数"""
    sse_config = SSEConfig(
        access_token="f3fbf44bc1a6d06236aac68e16e90ac2",
    )
    app = WeFlowSSEApp(sse_config=sse_config)
    
    # 注册内置处理器
    app.add_handler(log_message)
    app.add_handler(extract_info)
    
    # 启动
    await app.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
