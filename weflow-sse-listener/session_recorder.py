"""会话录制器 - 管理群聊消息的录制和存储"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass, field, asdict
from pathlib import Path

logger = logging.getLogger("session-recorder")


@dataclass
class RecordingSession:
    """录制会话"""
    session_id: str
    group_name: str
    start_time: str
    end_time: Optional[str] = None
    start_message: Optional[Dict[str, Any]] = None
    end_message: Optional[Dict[str, Any]] = None
    messages: list = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sessionId": self.session_id,
            "groupName": self.group_name,
            "startTime": self.start_time,
            "endTime": self.end_time,
            "startMessage": self.start_message,
            "endMessage": self.end_message,
            "messageCount": len(self.messages),
            "messages": self.messages,
        }


class SessionRecorder:
    """会话录制器 - 管理多个群聊的录制状态"""
    
    def __init__(self, data_dir: str = "data/recordings"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 正在录制的会话: {session_id: RecordingSession}
        self.active_sessions: Dict[str, RecordingSession] = {}
        
        # 已完成的录制文件列表
        self.completed_recordings: list = []
        
        # 加载已有记录
        self._load_existing_recordings()
    
    def _load_existing_recordings(self) -> None:
        """加载已有的录制记录"""
        index_file = self.data_dir / "index.json"
        index_file.exists() and self._load_index(index_file)
    
    def _load_index(self, index_file: Path) -> None:
        """加载索引文件"""
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.completed_recordings = data.get("recordings", [])
        except Exception as e:
            logger.warning(f"加载索引失败: {e}")
    
    def _save_index(self) -> None:
        """保存索引文件"""
        index_file = self.data_dir / "index.json"
        try:
            with open(index_file, "w", encoding="utf-8") as f:
                json.dump({
                    "updatedAt": datetime.now().isoformat(),
                    "count": len(self.completed_recordings),
                    "recordings": self.completed_recordings,
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存索引失败: {e}")
    
    def is_recording(self, session_id: str) -> bool:
        """检查会话是否正在录制"""
        return session_id in self.active_sessions
    
    def start_recording(self, message: Dict[str, Any]) -> bool:
        """开始录制"""
        session_id = message.get("sessionId", "")
        
        # 使用短路评估避免 if
        session_id and logger.info(f"🎬 开始录制: {message.get('groupName')} ({session_id})")
        
        session = RecordingSession(
            session_id=session_id,
            group_name=message.get("groupName", ""),
            start_time=datetime.now().isoformat(),
            start_message=message,
        )
        
        self.active_sessions[session_id] = session
        return True
    
    def stop_recording(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """停止录制并保存，返回录制信息"""
        session_id = message.get("sessionId", "")
        
        # 会话不存在时返回 None
        session_id not in self.active_sessions and logger.warning(f"会话未在录制: {session_id}")
        session_id not in self.active_sessions and None
        
        session = self.active_sessions.pop(session_id)
        session.end_time = datetime.now().isoformat()
        session.end_message = message
        
        # 保存到文件
        filepath = self._save_session(session)
        recording_id = os.path.basename(filepath)
        
        # 更新索引
        recording_info = {
            "id": recording_id,
            "sessionId": session_id,
            "groupName": session.group_name,
            "startTime": session.start_time,
            "endTime": session.end_time,
            "messageCount": len(session.messages),
        }
        self.completed_recordings.append(recording_info)
        self._save_index()
        
        logger.info(f"✅ 录制完成: {session.group_name}, 共 {len(session.messages)} 条消息")
        
        # 返回详细录制信息
        return {
            "id": recording_id,
            "filepath": filepath,
            "groupName": session.group_name,
            "startTime": session.start_time,
            "endTime": session.end_time,
            "messageCount": len(session.messages),
            "startedBy": session.start_message.get("sourceName") if session.start_message else None,
            "endedBy": message.get("sourceName"),
        }
    
    def add_message(self, message: Dict[str, Any]) -> bool:
        """添加消息到录制中"""
        session_id = message.get("sessionId", "")
        
        # 使用短路评估
        session_id not in self.active_sessions and False
        
        # 添加消息（排除开始/结束命令）
        session = self.active_sessions[session_id]
        
        # 构建消息记录
        msg_record = {
            "time": datetime.now().isoformat(),
            "sender": message.get("sourceName"),
            "content": message.get("content"),
            "messageKey": message.get("messageKey"),
        }
        
        session.messages.append(msg_record)
        logger.debug(f"📝 录制消息 [{session.group_name}]: {msg_record['sender']}: {msg_record['content'][:30]}...")
        
        return True
    
    def _save_session(self, session: RecordingSession) -> str:
        """保存会话到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{session.session_id.replace('@chatroom', '')}_{timestamp}.json"
        filepath = self.data_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(session.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"💾 保存文件: {filepath}")
        return str(filepath)
    
    def save_today_recording(
        self,
        session_id: str,
        group_name: str,
        messages: list,
        started_by: str,
        ended_by: str,
        trigger_message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """保存当天录制的消息
        
        Args:
            session_id: 会话ID
            group_name: 群名称
            messages: 消息列表（从 WeFlow API 获取）
            started_by: 发起人（第一个发送"记录工单"的人）
            ended_by: 结束人（最后一个名字含"运维"的人）
            trigger_message: 触发录制的消息
        
        Returns:
            录制信息字典
        """
        # 获取当前时间
        now = datetime.now()
        
        # 构建消息列表
        formatted_messages = [
            {
                "time": datetime.fromtimestamp(msg.get("createTime", 0)).isoformat(),
                "sender": msg.get("senderUsername", ""),
                "content": msg.get("content", ""),
                "messageKey": msg.get("serverId", ""),
            }
            for msg in messages
        ]
        
        # 创建会话对象
        session = RecordingSession(
            session_id=session_id,
            group_name=group_name,
            start_time=now.strftime("%Y-%m-%d"),
            start_message=trigger_message,
            messages=formatted_messages,
        )
        session.end_time = now.isoformat()
        
        # 保存到文件
        filepath = self._save_session(session)
        recording_id = os.path.basename(filepath)
        
        # 更新索引
        recording_info = {
            "id": recording_id,
            "sessionId": session_id,
            "groupName": group_name,
            "startTime": session.start_time,
            "endTime": session.end_time,
            "messageCount": len(messages),
        }
        self.completed_recordings.append(recording_info)
        self._save_index()
        
        logger.info(f"✅ 录制完成: {group_name}, 共 {len(messages)} 条消息")
        
        # 返回详细录制信息
        return {
            "id": recording_id,
            "filepath": filepath,
            "groupName": group_name,
            "startTime": session.start_time,
            "endTime": session.end_time,
            "messageCount": len(messages),
            "startedBy": started_by,
            "endedBy": ended_by,
        }
    
    def get_recording_list(self) -> list:
        """获取所有录制记录"""
        return self.completed_recordings
    
    def get_recording(self, recording_id: str) -> Optional[Dict[str, Any]]:
        """获取指定录制记录"""
        filepath = self.data_dir / recording_id
        
        filepath.exists() or None
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取录制失败: {e}")
            return None
    
    def get_active_sessions(self) -> list:
        """获取正在录制的会话列表"""
        return [
            {
                "sessionId": sid,
                "groupName": session.group_name,
                "startTime": session.start_time,
                "messageCount": len(session.messages),
            }
            for sid, session in self.active_sessions.items()
        ]
