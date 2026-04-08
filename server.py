"""WeFlow MCP Server - 为外部 AI 提供 WeFlow HTTP API 的 MCP 工具接口"""

import json
import logging
from typing import Optional

import httpx
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("weflow-mcp")

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
WEFLOW_BASE_URL = "http://127.0.0.1:5031"
DEFAULT_TIMEOUT = 30.0

mcp = FastMCP(
    name="WeFlow",
    instructions=(
        "WeFlow 是一个微信数据本地管理工具。本 MCP Server 提供以下能力：\n"
        "1. 健康检查 - 检查 WeFlow 服务是否正常运行\n"
        "2. 获取会话列表 - 获取所有聊天会话（私聊/群聊）\n"
        "3. 获取联系人列表 - 获取所有联系人信息\n"
        "4. 获取消息记录 - 读取指定会话的聊天记录，支持时间范围、关键词过滤、媒体导出\n"
        "5. 获取群成员列表 - 获取群聊成员信息，可选附带发言统计\n"
        "6. 访问导出媒体 - 获取消息中导出的图片/语音/视频/表情的 HTTP 地址\n"
        "7. 监听新消息推送 - 通过 SSE 实时接收新消息事件\n\n"
        "所有数据均来自本地 WeFlow 实例，不涉及远程服务。"
    ),
)

# ---------------------------------------------------------------------------
# 内部 HTTP 客户端
# ---------------------------------------------------------------------------
_http_client: Optional[httpx.AsyncClient] = None


async def get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            base_url=WEFLOW_BASE_URL,
            timeout=DEFAULT_TIMEOUT,
        )
    return _http_client


# ============================================================================
# MCP Tools — 覆盖全部 WeFlow HTTP API
# ============================================================================

@mcp.tool()
async def health_check() -> str:
    """检查 WeFlow 服务是否正常运行。

    Returns:
        服务状态信息，"ok" 表示正常。
    """
    client = await get_client()
    try:
        resp = await client.get("/health")
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "detail": str(e)}, ensure_ascii=False)


@mcp.tool()
async def get_sessions(keyword: Optional[str] = None, limit: int = 100) -> str:
    """获取会话列表（私聊、群聊）。

    Args:
        keyword: 可选，匹配会话的 username 或 displayName。
        limit: 返回条数，默认 100。

    Returns:
        会话列表 JSON，包含 username、displayName、type、lastTimestamp、unreadCount 等字段。
    """
    client = await get_client()
    params: dict = {"limit": limit}
    if keyword:
        params["keyword"] = keyword
    try:
        resp = await client.get("/api/v1/sessions", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "detail": str(e)}, ensure_ascii=False)


@mcp.tool()
async def get_contacts(keyword: Optional[str] = None, limit: int = 100) -> str:
    """获取联系人列表。

    Args:
        keyword: 可选，匹配 username、nickname、remark、displayName。
        limit: 返回条数，默认 100。

    Returns:
        联系人列表 JSON，包含 username、displayName、remark、nickname、alias、avatarUrl、type 等字段。
    """
    client = await get_client()
    params: dict = {"limit": limit}
    if keyword:
        params["keyword"] = keyword
    try:
        resp = await client.get("/api/v1/contacts", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "detail": str(e)}, ensure_ascii=False)


@mcp.tool()
async def get_messages(
    talker: str,
    limit: int = 100,
    offset: int = 0,
    start: Optional[str] = None,
    end: Optional[str] = None,
    keyword: Optional[str] = None,
    chatlab: bool = False,
    format: Optional[str] = None,
    media: bool = False,
    image: Optional[str] = None,
    voice: Optional[str] = None,
    video: Optional[str] = None,
    emoji: Optional[str] = None,
) -> str:
    """获取指定会话的消息记录。

    Args:
        talker: 会话 ID（必填）。私聊传对方 wxid，群聊传 xxx@chatroom。
        limit: 返回条数，默认 100，范围 1~10000。
        offset: 分页偏移，默认 0。
        start: 开始时间，支持 YYYYMMDD 或时间戳。
        end: 结束时间，支持 YYYYMMDD 或时间戳。
        keyword: 基于消息显示文本过滤。
        chatlab: 设为 True 时输出 ChatLab 格式。
        format: 指定输出格式，"json" 或 "chatlab"。
        media: 设为 True 时导出媒体文件并返回媒体地址。
        image: 在 media=True 时控制图片导出（"1"/"0"）。
        voice: 在 media=True 时控制语音导出（"1"/"0"）。
        video: 在 media=True 时控制视频导出（"1"/"0"）。
        emoji: 在 media=True 时控制表情导出（"1"/"0"）。

    Returns:
        消息列表 JSON。每条消息包含 localId、createTime、content、mediaUrl 等字段。
    """
    client = await get_client()
    params: dict = {"talker": talker, "limit": limit, "offset": offset}
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    if keyword:
        params["keyword"] = keyword
    if chatlab:
        params["chatlab"] = "1"
    if format:
        params["format"] = format
    if media:
        params["media"] = "1"
    if image is not None:
        params["image"] = image
    if voice is not None:
        params["voice"] = voice
    if video is not None:
        params["video"] = video
    if emoji is not None:
        params["emoji"] = emoji
    try:
        resp = await client.get("/api/v1/messages", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "detail": str(e)}, ensure_ascii=False)


