"""
消息处理器
核心业务流程：检测未读消息、抓取内容、生成回复、发送
"""

import json
from typing import Callable, Optional
from PySide6.QtCore import QObject, Signal, QTimer

from ..services.browser_service import BrowserService
from ..services.knowledge_service import KnowledgeService
from ..services.llm_service import LLMService
from .session_manager import SessionManager
from .reply_coordinator import ReplyCoordinator


class MessageProcessor(QObject):
    """消息处理器，负责整个自动回复流程"""

    # 信号
    status_changed = Signal(str)        # 状态变更
    log_message = Signal(str)           # 日志消息
    message_received = Signal(dict)     # 收到新消息
    reply_sent = Signal(str, str)       # (session_id, reply_text) 回复已发送
    error_occurred = Signal(str)        # 错误发生

    def __init__(self, browser_service: BrowserService,
                 knowledge_service: KnowledgeService,
                 llm_service: LLMService, session_manager: SessionManager,
                 reply_coordinator: ReplyCoordinator):
        super().__init__()
        self.browser = browser_service
        self.knowledge = knowledge_service
        self.llm = llm_service
        self.sessions = session_manager
        self.coordinator = reply_coordinator

        # 状态
        self._running = False
        self._poll_inflight = False
        self._page_ready = False
        self._last_user_name = None
        self._last_messages_hash = None
        self._last_chat_user = None  # 记录上次抓取的用户，避免重复抓取

        # 定时器
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_cycle)
        
        # DOM监听定时器 - 检测聊天页面
        self._dom_watch_timer = QTimer(self)
        self._dom_watch_timer.timeout.connect(self._check_chat_page)
        self._dom_watch_timer.setInterval(2000)  # 每2秒检测一次

        # 连接浏览器信号
        self.browser.page_loaded.connect(self._on_page_loaded)
        self.browser.url_changed.connect(self._on_url_changed)

        # 连接协调器信号
        self.coordinator.reply_prepared.connect(self._on_reply_prepared)

    def _on_page_loaded(self, success: bool):
        """页面加载完成"""
        self._page_ready = success
        self.status_changed.emit("ready" if success else "error")
        if success:
            self.log_message.emit("✅ 页面加载完成")
            # 启动DOM监听
            if not self._dom_watch_timer.isActive():
                self._dom_watch_timer.start()
    
    def _on_url_changed(self, url: str):
        """URL变化回调"""
        self.log_message.emit(f"[调试] URL变化: {url}")
    
    def _check_chat_page(self):
        """检测是否在聊天页面 - 通过DOM元素判断"""
        if not self._page_ready:
            return
        
        # 使用JS检测聊天页面的关键元素
        script = r"""
        (function() {
            // 检测聊天页面的关键元素
            var chatCustomerName = document.querySelector('.chat-customer-name');
            var inputTextarea = document.getElementById('input-textarea');
            var chatScrollView = document.getElementById('chat-scroll-view');
            
            if (chatCustomerName && inputTextarea && chatScrollView) {
                var userName = (chatCustomerName.textContent || '').trim();
                return JSON.stringify({
                    isChatPage: true,
                    userName: userName
                });
            }
            
            return JSON.stringify({
                isChatPage: false,
                userName: null
            });
        })()
        """
        
        def on_result(success, result):
            if not success:
                return
            
            try:
                if isinstance(result, str):
                    data = json.loads(result)
                else:
                    data = result
                
                is_chat_page = data.get('isChatPage', False)
                user_name = data.get('userName', '')
                
                # 如果在聊天页面且用户名不同（说明切换了用户）
                if is_chat_page and user_name and user_name != self._last_chat_user:
                    self._last_chat_user = user_name
                    self.log_message.emit(f"🔍 检测到进入用户聊天: {user_name}")
                    # 延迟1秒后抓取聊天记录
                    QTimer.singleShot(1000, self._auto_grab_chat_history)
            except Exception as e:
                pass
        
        self.browser.run_javascript(script, on_result)
    
    def _auto_grab_chat_history(self):
        """自动抓取聊天记录"""
        self.grab_and_display_chat_history()

    def start(self, interval_ms: int = 4000):
        """启动消息处理"""
        if self._running:
            return

        if not self._page_ready:
            self.log_message.emit("⚠️ 页面未就绪，等待加载...")
            return

        self._running = True
        self._poll_timer.start(interval_ms)
        self.status_changed.emit("running")
        self.log_message.emit("🚀 AI客服已启动")

    def stop(self):
        """停止消息处理"""
        self._running = False
        self._poll_timer.stop()
        self._dom_watch_timer.stop()
        self.status_changed.emit("stopped")
        self.log_message.emit("🛑 AI客服已停止")

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running

    def _poll_cycle(self):
        """轮询周期"""
        if not self._running or not self._page_ready or self._poll_inflight:
            return

        self._poll_inflight = True
        self._check_unread_messages()

    def _check_unread_messages(self):
        """检查未读消息并点击第一个"""
        def on_result(success, result):
            self.log_message.emit(f"[调试] 未读消息检查结果: success={success}, result={result}")

            if not success:
                self.log_message.emit("[调试] 检查未读消息失败")
                self._poll_inflight = False
                return

            if isinstance(result, dict):
                if result.get('found') and result.get('clicked'):
                    # 成功找到并点击了未读消息
                    self.log_message.emit(f"🔔 发现未读消息({result.get('badgeText')})，已自动点击进入")
                    # 延迟后直接发送硬编码回复（不需要先抓取消息）
                    QTimer.singleShot(1500, self._send_default_reply)
                elif result.get('found') and not result.get('clicked'):
                    self.log_message.emit(f"⚠️ 发现未读消息但点击失败: {result.get('reason')}")
                    self._poll_inflight = False
                else:
                    # 没有找到未读消息 - 这是正常情况，不记录日志避免刷屏
                    self._poll_inflight = False
            else:
                self.log_message.emit(f"⚠️ 未读消息检查返回格式异常: {result}")
                self._poll_inflight = False

        self.browser.find_and_click_first_unread(on_result)

    def _grab_messages(self):
        """抓取消息"""
        def on_data(success, data):
            if not success or not data:
                self._poll_inflight = False
                return

            try:
                user_name = data.get("user_name", "未知用户")
                messages = data.get("messages", [])

                if not messages:
                    self._poll_inflight = False
                    return

                # 查找最新消息
                user_messages = [m for m in messages if m.get("is_user")]
                if not user_messages:
                    self._poll_inflight = False
                    return

                latest_msg = user_messages[-1]
                msg_text = latest_msg.get("text", "")

                # 检查是否是重复消息
                msg_hash = hash(f"{user_name}:{msg_text}")
                if msg_hash == self._last_messages_hash:
                    self._poll_inflight = False
                    return

                self._last_messages_hash = msg_hash
                self._last_user_name = user_name

                # 显示消息
                self.log_message.emit(f"💬 [{user_name}]: {msg_text[:50]}...")

                # 生成并发送回复
                self._generate_and_send_reply(user_name, msg_text)

            except Exception as e:
                self.log_message.emit(f"❌ 处理消息错误: {e}")
                self._poll_inflight = False

        self.browser.grab_chat_data(on_data)

    def _generate_and_send_reply(self, user_name: str, user_message: str):
        """生成并发送回复"""
        # 获取或创建会话
        session = self.sessions.get_or_create_session(
            session_id=f"user_{hash(user_name)}",
            user_name=user_name
        )

        # 记录用户消息
        self.sessions.add_message(session.session_id, user_message, is_user=True)

        # 硬编码默认回复
        default_reply = "咱们家产品都是根据咱们脸型头围肤色和需求1v1定制的，不是网上千篇一律的假发，您到店买不买我们都提供1.免费试戴+发型设计，您可以留个☎️，我安排老师接待您。"
        
        # 直接发送硬编码回复
        self._send_reply(session.session_id, default_reply)

    def _on_reply_prepared(self, session_id: str, reply_text: str):
        """回复准备就绪"""
        self._send_reply(session_id, reply_text)

    def _send_default_reply(self):
        """发送硬编码的默认回复"""
        default_reply = "咱们家产品都是根据咱们脸型头围肤色和需求1v1定制的，不是网上千篇一律的假发，您到店买不买我们都提供1.免费试戴+发型设计，您可以留个☎️，我安排老师接待您。"
        
        def on_sent(success, result):
            self.log_message.emit(f"[调试] 发送结果: success={success}, result={result}")
            if success:
                self.log_message.emit(f"✅ 回复已发送: {default_reply[:50]}...")
            else:
                self.log_message.emit(f"❌ 发送失败: {result}")
            
            # 延迟重置状态
            QTimer.singleShot(2000, self._reset_poll_state)
        
        self.log_message.emit(f"📤 正在发送默认回复...")
        self.browser.send_message(default_reply, on_sent)

    def _send_reply(self, session_id: str, reply_text: str):
        """发送回复"""
        def on_sent(success, result):
            if success:
                self.log_message.emit(f"✅ 回复已发送: {reply_text[:50]}...")
                self.reply_sent.emit(session_id, reply_text)
            else:
                self.log_message.emit(f"❌ 发送失败")

            # 延迟重置状态
            QTimer.singleShot(2000, self._reset_poll_state)

        self.browser.send_message(reply_text, on_sent)

    def _reset_poll_state(self):
        """重置轮询状态"""
        self._poll_inflight = False

    def force_check(self):
        """强制检查一次"""
        if not self._poll_inflight:
            self._poll_cycle()

    def grab_and_display_chat_history(self):
        """抓取并格式化显示完整聊天记录"""
        def on_data(success, result):
            if not success:
                self.log_message.emit("❌ 抓取聊天记录失败")
                return
            
            try:
                # 解析JSON字符串
                if isinstance(result, str):
                    data = json.loads(result)
                else:
                    data = result
                
                user_name = data.get("user_name", "未知用户")
                messages = data.get("messages", [])
                debug = data.get("debug", [])
                
                # 输出调试信息
                for d in debug:
                    self.log_message.emit(f"[调试] {d}")
                
                if not messages:
                    self.log_message.emit(f"⚠️ 用户 {user_name} 暂无聊天记录")
                    return
                
                # 格式化输出聊天记录
                self.log_message.emit(f"\n{'='*50}")
                self.log_message.emit(f"📋 用户聊天记录：{user_name}")
                self.log_message.emit(f"{'='*50}\n")
                
                for msg in messages:
                    text = msg.get("text", "")
                    is_user = msg.get("is_user", False)
                    is_kf = msg.get("is_kf", False)
                    
                    if is_user:
                        self.log_message.emit(f"❤️‍🔥 用户（{user_name}）：{text}")
                    elif is_kf:
                        self.log_message.emit(f"🤖 客服（我）：{text}")
                    else:
                        self.log_message.emit(f"💬 {text}")
                
                self.log_message.emit(f"\n{'='*50}")
                self.log_message.emit(f"✅ 共 {len(messages)} 条消息")
                self.log_message.emit(f"{'='*50}\n")
                
            except Exception as e:
                self.log_message.emit(f"❌ 解析聊天记录错误: {e}")
        
        self.browser.grab_chat_data(on_data)

    def test_grab(self, callback: Callable = None):
        """测试抓取功能"""
        def on_data(success, data):
            if callback:
                callback(success, data)
            else:
                if success:
                    self.log_message.emit(f"测试抓取: {json.dumps(data, ensure_ascii=False)[:200]}")
                else:
                    self.log_message.emit("测试抓取失败")

        self.browser.grab_chat_data(on_data)
