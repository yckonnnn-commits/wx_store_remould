"""
私人客服 Agent
统一负责：意图识别、知识库命中、LLM补全、媒体决策、记忆更新。
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


@dataclass
class AgentDecision:
    reply_text: str
    intent: str
    route_reason: str
    reply_goal: str
    media_plan: str
    media_items: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "rule"


class CustomerServiceAgent:
    """客服 Agent 主决策器"""

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        llm_service: LLMService,
        memory_store: MemoryStore,
        images_dir: Path,
        image_categories_path: Path,
        system_prompt_doc_path: Path,
        playbook_doc_path: Path,
    ):
        self.knowledge_service = knowledge_service
        self.llm_service = llm_service
        self.memory_store = memory_store

        self.images_dir = images_dir
        self.image_categories_path = image_categories_path
        self.system_prompt_doc_path = system_prompt_doc_path
        self.playbook_doc_path = playbook_doc_path

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

        self._followup_variants = [
            "姐姐方便告诉我上海哪个区吗？我马上给您匹配最近门店。",
            "姐姐您说下上海哪个区呀，我按距离给您安排最近门店。",
            "姐姐给我一个上海区名，我立刻帮您匹配最近门店。",
        ]
        self._contact_followup_variants = [
            "姐姐您看下我刚发的联系方式图，按图添加后跟我说一声，我马上接着帮您安排😊",
            "姐姐刚刚那张联系方式图您点开就能看到，添加后回我一句，我立刻继续帮您跟进😊",
        ]
        self._dedupe_reply_pool = [
            "姐姐我在，您可以继续说下最关心的问题。",
            "姐姐收到，我帮您一步步梳理最合适的方案。",
            "姐姐明白，我先把关键点给您讲清楚。",
        ]

        self.reload_prompt_docs()
        self.reload_media_library()

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

        decision = None
        if self._is_address_scene(text, route, intent):
            decision = self._decide_address_reply(text, route, intent, session_state)
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
        }

    def _detect_intent(self, text: str) -> str:
        if self.knowledge_service.is_address_query(text):
            return "address"
        if self.knowledge_service.is_purchase_intent(text):
            return "purchase"
        if any(k in (text or "") for k in CONTACT_INTENT_KEYWORDS):
            return "contact"
        return "general"

    def _is_address_scene(self, text: str, route: Dict[str, Any], intent: str) -> bool:
        reason = route.get("reason", "unknown")
        target_store = route.get("target_store", "unknown")
        return (
            intent == "address"
            or reason in ("shanghai_need_district", "out_of_coverage")
            or target_store != "unknown"
        )

    def _decide_address_reply(
        self,
        text: str,
        route: Dict[str, Any],
        intent: str,
        session_state: Dict[str, Any],
    ) -> AgentDecision:
        reason = route.get("reason", "unknown")
        target_store = route.get("target_store", "unknown")

        if target_store != "unknown":
            store = self.knowledge_service.get_store_display(target_store)
            store_name = store.get("store_name", "门店")
            reply = f"姐姐，推荐您去{store_name}，我给您发一张位置图，您跟着图走会更直观。"
            return AgentDecision(
                reply_text=reply,
                intent="address",
                route_reason=reason,
                reply_goal="解答",
                media_plan="address_image",
                source="rule",
            )

        if reason == "shanghai_need_district":
            prompt_count = int(session_state.get("address_prompt_count", 0) or 0)
            if prompt_count <= 0:
                reply = "姐姐您在上海哪个区呀？我帮您匹配最近门店。"
            else:
                idx = (prompt_count - 1) % len(self._followup_variants)
                reply = self._followup_variants[idx]
            session_state["address_prompt_count"] = prompt_count + 1
            return AgentDecision(
                reply_text=reply,
                intent="address",
                route_reason=reason,
                reply_goal="追问地区",
                media_plan="none",
                source="rule",
            )

        if reason == "out_of_coverage":
            region = route.get("detected_region", "您所在地区")
            reply = (
                f"姐姐，{region}目前暂时没有我们的线下门店；我们现在是北京朝阳1家、上海5家"
                "（静安、人广、虹口、五角场、徐汇），您方便的话我可以帮您安排到店体验哦😊"
            )
            return AgentDecision(
                reply_text=reply,
                intent=intent if intent in ("purchase", "contact") else "general",
                route_reason=reason,
                reply_goal="引导预约",
                media_plan="contact_image",
                source="rule",
            )

        reply = (
            "姐姐，您在什么城市或区域呀？我可以按距离给您推荐最近门店。"
            "目前门店在北京朝阳和上海（静安、人广、虹口、五角场、徐汇）。"
        )
        return AgentDecision(
            reply_text=reply,
            intent="address",
            route_reason="unknown",
            reply_goal="追问地区",
            media_plan="none",
            source="rule",
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
        last_route_reason = session_state.get("last_route_reason", "unknown")
        warmed = bool(session_state.get("contact_warmup", False))
        contact_sent = int(session_state.get("contact_image_sent_count", 0) or 0) >= 1

        if intent == "contact":
            if contact_sent:
                prompt_count = int(session_state.get("contact_followup_prompt_count", 0) or 0)
                reply = self._contact_followup_variants[prompt_count % len(self._contact_followup_variants)]
                session_state["contact_followup_prompt_count"] = prompt_count + 1
                return AgentDecision(
                    reply_text=reply,
                    intent="contact",
                    route_reason=route_reason,
                    reply_goal="推进购买意图",
                    media_plan="none",
                    source="rule",
                )
            return AgentDecision(
                reply_text="姐姐我给您发一张联系方式图，您保存后我这边继续一对一跟进您呀😊",
                intent="contact",
                route_reason=route_reason,
                reply_goal="推进购买意图",
                media_plan="contact_image",
                source="rule",
            )

        # 非覆盖地区弱意图暖场后，下一轮优先补发联系方式图，避免反复文字拉扯。
        if route_reason == "unknown" and last_route_reason == "out_of_coverage" and warmed and not contact_sent:
            return AgentDecision(
                reply_text="姐姐我理解您过去不方便，我先给您发一张联系方式图，后续我一对一帮您安排呀😊",
                intent="contact",
                route_reason="out_of_coverage",
                reply_goal="推进购买意图",
                media_plan="contact_image",
                source="rule",
            )

        if self.use_knowledge_first:
            kb_answer = self.knowledge_service.find_answer(
                latest_user_text,
                threshold=self.knowledge_threshold,
            )
            if kb_answer:
                return AgentDecision(
                    reply_text=self._normalize_reply_text(kb_answer),
                    intent=intent,
                    route_reason=route.get("reason", "unknown"),
                    reply_goal="解答",
                    media_plan="none",
                    source="knowledge",
                )

        composed_prompt = self._build_composed_prompt(latest_user_text)
        self.llm_service.set_system_prompt(composed_prompt)
        success, result = self.llm_service.generate_reply_sync(
            user_message=latest_user_text,
            conversation_history=conversation_history,
        )
        if not success:
            return AgentDecision(
                reply_text="姐姐抱歉，系统现在有点忙，您稍后再发我马上跟进。",
                intent=intent,
                route_reason=route.get("reason", "unknown"),
                reply_goal="解答",
                media_plan="none",
                source="fallback",
            )

        parsed = self._parse_llm_json(result)
        llm_reply = self._normalize_reply_text(parsed.get("reply_text") or result)
        llm_reply = self._avoid_repeat(user_state, llm_reply)

        media_plan = parsed.get("media_plan", "none")
        if media_plan not in ("none", "address_image", "contact_image", "delayed_video"):
            media_plan = "none"

        llm_intent = parsed.get("intent") or intent
        llm_route_reason = parsed.get("route_reason") or route.get("reason", "unknown")
        llm_goal = parsed.get("reply_goal") or "解答"

        return AgentDecision(
            reply_text=llm_reply,
            intent=llm_intent,
            route_reason=llm_route_reason,
            reply_goal=llm_goal,
            media_plan=media_plan,
            source="llm",
        )

    def _plan_media_items(
        self,
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
            item = self._queue_address_image(session_state, target_store)
            if item:
                items.append(item)

        if media_plan == "contact_image" and not items:
            item = self._queue_contact_image(text, intent, reason, session_state)
            if item:
                items.append(item)

        # LLM 给出 delayed_video 仅作提示，不即时发送，仍由发送回执推进。
        if media_plan == "delayed_video" and not user_state.get("video_sent"):
            user_state["video_armed"] = True
            user_state["post_contact_reply_count"] = 0

        return items

    def _queue_address_image(self, session_state: Dict[str, Any], target_store: str) -> Optional[Dict[str, Any]]:
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
        text: str,
        intent: str,
        reason: str,
        session_state: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        sent_count = int(session_state.get("contact_image_sent_count", 0) or 0)
        if sent_count >= 1:
            return None

        if not self._contact_images:
            return None

        # out_of_coverage 场景：强意图直接发，弱意图暖场后发。
        if reason == "out_of_coverage":
            strong_intent = self.knowledge_service.is_purchase_intent(text) or intent == "contact"
            warmed = bool(session_state.get("contact_warmup", False))
            if not strong_intent and not warmed:
                session_state["contact_warmup"] = True
                return None

            return {
                "type": "contact_image",
                "path": random.choice(self._contact_images),
                "region": route_region(reason, text),
            }

        # 覆盖地区：主动问联系方式时可发
        if intent == "contact":
            return {
                "type": "contact_image",
                "path": random.choice(self._contact_images),
                "region": "",
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

    def _build_composed_prompt(self, latest_user_text: str) -> str:
        kb_examples = self._top_kb_examples(latest_user_text, limit=3)
        kb_block = "\n".join([f"- Q: {q}\n  A: {a}" for q, a in kb_examples])

        return (
            f"{self._system_prompt_doc_text}\n\n"
            "---\n"
            "【客服回复规则】\n"
            f"{self._playbook_doc_text}\n\n"
            "---\n"
            "【知识库参考（优先一致）】\n"
            f"{kb_block}\n\n"
            "请只输出 JSON：\n"
            "{\n"
            '  "reply_text": "...",\n'
            '  "intent": "address|purchase|contact|general",\n'
            '  "route_reason": "...",\n'
            '  "media_plan": "none|address_image|contact_image|delayed_video",\n'
            '  "reply_goal": "解答|追问地区|引导预约|推进购买意图"\n'
            "}\n"
            "要求：reply_text 用 1-2 句自然中文，禁止输出联系方式信息。"
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

    def _parse_llm_json(self, raw_text: str) -> Dict[str, Any]:
        text = (raw_text or "").strip()
        if not text:
            return {}

        fenced = re.match(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            text = fenced.group(1).strip()

        parsed = self._safe_json_load(text)
        if isinstance(parsed, dict):
            return parsed

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            parsed = self._safe_json_load(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed

        return {}

    def _normalize_reply_text(self, text: str) -> str:
        value = (text or "").strip()
        if not value:
            return "姐姐我在呢，您告诉我您最关心的是价格、地址还是佩戴效果？"

        value = re.sub(r"\s*\d{1,2}:\d{2}\S*$", "", value)
        value = " ".join(value.split())

        # 联系方式合规拦截
        if any(k in value for k in CONTACT_COMPLIANCE_BLOCK_KEYWORDS):
            value = "姐姐我们先在这里沟通就好，我先帮您把需求和方案梳理清楚。"

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
        if normalized in previous:
            return random.choice(self._dedupe_reply_pool)
        return reply_text

    def _normalize_for_dedupe(self, text: str) -> str:
        value = (text or "").strip().lower()
        value = re.sub(r"[^\w\u4e00-\u9fa5]", "", value)
        return value

    def _hash_user(self, text: str) -> str:
        return hashlib.md5((text or "unknown").encode("utf-8", errors="ignore")).hexdigest()[:10]

    def _safe_json_load(self, text: str) -> Any:
        try:
            return json.loads(text)
        except Exception:
            return None

    def _read_text(self, path: Path) -> str:
        if not path.exists():
            return ""
        try:
            return path.read_text(encoding="utf-8").strip()
        except Exception:
            return ""


def route_region(route_reason: str, text: str) -> str:
    if route_reason != "out_of_coverage":
        return ""
    m = re.search(r"([\u4e00-\u9fa5]{2,8}(?:省|市|区|县|州|盟|旗))", text or "")
    return m.group(1) if m else ""
