"""
会话日志落盘服务
用于沉淀训练数据（JSONL）。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


class ConversationLogger:
    """将会话事件按 session 追加写入 JSONL。"""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def append_event(
        self,
        session_id: str,
        user_id_hash: str,
        event_type: str,
        payload: Dict[str, Any],
        reply_source: str = "",
        rule_id: str = "",
        model_name: str = "",
    ) -> None:
        try:
            path = self._session_file(session_id)
            record = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "user_id_hash": user_id_hash,
                "event_type": event_type,
                "reply_source": reply_source or "",
                "rule_id": rule_id or "",
                "model_name": model_name or "",
                "payload": payload or {},
            }
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            # 日志沉淀不影响主链路
            return

    def _session_file(self, session_id: str) -> Path:
        safe = re.sub(r"[^0-9A-Za-z_\-]", "_", session_id or "unknown")
        return self.root_dir / f"{safe}.jsonl"

