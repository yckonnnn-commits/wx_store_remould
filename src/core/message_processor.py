"""
消息处理器
核心业务流程：检测未读消息、抓取内容、生成回复、发送
"""

import json
import random
from pathlib import Path
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
        self._last_grab_time = 0  # 记录上次抓取时间，防抖
        self._is_processing_reply = False  # 标记是否正在处理回复

        # 关键词触发配置
        self._keyword_triggers = []
        self._image_categories = {}  # {filename: category}
        self._user_image_sent = {}  # {user_hash: {category: count}}
        self._load_keyword_config()

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
    
    def _load_keyword_config(self):
        """加载关键词触发配置"""
        try:
            self._keyword_triggers = []
            self._image_categories = {}

            # 加载触发规则
            triggers_file = Path("config/keyword_triggers.json")
            if triggers_file.exists():
                with open(triggers_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._keyword_triggers = [t for t in data.get("triggers", []) if t.get("enabled", True)]
            
            # 加载图片分类
            categories_file = Path("config/image_categories.json")
            if categories_file.exists():
                with open(categories_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    images_data = data.get("images", {})
                    # 转换为 filename -> category 映射
                    for category, filenames in images_data.items():
                        for filename in filenames:
                            self._image_categories[filename] = category
                    
            self.log_message.emit(f"✅ 已加载 {len(self._keyword_triggers)} 条关键词触发规则")
        except Exception as e:
            self.log_message.emit(f"⚠️ 加载关键词配置失败: {str(e)}")

    def reload_keyword_config(self):
        """公开方法：重新加载关键词与图片分类配置"""
        self._load_keyword_config()

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
        """自动抓取聊天记录（带防抖）"""
        import time
        current_time = time.time()

        # 关键检查：AI必须处于启动状态才允许自动回复
        if not self._running:
            self.log_message.emit(f"⏸️ AI未启动，跳过自动抓取")
            return

        # 防抖：如果距离上次抓取不到5秒，或者正在处理回复，则跳过
        if current_time - self._last_grab_time < 5.0:
            self.log_message.emit(f"⏸️ 防抖：距离上次抓取不到5秒，跳过")
            return

        if self._is_processing_reply:
            self.log_message.emit(f"⏸️ 正在处理回复中，跳过本次抓取")
            return

        self._last_grab_time = current_time
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
        if not self._running:
            return

        self._running = False
        self._poll_timer.stop()
        self._dom_watch_timer.stop()
        
        # 清理LLM服务的工作线程
        self.llm.cleanup()
        
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
        """生成并发送回复 - 优先检查关键词触发"""
        # 检查关键词触发
        triggered_category, image_path = self._check_keyword_trigger(user_name, user_message)
        if triggered_category and image_path:
            self.log_message.emit(f"🖼️ 触发关键词 [{triggered_category}]，发送图片")
            self._send_image(image_path)
            return

        # 获取或创建会话
        session = self.sessions.get_or_create_session(
            session_id=f"user_{hash(user_name)}",
            user_name=user_name
        )

        # 记录用户消息
        self.sessions.add_message(session.session_id, user_message, is_user=True)

        # === 硬编码回复（已注释） ===
        # default_reply = "咱们家产品都是根据咱们脸型头围肤色和需求1v1定制的，不是网上千篇一律的假发，您到店买不买我们都提供1.免费试戴+发型设计，您可以留个☎️，我安排老师接待您。"
        # self._send_reply(session.session_id, default_reply)
        
        # === 使用大模型生成回复 ===
        def on_reply(success, reply_text):
            if success and reply_text:
                self._send_reply(session.session_id, reply_text)
            else:
                self.log_message.emit(f"❌ 大模型生成回复失败")
                self._poll_inflight = False

        self.coordinator.coordinate_reply(session.session_id, user_message, on_reply)

    def _on_reply_prepared(self, session_id: str, reply_text: str):
        """回复准备就绪"""
        # 如果正在手动处理回复（通过 _generate_reply_from_history），跳过信号触发的回复
        if self._is_processing_reply:
            self.log_message.emit(f"⏸️ 已在手动处理回复，跳过信号触发")
            return
        
        # 延迟3秒发送，模拟人工回复，避免被检测
        self.log_message.emit(f"⏳ 等待3秒后发送回复...")
        QTimer.singleShot(3000, lambda: self._send_reply(session_id, reply_text))

    def _send_default_reply(self):
        """自动抓取聊天记录并生成回复（进入未读消息时调用）"""
        self.log_message.emit(f"📋 正在抓取聊天记录...")
        # 自动抓取聊天记录并生成回复
        self.grab_and_display_chat_history(auto_reply=True)

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

    def _send_image(self, image_path: str):
        """发送图片"""
        def on_sent(success, result):
            if success:
                # 详细记录发送结果
                if isinstance(result, dict):
                    # 显示所有关键信息
                    send_method = result.get('sendMethod', result.get('method', 'unknown'))
                    trigger_method = result.get('triggerMethod', 'unknown')
                    step = result.get('step', '?')
                    btn_text = result.get('buttonText', '')
                    send_pos = result.get('sendPosition', {})
                    
                    log_parts = [f"step={step}", f"sendMethod={send_method}"]
                    if trigger_method != 'unknown':
                        log_parts.append(f"triggerMethod={trigger_method}")
                    if btn_text:
                        log_parts.append(f"buttonText={btn_text}")
                    if send_pos:
                        log_parts.append(f"pos=({send_pos.get('x', 0):.0f},{send_pos.get('y', 0):.0f})")
                    
                    self.log_message.emit(f"🖼️ 图片发送结果: {', '.join(log_parts)}")
                else:
                    self.log_message.emit(f"🖼️ 图片发送结果: {result}")
            else:
                # 详细记录失败原因
                if isinstance(result, dict):
                    error = result.get('error', 'unknown')
                    step = result.get('step', '?')
                    trigger_method = result.get('triggerMethod', '')
                    self.log_message.emit(f"❌ 图片发送失败: error={error}, step={step}, trigger={trigger_method}")
                else:
                    self.log_message.emit(f"❌ 图片发送失败: {result}")
            QTimer.singleShot(2000, self._reset_poll_state)

        self.browser.send_image(image_path, on_sent)

    def _pick_random_image(self) -> Optional[str]:
        """从图片库中随机选择一张图片"""
        image_dir = Path("images")
        if not image_dir.exists():
            return None

        exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff"}
        candidates = [p for p in image_dir.iterdir() if p.is_file() and p.suffix.lower() in exts]
        if not candidates:
            return None
        return str(random.choice(candidates).resolve())
    
    def _check_keyword_trigger(self, user_name: str, user_message: str) -> tuple[Optional[str], Optional[str]]:
        """
        检查是否触发关键词，并检查用户限制
        Returns: (category, image_path) or (None, None)
        """
        if not user_message:
            return None, None
        
        # 生成用户标识
        import hashlib
        user_hash = hashlib.md5(user_name.encode()).hexdigest()[:8]
        
        # 初始化用户记录
        if user_hash not in self._user_image_sent:
            self._user_image_sent[user_hash] = {}
        
        # 逐个匹配触发规则
        for trigger in self._keyword_triggers:
            keywords = trigger.get("keywords", [])
            category = trigger.get("category", "")
            
            # 检查是否匹配关键词
            matched = any(keyword in user_message for keyword in keywords)
            if not matched:
                continue
            
            # 检查用户是否已达到该分类的限制
            sent_count = self._user_image_sent[user_hash].get(category, 0)
            if sent_count >= 1:
                self.log_message.emit(f"⏸️ 用户已接收过 [{category}] 分类图片，跳过触发")
                continue
            
            # 从该分类中随机选择图片
            image_path = self._pick_category_image(category)
            if not image_path:
                self.log_message.emit(f"⚠️ [{category}] 分类没有图片")
                continue
            
            # 记录已发送
            self._user_image_sent[user_hash][category] = sent_count + 1
            
            return category, image_path
        
        return None, None
    
    def _pick_category_image(self, category: str) -> Optional[str]:
        """从指定分类中随机选择一张图片"""
        image_dir = Path("images")
        if not image_dir.exists():
            return None
        
        # 筛选属于该分类的图片
        category_images = []
        for filename, img_category in self._image_categories.items():
            if img_category == category:
                img_path = image_dir / filename
                if img_path.exists():
                    category_images.append(str(img_path.resolve()))
        
        if not category_images:
            return None
        
        return random.choice(category_images)

    def _reset_poll_state(self):
        """重置轮询状态"""
        self._poll_inflight = False

    def force_check(self):
        """强制检查一次"""
        if not self._poll_inflight:
            self._poll_cycle()

    def grab_and_display_chat_history(self, auto_reply=True):
        """抓取并格式化显示完整聊天记录，可选自动回复
        
        Args:
            auto_reply: 是否在抓取后自动生成并发送回复
        """
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
                user_messages = data.get("user_messages", [])
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
                
                # 如果启用自动回复且有用户消息
                if auto_reply and user_messages:
                    # 关键检查：最后一条消息必须是用户发的才回复
                    if messages and not messages[-1].get("is_user", False):
                        self.log_message.emit(f"⏸️ 最后一条消息不是用户发的，跳过自动回复")
                        return

                    # 提取最新的用户消息
                    latest_user_msg = user_messages[-1].get("text", "")
                    if latest_user_msg:
                        # 检查关键词触发
                        triggered_category, image_path = self._check_keyword_trigger(user_name, latest_user_msg)
                        if triggered_category and image_path:
                            self.log_message.emit(f"🖼️ 触发关键词 [{triggered_category}]，发送图片")
                            self._send_image(image_path)
                            return
                        
                        self.log_message.emit(f"🤖 准备调用大模型生成回复...")
                        self._generate_reply_from_history(user_name, messages, latest_user_msg)
                
            except Exception as e:
                self.log_message.emit(f"❌ 解析聊天记录错误: {e}")
        
        self.browser.grab_chat_data(on_data)
    
    def _generate_reply_from_history(self, user_name: str, chat_history: list, latest_message: str):
        """根据聊天记录生成回复

        Args:
            user_name: 用户名
            chat_history: 完整聊天记录
            latest_message: 最新用户消息
        """
        # 如果正在处理回复，跳过
        if self._is_processing_reply:
            self.log_message.emit(f"⏸️ 已有回复正在处理中，跳过")
            return

        # 标记开始处理
        self._is_processing_reply = True

        # 获取或创建会话
        session = self.sessions.get_or_create_session(
            session_id=f"user_{hash(user_name)}",
            user_name=user_name
        )

        # 记录用户消息到会话
        self.sessions.add_message(session.session_id, latest_message, is_user=True)

        # 构建对话历史（格式化为大模型可理解的格式）
        conversation_history = []
        for msg in chat_history[-10:]:  # 只取最近10条消息
            text = msg.get("text", "")
            is_user = msg.get("is_user", False)

            if is_user:
                conversation_history.append({"role": "user", "content": text})
            else:
                conversation_history.append({"role": "assistant", "content": text})

        self.log_message.emit(f"📤 发送聊天记录给大模型（共{len(conversation_history)}条）...")

        # 使用协调器生成回复
        self.log_message.emit(f"⏳ 大模型处理中...")

        def on_reply(success, reply_text):
            if success and reply_text:
                self.log_message.emit(f"✅ 大模型回复完成")
                self.log_message.emit(f"💬 回复内容: {reply_text[:100]}...")
                # 添加3秒延迟后发送回复
                self.log_message.emit(f"⏳ 等待3秒后发送回复...")
                QTimer.singleShot(3000, lambda: self._send_reply_and_reset(session.session_id, reply_text))
            else:
                self.log_message.emit(f"❌ 大模型生成回复失败")
                # 重置处理状态
                self._is_processing_reply = False

        # 调用协调器（不使用 reply_prepared 信号，只使用 callback）
        success = self.coordinator.coordinate_reply(
            session_id=session.session_id,
            user_message=latest_message,
            callback=on_reply
        )

        if not success:
            self.log_message.emit(f"⏸️ 协调器未启动回复流程（可能触发频率限制）")
            self._is_processing_reply = False
    
    def _send_reply_and_reset(self, session_id: str, reply_text: str):
        """发送回复并重置处理状态"""
        self._send_reply(session_id, reply_text)
        # 延迟重置处理状态，等待发送完成
        QTimer.singleShot(2000, lambda: setattr(self, '_is_processing_reply', False))

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
