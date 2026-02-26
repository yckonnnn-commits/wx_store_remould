"""
会话记忆持久化存储
用于跨重启保存客服 Agent 的会话上下文与媒体发送状态。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional


class MemoryStore:
    """跨重启记忆存储"""

    def __init__(self, file_path: Path):
        self.file_path = file_path
        self._data: Dict[str, Any] = {
            "version": 1,
            "updated_at": "",
            "sessions": {},
            "users": {},
        }
        self.load()

    def load(self) -> bool:
        """加载记忆文件"""
        try:
            if self.file_path.exists():
                loaded = json.loads(self.file_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._data["version"] = loaded.get("version", 1)
                    self._data["updated_at"] = loaded.get("updated_at", "")
                    self._data["sessions"] = loaded.get("sessions", {}) or {}
                    self._data["users"] = loaded.get("users", {}) or {}
            return True
        except Exception:
            self._data = {
                "version": 1,
                "updated_at": "",
                "sessions": {},
                "users": {},
            }
            return False

    def save(self) -> bool:
        """保存记忆文件"""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self._data["updated_at"] = datetime.now().isoformat()
            self.file_path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            return True
        except Exception:
            return False

    def _default_session_state(self, session_id: str, user_hash: str = "") -> Dict[str, Any]:
        return {
            "session_id": session_id,
            "user_hash": user_hash,
            "updated_at": datetime.now().isoformat(),
            "address_prompt_count": 0,
            "sent_address_stores": [],
            "address_image_sent_count": 0,
            "contact_image_sent_count": 0,
            "contact_warmup": False,
            "last_route_reason": "unknown",
            "last_intent": "general",
            "last_reply_goal": "解答",
        }

    def _default_user_state(self, user_hash: str) -> Dict[str, Any]:
        return {
            "user_hash": user_hash,
            "updated_at": datetime.now().isoformat(),
            "video_armed": False,
            "video_sent": False,
            "post_contact_reply_count": 0,
            "recent_reply_hashes": [],
        }

    def get_session_state(self, session_id: str, user_hash: str = "") -> Dict[str, Any]:
        sessions = self._data.setdefault("sessions", {})
        if session_id not in sessions:
            sessions[session_id] = self._default_session_state(session_id, user_hash)
        state = sessions[session_id]
        if user_hash and not state.get("user_hash"):
            state["user_hash"] = user_hash
            state["updated_at"] = datetime.now().isoformat()
        return state

    def update_session_state(self, session_id: str, updates: Dict[str, Any], user_hash: str = "") -> Dict[str, Any]:
        state = self.get_session_state(session_id, user_hash=user_hash)
        state.update(updates or {})
        state["updated_at"] = datetime.now().isoformat()
        return state

    def get_user_state(self, user_hash: str) -> Dict[str, Any]:
        users = self._data.setdefault("users", {})
        if user_hash not in users:
            users[user_hash] = self._default_user_state(user_hash)
        return users[user_hash]

    def update_user_state(self, user_hash: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        state = self.get_user_state(user_hash)
        state.update(updates or {})
        state["updated_at"] = datetime.now().isoformat()
        return state

    def prune_expired(self, ttl_days: int = 30) -> None:
        """清理超过 ttl_days 的会话/用户记录"""
        cutoff = datetime.now() - timedelta(days=max(1, ttl_days))

        sessions = self._data.setdefault("sessions", {})
        session_keys = list(sessions.keys())
        for key in session_keys:
            updated_at = sessions[key].get("updated_at", "")
            dt = self._parse_datetime(updated_at)
            if dt and dt < cutoff:
                sessions.pop(key, None)

        users = self._data.setdefault("users", {})
        user_keys = list(users.keys())
        for key in user_keys:
            updated_at = users[key].get("updated_at", "")
            dt = self._parse_datetime(updated_at)
            if dt and dt < cutoff:
                users.pop(key, None)

    def _parse_datetime(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None
