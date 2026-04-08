"""内置处理器示例 - 提供常用的消息处理功能"""

import json
import logging
from typing import Dict, Any

logger = logging.getLogger("weflow-handlers")


def log_message(message: Dict[str, Any]) -> None:
    """记录消息详情"""
    logger.info(f"📝 处理消息 - 群: {message.get('groupName')}, 发送者: {message.get('sourceName')}")
    logger.info(f"   内容: {message.get('content')}")


def extract_info(message: Dict[str, Any]) -> None:
    """提取消息关键信息"""
    info = {
        "sessionId": message.get("sessionId"),
        "messageKey": message.get("messageKey"),
        "sender": message.get("sourceName"),
        "group": message.get("groupName"),
        "content": message.get("content"),
    }
    logger.info(f"🔍 提取信息: {json.dumps(info, ensure_ascii=False)}")


def save_to_file(filepath: str = "messages.json"):
    """保存消息到文件（返回处理器函数）"""
    async def handler(message: Dict[str, Any]) -> None:
        try:
            # 读取现有数据
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except FileNotFoundError:
                data = []
            
            # 添加新消息
            data.append(message)
            
            # 写入文件
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"💾 消息已保存到 {filepath}")
        except Exception as e:
            logger.error(f"保存失败: {e}")
    
    return handler


# 异步处理器示例
async def log_message_async(message: Dict[str, Any]) -> None:
    """异步记录消息详情"""
    log_message(message)


async def extract_info_async(message: Dict[str, Any]) -> None:
    """异步提取消息关键信息"""
    extract_info(message)
