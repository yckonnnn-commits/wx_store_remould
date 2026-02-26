"""
私人客服 Agent
统一负责：强规则决策、知识库命中、LLM规则外补全、媒体决策、记忆更新。
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..data.memory_store import MemoryStore
from ..services.knowledge_service import KnowledgeService
from ..services.llm_service import LLMService


CONTACT_INTENT_KEYWORDS = (
    "微信",
    "微信号",
    "联系电话",
    "电话",
    "手机号",
    "qq",
    "QQ",
    "二维码",
    "外链",
    "邮箱",
    "怎么关注",
    "如何关注",
    "关注客服",
    "联系客服",
    "怎么联系",
    "如何联系",
)

CONTACT_COMPLIANCE_BLOCK_KEYWORDS = (
    "微信",
    "微信号",
    "联系电话",
    "电话",
    "手机号",
    "qq",
    "QQ",
    "二维码",
    "外链",
    "邮箱",
)


DEFAULT_REPLY_TEMPLATES: Dict[str, Any] = {
    "ask_region_r1": "姐姐，您在什么城市/区域呀？方便告诉我吗？我可以帮您针对性推荐门店，我们目前北京朝阳1家、上海5家（静安、人广、虹口、五角场、徐汇）🌹",
    "ask_region_r2": "姐姐，我再帮您确认一下，您现在在哪个城市或区域呀？我按距离给您匹配最近门店～🌹",
    "ask_region_choice": "姐姐您在静安/徐汇/杨浦附近吗？不确定也没关系，告诉我个地标我也能帮您匹配～🌹",
    "ask_region_r1_reset": "姐姐我再帮您快速确认下，您在什么城市或区域呀？我马上按距离给您匹配最近门店～🌹",
    "ask_sh_district_r1": "姐姐您在上海哪个区呀？我帮您匹配最近门店～🌹",
    "ask_sh_district_r2": "姐姐再确认下，您在上海哪个区或附近地标呢？我马上给您对门店～🌹",
    "ask_sh_district_choice": "姐姐您在静安/徐汇/杨浦附近吗？不确定也没关系，告诉我个地标我也能帮您匹配～🌹",
    "ask_sh_district_r1_reset": "姐姐我再确认下，您在上海哪个区呀？我这边马上帮您匹配最近门店～🌹",
    "store_recommend": "姐姐，推荐您去{store_name}，我给您发一张位置图，您跟着图走会更直观～🌹",
    "non_coverage_contact": "姐姐，{region}暂时没有我们的门店，目前假发是需要根据头围和脸型进行私人定制的，您可以看看下面图中画圈圈的地方，会有专门的老师跟您远程鉴定～💗",
    "contact_intro": "姐姐我给您发一张联系方式图，您按图添加后我这边一对一继续跟进您呀😊",
    "contact_followup_1": "姐姐您看下我刚发的联系方式图，按图添加后跟我说一声，我马上接着帮您安排😊",
    "contact_followup_2": "姐姐刚刚那张联系方式图您点开就能看到，添加后回我一句，我立刻继续帮您跟进😊",
    "llm_fallback": "姐姐抱歉，系统现在有点忙，您稍后再发我马上跟进您哦🌹",
    "general_empty": "姐姐我在呢，您告诉我最关心的是价格、佩戴体验还是门店位置呀🌹",
    "repeat_pool": [
        "姐姐我在，您可以继续说下最关心的问题呀🌹",
        "姐姐收到，我帮您一步步梳理最合适的方案呀🌹",
        "姐姐明白，我先把关键点给您讲清楚呀🌹",
    ],
}


@dataclass
class AgentDecision:
    reply_text: str
    intent: str
    route_reason: str
    reply_goal: str
    media_plan: str
    media_items: List[Dict[str, Any]] = field(default_factory=list)
    reply_source: str = "rule"
    rule_id: str = ""
    rule_applied: bool = False
    llm_model: str = ""
    llm_fallback_reason: str = ""


class _SafeDict(dict):
    def __missing__(self, key):
        return ""


class CustomerServiceAgent:
    """客服 Agent 主决策器（规则优先，LLM仅规则外回复）。"""

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        llm_service: LLMService,
        memory_store: MemoryStore,
        images_dir: Path,
        image_categories_path: Path,
        system_prompt_doc_path: Path,
        playbook_doc_path: Path,
        reply_templates_path: Optional[Path] = None,
        media_whitelist_path: Optional[Path] = None,
    ):
        self.knowledge_service = knowledge_service
        self.llm_service = llm_service
        self.memory_store = memory_store

        self.images_dir = images_dir
        self.image_categories_path = image_categories_path
        self.system_prompt_doc_path = system_prompt_doc_path
        self.playbook_doc_path = playbook_doc_path
        self.reply_templates_path = reply_templates_path or (Path("config") / "reply_templates.json")
        self.media_whitelist_path = media_whitelist_path or (Path("config") / "media_whitelist.json")

        self.use_knowledge_first = True
        self.knowledge_threshold = 0.6
        self.memory_ttl_days = 30

        self._address_index: Dict[str, List[str]] = {
            "beijing_chaoyang": [],
            "sh_xuhui": [],
            "sh_jingan": [],
            "sh_hongkou": [],
            "sh_wujiaochang": [],
            "sh_renmin": [],
        }
        self._contact_images: List[str] = []
        self._video_medias: List[str] = []

        self._system_prompt_doc_text = ""
        self._playbook_doc_text = ""
        self._reply_templates: Dict[str, Any] = dict(DEFAULT_REPLY_TEMPLATES)
        self._media_whitelist_sessions: set[str] = set()

        self._dedupe_reply_pool = list(DEFAULT_REPLY_TEMPLATES.get("repeat_pool", []))

        self.reload_prompt_docs()
        self.reload_media_library()
        self.reload_rule_configs()

    def reload_prompt_docs(self) -> bool:
        """重载 system prompt 与 playbook 文档"""
        self._system_prompt_doc_text = self._read_text(self.system_prompt_doc_path)
        self._playbook_doc_text = self._read_text(self.playbook_doc_path)
        return bool(self._system_prompt_doc_text)

    def reload_media_library(self) -> None:
        """重建地址/联系方式/视频素材索引"""
        for key in self._address_index:
            self._address_index[key] = []
        self._contact_images = []
        self._video_medias = []

        if not self.image_categories_path.exists():
            return

        try:
            data = json.loads(self.image_categories_path.read_text(encoding="utf-8"))
        except Exception:
            return

        images_data = data.get("images", {}) or {}

        for raw_name in images_data.get("联系方式", []):
            filename = Path(raw_name).name
            path = self.images_dir / filename
            if path.exists():
                self._contact_images.append(str(path.resolve()))

        for raw_name in images_data.get("视频素材", []):
            filename = Path(raw_name).name
            path = self.images_dir / filename
            if path.exists():
                self._video_medias.append(str(path.resolve()))

        for raw_name in images_data.get("店铺地址", []):
            filename = Path(raw_name).name
            path = self.images_dir / filename
            if not path.exists():
                continue

            full = str(path.resolve())
            if "北京" in filename:
                self._address_index["beijing_chaoyang"].append(full)
            elif "徐汇" in filename:
                self._address_index["sh_xuhui"].append(full)
            elif "静安" in filename:
                self._address_index["sh_jingan"].append(full)
            elif "虹口" in filename:
                self._address_index["sh_hongkou"].append(full)
            elif "五角场" in filename or "杨浦" in filename:
                self._address_index["sh_wujiaochang"].append(full)
            elif "人广" in filename or "人民广场" in filename or "黄浦" in filename or "黄埔" in filename:
                self._address_index["sh_renmin"].append(full)
            else:
                self._address_index["sh_renmin"].append(full)

    def reload_rule_configs(self) -> None:
        """重载规则模板与媒体白名单。"""
        self.knowledge_service.reload_address_config()
        self._reply_templates = dict(DEFAULT_REPLY_TEMPLATES)
        if self.reply_templates_path.exists():
            try:
                loaded = json.loads(self.reply_templates_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._reply_templates.update(loaded)
            except Exception:
                pass

        repeat_pool = self._reply_templates.get("repeat_pool")
        if isinstance(repeat_pool, list):
            pool = [str(x).strip() for x in repeat_pool if str(x).strip()]
            self._dedupe_reply_pool = pool or list(DEFAULT_REPLY_TEMPLATES.get("repeat_pool", []))
        else:
            self._dedupe_reply_pool = list(DEFAULT_REPLY_TEMPLATES.get("repeat_pool", []))

        self._media_whitelist_sessions = set()
        if self.media_whitelist_path.exists():
            try:
                loaded = json.loads(self.media_whitelist_path.read_text(encoding="utf-8"))
                session_ids = loaded.get("session_ids", []) if isinstance(loaded, dict) else []
                if isinstance(session_ids, list):
                    self._media_whitelist_sessions = {str(x).strip() for x in session_ids if str(x).strip()}
            except Exception:
                self._media_whitelist_sessions = set()

    def decide(
        self,
        session_id: str,
        user_name: str,
        latest_user_text: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> AgentDecision:
        """主决策入口"""
        self.memory_store.prune_expired(ttl_days=self.memory_ttl_days)

        user_hash = self._hash_user(user_name or session_id)
        session_state = self.memory_store.get_session_state(session_id, user_hash=user_hash)
        user_state = self.memory_store.get_user_state(user_hash)

        text = (latest_user_text or "").strip()
        route = self.knowledge_service.resolve_store_recommendation(text)
        intent = self._detect_intent(text)

        if self._should_apply_rule_decision(text=text, intent=intent, route=route, session_state=session_state):
            decision = self._decide_rule_reply(
                text=text,
                intent=intent,
                route=route,
                session_state=session_state,
            )
        else:
            decision = self._decide_general_reply(
                latest_user_text=text,
                intent=intent,
                route=route,
                conversation_history=conversation_history or [],
                session_state=session_state,
                user_state=user_state,
            )

        decision.media_items = self._plan_media_items(
            session_id=session_id,
            text=text,
            intent=decision.intent,
            route=route,
            route_reason=decision.route_reason,
            media_plan=decision.media_plan,
            session_state=session_state,
            user_state=user_state,
        )
        if not decision.media_items:
            decision.media_plan = "none"

        self.memory_store.update_session_state(
            session_id,
            {
                "last_route_reason": decision.route_reason,
                "last_intent": decision.intent,
                "last_reply_goal": decision.reply_goal,
                "last_detected_region": route.get("detected_region", "") or session_state.get("last_detected_region", ""),
            },
            user_hash=user_hash,
        )
        self.memory_store.save()
        return decision

    def mark_reply_sent(self, session_id: str, user_name: str, reply_text: str) -> Optional[Dict[str, Any]]:
        """文本发送成功后的状态推进；返回需要立即发送的视频媒体（若命中）"""
        user_hash = self._hash_user(user_name or session_id)
        user_state = self.memory_store.get_user_state(user_hash)
        normalized = self._normalize_for_dedupe(reply_text)

        recent_hashes = list(user_state.get("recent_reply_hashes", []) or [])
        if normalized:
            recent_hashes.append(normalized)
        if len(recent_hashes) > 40:
            recent_hashes = recent_hashes[-40:]
        user_state["recent_reply_hashes"] = recent_hashes

        if user_state.get("video_armed") and not user_state.get("video_sent"):
            user_state["post_contact_reply_count"] = int(user_state.get("post_contact_reply_count", 0) or 0) + 1
            if int(user_state.get("post_contact_reply_count", 0)) >= 2:
                video_path = self._pick_video_media()
                if video_path:
                    user_state["video_armed"] = False
                    user_state["post_contact_reply_count"] = 0
                    self.memory_store.update_user_state(user_hash, user_state)
                    self.memory_store.save()
                    return {
                        "type": "delayed_video",
                        "path": video_path,
                    }

        self.memory_store.update_user_state(user_hash, user_state)
        self.memory_store.save()
        return None

    def mark_media_sent(self, session_id: str, user_name: str, media_item: Dict[str, Any], success: bool) -> None:
        """媒体发送回执"""
        if not success or not media_item:
            return

        user_hash = self._hash_user(user_name or session_id)
        session_state = self.memory_store.get_session_state(session_id, user_hash=user_hash)
        user_state = self.memory_store.get_user_state(user_hash)

        media_type = media_item.get("type", "")

        if media_type == "address_image":
            sent_count = int(session_state.get("address_image_sent_count", 0) or 0)
            session_state["address_image_sent_count"] = sent_count + 1
            stores = set(session_state.get("sent_address_stores", []) or [])
            target_store = media_item.get("target_store", "")
            if target_store:
                stores.add(target_store)
            session_state["sent_address_stores"] = list(stores)

        elif media_type == "contact_image":
            sent_count = int(session_state.get("contact_image_sent_count", 0) or 0)
            session_state["contact_image_sent_count"] = sent_count + 1
            session_state["contact_warmup"] = False
            session_state["last_geo_pending"] = False

            user_state["video_armed"] = True
            user_state["post_contact_reply_count"] = 0

        elif media_type == "delayed_video":
            user_state["video_sent"] = True
            user_state["video_armed"] = False
            user_state["post_contact_reply_count"] = 0

        self.memory_store.update_session_state(session_id, session_state, user_hash=user_hash)
        self.memory_store.update_user_state(user_hash, user_state)
        self.memory_store.save()

    def set_options(self, use_knowledge_first: bool, knowledge_threshold: float) -> None:
        self.use_knowledge_first = bool(use_knowledge_first)
        self.knowledge_threshold = max(0.0, min(1.0, float(knowledge_threshold)))

    def get_status(self) -> Dict[str, Any]:
        """给 UI 的状态快照"""
        return {
            "use_knowledge_first": self.use_knowledge_first,
            "knowledge_threshold": self.knowledge_threshold,
            "memory_ttl_days": self.memory_ttl_days,
            "system_prompt_loaded": bool(self._system_prompt_doc_text),
            "playbook_loaded": bool(self._playbook_doc_text),
            "address_image_count": sum(len(v) for v in self._address_index.values()),
            "contact_image_count": len(self._contact_images),
            "video_media_count": len(self._video_medias),
            "template_loaded": bool(self._reply_templates),
            "media_whitelist_count": len(self._media_whitelist_sessions),
        }

    def _detect_intent(self, text: str) -> str:
        if self.knowledge_service.is_address_query(text):
            return "address"
        if self.knowledge_service.is_purchase_intent(text):
            return "purchase"
        if any(k in (text or "") for k in CONTACT_INTENT_KEYWORDS):
            return "contact"
        return "general"

    def _should_apply_rule_decision(
        self,
        text: str,
        intent: str,
        route: Dict[str, Any],
        session_state: Dict[str, Any],
    ) -> bool:
        route_type = route.get("route_type", "unknown")
        if route_type in ("coverage", "non_coverage", "need_district"):
            return True
        if intent in ("address", "purchase"):
            return True
        if bool(session_state.get("last_geo_pending", False)) and self._looks_like_geo_reply(text=text, route=route):
            return True
        return False

    def _looks_like_geo_reply(self, text: str, route: Dict[str, Any]) -> bool:
        reason = route.get("reason", "unknown")
        if reason != "unknown":
            return True

        normalized = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]", "", (text or ""))
        if not normalized:
            return False

        geo_tokens = (
            "北京", "上海", "徐汇", "静安", "虹口", "杨浦", "五角场", "人广", "人民广场",
            "河北", "天津", "内蒙古", "江苏", "浙江", "苏州", "杭州", "东北", "省", "市", "区", "县", "州", "盟", "旗"
        )
        return any(token in normalized for token in geo_tokens)

    def _decide_rule_reply(
        self,
        text: str,
        intent: str,
        route: Dict[str, Any],
        session_state: Dict[str, Any],
    ) -> AgentDecision:
        reason = route.get("reason", "unknown")
        target_store = route.get("target_store", "unknown")

        if target_store != "unknown":
            store = self.knowledge_service.get_store_display(target_store)
            store_name = store.get("store_name", "门店")
            session_state["last_geo_pending"] = False
            session_state["geo_followup_round"] = 0
            session_state["geo_choice_offered"] = False
            return AgentDecision(
                reply_text=self._render_template("store_recommend", store_name=store_name),
                intent="address",
                route_reason=reason,
                reply_goal="解答",
                media_plan="address_image",
                reply_source="rule",
                rule_id="ADDR_STORE_RECOMMEND",
                rule_applied=True,
            )

        if reason == "shanghai_need_district":
            return self._build_geo_followup_decision(session_state=session_state, route_reason="need_district", intent="address")

        if reason == "out_of_coverage":
            region = route.get("detected_region") or route_region(reason, text) or session_state.get("last_detected_region", "") or "您所在地区"
            session_state["last_geo_pending"] = False
            session_state["geo_followup_round"] = 0
            session_state["geo_choice_offered"] = False
            return AgentDecision(
                reply_text=self._render_template("non_coverage_contact", region=region),
                intent="purchase" if intent == "purchase" else "address",
                route_reason="out_of_coverage",
                reply_goal="推进购买意图",
                media_plan="contact_image",
                reply_source="rule",
                rule_id="ADDR_OUT_OF_COVERAGE",
                rule_applied=True,
            )

        # address / purchase 未识别到地区：进入 2次追问 + 1次选择题
        return self._build_geo_followup_decision(session_state=session_state, route_reason="need_region", intent=intent)

    def _build_geo_followup_decision(self, session_state: Dict[str, Any], route_reason: str, intent: str) -> AgentDecision:
        round_count = int(session_state.get("geo_followup_round", 0) or 0)
        choice_offered = bool(session_state.get("geo_choice_offered", False))

        if round_count < 2:
            next_round = round_count + 1
            session_state["geo_followup_round"] = next_round
            session_state["geo_choice_offered"] = False
            session_state["last_geo_pending"] = True
            if route_reason == "need_district":
                template_key = "ask_sh_district_r1" if next_round == 1 else "ask_sh_district_r2"
                rule_id = f"ADDR_ASK_DISTRICT_R{next_round}"
            else:
                template_key = "ask_region_r1" if next_round == 1 else "ask_region_r2"
                rule_id = f"ADDR_ASK_REGION_R{next_round}"
        elif not choice_offered:
            session_state["geo_choice_offered"] = True
            session_state["last_geo_pending"] = True
            template_key = "ask_sh_district_choice" if route_reason == "need_district" else "ask_region_choice"
            rule_id = "ADDR_ASK_DISTRICT_CHOICE" if route_reason == "need_district" else "ADDR_ASK_REGION_CHOICE"
        else:
            # 用户持续地址/购买类但仍不给地区，重置到下一轮 2+1 循环
            session_state["geo_followup_round"] = 1
            session_state["geo_choice_offered"] = False
            session_state["last_geo_pending"] = True
            template_key = "ask_sh_district_r1_reset" if route_reason == "need_district" else "ask_region_r1_reset"
            rule_id = "ADDR_ASK_DISTRICT_R1_RESET" if route_reason == "need_district" else "ADDR_ASK_REGION_R1_RESET"

        out_intent = intent if intent in ("address", "purchase") else "address"
        return AgentDecision(
            reply_text=self._render_template(template_key),
            intent=out_intent,
            route_reason=route_reason,
            reply_goal="追问地区",
            media_plan="none",
            reply_source="rule",
            rule_id=rule_id,
            rule_applied=True,
        )

    def _decide_general_reply(
        self,
        latest_user_text: str,
        intent: str,
        route: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        session_state: Dict[str, Any],
        user_state: Dict[str, Any],
    ) -> AgentDecision:
        route_reason = route.get("reason", "unknown")
        contact_sent = int(session_state.get("contact_image_sent_count", 0) or 0) >= 1

        if intent == "contact":
            if contact_sent:
                prompt_count = int(session_state.get("contact_followup_prompt_count", 0) or 0)
                session_state["contact_followup_prompt_count"] = prompt_count + 1
                template_key = "contact_followup_1" if (prompt_count % 2) == 0 else "contact_followup_2"
                return AgentDecision(
                    reply_text=self._render_template(template_key),
                    intent="contact",
                    route_reason=route_reason,
                    reply_goal="推进购买意图",
                    media_plan="none",
                    reply_source="rule",
                    rule_id="CONTACT_FOLLOWUP",
                    rule_applied=True,
                )
            return AgentDecision(
                reply_text=self._render_template("contact_intro"),
                intent="contact",
                route_reason=route_reason,
                reply_goal="推进购买意图",
                media_plan="contact_image",
                reply_source="rule",
                rule_id="CONTACT_SEND_IMAGE",
                rule_applied=True,
            )

        # 规则外：先知识库，未命中再 LLM
        if self.use_knowledge_first:
            kb_answer = self.knowledge_service.find_answer(
                latest_user_text,
                threshold=self.knowledge_threshold,
            )
            if kb_answer:
                return AgentDecision(
                    reply_text=self._normalize_reply_text(kb_answer),
                    intent=intent,
                    route_reason=route_reason,
                    reply_goal="解答",
                    media_plan="none",
                    reply_source="knowledge",
                    rule_id="KB_MATCH",
                    rule_applied=False,
                )

        composed_prompt = self._build_general_llm_prompt(latest_user_text)
        self.llm_service.set_system_prompt(composed_prompt)
        success, result = self.llm_service.generate_reply_sync(
            user_message=latest_user_text,
            conversation_history=conversation_history,
        )
        model_name = self.llm_service.get_current_model_name()
        if not success:
            return AgentDecision(
                reply_text=self._render_template("llm_fallback"),
                intent=intent,
                route_reason=route_reason,
                reply_goal="解答",
                media_plan="none",
                reply_source="fallback",
                rule_id="LLM_FALLBACK",
                rule_applied=False,
                llm_model=model_name,
                llm_fallback_reason=str(result or ""),
            )

        llm_reply = self._normalize_reply_text(result)
        llm_reply = self._avoid_repeat(user_state, llm_reply)

        return AgentDecision(
            reply_text=llm_reply,
            intent=intent,
            route_reason=route_reason,
            reply_goal="解答",
            media_plan="none",
            reply_source="llm",
            rule_id="LLM_GENERAL",
            rule_applied=False,
            llm_model=model_name,
        )

    def _plan_media_items(
        self,
        session_id: str,
        text: str,
        intent: str,
        route: Dict[str, Any],
        route_reason: str,
        media_plan: str,
        session_state: Dict[str, Any],
        user_state: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        target_store = route.get("target_store", "unknown")
        reason = route_reason or route.get("reason", "unknown")

        if media_plan == "address_image" and target_store != "unknown":
            item = self._queue_address_image(session_id=session_id, session_state=session_state, target_store=target_store)
            if item:
                items.append(item)

        if media_plan == "contact_image" and not items:
            item = self._queue_contact_image(
                session_id=session_id,
                text=text,
                intent=intent,
                reason=reason,
                route=route,
                session_state=session_state,
            )
            if item:
                items.append(item)

        # delayed_video 不即时发送，仍由发送回执推进。
        if media_plan == "delayed_video" and not user_state.get("video_sent"):
            user_state["video_armed"] = True
            user_state["post_contact_reply_count"] = 0

        return items

    def _queue_address_image(self, session_id: str, session_state: Dict[str, Any], target_store: str) -> Optional[Dict[str, Any]]:
        whitelist = self._is_media_whitelist_session(session_id)

        if not whitelist:
            sent_count = int(session_state.get("address_image_sent_count", 0) or 0)
            if sent_count >= 6:
                return None

            sent_stores = set(session_state.get("sent_address_stores", []) or [])
            if target_store in sent_stores:
                return None

        image_path = self._pick_address_image(target_store)
        if not image_path:
            return None

        return {
            "type": "address_image",
            "path": image_path,
            "target_store": target_store,
        }

    def _queue_contact_image(
        self,
        session_id: str,
        text: str,
        intent: str,
        reason: str,
        route: Dict[str, Any],
        session_state: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if not self._contact_images:
            return None

        whitelist = self._is_media_whitelist_session(session_id)
        sent_count = int(session_state.get("contact_image_sent_count", 0) or 0)
        if not whitelist and sent_count >= 1:
            return None

        if reason == "out_of_coverage" or intent == "contact":
            return {
                "type": "contact_image",
                "path": random.choice(self._contact_images),
                "region": route.get("detected_region", "") or route_region(reason, text),
            }

        return None

    def _pick_address_image(self, target_store: str) -> Optional[str]:
        pool = self._address_index.get(target_store, [])
        if not pool and target_store.startswith("sh_"):
            pool = self._address_index.get("sh_renmin", [])
        if not pool and target_store == "beijing_chaoyang":
            pool = self._address_index.get("beijing_chaoyang", [])
        if not pool:
            return None
        return random.choice(pool)

    def _pick_video_media(self) -> Optional[str]:
        if not self._video_medias:
            return None
        return random.choice(self._video_medias)

    def _is_media_whitelist_session(self, session_id: str) -> bool:
        return session_id in self._media_whitelist_sessions

    def _build_general_llm_prompt(self, latest_user_text: str) -> str:
        kb_examples = self._top_kb_examples(latest_user_text, limit=3)
        kb_block = "\n".join([f"- 问：{q}\n  答：{a}" for q, a in kb_examples])

        return (
            "你是艾耐儿私域客服助手。\n"
            "你只负责补充规则外的一般问答，不做任何地址/媒体/流程决策。\n"
            "语气要自然、亲切、专业，面向中老年假发咨询场景。\n"
            "回复要求：1-2句中文，简洁，不要编造价格活动，不要输出联系方式信息。\n\n"
            f"【品牌系统提示词参考】\n{self._system_prompt_doc_text}\n\n"
            f"【客服话术参考】\n{self._playbook_doc_text}\n\n"
            f"【知识库参考】\n{kb_block}\n\n"
            "仅输出最终客服话术纯文本，不要输出JSON、代码块或解释。"
        )

    def _top_kb_examples(self, query: str, limit: int = 3) -> List[Tuple[str, str]]:
        q = self._normalize_for_dedupe(query)
        if not q:
            return []

        scored: List[Tuple[float, Tuple[str, str]]] = []
        items = self.knowledge_service.get_all_items()
        for item in items:
            question = (item.question or "").strip()
            answer = (item.answer or "").strip()
            if not question or not answer:
                continue
            score = self._simple_overlap_score(q, self._normalize_for_dedupe(question))
            if score > 0:
                scored.append((score, (question, answer)))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[:limit]]

    def _simple_overlap_score(self, a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        if a in b or b in a:
            return 0.9
        sa = set(a)
        sb = set(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _normalize_reply_text(self, text: str) -> str:
        value = (text or "").strip()
        if not value:
            return self._render_template("general_empty")

        value = re.sub(r"\s*\d{1,2}:\d{2}\S*$", "", value)
        value = " ".join(value.split())

        # 联系方式合规拦截
        if any(k in value for k in CONTACT_COMPLIANCE_BLOCK_KEYWORDS):
            value = "姐姐我们先在这里沟通就好，我先帮您把需求和方案梳理清楚呀🌹"

        if len(value) > 130:
            value = value[:130].rstrip() + "..."

        if value and value[-1] not in "。！？":
            value += "。"

        return value

    def _avoid_repeat(self, user_state: Dict[str, Any], reply_text: str) -> str:
        normalized = self._normalize_for_dedupe(reply_text)
        if not normalized:
            return reply_text

        previous = set(user_state.get("recent_reply_hashes", []) or [])
        if normalized in previous and self._dedupe_reply_pool:
            return random.choice(self._dedupe_reply_pool)
        return reply_text

    def _normalize_for_dedupe(self, text: str) -> str:
        value = (text or "").strip().lower()
        value = re.sub(r"[^\w\u4e00-\u9fa5]", "", value)
        return value

    def _hash_user(self, text: str) -> str:
        return hashlib.md5((text or "unknown").encode("utf-8", errors="ignore")).hexdigest()[:10]

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""

    def _render_template(self, key: str, **kwargs: Any) -> str:
        template = self._reply_templates.get(key)
        if not isinstance(template, str) or not template.strip():
            template = DEFAULT_REPLY_TEMPLATES.get(key, "")
        text = str(template or "").format_map(_SafeDict(kwargs))
        text = " ".join(text.split())
        if not text:
            return self._render_template("general_empty") if key != "general_empty" else "姐姐我在呢🌹"
        return text


def route_region(route_reason: str, text: str) -> str:
    if route_reason != "out_of_coverage":
        return ""
    m = re.search(r"([\u4e00-\u9fa5]{2,8}(?:省|市|区|县|州|盟|旗))", text or "")
    return m.group(1) if m else ""