@mcp.tool()
async def get_group_members(
    chatroom_id: str,
    include_message_counts: bool = False,
    force_refresh: bool = False,
) -> str:
    """获取群成员列表。

    Args:
        chatroom_id: 群 ID，即 xxx@chatroom。
        include_message_counts: 设为 True 时附带每个成员的发言数统计。
        force_refresh: 设为 True 时跳过内存缓存强制刷新。

    Returns:
        群成员列表 JSON，包含 wxid、displayName、nickname、remark、alias、groupNickname、
        avatarUrl、isOwner、isFriend、messageCount 等字段。
    """
    client = await get_client()
    params: dict = {"chatroomId": chatroom_id}
    if include_message_counts:
        params["includeMessageCounts"] = "1"
    if force_refresh:
        params["forceRefresh"] = "1"
    try:
        resp = await client.get("/api/v1/group-members", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "detail": str(e)}, ensure_ascii=False)


@mcp.tool()
async def get_new_messages(talker: str) -> str:
    """获取指定会话的最新未读消息。

    Args:
        talker: 会话 ID（必填）。私聊传对方 wxid，群聊传 xxx@chatroom。

    Returns:
        最新消息列表 JSON，结构同 get_messages。
    """
    client = await get_client()
    params: dict = {"talker": talker}
    try:
        resp = await client.get("/api/v1/messages/new", params=params)
        resp.raise_for_status()
        return json.dumps(resp.json(), ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "detail": str(e)}, ensure_ascii=False)


@mcp.tool()
async def get_media_url(relative_path: str) -> str:
    """构建导出媒体的访问 URL。

    注意：此工具仅返回媒体文件的 HTTP 访问地址。在调用前，需要先通过 get_messages(media=True) 导出媒体，
    否则访问该地址会返回 404。

    Args:
        relative_path: 媒体相对路径，例如 "xxx@chatroom/images/abc123.jpg"。
                       通常从 get_messages 返回的 mediaUrl 字段中获取。

    Returns:
        完整的媒体访问 URL 和本地路径信息。
    """
    url = f"{WEFLOW_BASE_URL}/api/v1/media/{relative_path}"
    return json.dumps(
        {
            "mediaUrl": url,
            "relativePath": relative_path,
            "note": "确保已通过 get_messages(media=True) 导出对应媒体后才能访问此地址",
        },
        ensure_ascii=False,
    )


@mcp.tool()
async def listen_new_messages(timeout_seconds: int = 60) -> str:
    """监听新消息推送（SSE）。连接 WeFlow 的 SSE 端点，在指定超时时间内收集所有新消息事件。

    注意：需要在 WeFlow 设置中同时开启「主动推送」功能。

    Args:
        timeout_seconds: 监听超时时间（秒），默认 60 秒。超时后返回在此期间收到的所有消息。

    Returns:
        收到的新消息事件列表 JSON。每条包含 event、sessionId、messageKey、avatarUrl、
        sourceName、groupName、content 等字段。
    """
    client = await get_client()
    events = []
    try:
        async with client.stream(
            "GET",
            "/api/v1/push/messages",
            timeout=timeout_seconds,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    if data_str:
                        try:
                            events.append(json.loads(data_str))
                        except json.JSONDecodeError:
                            pass
    except httpx.TimeoutException:
        pass
    except Exception as e:
        return json.dumps(
            {
                "success": False,
                "detail": str(e),
                "hint": "请确认已在 WeFlow 设置中开启「主动推送」",
            },
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "success": True,
            "count": len(events),
            "events": events,
        },
        ensure_ascii=False,
    )


# ============================================================================
# MCP Resources — 提供结构化的上下文信息
# ============================================================================

@mcp.resource("weflow://api-info")
async def api_info() -> str:
    """WeFlow MCP Server 的 API 能力概览"""
    return json.dumps(
        {
            "name": "WeFlow MCP Server",
            "version": "1.0.0",
            "base_url": WEFLOW_BASE_URL,
            "tools": [
                {
                    "name": "health_check",
                    "description": "检查 WeFlow 服务健康状态",
                    "weflow_endpoint": "GET /health",
                },
                {
                    "name": "get_sessions",
                    "description": "获取会话列表",
                    "weflow_endpoint": "GET /api/v1/sessions",
                },
                {
                    "name": "get_contacts",
                    "description": "获取联系人列表",
                    "weflow_endpoint": "GET /api/v1/contacts",
                },
                {
                    "name": "get_messages",
                    "description": "获取指定会话的消息记录",
                    "weflow_endpoint": "GET /api/v1/messages",
                },
                {
                    "name": "get_new_messages",
                    "description": "获取指定会话的最新未读消息",
                    "weflow_endpoint": "GET /api/v1/messages/new",
                },
                {
                    "name": "get_group_members",
                    "description": "获取群成员列表",
                    "weflow_endpoint": "GET /api/v1/group-members",
                },
                {
                    "name": "get_media_url",
                    "description": "构建导出媒体的访问 URL",
                    "weflow_endpoint": "GET /api/v1/media/*",
                },
                {
                    "name": "listen_new_messages",
                    "description": "通过 SSE 监听新消息推送",
                    "weflow_endpoint": "GET /api/v1/push/messages",
                },
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


# ============================================================================
# 启动
# ============================================================================
if __name__ == "__main__":
    import sys

    transport_arg = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport_arg == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport=transport_arg, host="0.0.0.0", port=8801)  # type: ignore[arg-type]
