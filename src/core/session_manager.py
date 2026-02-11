"""
会话管理器
负责管理用户会话状态和消息历史
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from PySide6.QtCore import QObject, Signal


class ChatSession:
    """聊天会话"""

    def __init__(self, session_id: str, user_name: str = ""):
        self.session_id = session_id
        self.user_name = user_name
        self.messages: List[Dict] = []
        self.created_at = datetime.now()
        self.last_activity = datetime.now()
        self.reply_count = 0
        self.last_reply_time: Optional[datetime] = None
        self.context: Dict = {
            "address_prompt_count": 0,
            "last_target_store": "",
            "last_address_query_at": None
        }

    def add_message(self, text: str, is_user: bool = True):
        """添加消息"""
        self.messages.append({
            "text": text,
            "is_user": is_user,
            "timestamp": datetime.now().isoformat()
        })
        self.last_activity = datetime.now()

    def get_recent_messages(self, count: int = 5) -> List[Dict]:
        """获取最近的消息"""
        return self.messages[-count:] if self.messages else []

    def get_conversation_history(self, max_turns: int = 3) -> List[Dict]:
        """获取对话历史（用于LLM上下文）"""
        history = []
        recent = self.messages[-max_turns * 2:]  # 最近 N 轮对话
        for msg in recent:
            role = "user" if msg["is_user"] else "assistant"
            history.append({
                "role": role,
                "content": msg["text"]
            })
        return history

    def record_reply(self):
        """记录回复"""
        self.reply_count += 1
        self.last_reply_time = datetime.now()

    def get_context(self, key: str, default=None):
        return self.context.get(key, default)

    def set_context(self, key: str, value):
        self.context[key] = value

    def should_reply(self, min_interval_seconds: int = 60) -> bool:
        """检查是否应该回复（防止过于频繁）"""
        if not self.last_reply_time:
            return True
        elapsed = (datetime.now() - self.last_reply_time).total_seconds()
        return elapsed >= min_interval_seconds

    def is_expired(self, timeout_hours: int = 24) -> bool:
        """检查会话是否过期"""
        elapsed = datetime.now() - self.last_activity
        return elapsed > timedelta(hours=timeout_hours)


class SessionManager(QObject):
    """会话管理器"""

    session_created = Signal(str)      # 新会话创建 (session_id)
    session_updated = Signal(str)      # 会话更新 (session_id)
    session_expired = Signal(str)      # 会话过期 (session_id)

    def __init__(self, max_sessions: int = 100):
        super().__init__()
        self.max_sessions = max_sessions
        self._sessions: Dict[str, ChatSession] = {}
        self._user_name_to_session: Dict[str, str] = {}

    def get_or_create_session(self, session_id: str, user_name: str = "") -> ChatSession:
        """获取或创建会话"""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            if user_name and not session.user_name:
                session.user_name = user_name
                self._user_name_to_session[user_name] = session_id
            return session

        # 创建新会话
        session = ChatSession(session_id, user_name)
        self._sessions[session_id] = session
        if user_name:
            self._user_name_to_session[user_name] = session_id

        # 检查会话数量限制
        if len(self._sessions) > self.max_sessions:
            self._cleanup_old_sessions()

        self.session_created.emit(session_id)
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """获取会话"""
        return self._sessions.get(session_id)

    def get_session_by_user_name(self, user_name: str) -> Optional[ChatSession]:
        """根据用户名获取会话"""
        session_id = self._user_name_to_session.get(user_name)
        if session_id:
            return self._sessions.get(session_id)
        return None

    def add_message(self, session_id: str, text: str, is_user: bool = True,
                    user_name: str = ""):
        """添加消息到会话"""
        session = self.get_or_create_session(session_id, user_name)
        session.add_message(text, is_user)
        self.session_updated.emit(session_id)

    def record_reply(self, session_id: str):
        """记录会话的回复"""
        session = self._sessions.get(session_id)
        if session:
            session.record_reply()
            self.session_updated.emit(session_id)

    def should_reply(self, session_id: str, min_interval: int = 60) -> bool:
        """检查是否应该回复"""
        session = self._sessions.get(session_id)
        if not session:
            return True
        return session.should_reply(min_interval)

    def cleanup_expired_sessions(self, timeout_hours: int = 24):
        """清理过期会话"""
        expired = []
        for session_id, session in self._sessions.items():
            if session.is_expired(timeout_hours):
                expired.append(session_id)

        for session_id in expired:
            self._remove_session(session_id)
            self.session_expired.emit(session_id)

    def _cleanup_old_sessions(self, keep_count: int = 80):
        """清理旧会话（当数量超过限制时）"""
        if len(self._sessions) <= keep_count:
            return

        # 按最后活动时间排序
        sorted_sessions = sorted(
            self._sessions.items(),
            key=lambda x: x[1].last_activity
        )

        # 删除最早的会话
        to_remove = len(self._sessions) - keep_count
        for i in range(to_remove):
            session_id = sorted_sessions[i][0]
            self._remove_session(session_id)

    def _remove_session(self, session_id: str):
        """移除会话"""
        session = self._sessions.pop(session_id, None)
        if session and session.user_name:
            self._user_name_to_session.pop(session.user_name, None)

    def get_all_sessions(self) -> List[ChatSession]:
        """获取所有会话"""
        return list(self._sessions.values())

    def get_active_sessions(self, minutes: int = 30) -> List[ChatSession]:
        """获取活跃会话（最近有活动的）"""
        cutoff = datetime.now() - timedelta(minutes=minutes)
        return [
            session for session in self._sessions.values()
            if session.last_activity > cutoff
        ]

    def get_stats(self) -> Dict:
        """获取会话统计信息"""
        total = len(self._sessions)
        active_1h = len(self.get_active_sessions(60))
        active_24h = len(self.get_active_sessions(24 * 60))
        total_messages = sum(len(s.messages) for s in self._sessions.values())
        total_replies = sum(s.reply_count for s in self._sessions.values())

        return {
            "total_sessions": total,
            "active_1h": active_1h,
            "active_24h": active_24h,
            "total_messages": total_messages,
            "total_replies": total_replies
        }

    def clear_all(self):
        """清空所有会话"""
        self._sessions.clear()
        self._user_name_to_session.clear()
