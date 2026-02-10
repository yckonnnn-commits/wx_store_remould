"""
消息处理器
核心业务流程：检测未读消息、抓取内容、生成回复、发送
"""

import json
import random
import re
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
        self._image_cities = {}  # {filename: city}
        self._address_image_index = {}  # {store_key: [image_path, ...]}
        self._user_image_sent = {}  # {user_hash: {category: count}}
        self._user_address_image_sent_count = {}  # {user_hash: count}
        self._user_video_state = {}  # {user_hash: {"armed": bool, "replied_count": int, "video_sent": bool}}
        self._user_sent_reply_texts = {}  # {user_hash: set(normalized_reply_text)}
        self._pending_post_reply_media = {}  # {session_id: {"type": "address_image", "path": str, "user_hash": str}}
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
            self._image_cities = {}
            self._address_image_index = {}

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
                    self._image_cities = data.get("cities", {}) or {}
                    # 转换为 filename -> category 映射
                    for category, filenames in images_data.items():
                        for filename in filenames:
                            self._image_categories[filename] = category
            self._rebuild_address_image_index()
                    
            self.log_message.emit(f"✅ 已加载 {len(self._keyword_triggers)} 条关键词触发规则")
        except Exception as e:
            self.log_message.emit(f"⚠️ 加载关键词配置失败: {str(e)}")

    def _rebuild_address_image_index(self):
        """根据分类+城市+文件名重建地址图片索引"""
        index = {
            "beijing_chaoyang": [],
            "sh_xuhui": [],
            "sh_jingan": [],
            "sh_hongkou": [],
            "sh_wujiaochang": [],
            "sh_renmin": [],
        }
        image_dir = Path("images")
        for filename, category in self._image_categories.items():
            if category != "店铺地址":
                continue
            img_path = image_dir / filename
            if not img_path.exists():
                continue

            city = self._image_cities.get(filename, "")
            lower_name = filename.lower()
            abs_path = str(img_path.resolve())

            if city == "北京":
                index["beijing_chaoyang"].append(abs_path)
                continue

            if "徐汇" in filename:
                index["sh_xuhui"].append(abs_path)
            elif "静安" in filename:
                index["sh_jingan"].append(abs_path)
            elif "虹口" in filename:
                index["sh_hongkou"].append(abs_path)
            elif "五角场" in filename or "杨浦" in filename:
                index["sh_wujiaochang"].append(abs_path)
            elif "人广" in filename or "人民广场" in filename or "黄浦" in filename:
                index["sh_renmin"].append(abs_path)
            elif city == "上海":
                index["sh_renmin"].append(abs_path)

        self._address_image_index = index

    def _get_user_hash(self, user_name: str) -> str:
        import hashlib
        return hashlib.md5(user_name.encode()).hexdigest()[:8]

    def _get_user_hash_by_session(self, session_id: str) -> Optional[str]:
        """根据会话ID获取用户哈希"""
        session = self.sessions.get_session(session_id)
        if not session or not session.user_name:
            return None
        return self._get_user_hash(session.user_name)

    def _ensure_user_video_state(self, user_hash: str) -> dict:
        """确保用户视频状态存在"""
        if user_hash not in self._user_video_state:
            self._user_video_state[user_hash] = {
                "armed": False,
                "replied_count": 0,
                "video_sent": False
            }
        return self._user_video_state[user_hash]

    def _format_video_state(self, user_hash: str) -> str:
        """格式化用户视频状态日志"""
        state = self._ensure_user_video_state(user_hash)
        return (
            f"user={user_hash}, armed={state.get('armed', False)}, "
            f"replied_count={state.get('replied_count', 0)}, video_sent={state.get('video_sent', False)}"
        )

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
        session_id = f"user_{hash(user_name)}"
        session = self.sessions.get_or_create_session(
            session_id=session_id,
            user_name=user_name
        )

        # 检查关键词触发
        triggered_category, image_path, extra = self._check_keyword_trigger(user_name, user_message)
        if triggered_category and image_path:
            if triggered_category == "店铺地址" and extra.get("address_pending"):
                self._pending_post_reply_media[session_id] = {
                    "type": "address_image",
                    "path": image_path,
                    "user_hash": extra.get("user_hash", "")
                }
                self.log_message.emit(f"🗺️ 已识别门店[{extra.get('target_store')}]，本轮文字回复后发送地址图片")
            else:
                self.log_message.emit(f"🖼️ 触发关键词 [{triggered_category}]，发送图片")
                self._send_image(
                    image_path,
                    media_meta={
                        "type": "category_image",
                        "category": triggered_category,
                        "user_hash": extra.get("user_hash", "")
                    }
                )
                return
        elif self._has_recent_address_context(session_id):
            self._try_queue_address_image(session_id, user_name, user_message)

        # 记录用户消息
        self.sessions.add_message(session.session_id, user_message, is_user=True)

        # === 硬编码回复（已注释） ===
        # default_reply = "咱们家产品都是根据咱们脸型头围肤色和需求1v1定制的，不是网上千篇一律的假发，您到店买不买我们都提供1.免费试戴+发型设计，您可以留个☎️，我安排老师接待您。"
        # self._send_reply(session.session_id, default_reply)
        
        # === 使用大模型生成回复 ===
        def on_reply(success, reply_text):
            # 成功发送统一走 reply_prepared 信号，避免重复发送
            if not success:
                self.log_message.emit(f"❌ 大模型生成回复失败")
                self._poll_inflight = False

        started = self.coordinator.coordinate_reply(session.session_id, user_message, on_reply)
        if not started:
            self.log_message.emit("⏸️ 协调器未启动回复流程（可能触发频率限制）")
            self._poll_inflight = False

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
        user_hash = self._get_user_hash_by_session(session_id)
        normalized_reply = self._normalize_outgoing_text(reply_text)
        if user_hash and normalized_reply:
            sent_texts = self._user_sent_reply_texts.setdefault(user_hash, set())
            if normalized_reply in sent_texts:
                self.log_message.emit(
                    f"⏸️ 已拦截重复回复（同一用户同一内容）: session={session_id}, user={user_hash}"
                )
                stale_pending = self._pending_post_reply_media.pop(session_id, None)
                if stale_pending:
                    self.log_message.emit(
                        f"🧹 已清理本轮待发送媒体，避免重复链路继续触发: session={session_id}"
                    )
                QTimer.singleShot(300, self._reset_poll_state)
                return

        def on_sent(success, result):
            if success:
                self.log_message.emit(f"✅ 回复已发送: {reply_text[:50]}...")
                if user_hash and normalized_reply:
                    sent_texts = self._user_sent_reply_texts.setdefault(user_hash, set())
                    sent_texts.add(normalized_reply)
                self.reply_sent.emit(session_id, reply_text)
                video_user_hash = self._mark_reply_progress_for_video(session_id)
                pending_media = self._pending_post_reply_media.pop(session_id, None)
                if pending_media and pending_media.get("type") == "address_image" and pending_media.get("path"):
                    self.log_message.emit("🖼️ 本轮地址回复完成，发送对应门店图片")
                    self._send_image(
                        pending_media["path"],
                        media_meta={
                            "type": "address_image",
                            "user_hash": pending_media.get("user_hash", "")
                        }
                    )
                    return
                if video_user_hash and self._maybe_send_delayed_video(session_id, video_user_hash):
                    return
            else:
                self.log_message.emit(f"❌ 发送失败")

            # 延迟重置状态
            QTimer.singleShot(2000, self._reset_poll_state)

        self.browser.send_message(reply_text, on_sent)

    def _send_image(self, image_path: str, media_meta: Optional[dict] = None):
        """发送图片"""
        def on_sent(success, result):
            if success:
                if media_meta and media_meta.get("type") == "address_image":
                    user_hash = media_meta.get("user_hash", "")
                    if user_hash:
                        self._user_address_image_sent_count[user_hash] = self._user_address_image_sent_count.get(user_hash, 0) + 1
                        self.log_message.emit(
                            f"🧭 地址图发送成功，触发延迟视频激活: user={user_hash}, "
                            f"address_sent_count={self._user_address_image_sent_count[user_hash]}"
                        )
                        self._arm_delayed_video(user_hash)
                if media_meta and media_meta.get("type") == "category_image":
                    category = media_meta.get("category", "")
                    user_hash = media_meta.get("user_hash", "")
                    if user_hash and category in ("联系方式", "店铺地址"):
                        self.log_message.emit(
                            f"🧭 分类图发送成功，触发延迟视频激活: user={user_hash}, category={category}"
                        )
                        self._arm_delayed_video(user_hash)
                if media_meta and media_meta.get("type") == "delayed_video":
                    user_hash = media_meta.get("user_hash", "")
                    if user_hash:
                        state = self._ensure_user_video_state(user_hash)
                        state["video_sent"] = True
                        state["armed"] = False
                        self.log_message.emit(
                            f"🎬 延迟视频发送成功，本用户不再重复发送视频: "
                            f"{self._format_video_state(user_hash)}"
                        )
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
                if media_meta and media_meta.get("type") == "delayed_video":
                    user_hash = media_meta.get("user_hash", "")
                    if user_hash:
                        state = self._ensure_user_video_state(user_hash)
                        if not state.get("video_sent", False):
                            state["armed"] = True
                            self.log_message.emit(
                                f"🎬 延迟视频发送失败，恢复待发送状态: {self._format_video_state(user_hash)}"
                            )
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
    
    def _check_keyword_trigger(self, user_name: str, user_message: str) -> tuple[Optional[str], Optional[str], dict]:
        """
        检查是否触发关键词，并检查用户限制
        Returns: (category, image_path, extra)
        """
        if not user_message:
            return None, None, {}

        user_hash = self._get_user_hash(user_name)
        
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

            if self._is_video_category(category):
                self.log_message.emit("ℹ️ 视频素材关键词已命中，但已改为延迟触发，跳过即时发送")
                continue

            if category == "店铺地址":
                route = self.knowledge.resolve_store_recommendation(user_message)
                target_store = route.get("target_store", "unknown")
                if target_store == "unknown":
                    self.log_message.emit("ℹ️ 地址意图已触发，但尚未识别到城市/区域，先走文字引导")
                    return None, None, {"address_route": route, "address_pending": False}

                sent_count = self._user_address_image_sent_count.get(user_hash, 0)
                if sent_count >= 1:
                    self.log_message.emit("⏸️ 当前用户地址图片已达上限（1次），仅发送文字回复")
                    return None, None, {"address_route": route, "address_pending": False}

                image_path = self._pick_address_image_for_store(target_store)
                if not image_path:
                    self.log_message.emit(f"⚠️ 目标门店[{target_store}]无可用地址图片，跳过发图")
                    return None, None, {"address_route": route, "address_pending": False}

                return category, image_path, {
                    "address_route": route,
                    "address_pending": True,
                    "user_hash": user_hash,
                    "target_store": target_store,
                }
            
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
            
            return category, image_path, {
                "user_hash": user_hash,
                "category": category
            }
        
        return None, None, {}

    def _pick_address_image_for_store(self, target_store: str) -> Optional[str]:
        """按目标门店随机选取地址图片，若池为空按城市兜底"""
        pool = self._address_image_index.get(target_store, [])
        if pool:
            return random.choice(pool)

        if target_store.startswith("sh_"):
            fallback = self._address_image_index.get("sh_renmin", [])
            if fallback:
                return random.choice(fallback)
        if target_store == "beijing_chaoyang":
            fallback = self._address_image_index.get("beijing_chaoyang", [])
            if fallback:
                return random.choice(fallback)
        return None

    def _has_recent_address_context(self, session_id: str) -> bool:
        """当前会话近期是否在聊地址相关"""
        session = self.sessions.get_session(session_id)
        if not session:
            return False
        for msg in session.get_recent_messages(8):
            text = msg.get("text", "")
            if "地址" in text or "门店" in text or "哪个区" in text or "哪个城市" in text or "就近安排" in text:
                return True
        return False

    def _try_queue_address_image(self, session_id: str, user_name: str, user_message: str) -> bool:
        """尝试根据用户地区在本轮回复后补发地址图片"""
        route = self.knowledge.resolve_store_recommendation(user_message)
        target_store = route.get("target_store", "unknown")
        if target_store == "unknown":
            return False

        user_hash = self._get_user_hash(user_name)
        sent_count = self._user_address_image_sent_count.get(user_hash, 0)
        if sent_count >= 1:
            self.log_message.emit("⏸️ 当前用户地址图片已达上限（1次），仅发送文字回复")
            return False

        image_path = self._pick_address_image_for_store(target_store)
        if not image_path:
            self.log_message.emit(f"⚠️ 目标门店[{target_store}]无可用地址图片，跳过发图")
            return False

        self._pending_post_reply_media[session_id] = {
            "type": "address_image",
            "path": image_path,
            "user_hash": user_hash
        }
        self.log_message.emit(f"🗺️ 已识别门店[{target_store}]，本轮文字回复后发送地址图片")
        return True
    
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

    def _pick_video_media(self) -> Optional[str]:
        """从视频素材分类选择媒体，优先视频文件"""
        image_dir = Path("images")
        if not image_dir.exists():
            return None

        media_candidates = []
        video_candidates = []
        video_exts = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".wmv", ".flv", ".webm"}
        for filename, category in self._image_categories.items():
            if category != "视频素材":
                continue
            media_path = image_dir / filename
            if not media_path.exists():
                continue
            abs_path = str(media_path.resolve())
            media_candidates.append(abs_path)
            if media_path.suffix.lower() in video_exts:
                video_candidates.append(abs_path)

        if video_candidates:
            return random.choice(video_candidates)
        if media_candidates:
            return random.choice(media_candidates)
        return None

    def _is_video_category(self, category: str) -> bool:
        """是否视频素材分类"""
        return category == "视频素材"

    def _arm_delayed_video(self, user_hash: str):
        """激活用户延迟视频发送状态（重复触发时重置计数）"""
        if not user_hash:
            return
        state = self._ensure_user_video_state(user_hash)
        if state.get("video_sent", False):
            self.log_message.emit(
                f"🎬 用户已发过延迟视频，本次不再激活: {self._format_video_state(user_hash)}"
            )
            return
        was_armed = state.get("armed", False)
        prev_count = state.get("replied_count", 0)
        state["armed"] = True
        state["replied_count"] = 0
        self.log_message.emit(
            "🎬 已激活延迟视频发送（联系方式/地址图成功后）: "
            f"user={user_hash}, reset={was_armed}, prev_count={prev_count}, "
            f"{self._format_video_state(user_hash)}"
        )

    def _mark_reply_progress_for_video(self, session_id: str) -> Optional[str]:
        """记录该会话一次成功回复，推进延迟视频计数"""
        user_hash = self._get_user_hash_by_session(session_id)
        if not user_hash:
            self.log_message.emit(f"🎬 延迟视频计数跳过：无法从会话获取用户信息 session={session_id}")
            return None

        state = self._ensure_user_video_state(user_hash)
        if state.get("video_sent", False) or not state.get("armed", False):
            self.log_message.emit(
                f"🎬 延迟视频计数不推进: session={session_id}, {self._format_video_state(user_hash)}"
            )
            return user_hash

        state["replied_count"] = state.get("replied_count", 0) + 1
        self.log_message.emit(
            f"🎬 延迟视频计数 +1: session={session_id}, progress={state['replied_count']}/2, "
            f"{self._format_video_state(user_hash)}"
        )
        return user_hash

    def _maybe_send_delayed_video(self, session_id: str, user_hash: str) -> bool:
        """达到阈值后发送延迟视频"""
        if not user_hash:
            return False

        state = self._ensure_user_video_state(user_hash)
        if state.get("video_sent", False):
            self.log_message.emit(
                f"🎬 延迟视频发送检查：已发送过，跳过 session={session_id}, {self._format_video_state(user_hash)}"
            )
            return False
        if not state.get("armed", False):
            self.log_message.emit(
                f"🎬 延迟视频发送检查：未激活，跳过 session={session_id}, {self._format_video_state(user_hash)}"
            )
            return False
        if state.get("replied_count", 0) < 2:
            self.log_message.emit(
                f"🎬 延迟视频发送检查：计数不足，跳过 session={session_id}, {self._format_video_state(user_hash)}"
            )
            return False

        media_path = self._pick_video_media()
        if not media_path:
            self.log_message.emit(
                f"⚠️ 未找到可发送的视频素材，保留延迟发送状态: session={session_id}, "
                f"{self._format_video_state(user_hash)}"
            )
            return False

        # 防止同一轮内重复触发发送
        state["armed"] = False
        self.log_message.emit(
            f"🎬 达到延迟发送条件，准备发送视频素材: session={session_id}, path={media_path}, "
            f"{self._format_video_state(user_hash)}"
        )
        self._send_image(
            media_path,
            media_meta={
                "type": "delayed_video",
                "user_hash": user_hash,
                "session_id": session_id
            }
        )
        return True

    def _reset_poll_state(self):
        """重置轮询状态"""
        self._poll_inflight = False

    def _normalize_outgoing_text(self, text: str) -> str:
        """标准化回复文本用于去重比较"""
        if not text:
            return ""
        normalized = re.sub(r"\s+", "", text).strip()
        return normalized

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
                self._reset_poll_state()
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
                    self._reset_poll_state()
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
                        self._reset_poll_state()
                        return

                    # 提取最新的用户消息
                    latest_user_msg = user_messages[-1].get("text", "")
                    if latest_user_msg:
                        session_id = f"user_{hash(user_name)}"
                        self.sessions.get_or_create_session(session_id=session_id, user_name=user_name)
                        # 检查关键词触发
                        triggered_category, image_path, extra = self._check_keyword_trigger(user_name, latest_user_msg)
                        if triggered_category and image_path:
                            if triggered_category == "店铺地址" and extra.get("address_pending"):
                                self._pending_post_reply_media[session_id] = {
                                    "type": "address_image",
                                    "path": image_path,
                                    "user_hash": extra.get("user_hash", "")
                                }
                                self.log_message.emit(f"🗺️ 已识别门店[{extra.get('target_store')}]，本轮文字回复后发送地址图片")
                            else:
                                self.log_message.emit(f"🖼️ 触发关键词 [{triggered_category}]，发送图片")
                                self._send_image(
                                    image_path,
                                    media_meta={
                                        "type": "category_image",
                                        "category": triggered_category,
                                        "user_hash": extra.get("user_hash", "")
                                    }
                                )
                                return
                        else:
                            session_id = f"user_{hash(user_name)}"
                            if self._has_recent_address_context(session_id):
                                self._try_queue_address_image(session_id, user_name, latest_user_msg)
                        
                        self.log_message.emit(f"🤖 准备调用大模型生成回复...")
                        self._generate_reply_from_history(user_name, messages, latest_user_msg)
                        return
                self._reset_poll_state()
                
            except Exception as e:
                self.log_message.emit(f"❌ 解析聊天记录错误: {e}")
                self._reset_poll_state()
        
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
        history_source = chat_history[:-1] if chat_history and chat_history[-1].get("is_user", False) else chat_history
        for msg in history_source[-10:]:  # 只取最近10条消息（不含最新用户消息）
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
                self._reset_poll_state()

        # 调用协调器（不使用 reply_prepared 信号，只使用 callback）
        success = self.coordinator.coordinate_reply(
            session_id=session.session_id,
            user_message=latest_message,
            callback=on_reply,
            conversation_history=conversation_history
        )

        if not success:
            self.log_message.emit(f"⏸️ 协调器未启动回复流程（可能触发频率限制）")
            self._is_processing_reply = False
            self._reset_poll_state()
    
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
