"""API 服务器 - 提供 HTTP 访问录制的聊天记录"""

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from session_recorder import SessionRecorder

logger = logging.getLogger("api-server")

# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(
    title="WeFlow 录制记录 API",
    description="访问录制的群聊消息记录",
    version="1.0.0",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局录制器实例
recorder: Optional[SessionRecorder] = None


def init_recorder(data_dir: str = "data/recordings") -> SessionRecorder:
    """初始化录制器"""
    global recorder
    recorder = SessionRecorder(data_dir)
    return recorder


# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    """根路径"""
    return {
        "name": "WeFlow 录制记录 API",
        "version": "1.0.0",
        "endpoints": {
            "GET /recordings": "获取所有录制记录列表",
            "GET /recordings/{recording_id}": "获取指定录制记录详情",
            "GET /recordings/{recording_id}/download": "下载录制记录 JSON 文件",
            "GET /active": "获取正在录制的会话",
            "GET /health": "健康检查",
        }
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


@app.get("/recordings")
async def list_recordings():
    """获取所有录制记录列表"""
    recordings = recorder.get_recording_list()
    return {
        "success": True,
        "count": len(recordings),
        "recordings": recordings,
    }


@app.get("/recordings/{recording_id}")
async def get_recording(recording_id: str):
    """获取指定录制记录详情"""
    recording = recorder.get_recording(recording_id)
    
    # 使用短路评估
    recording or HTTPException(status_code=404, detail="录制记录不存在")
    
    return {
        "success": True,
        "recording": recording,
    }


@app.get("/recordings/{recording_id}/download")
async def download_recording(recording_id: str):
    """下载录制记录 JSON 文件"""
    filepath = Path(recorder.data_dir) / recording_id
    
    # 使用短路评估
    filepath.exists() or HTTPException(status_code=404, detail="文件不存在")
    
    return FileResponse(
        path=filepath,
        media_type="application/json",
        filename=recording_id,
    )


@app.get("/active")
async def list_active_sessions():
    """获取正在录制的会话"""
    sessions = recorder.get_active_sessions()
    return {
        "success": True,
        "count": len(sessions),
        "sessions": sessions,
    }


# ---------------------------------------------------------------------------
# 启动服务器
# ---------------------------------------------------------------------------

def run_server(host: str = "127.0.0.1", port: int = 5032, data_dir: str = "data/recordings"):
    """运行 API 服务器"""
    init_recorder(data_dir)
    
    logger.info(f"🚀 API 服务器启动: http://{host}:{port}")
    logger.info(f"📁 数据目录: {data_dir}")
    
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )


# ---------------------------------------------------------------------------
# 独立运行
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5032
    
    run_server(host=host, port=port)
