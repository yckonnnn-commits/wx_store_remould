"""
回复协调器
协调知识库匹配和AI回复生成
"""

from typing import Optional, Callable
from PySide6.QtCore import QObject, Signal

from ..services.knowledge_service import KnowledgeService
from ..services.llm_service import LLMService
from .session_manager import SessionManager, ChatSession


class ReplyCoordinator(QObject):
    """回复协调器，管理回复生成的整个流程"""

    reply_prepared = Signal(str, str)   # (session_id, reply_text) - 回复准备就绪
    reply_error = Signal(str, str)      # (session_id, error) - 回复生成错误

    def __init__(self, knowledge_service: KnowledgeService,
                 llm_service: LLMService, session_manager: SessionManager):
        super().__init__()
        self.knowledge_service = knowledge_service
        self.llm_service = llm_service
        self.session_manager = session_manager

        # 配置
        self.knowledge_threshold = 0.6  # 知识库匹配阈值
        self.use_knowledge_first = True  # 优先使用知识库
        self.max_history_turns = 3      # 最大历史轮数

        # 连接LLM服务信号
        self.llm_service.reply_ready.connect(self._on_llm_reply_ready)
        self.llm_service.error_occurred.connect(self._on_llm_error)

        # 待处理的请求
        self._pending_requests: dict = {}

    def coordinate_reply(self, session_id: str, user_message: str,
                        callback: Callable = None) -> bool:
        """协调回复生成

        流程：
        1. 先查询知识库
        2. 如果知识库有匹配，使用知识库回复
        3. 否则调用LLM生成回复

        Args:
            session_id: 会话ID
            user_message: 用户消息
            callback: 回调函数 (success, reply_text)

        Returns:
            是否成功启动回复流程
        """
        # 获取会话
        session = self.session_manager.get_session(session_id)
        if not session:
            session = self.session_manager.get_or_create_session(session_id)

        # 检查是否应该回复（频率控制）
        if not session.should_reply(min_interval_seconds=30):
            return False

        # 首先尝试知识库匹配
        if self.use_knowledge_first:
            kb_answer = self.knowledge_service.find_answer(
                user_message,
                threshold=self.knowledge_threshold
            )
            if kb_answer:
                # 知识库匹配成功
                self._handle_reply(session_id, kb_answer, source="knowledge")
                if callback:
                    callback(True, kb_answer)
                self.reply_prepared.emit(session_id, kb_answer)
                return True

        # 知识库未匹配，调用LLM
        return self._call_llm(session_id, user_message, callback)

    def _call_llm(self, session_id: str, user_message: str,
                  callback: Callable = None) -> bool:
        """调用LLM生成回复"""
        session = self.session_manager.get_session(session_id)
        if not session:
            return False

        # 获取对话历史
        history = session.get_conversation_history(self.max_history_turns)

        # 发送请求
        request_id = self.llm_service.generate_reply(
            user_message=user_message,
            conversation_history=history
        )

        # 记录待处理请求
        self._pending_requests[request_id] = {
            "session_id": session_id,
            "callback": callback
        }

        return True

    def _on_llm_reply_ready(self, request_id: str, reply_text: str):
        """LLM回复就绪"""
        if request_id not in self._pending_requests:
            return

        req_info = self._pending_requests.pop(request_id)
        session_id = req_info["session_id"]
        callback = req_info["callback"]

        # 处理回复文本
        processed_reply = self._process_reply_text(reply_text)

        # 记录回复
        self._handle_reply(session_id, processed_reply, source="llm")

        # 回调
        if callback:
            callback(True, processed_reply)

        self.reply_prepared.emit(session_id, processed_reply)

    def _on_llm_error(self, request_id: str, error: str):
        """LLM调用错误"""
        if request_id not in self._pending_requests:
            return

        req_info = self._pending_requests.pop(request_id)
        session_id = req_info["session_id"]
        callback = req_info["callback"]

        # 使用默认错误回复
        error_reply = "抱歉，系统暂时出现问题，请稍后再试。"

        if callback:
            callback(False, error_reply)

        self.reply_error.emit(session_id, error)

    def _handle_reply(self, session_id: str, reply_text: str, source: str):
        """处理生成的回复"""
        # 记录到会话
        self.session_manager.add_message(session_id, reply_text, is_user=False)
        self.session_manager.record_reply(session_id)

    def _process_reply_text(self, text: str) -> str:
        """处理回复文本（清理、格式化等）"""
        if not text:
            return "抱歉，我无法理解您的问题。"

        # 清理多余空白
        text = " ".join(text.split())

        # 限制长度
        max_length = 500
        if len(text) > max_length:
            text = text[:max_length] + "..."

        return text.strip()

    def get_quick_reply(self, keyword: str) -> Optional[str]:
        """获取快速回复"""
        return self.knowledge_service.find_answer(keyword, threshold=0.8)

    def set_knowledge_threshold(self, threshold: float):
        """设置知识库匹配阈值"""
        self.knowledge_threshold = max(0.0, min(1.0, threshold))

    def set_use_knowledge_first(self, enabled: bool):
        """设置是否优先使用知识库"""
        self.use_knowledge_first = enabled
