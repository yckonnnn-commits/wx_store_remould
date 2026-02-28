"""
私人客服 Agent
统一负责：强规则决策、知识库命中、LLM规则外补全、媒体决策、记忆更新。
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import datetime, timedelta
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

NEG_SHANGHAI_HINT_KEYWORDS = (
    "不在上海",
    "不是上海",
    "不去上海",
)

SHIPPING_BLOCK_KEYWORDS = (
    "包邮",
    "快递",
    "邮寄",
    "到家",
)
SHIPPING_BLOCK_REPLACEMENT = "姐姐我们是到店定制哦"
DEFAULT_REPLY_EMOJI = "🌹"
ENTERPRISE_GUARD_DOC_PATH = Path("docs") / "llm_enterprise_knowledge_guard_v1.md"


DEFAULT_REPLY_TEMPLATES: Dict[str, Any] = {
    "ask_region_r1": "姐姐，您在什么城市/区域呀？方便告诉我吗？我可以帮您针对性推荐门店，我们目前北京朝阳1家、上海5家（静安、人广、虹口、五角场、徐汇）🌹",
    "ask_region_r2": "姐姐，我再帮您确认一下，您现在在哪个城市或区域呀？我按距离给您匹配最近门店～🌹",
    "ask_region_choice": "姐姐您在上海吗？不确定也没关系，告诉我个地标我也能帮您匹配～🌹",
    "ask_region_r1_reset": "姐姐我再帮您快速确认下，您在什么城市或区域呀？我马上按距离给您匹配最近门店～🌹",
    "ask_sh_district_r1": "姐姐您在上海哪个区呀？我帮您匹配最近门店～🌹",
    "ask_sh_district_r2": "姐姐再确认下，您在上海哪个区或附近地标呢？我马上给您对门店～🌹",
    "ask_sh_district_choice": "姐姐您在静安/徐汇/杨浦附近吗？不确定也没关系，告诉我个地标我也能帮您匹配～🌹",
    "ask_sh_district_r1_reset": "姐姐我再确认下，您在上海哪个区呀？我这边马上帮您匹配最近门店～🌹",
    "store_recommend": "姐姐，推荐您去{store_name}，可以看下面的红框框，您跟着图走会更直观，但是一定要预约哦～🌹",
    "non_coverage_contact": "姐姐，{region}暂时没有我们的门店，目前假发是需要根据头围和脸型进行私人定制的，您可以看看下面图中画圈圈的地方，会有专门的老师跟您远程鉴定～💗",
    "contact_intro": "姐姐可以看下红框框的内容，您按图添加后我这边一对一继续跟进您呀😊",
    "purchase_contact_intro": "姐姐可以看看图中画框框的地方，会有专门的老师给您介绍～❤️",
    "purchase_contact_remind_only": "姐姐，请注意一下上面图中的圈圈位置哦，可以详细给您介绍怎么买～💗",
    "purchase_contact_remote_remind_only": "姐姐，您可以往上看看图中画圈的地方，我让老师一对一跟您远程定制❤️",
    "strong_intent_after_both_first": "姐姐，您可以看上面的画圈圈地方，我让老师跟您预约～💗",
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

ADDRESS_IMAGE_COOLDOWN_HOURS = 24


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
    geo_context_source: str = ""
    media_skip_reason: str = ""
    both_images_sent_state: bool = False
    kb_match_score: float = 0.0
    kb_match_question: str = ""
    kb_match_mode: str = ""
    kb_item_id: str = ""
    kb_variant_total: int = 0
    kb_variant_selected_index: int = -1
    kb_variant_fallback_llm: bool = False
    kb_confident: bool = False
    kb_blocked_by_polite_guard: bool = False
    kb_polite_guard_reason: str = ""
    is_first_turn_global: bool = False
    first_turn_media_guard_applied: bool = False
    kb_repeat_rewritten: bool = False
    purchase_both_first_hint_sent: bool = False
    video_trigger_user_count: int = 0


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
        conversation_log_dir: Optional[Path] = None,
    ):
        self.knowledge_service = knowledge_service
        self.llm_service = llm_service
        self.memory_store = memory_store

        self.images_dir = images_dir
        self.image_categories_path = image_categories_path
        self.system_prompt_doc_path = system_prompt_doc_path
        self.playbook_doc_path = playbook_doc_path
        self.enterprise_guard_doc_path = ENTERPRISE_GUARD_DOC_PATH
        self.reply_templates_path = reply_templates_path or (Path("config") / "reply_templates.json")
        self.media_whitelist_path = media_whitelist_path or (Path("config") / "media_whitelist.json")
        self.conversation_log_dir = conversation_log_dir or (Path("data") / "conversations")

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
        self._enterprise_guard_doc_text = ""
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
        self._enterprise_guard_doc_text = self._read_text(self.enterprise_guard_doc_path)
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

        # 视频素材兜底：配置文件名变更时按目录模糊匹配，再回退到任意视频文件。
        if not self._video_medias and self.images_dir.exists():
            all_files = [p for p in self.images_dir.iterdir() if p.is_file()]
            preferred = [
                p for p in all_files
                if p.suffix.lower() in (".mp4", ".mov", ".m4v") and ("预约" in p.name or "视频" in p.name)
            ]
            if not preferred:
                preferred = [p for p in all_files if p.suffix.lower() in (".mp4", ".mov", ".m4v")]
            self._video_medias = [str(p.resolve()) for p in preferred if p.exists()]

        if self._video_medias:
            # 去重，保留顺序
            self._video_medias = list(dict.fromkeys(self._video_medias))

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
        is_first_turn_global = self.is_user_first_turn_global(user_id_hash=user_hash)
        self._sync_media_state_from_conversation_log(
            session_id=session_id,
            user_hash=user_hash,
            session_state=session_state,
        )

        text = (latest_user_text or "").strip()
        route = self.knowledge_service.resolve_store_recommendation(text)
        intent = self._detect_intent(text)

        if self._should_apply_rule_decision(text=text, intent=intent, route=route, session_state=session_state):
            decision = self._decide_rule_reply(
                text=text,
                intent=intent,
                route=route,
                session_state=session_state,
                conversation_history=conversation_history or [],
                user_state=user_state,
                is_first_turn_global=is_first_turn_global,
            )
        else:
            decision = self._decide_general_reply(
                latest_user_text=text,
                intent=intent,
                route=route,
                conversation_history=conversation_history or [],
                session_state=session_state,
                user_state=user_state,
                user_id_hash=user_hash,
            )

        copy_lock_rule_ids = {
            "PURCHASE_CONTACT_FROM_KNOWN_GEO",
            "PURCHASE_REMOTE_CONTACT_IMAGE",
            "PURCHASE_REMOTE_CONTACT_REMIND_ONLY",
            "ADDR_OUT_OF_COVERAGE",
            "ADDR_STORE_RECOMMEND",
            "CONTACT_SEND_IMAGE",
        }
        should_rewrite = (
            decision.reply_source in ("llm", "fallback")
            and decision.rule_id not in copy_lock_rule_ids
        )
        if should_rewrite:
            knowledge_reply_count = int(session_state.get("knowledge_reply_count", 0) or 0)
            rewritten_text, _ = self._rewrite_if_repeated(
                reply_text=decision.reply_text,
                latest_user_text=text,
                conversation_history=conversation_history or [],
                user_state=user_state,
                user_id_hash=user_hash,
            )
            decision.reply_text = rewritten_text
            decision.kb_repeat_rewritten = False
        else:
            knowledge_reply_count = int(session_state.get("knowledge_reply_count", 0) or 0)

        decision.purchase_both_first_hint_sent = bool(
            session_state.get("purchase_both_first_hint_sent", False)
        )
        decision.is_first_turn_global = bool(is_first_turn_global)
        both_images_sent = self._has_both_images_sent(session_state)
        decision.both_images_sent_state = both_images_sent
        decision.video_trigger_user_count = int(session_state.get("session_user_message_count_after_contact", 0) or 0)

        original_media_plan = decision.media_plan
        media_items, media_skip_reason = self._plan_media_items(
            session_id=session_id,
            text=text,
            intent=decision.intent,
            route=route,
            route_reason=decision.route_reason,
            media_plan=original_media_plan,
            session_state=session_state,
            user_state=user_state,
            is_first_turn_global=is_first_turn_global,
        )
        decision.media_items = media_items
        decision.media_skip_reason = media_skip_reason
        decision.first_turn_media_guard_applied = bool(
            is_first_turn_global
            and original_media_plan in ("address_image", "contact_image")
            and media_skip_reason == "first_turn_global_no_media"
        )
        if not decision.media_items:
            decision.media_plan = "none"

        now = datetime.now().isoformat()
        target_store = route.get("target_store", "unknown")
        detected_region = route.get("detected_region", "") or ""
        next_knowledge_reply_count = knowledge_reply_count + (1 if decision.reply_source == "knowledge" else 0)
        self.memory_store.update_session_state(
            session_id,
            {
                "last_route_reason": decision.route_reason,
                "last_intent": decision.intent,
                "last_reply_goal": decision.reply_goal,
                "last_detected_region": detected_region or session_state.get("last_detected_region", ""),
                "last_target_store": target_store if target_store != "unknown" else session_state.get("last_target_store", ""),
                "last_geo_route_reason": route.get("reason", "unknown") if (target_store != "unknown" or detected_region) else session_state.get("last_geo_route_reason", "unknown"),
                "last_geo_updated_at": now if (target_store != "unknown" or detected_region) else session_state.get("last_geo_updated_at", ""),
                "knowledge_reply_count": next_knowledge_reply_count,
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

        session_video = self.summarize_session_video_from_log(session_id=session_id)
        if session_video.get("contact_sent") and not session_video.get("video_sent"):
            user_messages_after_contact = int(session_video.get("user_message_count_after_contact", 0) or 0)
            if user_messages_after_contact >= 2:
                video_path = self._pick_video_media()
                if video_path:
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
        now = datetime.now().isoformat()

        media_type = media_item.get("type", "")

        if media_type == "address_image":
            sent_count = int(session_state.get("address_image_sent_count", 0) or 0)
            session_state["address_image_sent_count"] = sent_count + 1
            stores = set(session_state.get("sent_address_stores", []) or [])
            target_store = media_item.get("target_store", "")
            if target_store:
                stores.add(target_store)
                sent_map = session_state.get("address_image_last_sent_at_by_store", {}) or {}
                if not isinstance(sent_map, dict):
                    sent_map = {}
                sent_map[target_store] = now
                session_state["address_image_last_sent_at_by_store"] = sent_map
                session_state["last_target_store"] = target_store
            session_state["sent_address_stores"] = list(stores)

        elif media_type == "contact_image":
            sent_count = int(session_state.get("contact_image_sent_count", 0) or 0)
            session_state["contact_image_sent_count"] = sent_count + 1
            session_state["contact_image_last_sent_at"] = now
            session_state["contact_warmup"] = False
            session_state["last_geo_pending"] = False

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

    def _resolve_geo_context(self, route: Dict[str, Any], session_state: Dict[str, Any]) -> Dict[str, Any]:
        target_store = route.get("target_store", "unknown")
        detected_region = route.get("detected_region", "") or ""
        if target_store and target_store != "unknown":
            return {
                "known": True,
                "source": "route_target_store",
                "target_store": target_store,
                "region": detected_region,
            }
        if detected_region:
            return {
                "known": True,
                "source": "route_detected_region",
                "target_store": session_state.get("last_target_store", ""),
                "region": detected_region,
            }

        last_target_store = session_state.get("last_target_store", "")
        if last_target_store and last_target_store != "unknown":
            return {
                "known": True,
                "source": "session_last_target_store",
                "target_store": last_target_store,
                "region": session_state.get("last_detected_region", ""),
            }

        last_region = session_state.get("last_detected_region", "")
        if last_region:
            return {
                "known": True,
                "source": "session_last_detected_region",
                "target_store": "",
                "region": last_region,
            }

        if int(session_state.get("address_image_sent_count", 0) or 0) > 0:
            return {
                "known": True,
                "source": "session_address_image_history",
                "target_store": "",
                "region": "",
            }

        return {
            "known": False,
            "source": "",
            "target_store": "",
            "region": "",
        }

    def _decide_rule_reply(
        self,
        text: str,
        intent: str,
        route: Dict[str, Any],
        session_state: Dict[str, Any],
        conversation_history: List[Dict[str, str]],
        user_state: Dict[str, Any],
        is_first_turn_global: bool = False,
    ) -> AgentDecision:
        reason = route.get("reason", "unknown")
        target_store = route.get("target_store", "unknown")
        geo_context = self._resolve_geo_context(route, session_state)
        both_images_sent = self._has_both_images_sent(session_state)
        neg_shanghai_hint = self._has_neg_shanghai_hint(text)

        if is_first_turn_global and intent == "purchase" and reason in ("unknown", "need_region"):
            return self._build_geo_followup_decision(session_state=session_state, route_reason="need_region", intent="purchase")

        if reason == "shanghai_need_district":
            return self._build_geo_followup_decision(session_state=session_state, route_reason="need_district", intent="address")

        # “不在上海怎么买”优先走远程联系方式逻辑，避免被历史上海门店上下文误导。
        if (
            intent == "purchase"
            and neg_shanghai_hint
            and geo_context.get("known")
            and not (reason == "out_of_coverage" and route.get("detected_region"))
        ):
            session_state["last_geo_pending"] = False
            session_state["geo_followup_round"] = 0
            session_state["geo_choice_offered"] = False
            if self._is_contact_image_sent_for_current_geo(session_state):
                return AgentDecision(
                    reply_text=self._render_template("purchase_contact_remote_remind_only"),
                    intent="purchase",
                    route_reason="not_in_shanghai_remote",
                    reply_goal="推进购买意图",
                    media_plan="none",
                    reply_source="rule",
                    rule_id="PURCHASE_REMOTE_CONTACT_REMIND_ONLY",
                    rule_applied=True,
                    geo_context_source=geo_context.get("source", ""),
                )
            return AgentDecision(
                reply_text=self._render_template("purchase_contact_intro"),
                intent="purchase",
                route_reason="not_in_shanghai_remote",
                reply_goal="推进购买意图",
                media_plan="contact_image",
                reply_source="rule",
                rule_id="PURCHASE_REMOTE_CONTACT_IMAGE",
                rule_applied=True,
                geo_context_source=geo_context.get("source", ""),
            )

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
                geo_context_source=geo_context.get("source", ""),
            )

        # 北方（天津/河北/内蒙古）默认走北京门店地址导向；
        # 若已发过联系方式图，则优先固定“画圈”提醒，避免偏航到包邮话术。
        if reason == "north_fallback_beijing" and intent in ("purchase", "address"):
            session_state["last_geo_pending"] = False
            session_state["geo_followup_round"] = 0
            session_state["geo_choice_offered"] = False
            if self._is_contact_image_sent_for_current_geo(session_state):
                return AgentDecision(
                    reply_text=self._render_template("purchase_contact_remote_remind_only"),
                    intent="purchase",
                    route_reason=reason,
                    reply_goal="推进购买意图",
                    media_plan="none",
                    reply_source="rule",
                    rule_id="PURCHASE_REMOTE_CONTACT_REMIND_ONLY",
                    rule_applied=True,
                    geo_context_source=geo_context.get("source", ""),
                )

            store = self.knowledge_service.get_store_display("beijing_chaoyang")
            store_name = store.get("store_name", "北京朝阳门店")
            return AgentDecision(
                reply_text=self._render_template("store_recommend", store_name=store_name),
                intent="address",
                route_reason=reason,
                reply_goal="解答",
                media_plan="address_image",
                reply_source="rule",
                rule_id="ADDR_STORE_RECOMMEND",
                rule_applied=True,
                geo_context_source=geo_context.get("source", ""),
            )

        if intent == "purchase" and reason != "shanghai_need_district" and geo_context.get("known") and both_images_sent:
            strong_count = int(session_state.get("strong_intent_after_both_count", 0) or 0)
            session_state["strong_intent_after_both_count"] = strong_count + 1
            hint_sent = bool(session_state.get("purchase_both_first_hint_sent", False))
            if not hint_sent:
                session_state["purchase_both_first_hint_sent"] = True
                return AgentDecision(
                    reply_text=self._render_template("strong_intent_after_both_first"),
                    intent="purchase",
                    route_reason=reason if reason != "unknown" else "both_images_lock",
                    reply_goal="推进购买意图",
                    media_plan="none",
                    reply_source="rule",
                    rule_id="PURCHASE_AFTER_BOTH_FIRST_HINT",
                    rule_applied=True,
                    geo_context_source=geo_context.get("source", ""),
                    both_images_sent_state=True,
                    purchase_both_first_hint_sent=True,
                )

            follow_decision = self._decide_general_reply(
                latest_user_text=text,
                intent=intent,
                route=route,
                conversation_history=conversation_history,
                session_state=session_state,
                user_state=user_state,
            )
            follow_decision.media_plan = "none"
            follow_decision.geo_context_source = geo_context.get("source", "")
            follow_decision.both_images_sent_state = True
            follow_decision.purchase_both_first_hint_sent = bool(
                session_state.get("purchase_both_first_hint_sent", False)
            )
            return follow_decision

        if intent == "purchase" and reason != "shanghai_need_district" and geo_context.get("known"):
            contact_sent = self._is_contact_image_sent_for_current_geo(session_state)
            session_state["last_geo_pending"] = False
            session_state["geo_followup_round"] = 0
            session_state["geo_choice_offered"] = False
            if contact_sent:
                return AgentDecision(
                    reply_text=self._render_template("purchase_contact_remind_only"),
                    intent="purchase",
                    route_reason=reason if reason != "unknown" else "known_geo_context",
                    reply_goal="推进购买意图",
                    media_plan="none",
                    reply_source="rule",
                    rule_id="PURCHASE_CONTACT_REMIND_ONLY",
                    rule_applied=True,
                    geo_context_source=geo_context.get("source", ""),
                )

            return AgentDecision(
                reply_text=self._render_template("purchase_contact_intro"),
                intent="purchase",
                route_reason=reason if reason != "unknown" else "known_geo_context",
                reply_goal="推进购买意图",
                media_plan="contact_image",
                reply_source="rule",
                rule_id="PURCHASE_CONTACT_FROM_KNOWN_GEO",
                rule_applied=True,
                geo_context_source=geo_context.get("source", ""),
            )

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
                geo_context_source=geo_context.get("source", ""),
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
        user_id_hash: str = "",
    ) -> AgentDecision:
        route_reason = route.get("reason", "unknown")
        contact_sent = int(session_state.get("contact_image_sent_count", 0) or 0) >= 1
        kb_blocked_by_polite_guard = False
        kb_polite_guard_reason = ""

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
            kb_detail = self.knowledge_service.find_answer_detail(
                latest_user_text,
                threshold=self.knowledge_threshold,
            )
            kb_blocked_by_polite_guard = bool(kb_detail.get("blocked_by_polite_guard", False))
            kb_polite_guard_reason = str(kb_detail.get("polite_guard_reason", "") or "")
            if kb_detail.get("matched"):
                kb_answer = str(kb_detail.get("answer", "") or "").strip()
                kb_answers = [
                    str(x).strip()
                    for x in (kb_detail.get("answers", []) or [])
                    if str(x).strip()
                ]
                if kb_answer and kb_answer not in kb_answers:
                    kb_answers.insert(0, kb_answer)

                selected_answer, selected_index, exhausted = self._select_kb_variant_answer(
                    answers=kb_answers,
                    user_state=user_state,
                    user_id_hash=user_id_hash,
                )
                if selected_answer:
                    return AgentDecision(
                        reply_text=selected_answer,
                        intent=intent,
                        route_reason=route_reason,
                        reply_goal="解答",
                        media_plan="none",
                        reply_source="knowledge",
                        rule_id="KB_MATCH",
                        rule_applied=False,
                        kb_match_score=float(kb_detail.get("score", 0.0) or 0.0),
                        kb_match_question=str(kb_detail.get("question", "") or ""),
                        kb_match_mode=str(kb_detail.get("mode", "") or ""),
                        kb_item_id=str(kb_detail.get("item_id", "") or ""),
                        kb_variant_total=len(kb_answers),
                        kb_variant_selected_index=selected_index,
                        kb_variant_fallback_llm=False,
                        kb_confident=True,
                        kb_blocked_by_polite_guard=False,
                        kb_polite_guard_reason="",
                    )

                if exhausted:
                    rewrite_prompt = self._build_kb_variant_fallback_prompt(
                        latest_user_text=latest_user_text,
                        kb_question=str(kb_detail.get("question", "") or ""),
                        kb_answer=kb_answer or (kb_answers[0] if kb_answers else ""),
                    )
                    return self._decide_llm_reply(
                        latest_user_text=latest_user_text,
                        intent=intent,
                        route_reason=route_reason,
                        conversation_history=conversation_history,
                        kb_blocked_by_polite_guard=False,
                        kb_polite_guard_reason="",
                        user_message_override=rewrite_prompt,
                        rule_id="LLM_KB_VARIANT_FALLBACK",
                        kb_match_score=float(kb_detail.get("score", 0.0) or 0.0),
                        kb_match_question=str(kb_detail.get("question", "") or ""),
                        kb_match_mode=str(kb_detail.get("mode", "") or ""),
                        kb_item_id=str(kb_detail.get("item_id", "") or ""),
                        kb_variant_total=len(kb_answers),
                        kb_variant_selected_index=-1,
                        kb_variant_fallback_llm=True,
                        kb_confident=True,
                    )

        return self._decide_llm_reply(
            latest_user_text=latest_user_text,
            intent=intent,
            route_reason=route_reason,
            conversation_history=conversation_history,
            kb_blocked_by_polite_guard=kb_blocked_by_polite_guard,
            kb_polite_guard_reason=kb_polite_guard_reason,
        )

    def _decide_llm_reply(
        self,
        latest_user_text: str,
        intent: str,
        route_reason: str,
        conversation_history: List[Dict[str, str]],
        kb_blocked_by_polite_guard: bool = False,
        kb_polite_guard_reason: str = "",
        user_message_override: str = "",
        rule_id: str = "LLM_GENERAL",
        kb_match_score: float = 0.0,
        kb_match_question: str = "",
        kb_match_mode: str = "",
        kb_item_id: str = "",
        kb_variant_total: int = 0,
        kb_variant_selected_index: int = -1,
        kb_variant_fallback_llm: bool = False,
        kb_confident: bool = False,
    ) -> AgentDecision:
        composed_prompt = self._build_general_llm_prompt(latest_user_text)
        self.llm_service.set_system_prompt(composed_prompt)
        success, result = self.llm_service.generate_reply_sync(
            user_message=user_message_override or latest_user_text,
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
                kb_match_score=kb_match_score,
                kb_match_question=kb_match_question,
                kb_match_mode=kb_match_mode,
                kb_item_id=kb_item_id,
                kb_variant_total=kb_variant_total,
                kb_variant_selected_index=kb_variant_selected_index,
                kb_variant_fallback_llm=kb_variant_fallback_llm,
                kb_confident=kb_confident,
                kb_blocked_by_polite_guard=kb_blocked_by_polite_guard,
                kb_polite_guard_reason=kb_polite_guard_reason,
            )

        llm_reply = self._normalize_reply_text(result)

        return AgentDecision(
            reply_text=llm_reply,
            intent=intent,
            route_reason=route_reason,
            reply_goal="解答",
            media_plan="none",
            reply_source="llm",
            rule_id=rule_id,
            rule_applied=False,
            llm_model=model_name,
            kb_match_score=kb_match_score,
            kb_match_question=kb_match_question,
            kb_match_mode=kb_match_mode,
            kb_item_id=kb_item_id,
            kb_variant_total=kb_variant_total,
            kb_variant_selected_index=kb_variant_selected_index,
            kb_variant_fallback_llm=kb_variant_fallback_llm,
            kb_confident=kb_confident,
            kb_blocked_by_polite_guard=kb_blocked_by_polite_guard,
            kb_polite_guard_reason=kb_polite_guard_reason,
        )

    def _select_kb_variant_answer(
        self,
        answers: List[str],
        user_state: Dict[str, Any],
        user_id_hash: str = "",
    ) -> Tuple[str, int, bool]:
        candidates: List[str] = []
        seen: set[str] = set()
        for raw in answers or []:
            text = str(raw or "").strip()
            if not text:
                continue
            norm = self._normalize_for_dedupe(text)
            if not norm or norm in seen:
                continue
            seen.add(norm)
            candidates.append(text)
            if len(candidates) >= 5:
                break
        if not candidates:
            return "", -1, False

        previous = self.summarize_recent_assistant_hashes_from_logs(user_id_hash=user_id_hash, limit=80)
        previous |= set(user_state.get("recent_reply_hashes", []) or [])
        for idx, candidate in enumerate(candidates):
            if self._normalize_for_dedupe(candidate) not in previous:
                return candidate, idx, False
        return "", -1, True

    def _build_kb_variant_fallback_prompt(self, latest_user_text: str, kb_question: str, kb_answer: str) -> str:
        return (
            f"用户刚问：{latest_user_text}\n"
            f"命中的知识库问题：{kb_question}\n"
            f"核心结论：{kb_answer}\n"
            "请保持核心结论不变，改写成结论先行、完整自然的客服回复。"
        )

    def _rewrite_if_repeated(
        self,
        reply_text: str,
        latest_user_text: str,
        conversation_history: List[Dict[str, str]],
        user_state: Dict[str, Any],
        user_id_hash: str = "",
    ) -> Tuple[str, bool]:
        normalized = self._normalize_for_dedupe(reply_text)
        if not normalized:
            return reply_text, False

        previous = self.summarize_recent_assistant_hashes_from_logs(user_id_hash=user_id_hash, limit=40)
        memory_hashes = set(user_state.get("recent_reply_hashes", []) or [])
        if memory_hashes:
            previous |= memory_hashes
        if normalized not in previous:
            return reply_text, False

        # 优先让 LLM 改写，最多 2 次；仍重复则走去重池兜底。
        rewrite_prompt = (
            f"用户刚问：{latest_user_text}\n"
            f"下面这句客服话术和历史重复，请保留核心意思但换一种自然表达：{reply_text}"
        )
        composed_prompt = self._build_general_llm_prompt(latest_user_text)
        self.llm_service.set_system_prompt(composed_prompt)

        for _ in range(2):
            ok, result = self.llm_service.generate_reply_sync(
                user_message=rewrite_prompt,
                conversation_history=conversation_history,
            )
            if not ok:
                continue
            candidate = self._normalize_reply_text(result)
            if self._normalize_for_dedupe(candidate) not in previous:
                return candidate, True
            rewrite_prompt = f"仍重复，请再次改写这句客服回复：{candidate}"

        fallback = self._avoid_repeat(user_state, reply_text)
        return fallback, self._normalize_for_dedupe(fallback) != normalized

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
        is_first_turn_global: bool = False,
    ) -> Tuple[List[Dict[str, Any]], str]:
        items: List[Dict[str, Any]] = []
        skip_reason = ""
        target_store = route.get("target_store", "unknown")
        reason = route_reason or route.get("reason", "unknown")
        detected_region = route.get("detected_region", "") or ""

        if is_first_turn_global and media_plan in ("address_image", "contact_image"):
            return [], "first_turn_global_no_media"

        if media_plan == "address_image":
            if target_store == "unknown":
                skip_reason = "address_target_unknown"
            item, reason_hint = self._queue_address_image(
                session_id=session_id,
                session_state=session_state,
                target_store=target_store,
                route_reason=reason,
                detected_region=detected_region,
            )
            if item:
                items.append(item)
            elif reason_hint:
                skip_reason = reason_hint

        if media_plan == "contact_image" and not items:
            item, reason_hint = self._queue_contact_image(
                session_id=session_id,
                text=text,
                intent=intent,
                reason=reason,
                route=route,
                session_state=session_state,
            )
            if item:
                items.append(item)
            elif reason_hint and not skip_reason:
                skip_reason = reason_hint

        # delayed_video 不即时发送，仍由发送回执推进。
        return items, skip_reason

    def _queue_address_image(
        self,
        session_id: str,
        session_state: Dict[str, Any],
        target_store: str,
        route_reason: str,
        detected_region: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if target_store == "unknown":
            return None, "address_target_unknown"

        whitelist = self._is_media_whitelist_session(session_id)

        if not whitelist:
            sent_count = int(session_state.get("address_image_sent_count", 0) or 0)
            if sent_count >= 6:
                return None, "address_image_limit_reached"

            sent_map = session_state.get("address_image_last_sent_at_by_store", {}) or {}
            if not isinstance(sent_map, dict):
                sent_map = {}
                session_state["address_image_last_sent_at_by_store"] = sent_map

            last_sent_text = str(sent_map.get(target_store, "") or "").strip()
            if last_sent_text:
                last_sent = self._parse_iso(last_sent_text)
                if last_sent:
                    elapsed = datetime.now() - last_sent
                    if elapsed < timedelta(hours=ADDRESS_IMAGE_COOLDOWN_HOURS):
                        return None, "address_image_cooldown"

        image_path = self._pick_address_image(target_store)
        if not image_path:
            return None, "address_image_missing"

        store = self.knowledge_service.get_store_display(target_store)

        return (
            {
                "type": "address_image",
                "path": image_path,
                "target_store": target_store,
                "store_name": store.get("store_name", ""),
                "store_address": store.get("store_address", ""),
                "detected_region": detected_region,
                "route_reason": route_reason,
            },
            "",
        )

    def _queue_contact_image(
        self,
        session_id: str,
        text: str,
        intent: str,
        reason: str,
        route: Dict[str, Any],
        session_state: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if not self._contact_images:
            return None, "contact_image_missing"

        whitelist = self._is_media_whitelist_session(session_id)
        if not whitelist:
            sent_count = int(session_state.get("contact_image_sent_count", 0) or 0)
            if sent_count >= 1:
                return None, "contact_image_already_sent"

        if reason == "out_of_coverage" or intent in ("contact", "purchase"):
            return (
                {
                    "type": "contact_image",
                    "path": random.choice(self._contact_images),
                    "detected_region": route.get("detected_region", "") or route_region(reason, text),
                    "route_reason": reason,
                    "target_store": route.get("target_store", ""),
                },
                "",
            )

        return None, "contact_image_not_applicable"

    def _is_contact_image_sent_for_current_geo(self, session_state: Dict[str, Any]) -> bool:
        return int(session_state.get("contact_image_sent_count", 0) or 0) > 0

    def _has_both_images_sent(self, session_state: Dict[str, Any]) -> bool:
        return (
            int(session_state.get("address_image_sent_count", 0) or 0) > 0
            and int(session_state.get("contact_image_sent_count", 0) or 0) > 0
        )

    def _sync_media_state_from_conversation_log(
        self,
        session_id: str,
        user_hash: str,
        session_state: Dict[str, Any],
    ) -> None:
        user_summary = self.summarize_user_media_from_logs(user_id_hash=user_hash)
        session_state["address_image_sent_count"] = int(user_summary.get("address_image_sent_count", 0) or 0)
        session_state["contact_image_sent_count"] = int(user_summary.get("contact_image_sent_count", 0) or 0)
        session_state["address_image_last_sent_at_by_store"] = dict(user_summary.get("address_image_last_sent_at_by_store", {}) or {})
        session_state["sent_address_stores"] = list(user_summary.get("sent_address_stores", []) or [])
        session_state["contact_image_last_sent_at"] = str(user_summary.get("contact_image_last_sent_at", "") or "")

        latest_store = str(user_summary.get("last_target_store", "") or "").strip()
        if latest_store:
            session_state["last_target_store"] = latest_store

        session_video = self.summarize_session_video_from_log(session_id=session_id)
        session_state["session_video_armed"] = bool(session_video.get("contact_sent"))
        session_state["session_video_sent"] = bool(session_video.get("video_sent"))
        session_state["session_post_contact_reply_count"] = int(session_video.get("assistant_reply_count_after_contact", 0) or 0)
        session_state["session_user_message_count_after_contact"] = int(session_video.get("user_message_count_after_contact", 0) or 0)

    def summarize_user_media_from_logs(self, user_id_hash: str) -> Dict[str, Any]:
        summary = {
            "address_image_sent_count": 0,
            "contact_image_sent_count": 0,
            "address_image_last_sent_at_by_store": {},
            "sent_address_stores": [],
            "contact_image_last_sent_at": "",
            "last_target_store": "",
        }
        if not user_id_hash:
            return summary

        address_ts_map: Dict[str, datetime] = {}
        sent_address_stores: set[str] = set()
        last_target_store = ""
        last_target_store_ts: Optional[datetime] = None
        contact_last_ts: Optional[datetime] = None

        for log_path in self.conversation_log_dir.glob("*.jsonl"):
            records = self._scan_session_media_records(log_path=log_path, user_id_hash=user_id_hash)
            for rec in records:
                media_type = rec.get("type", "")
                ts = self._parse_iso(str(rec.get("timestamp", "") or ""))
                if media_type == "address_image":
                    summary["address_image_sent_count"] += 1
                    target_store = str(rec.get("target_store", "") or "")
                    if target_store:
                        sent_address_stores.add(target_store)
                        if ts and (target_store not in address_ts_map or ts > address_ts_map[target_store]):
                            address_ts_map[target_store] = ts
                        if ts and (not last_target_store_ts or ts > last_target_store_ts):
                            last_target_store = target_store
                            last_target_store_ts = ts
                        elif not ts and not last_target_store:
                            last_target_store = target_store
                elif media_type == "contact_image":
                    summary["contact_image_sent_count"] += 1
                    if ts and (not contact_last_ts or ts > contact_last_ts):
                        contact_last_ts = ts

        summary["sent_address_stores"] = sorted(sent_address_stores)
        summary["last_target_store"] = last_target_store
        summary["address_image_last_sent_at_by_store"] = {
            store: dt.isoformat() for store, dt in address_ts_map.items()
        }
        if contact_last_ts:
            summary["contact_image_last_sent_at"] = contact_last_ts.isoformat()
        return summary

    def summarize_user_turns_from_logs(self, user_id_hash: str) -> Dict[str, int]:
        summary = {
            "user_message_count": 0,
            "assistant_reply_count": 0,
        }
        if not user_id_hash:
            return summary

        for log_path in self.conversation_log_dir.glob("*.jsonl"):
            try:
                for raw_line in log_path.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(record, dict):
                        continue
                    if str(record.get("user_id_hash", "") or "") != user_id_hash:
                        continue
                    event_type = str(record.get("event_type", "") or "")
                    if event_type == "user_message":
                        summary["user_message_count"] += 1
                    elif event_type == "assistant_reply":
                        summary["assistant_reply_count"] += 1
            except Exception:
                continue
        return summary

    def is_user_first_turn_global(self, user_id_hash: str) -> bool:
        turns = self.summarize_user_turns_from_logs(user_id_hash=user_id_hash)
        return int(turns.get("assistant_reply_count", 0) or 0) == 0

    def summarize_session_video_from_log(self, session_id: str) -> Dict[str, Any]:
        summary = {
            "contact_sent": False,
            "video_sent": False,
            "assistant_reply_count_after_contact": 0,
            "user_message_count_after_contact": 0,
        }
        log_path = self._session_log_file(session_id)
        if not log_path.exists():
            return summary

        try:
            lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except Exception:
            return summary

        latest_contact_idx = -1
        for idx, record in enumerate(lines):
            if not isinstance(record, dict):
                continue
            if str(record.get("event_type", "") or "") != "media_result":
                continue
            payload = record.get("payload", {})
            if not isinstance(payload, dict):
                continue
            if str(payload.get("type", "") or "") == "contact_image" and bool(payload.get("success")):
                latest_contact_idx = idx

        if latest_contact_idx < 0:
            return summary
        summary["contact_sent"] = True

        reply_count = 0
        user_count = 0
        for idx in range(latest_contact_idx + 1, len(lines)):
            record = lines[idx]
            if not isinstance(record, dict):
                continue
            event_type = str(record.get("event_type", "") or "")
            payload = record.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            if event_type == "media_result":
                if str(payload.get("type", "") or "") == "delayed_video" and bool(payload.get("success")):
                    summary["video_sent"] = True
            elif event_type == "user_message":
                user_count += 1
            elif event_type == "assistant_reply":
                sent_types = payload.get("round_media_sent_types", [])
                if isinstance(sent_types, list) and "contact_image" in sent_types:
                    continue
                reply_count += 1

        summary["assistant_reply_count_after_contact"] = reply_count
        summary["user_message_count_after_contact"] = user_count
        return summary

    def _scan_session_media_records(self, log_path: Path, user_id_hash: str) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        pending_attempts: Dict[str, List[Dict[str, Any]]] = {
            "address_image": [],
            "contact_image": [],
            "delayed_video": [],
        }
        try:
            for raw_line in log_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if not isinstance(record, dict):
                    continue
                if str(record.get("user_id_hash", "") or "") != user_id_hash:
                    continue
                event_type = str(record.get("event_type", "") or "")
                payload = record.get("payload", {})
                if not isinstance(payload, dict):
                    payload = {}

                if event_type == "media_attempt":
                    media_type = str(payload.get("type", "") or "")
                    if media_type in pending_attempts:
                        pending_attempts[media_type].append(payload)
                    continue

                if event_type != "media_result":
                    continue

                media_type = str(payload.get("type", "") or "")
                if media_type not in pending_attempts:
                    continue
                if not bool(payload.get("success")):
                    queue = pending_attempts.get(media_type, [])
                    if queue:
                        queue.pop(0)
                    continue

                attempt_payload = {}
                queue = pending_attempts.get(media_type, [])
                if queue:
                    attempt_payload = queue.pop(0)

                path = str((attempt_payload or {}).get("path", "") or "")
                target_store = str((attempt_payload or {}).get("target_store", "") or "").strip()
                if media_type == "address_image" and not target_store:
                    target_store = self._infer_store_from_image_path(path)

                records.append(
                    {
                        "type": media_type,
                        "timestamp": str(record.get("timestamp", "") or ""),
                        "path": path,
                        "target_store": target_store,
                        "store_name": str((attempt_payload or {}).get("store_name", "") or ""),
                        "store_address": str((attempt_payload or {}).get("store_address", "") or ""),
                        "detected_region": str((attempt_payload or {}).get("detected_region", "") or ""),
                        "route_reason": str((attempt_payload or {}).get("route_reason", "") or ""),
                    }
                )
        except Exception:
            return records
        return records

    def _session_log_file(self, session_id: str) -> Path:
        safe = re.sub(r"[^0-9A-Za-z_\-]", "_", session_id or "unknown")
        return self.conversation_log_dir / f"{safe}.jsonl"

    def _infer_store_from_image_path(self, media_path: str) -> str:
        name = Path(str(media_path or "")).name
        if not name:
            return ""
        if "北京" in name:
            return "beijing_chaoyang"
        if "徐汇" in name:
            return "sh_xuhui"
        if "静安" in name:
            return "sh_jingan"
        if "虹口" in name:
            return "sh_hongkou"
        if "五角场" in name or "杨浦" in name:
            return "sh_wujiaochang"
        if any(k in name for k in ("人广", "人民广场", "黄浦", "黄埔")):
            return "sh_renmin"
        return ""

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

    def summarize_recent_assistant_hashes_from_logs(self, user_id_hash: str, limit: int = 40) -> set[str]:
        if not user_id_hash:
            return set()
        entries: List[Tuple[Optional[datetime], str]] = []
        for log_path in sorted(self.conversation_log_dir.glob("*.jsonl")):
            try:
                for raw_line in log_path.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except Exception:
                        continue
                    if not isinstance(record, dict):
                        continue
                    if str(record.get("user_id_hash", "") or "") != user_id_hash:
                        continue
                    if str(record.get("event_type", "") or "") != "assistant_reply":
                        continue
                    payload = record.get("payload", {})
                    if not isinstance(payload, dict):
                        continue
                    text = str(payload.get("text", "") or "").strip()
                    if not text:
                        continue
                    norm = self._normalize_for_dedupe(text)
                    if not norm:
                        continue
                    ts = self._parse_iso(str(record.get("timestamp", "") or ""))
                    entries.append((ts, norm))
            except Exception:
                continue
        entries.sort(key=lambda item: (item[0] is None, item[0] or datetime.min))
        tail = entries[-max(1, int(limit or 1)) :]
        return {norm for _, norm in tail}

    def _is_media_whitelist_session(self, session_id: str) -> bool:
        return session_id in self._media_whitelist_sessions

    def _build_general_llm_prompt(self, latest_user_text: str) -> str:
        kb_examples = self._top_kb_examples(latest_user_text, limit=2)
        kb_block = "\n".join([f"- 问：{q}\n  答：{a}" for q, a in kb_examples]) or "（当前无高相关知识库样例）"
        enterprise_guard = self._enterprise_guard_doc_text or "（企业知识约束文档缺失，请按已有品牌口径稳妥回复）"

        return (
            "你是艾耐儿私域客服助手。\n"
            "你只负责补充规则外的一般问答，不做任何地址/媒体/流程决策。\n"
            "语气自然、亲切、像真人客服。\n"
            "硬规则：结论先行；尽量1句话完成回复，且必须是完整句；末尾只保留1个emoji表情。\n"
            "超出知识库可常规发挥，但必须围绕企业知识口径；禁止编造活动承诺、联系方式或超出事实的信息。\n"
            "若信息不确定，给稳妥结论并引导用户补充。\n\n"
            f"【企业知识约束】\n{enterprise_guard}\n\n"
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
        value = self._strip_inline_emoji_symbols(value)

        # 联系方式合规拦截
        if any(k in value for k in CONTACT_COMPLIANCE_BLOCK_KEYWORDS):
            value = "姐姐我们先在这里沟通就好，我先帮您把需求和方案梳理清楚呀"
        elif any(k in value for k in SHIPPING_BLOCK_KEYWORDS):
            value = SHIPPING_BLOCK_REPLACEMENT

        if not value:
            value = "姐姐我在呢"
        value = value.rstrip("，,；; ")
        if not re.search(r"[。！？!?]$", value):
            value = f"{value}。"
        return f"{value}{DEFAULT_REPLY_EMOJI}"

    def _strip_inline_emoji_symbols(self, text: str) -> str:
        cleaned = re.sub(
            r"[\U0001F1E6-\U0001F1FF\U0001F300-\U0001FAFF\u2600-\u26FF\u2700-\u27BF\uFE0F\u200D]",
            "",
            text or "",
        )
        return re.sub(r"[~～]+", "", cleaned)

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

    def _has_neg_shanghai_hint(self, text: str) -> bool:
        value = re.sub(r"\s+", "", (text or ""))
        if not value:
            return False
        return any(keyword in value for keyword in NEG_SHANGHAI_HINT_KEYWORDS)

    def _hash_user(self, text: str) -> str:
        return hashlib.md5((text or "unknown").encode("utf-8", errors="ignore")).hexdigest()[:10]

    def _parse_iso(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

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
            return self._render_template("general_empty") if key != "general_empty" else "姐姐我在呢，关于假发有什么问题您都可以问我🌹"
        return text


def route_region(route_reason: str, text: str) -> str:
    if route_reason != "out_of_coverage":
        return ""
    m = re.search(r"([\u4e00-\u9fa5]{2,8}(?:省|市|区|县|州|盟|旗))", text or "")
    return m.group(1) if m else ""
