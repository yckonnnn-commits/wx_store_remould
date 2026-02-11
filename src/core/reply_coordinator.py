"""
回复协调器
协调知识库匹配和AI回复生成
"""

import random
import re
from typing import Optional, Callable, List, Dict
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
        self._address_first_prompt = (
            "姐姐，您在什么城市/区域？方便告诉我吗？我可以帮您针对性推荐相对应的门店，"
            "我们的门店分布：北京1家店在朝阳区，上海有5家店（静安，人广，虹口，五角场，徐汇）"
        )
        self._address_followups = [
            "姐姐方便说下您所在城市或区域吗？我好给您推荐最近门店。",
            "姐姐您大概在什么城市或哪个区呀？我按距离给您就近安排。",
            "姐姐告诉我您所在城市/区域，我马上给您匹配最近门店地址。"
        ]
        self._address_reply_markers = (
            "推荐您去", "门店", "画红框", "图中画线", "人民广场门店", "徐汇门店",
            "静安门店", "虹口门店", "五角场门店", "北京朝阳门店"
        )
        self._emoji_pool = (
            "😊", "🌸", "✨", "👍", "🤝", "💗", "😄", "🙂", "😉", "🥰",
            "🙌", "💪", "🌟", "🍀", "🫶", "😌", "🤗", "💫", "🌷", "🎉"
        )
        self._location_hint_keywords = (
            "区", "市", "北京", "上海", "天津", "河北", "内蒙古", "江苏", "浙江",
            "苏州", "无锡", "常州", "南通", "南京", "宁波", "杭州", "绍兴", "嘉兴", "湖州"
        )
        self._beijing_districts = (
            "朝阳", "海淀", "丰台", "通州", "顺义", "门头沟", "大兴", "昌平", "石景山",
            "西城", "东城", "房山", "怀柔", "平谷", "密云", "延庆"
        )
        self._jiangzhe_regions = (
            "江浙沪", "江苏", "浙江", "苏州", "无锡", "常州", "南通", "南京",
            "宁波", "杭州", "绍兴", "嘉兴", "湖州", "金华", "温州"
        )

    def coordinate_reply(self, session_id: str, user_message: str,
                        callback: Callable = None,
                        conversation_history: Optional[List[Dict]] = None) -> bool:
        """协调回复生成

        流程：
        1. 先查询知识库
        2. 如果知识库有匹配，使用知识库回复
        3. 否则调用LLM生成回复

        Args:
            session_id: 会话ID
            user_message: 用户消息
            callback: 回调函数 (success, reply_text)
            conversation_history: 可选对话历史（不含当前 user_message）

        Returns:
            是否成功启动回复流程
        """
        # 获取会话
        session = self.session_manager.get_session(session_id)
        if not session:
            session = self.session_manager.get_or_create_session(session_id)

        is_address_query = self.knowledge_service.is_address_query(user_message)
        route = self.knowledge_service.resolve_store_recommendation(user_message)
        has_address_context = self._has_recent_address_context(session)
        has_location_hint = self._has_location_hint(user_message)

        # 地址场景优先：地址询问，或在地址上下文中提供了地区信息（含“只说上海未说区”）
        if (
            is_address_query
            or route.get("reason") == "shanghai_need_district"
            or route.get("reason") == "out_of_coverage"
            or (route.get("target_store") != "unknown" and (has_address_context or has_location_hint))
        ):
            return self._coordinate_address_reply(
                session_id=session_id,
                session=session,
                user_message=user_message,
                route=route,
                is_address_query=is_address_query,
                callback=callback
            )

        # 非地址场景再做频率控制，避免漏掉“门头沟有吗”这类地址追问
        if not session.should_reply(min_interval_seconds=8):
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
        return self._call_llm(session_id, user_message, callback, conversation_history)

    def _coordinate_address_reply(self, session_id: str, session: ChatSession, user_message: str,
                                  route: dict, is_address_query: bool, callback: Callable = None) -> bool:
        target_store = route.get("target_store", "unknown")
        reason = route.get("reason", "unknown")

        # 有明确门店：仅给门店名，不透传具体地址（平台限制）
        if target_store != "unknown":
            store = self.knowledge_service.get_store_display(target_store)
            store_name = store.get("store_name", "门店")
            jiangzhe_region = self._extract_jiangzhe_region(user_message)
            if target_store == "sh_renmin" and jiangzhe_region:
                reply = f"姐姐，{jiangzhe_region}地区推荐您到上海人民广场店，您方便的话可以过来看看试戴～"
                session.set_context("last_target_store", target_store)
                session.set_context("last_address_query_at", user_message)
                self._emit_direct_reply(session_id, reply, callback)
                return True
            sent_stores = set(session.get_context("sent_address_stores", []) or [])
            if target_store in sent_stores:
                district = self._extract_beijing_district(user_message)
                if target_store == "beijing_chaoyang":
                    if district:
                        reply = (
                            f"姐姐，{district}区目前没有我们的门店，北京目前只有朝阳这1家，"
                            "您方便的话可以过来看看试戴～"
                        )
                    else:
                        reply = "姐姐，北京目前只有朝阳这1家门店，您方便的话可以过来看看试戴～"
                else:
                    region_hint = self._extract_region_hint(user_message)
                    if target_store == "sh_renmin" and region_hint:
                        reply = f"姐姐，{region_hint}地区推荐您到上海人民广场店，您方便的话可以过来看看试戴～"
                    else:
                        reply = (
                            f"姐姐，这个区域就近还是{store_name}，之前已经给您发过位置图了，"
                            "我也可以帮您安排预约时间～"
                        )
                session.set_context("last_target_store", target_store)
                session.set_context("last_address_query_at", user_message)
                self._emit_direct_reply(session_id, reply, callback)
                return True
            reply = (
                f"姐姐，推荐您去{store_name}，可以看下图片画红框框的地方，"
                "不懂得您可以继续问我～"
            )
            session.set_context("last_target_store", target_store)
            session.set_context("last_address_query_at", user_message)
            self._emit_direct_reply(session_id, reply, callback)
            return True

        # 只说“上海”没说区：优先追问区
        if reason == "shanghai_need_district":
            prompt_count = int(session.get_context("address_prompt_count", 0) or 0)
            if prompt_count <= 0:
                reply = "姐姐您在上海哪个区呀？我帮您匹配最近门店。"
            else:
                reply = "姐姐方便告诉我上海哪个区吗？我马上给您推荐最近门店。"
            session.set_context("address_prompt_count", prompt_count + 1)
            session.set_context("last_address_query_at", user_message)
            self._emit_direct_reply(session_id, reply, callback)
            return True

        # 明确非覆盖地区（如新疆/大连）固定话术
        if reason == "out_of_coverage":
            region = route.get("detected_region", "")
            if region:
                reply = (
                    "姐姐，我们目前的门店分布为：北京1家店在朝阳区，上海有5家店"
                    "（静安，人广，虹口，五角场，徐汇），"
                    f"您所在的{region}目前没有我们的门店，如果可以的话，可以来我们的门店预约试戴。"
                )
            else:
                reply = (
                    "姐姐，我们目前的门店分布为：北京1家店在朝阳区，上海有5家店"
                    "（静安，人广，虹口，五角场，徐汇），"
                    "您所在的地区目前没有我们的门店，如果可以的话，可以来我们的门店预约试戴。"
                )
            session.set_context("last_address_query_at", user_message)
            self._emit_direct_reply(session_id, reply, callback)
            return True

        # 没有地区信息：首次长模板，后续变体追问（不重复）
        if is_address_query:
            prompt_count = int(session.get_context("address_prompt_count", 0) or 0)
            if prompt_count <= 0:
                reply = self._address_first_prompt
            else:
                idx = (prompt_count - 1) % len(self._address_followups)
                reply = self._address_followups[idx]
            session.set_context("address_prompt_count", prompt_count + 1)
            session.set_context("last_address_query_at", user_message)
            self._emit_direct_reply(session_id, reply, callback)
            return True

        return False

    def _emit_direct_reply(self, session_id: str, reply_text: str, callback: Callable = None):
        self._handle_reply(session_id, reply_text, source="knowledge")
        if callback:
            callback(True, reply_text)
        self.reply_prepared.emit(session_id, reply_text)

    def _has_location_hint(self, text: str) -> bool:
        text = (text or "").strip()
        return bool(text) and any(k in text for k in self._location_hint_keywords)

    def _extract_beijing_district(self, text: str) -> str:
        text = (text or "").strip()
        for d in self._beijing_districts:
            if d in text:
                return d
        return ""

    def _extract_jiangzhe_region(self, text: str) -> str:
        text = (text or "").strip()
        for r in self._jiangzhe_regions:
            if r in text:
                return r
        return ""

    def _extract_region_hint(self, text: str) -> str:
        hint = self._extract_beijing_district(text)
        if hint:
            return f"{hint}区"
        hint = self._extract_jiangzhe_region(text)
        if hint:
            return hint
        return ""

    def _call_llm(self, session_id: str, user_message: str,
                  callback: Callable = None,
                  conversation_history: Optional[List[Dict]] = None) -> bool:
        """调用LLM生成回复"""
        session = self.session_manager.get_session(session_id)
        if not session:
            return False

        # 获取对话历史
        history = conversation_history if conversation_history is not None else session.get_conversation_history(self.max_history_turns)

        # 发送请求
        request_id = self.llm_service.generate_reply(
            user_message=user_message,
            conversation_history=history
        )

        # 记录待处理请求
        self._pending_requests[request_id] = {
            "session_id": session_id,
            "callback": callback,
            "user_message": user_message
        }

        return True

    def _on_llm_reply_ready(self, request_id: str, reply_text: str):
        """LLM回复就绪"""
        if request_id not in self._pending_requests:
            return

        req_info = self._pending_requests.pop(request_id)
        session_id = req_info["session_id"]
        callback = req_info["callback"]
        user_message = req_info.get("user_message", "")

        # 处理回复文本
        processed_reply = self._process_reply_text(reply_text)
        processed_reply = self._sanitize_non_address_reply(user_message, processed_reply)
        processed_reply = self._enforce_llm_reply_policy(session_id, user_message, processed_reply)

        # 记录回复
        self._handle_reply(session_id, processed_reply, source="llm")

        # 回调
        if callback:
            callback(True, processed_reply)

        self.reply_prepared.emit(session_id, processed_reply)

    def _sanitize_non_address_reply(self, user_message: str, reply_text: str) -> str:
        """非地址问题时，拦截误触发的地址推荐文案"""
        if not reply_text:
            return reply_text

        is_address_query = self.knowledge_service.is_address_query(user_message)
        route = self.knowledge_service.resolve_store_recommendation(user_message)
        has_location_signal = route.get("target_store", "unknown") != "unknown"
        if is_address_query or has_location_signal:
            return reply_text

        if any(marker in reply_text for marker in self._address_reply_markers):
            return "姐姐，需要预约的，我帮您安排时间，您想今天还是明天到店呢？"

        return reply_text

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

    def _enforce_llm_reply_policy(self, session_id: str, user_message: str, reply_text: str) -> str:
        """LLM输出轻约束：保留语义，仅做去噪与emoji补充"""
        text = self._strip_reply_noise(reply_text)
        if not text:
            text = "姐姐我在呢，您继续说说需求😊"

        text = self._ensure_single_line(text)
        text = self._collapse_repeated_phrases(text)
        # 仅做极长保护，避免异常输出刷屏
        if len(text) > 120:
            text = text[:120].strip()
        text = self._ensure_emoji(text, session_id=session_id)
        return text

    def _strip_reply_noise(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""
        # 去掉常见尾部噪音，如“15:13胃不疼”
        text = re.sub(r"\s*\d{1,2}:\d{2}\S*$", "", text).strip()
        return text

    def _ensure_single_line(self, text: str) -> str:
        return " ".join((text or "").split()).strip()

    def _collapse_repeated_phrases(self, text: str) -> str:
        text = re.sub(r"(姐姐，?){2,}", "姐姐，", text)
        text = re.sub(r"(我帮您安排(?:时间)?，?){2,}", "我帮您安排，", text)
        text = re.sub(r"(您方便(?:的话)?，?){2,}", "您方便，", text)
        return text.strip("，,。") + ("。" if text and text[-1] not in "。！？" else "")

    def _contains_emoji(self, text: str) -> bool:
        if not text:
            return False
        emoji_pattern = re.compile(
            "[\U0001F300-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]"
        )
        return bool(emoji_pattern.search(text))

    def _pick_session_emoji(self, session_id: str) -> str:
        if not self._emoji_pool:
            return "😊"
        session = self.session_manager.get_session(session_id)
        if not session:
            return random.choice(self._emoji_pool)
        last_idx = int(session.get_context("last_emoji_idx", -1) or -1)
        candidates = list(range(len(self._emoji_pool)))
        if len(candidates) > 1 and last_idx in candidates:
            candidates.remove(last_idx)
        idx = random.choice(candidates)
        session.set_context("last_emoji_idx", idx)
        return self._emoji_pool[idx]

    def _ensure_emoji(self, text: str, session_id: str = "") -> str:
        text = (text or "").strip()
        if not text:
            text = "姐姐我在呢"

        emoji = self._pick_session_emoji(session_id or "")
        # 统一结尾：去掉尾部多余标点/emoji，避免出现“。😊。”
        ended_question = text.endswith(("?", "？"))
        ended_exclaim = text.endswith(("!", "！"))
        base = re.sub(
            r"[\s。.!?！？…\U0001F300-\U0001FAFF\U00002600-\U000026FF\U00002700-\U000027BF]+$",
            "",
            text
        ).strip()
        if not base:
            base = "姐姐我在呢"

        end_punc = "？" if ended_question else ("！" if ended_exclaim else "。")
        return f"{base}{end_punc}{emoji}"

    def get_quick_reply(self, keyword: str) -> Optional[str]:
        """获取快速回复"""
        return self.knowledge_service.find_answer(keyword, threshold=0.8)

    def set_knowledge_threshold(self, threshold: float):
        """设置知识库匹配阈值"""
        self.knowledge_threshold = max(0.0, min(1.0, threshold))

    def set_use_knowledge_first(self, enabled: bool):
        """设置是否优先使用知识库"""
        self.use_knowledge_first = enabled

    def _has_recent_address_context(self, session: ChatSession) -> bool:
        """近期是否处于地址相关对话上下文"""
        recent = session.get_recent_messages(8)
        for msg in recent:
            text = msg.get("text", "")
            if "门店" in text or "地址" in text or "哪个区" in text or "在哪个城市" in text:
                return True
        return False
