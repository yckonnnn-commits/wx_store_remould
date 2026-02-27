import json
import tempfile
import unittest
from pathlib import Path

from src.core.private_cs_agent import CustomerServiceAgent
from src.data.knowledge_repository import KnowledgeRepository
from src.data.memory_store import MemoryStore
from src.services.knowledge_service import KnowledgeService


class DummyLLMService:
    def __init__(self, reply_text: str = "姐姐这个问题我给您详细说明下哈🌹"):
        self.reply_text = reply_text
        self.reply_queue = []
        self.calls = 0
        self.prompt = ""

    def set_system_prompt(self, prompt: str):
        self.prompt = prompt

    def generate_reply_sync(self, user_message: str, conversation_history=None):
        self.calls += 1
        if self.reply_queue:
            return True, self.reply_queue.pop(0)
        return True, self.reply_text

    def get_current_model_name(self) -> str:
        return "DummyLLM"


class RuleEngineTestCase(unittest.TestCase):
    def _build_agent(self, temp_dir: Path, whitelist_sessions=None):
        whitelist_sessions = whitelist_sessions or []

        images_dir = temp_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        (images_dir / "contact.jpg").write_text("x", encoding="utf-8")
        (images_dir / "北京地址.jpg").write_text("x", encoding="utf-8")
        (images_dir / "video.mp4").write_text("x", encoding="utf-8")

        image_categories_path = temp_dir / "image_categories.json"
        image_categories_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "categories": ["联系方式", "店铺地址", "视频素材"],
                    "images": {
                        "联系方式": ["contact.jpg"],
                        "店铺地址": ["北京地址.jpg"],
                        "视频素材": ["video.mp4"],
                    },
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        reply_templates_path = temp_dir / "reply_templates.json"
        reply_templates_path.write_text("{}", encoding="utf-8")

        media_whitelist_path = temp_dir / "media_whitelist.json"
        media_whitelist_path.write_text(
            json.dumps({"version": 1, "session_ids": whitelist_sessions}, ensure_ascii=False),
            encoding="utf-8",
        )
        conversation_log_dir = temp_dir / "conversations"
        conversation_log_dir.mkdir(parents=True, exist_ok=True)

        system_prompt = temp_dir / "system_prompt.md"
        playbook = temp_dir / "playbook.md"
        system_prompt.write_text("你是客服助手。", encoding="utf-8")
        playbook.write_text("语气友好。", encoding="utf-8")

        kb_file = temp_dir / "knowledge.json"
        kb_file.write_text("[]", encoding="utf-8")

        memory_path = temp_dir / "memory.json"

        repository = KnowledgeRepository(kb_file)
        knowledge_service = KnowledgeService(repository, address_config_path=Path("config") / "address.json")
        llm_service = DummyLLMService()
        memory_store = MemoryStore(memory_path)

        agent = CustomerServiceAgent(
            knowledge_service=knowledge_service,
            llm_service=llm_service,
            memory_store=memory_store,
            images_dir=images_dir,
            image_categories_path=image_categories_path,
            system_prompt_doc_path=system_prompt,
            playbook_doc_path=playbook,
            reply_templates_path=reply_templates_path,
            media_whitelist_path=media_whitelist_path,
            conversation_log_dir=conversation_log_dir,
        )
        return agent, knowledge_service, repository, llm_service

    def _append_media_success_log(
        self,
        conversations_dir: Path,
        session_id: str,
        media_type: str,
        media_path: str,
        ts: str,
        user_id_hash: str,
    ) -> None:
        log_file = conversations_dir / f"{session_id}.jsonl"
        records = []
        if log_file.exists():
            existing = [x for x in log_file.read_text(encoding="utf-8").splitlines() if x.strip()]
            for line in existing:
                try:
                    records.append(json.loads(line))
                except Exception:
                    continue
        records.extend(
            [
                {
                    "timestamp": ts,
                    "session_id": session_id,
                    "user_id_hash": user_id_hash,
                    "event_type": "media_attempt",
                    "reply_source": "",
                    "rule_id": "",
                    "model_name": "",
                    "payload": {"type": media_type, "path": media_path},
                },
                {
                    "timestamp": ts,
                    "session_id": session_id,
                    "user_id_hash": user_id_hash,
                    "event_type": "media_result",
                    "reply_source": "",
                    "rule_id": "",
                    "model_name": "",
                    "payload": {"type": media_type, "success": True, "result": {"ok": True}},
                },
            ]
        )
        log_file.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in records) + "\n", encoding="utf-8")

    def test_region_route_precedence(self):
        with tempfile.TemporaryDirectory() as td:
            kb_file = Path(td) / "knowledge.json"
            kb_file.write_text("[]", encoding="utf-8")
            repository = KnowledgeRepository(kb_file)
            service = KnowledgeService(repository, address_config_path=Path("config") / "address.json")

            hebei_route = service.resolve_store_recommendation("我在河北")
            self.assertEqual(hebei_route.get("target_store"), "beijing_chaoyang")

            sh_route = service.resolve_store_recommendation("我在上海徐汇")
            self.assertEqual(sh_route.get("target_store"), "sh_xuhui")

            non_cov_route = service.resolve_store_recommendation("我在黑龙江")
            self.assertEqual(non_cov_route.get("reason"), "out_of_coverage")

    def test_geo_followup_cycle_two_plus_one(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, _ = self._build_agent(Path(td))
            session_id = "chat_cycle"
            user_name = "用户A"

            d1 = agent.decide(session_id, user_name, "怎么买", [])
            self.assertEqual(d1.rule_id, "ADDR_ASK_REGION_R1")

            d2 = agent.decide(session_id, user_name, "怎么买呀", [])
            self.assertEqual(d2.rule_id, "ADDR_ASK_REGION_R2")

            d3 = agent.decide(session_id, user_name, "怎么买啊", [])
            self.assertEqual(d3.rule_id, "ADDR_ASK_REGION_CHOICE")

            d4 = agent.decide(session_id, user_name, "我想买", [])
            self.assertEqual(d4.rule_id, "ADDR_ASK_REGION_R1_RESET")

    def test_kb_first_then_llm(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, repository, llm = self._build_agent(Path(td))
            repository.add("透气吗", "姐姐，我们这款透气性很好🌹", intent="wearing", tags=["佩戴体验"])

            d1 = agent.decide("chat_kb", "用户B", "透气吗", [])
            self.assertEqual(d1.reply_source, "knowledge")
            self.assertEqual(llm.calls, 0)

            d2 = agent.decide("chat_kb", "用户B", "你们售后多久", [])
            self.assertEqual(d2.reply_source, "llm")
            self.assertEqual(llm.calls, 1)

    def test_kb_match_returns_original_answer_without_rewrite(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, repository, llm = self._build_agent(Path(td))
            repository.add(
                "会掉吗头发？会掉吗？",
                "非常牢固，我们有客户戴着做过山车都没问题！🎢",
                intent="wearing",
                tags=["佩戴体验"],
            )

            user_name = "用户KB"
            user_hash = agent._hash_user(user_name)
            user_state = agent.memory_store.get_user_state(user_hash)
            user_state["recent_reply_hashes"] = [
                agent._normalize_for_dedupe("非常牢固，我们有客户戴着做过山车都没问题！🎢")
            ]
            agent.memory_store.update_user_state(user_hash, user_state)

            d = agent.decide("chat_kb_exact", user_name, "会掉吗？", [])
            self.assertEqual(d.reply_source, "knowledge")
            self.assertEqual(d.reply_text, "非常牢固，我们有客户戴着做过山车都没问题！🎢")
            self.assertEqual(llm.calls, 0)

    def test_contact_image_frequency_and_whitelist(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            white_session = "chat_white"
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir, whitelist_sessions=[white_session])
            user_name = "用户C"

            s1 = "chat_normal"
            d1 = agent.decide(s1, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d1.media_plan, "contact_image")
            self.assertTrue(d1.media_items)
            agent.mark_media_sent(s1, user_name, d1.media_items[0], success=True)
            user_hash = agent._hash_user(user_name)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=s1,
                media_type="contact_image",
                media_path=d1.media_items[0]["path"],
                ts="2999-01-01T00:00:00",
                user_id_hash=user_hash,
            )

            d2 = agent.decide(s1, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d2.media_plan, "none")
            self.assertFalse(d2.media_items)

            d3 = agent.decide(white_session, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d3.media_plan, "contact_image")
            self.assertTrue(d3.media_items)
            agent.mark_media_sent(white_session, user_name, d3.media_items[0], success=True)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=white_session,
                media_type="contact_image",
                media_path=d3.media_items[0]["path"],
                ts="2999-01-01T00:01:00",
                user_id_hash=user_hash,
            )

            d4 = agent.decide(white_session, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d4.media_plan, "contact_image")
            self.assertTrue(d4.media_items)

    def test_video_session_once_with_log_driven_state(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            user_name = "用户D"
            user_hash = agent._hash_user(user_name)

            d1 = agent.decide("chat_a", user_name, "我在黑龙江怎么买", [])
            agent.mark_media_sent("chat_a", user_name, d1.media_items[0], success=True)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id="chat_a",
                media_type="contact_image",
                media_path=d1.media_items[0]["path"],
                ts="2026-02-27T10:00:00",
                user_id_hash=user_hash,
            )
            # 联系方式图之后的第一轮（有 user_message + assistant_reply）
            (conversations_dir / "chat_a.jsonl").write_text(
                (conversations_dir / "chat_a.jsonl").read_text(encoding="utf-8")
                + json.dumps(
                    {
                        "timestamp": "2026-02-27T10:00:01",
                        "session_id": "chat_a",
                        "user_id_hash": user_hash,
                        "event_type": "user_message",
                        "reply_source": "",
                        "rule_id": "",
                        "model_name": "",
                        "payload": {"text": "好的"},
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "timestamp": "2026-02-27T10:00:02",
                        "session_id": "chat_a",
                        "user_id_hash": user_hash,
                        "event_type": "assistant_reply",
                        "reply_source": "rule",
                        "rule_id": "DUMMY",
                        "model_name": "",
                        "payload": {"text": "收到", "round_media_sent_types": []},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            video_item = agent.mark_reply_sent("chat_a", user_name, "继续说")
            self.assertIsNotNone(video_item)
            self.assertEqual(video_item.get("type"), "delayed_video")
            agent.mark_media_sent("chat_a", user_name, video_item, success=True)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id="chat_a",
                media_type="delayed_video",
                media_path=str(temp_dir / "images" / "video.mp4"),
                ts="2026-02-27T10:00:10",
                user_id_hash=user_hash,
            )

            d2 = agent.decide("chat_b", user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d2.media_plan, "none")
            self.assertIsNone(agent.mark_reply_sent("chat_a", user_name, "再追问一次"))

    def test_purchase_known_geo_contact_then_remind(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_geo"
            user_name = "用户E"

            d0 = agent.decide(session_id, user_name, "我在长宁", [])
            self.assertEqual(d0.rule_id, "ADDR_STORE_RECOMMEND")

            d1 = agent.decide(session_id, user_name, "怎么买啊", [])
            self.assertEqual(d1.rule_id, "PURCHASE_CONTACT_FROM_KNOWN_GEO")
            self.assertEqual(d1.media_plan, "contact_image")
            self.assertTrue(d1.media_items)
            agent.mark_media_sent(session_id, user_name, d1.media_items[0], success=True)
            user_hash = agent._hash_user(user_name)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="contact_image",
                media_path=d1.media_items[0]["path"],
                ts="2999-01-01T00:02:00",
                user_id_hash=user_hash,
            )

            d2 = agent.decide(session_id, user_name, "怎么预约", [])
            self.assertEqual(d2.rule_id, "PURCHASE_CONTACT_REMIND_ONLY")
            self.assertEqual(d2.media_plan, "none")
            self.assertFalse(d2.media_items)

    def test_purchase_known_geo_not_blocked_by_legacy_contact_count(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, _ = self._build_agent(Path(td))
            session_id = "chat_geo_legacy"
            user_name = "用户G"

            user_hash = agent._hash_user(user_name)
            agent.memory_store.update_session_state(
                session_id,
                {
                    "contact_image_sent_count": 1,
                    "contact_image_last_sent_at": "",
                },
                user_hash=user_hash,
            )

            d0 = agent.decide(session_id, user_name, "我在长宁", [])
            self.assertEqual(d0.rule_id, "ADDR_STORE_RECOMMEND")

            d1 = agent.decide(session_id, user_name, "需要预约吗？", [])
            self.assertEqual(d1.rule_id, "PURCHASE_CONTACT_FROM_KNOWN_GEO")
            self.assertEqual(d1.media_plan, "contact_image")
            self.assertTrue(d1.media_items)

    def test_address_image_cooldown_24h(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_addr"
            user_name = "用户F"

            d1 = agent.decide(session_id, user_name, "我在门头沟", [])
            self.assertEqual(d1.rule_id, "ADDR_STORE_RECOMMEND")
            self.assertEqual(d1.media_plan, "address_image")
            self.assertTrue(d1.media_items)
            agent.mark_media_sent(session_id, user_name, d1.media_items[0], success=True)
            user_hash = agent._hash_user(user_name)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="address_image",
                media_path=d1.media_items[0]["path"],
                ts="2026-02-27T10:20:00",
                user_id_hash=user_hash,
            )

            d2 = agent.decide(session_id, user_name, "我在门头沟", [])
            self.assertEqual(d2.rule_id, "ADDR_STORE_RECOMMEND")
            self.assertEqual(d2.media_plan, "none")
            self.assertEqual(d2.media_skip_reason, "address_image_cooldown")
            self.assertFalse(d2.media_items)

            (conversations_dir / f"{session_id}.jsonl").unlink(missing_ok=True)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="address_image",
                media_path=d1.media_items[0]["path"],
                ts="2020-01-01T00:00:00",
                user_id_hash=user_hash,
            )

            d3 = agent.decide(session_id, user_name, "我在门头沟", [])
            self.assertEqual(d3.media_plan, "address_image")
            self.assertTrue(d3.media_items)

    def test_both_images_lock_blocks_future_images(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_lock"
            user_name = "用户H"
            user_hash = agent._hash_user(user_name)

            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="address_image",
                media_path=str(temp_dir / "images" / "北京地址.jpg"),
                ts="2020-01-01T10:30:00",
                user_id_hash=user_hash,
            )
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="contact_image",
                media_path=str(temp_dir / "images" / "contact.jpg"),
                ts="2020-01-01T10:31:00",
                user_id_hash=user_hash,
            )

            d = agent.decide(session_id, user_name, "我在门头沟", [])
            self.assertEqual(d.rule_id, "ADDR_STORE_RECOMMEND")
            self.assertEqual(d.media_plan, "address_image")
            self.assertTrue(d.media_items)

    def test_both_images_strong_intent_first_fixed_then_llm(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, llm = self._build_agent(temp_dir)
            session_id = "chat_lock_purchase"
            user_name = "用户I"
            user_hash = agent._hash_user(user_name)

            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="address_image",
                media_path=str(temp_dir / "images" / "北京地址.jpg"),
                ts="2026-02-27T10:40:00",
                user_id_hash=user_hash,
            )
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="contact_image",
                media_path=str(temp_dir / "images" / "contact.jpg"),
                ts="2026-02-27T10:41:00",
                user_id_hash=user_hash,
            )
            agent.memory_store.update_session_state(
                session_id,
                {"last_target_store": "beijing_chaoyang"},
                user_hash=user_hash,
            )

            d1 = agent.decide(session_id, user_name, "怎么预约", [])
            self.assertEqual(d1.rule_id, "PURCHASE_AFTER_BOTH_FIRST_HINT")
            self.assertEqual(d1.media_plan, "none")
            self.assertIn("画圈圈", d1.reply_text)

            llm.reply_text = "姐姐我这边帮您安排，您告诉我方便到店时间哈🌹"
            d2 = agent.decide(session_id, user_name, "我想买", [])
            self.assertIn(d2.reply_source, ("llm", "knowledge"))
            self.assertEqual(d2.media_plan, "none")

    def test_repeat_rewrite_fallback_to_pool(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, llm = self._build_agent(Path(td))
            session_id = "chat_repeat"
            user_name = "用户J"
            repeated = "姐姐我来帮您安排～🌹"
            normalized = agent._normalize_for_dedupe(repeated)

            user_hash = agent._hash_user(user_name)
            user_state = agent.memory_store.get_user_state(user_hash)
            user_state["recent_reply_hashes"] = [normalized]
            agent.memory_store.update_user_state(user_hash, user_state)

            llm.reply_text = repeated
            llm.reply_queue = [repeated, repeated]  # 触发两次改写仍重复，最终落去重池

            d = agent.decide(session_id, user_name, "售后多久", [])
            self.assertNotEqual(agent._normalize_for_dedupe(d.reply_text), normalized)
            self.assertIn(d.reply_text, agent._dedupe_reply_pool)

    def test_log_deleted_resets_stale_media_state(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_reset_by_log_delete"
            user_name = "用户K"

            user_hash = agent._hash_user(user_name)
            agent.memory_store.update_session_state(
                session_id,
                {
                    "address_image_sent_count": 3,
                    "contact_image_sent_count": 2,
                    "address_image_last_sent_at_by_store": {"beijing_chaoyang": "2026-01-01T00:00:00"},
                    "contact_image_last_sent_at": "2026-01-01T00:00:00",
                },
                user_hash=user_hash,
            )

            # 未生成会话日志时，应回放为空并清掉“已发图”状态
            d = agent.decide(session_id, user_name, "我在门头沟", [])
            self.assertEqual(d.rule_id, "ADDR_STORE_RECOMMEND")
            self.assertEqual(d.media_plan, "address_image")
            self.assertFalse(d.media_skip_reason)
            self.assertTrue(d.media_items)

    def test_log_deleted_resets_video_state(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir, whitelist_sessions=["chat_video_reset"])
            session_id = "chat_video_reset"
            user_name = "用户V"
            user_hash = agent._hash_user(user_name)

            d1 = agent.decide(session_id, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d1.media_plan, "contact_image")
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="contact_image",
                media_path=d1.media_items[0]["path"],
                ts="2026-02-27T10:00:00",
                user_id_hash=user_hash,
            )
            (conversations_dir / f"{session_id}.jsonl").write_text(
                (conversations_dir / f"{session_id}.jsonl").read_text(encoding="utf-8")
                + json.dumps(
                    {
                        "timestamp": "2026-02-27T10:00:01",
                        "session_id": session_id,
                        "user_id_hash": user_hash,
                        "event_type": "user_message",
                        "reply_source": "",
                        "rule_id": "",
                        "model_name": "",
                        "payload": {"text": "收到"},
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "timestamp": "2026-02-27T10:00:02",
                        "session_id": session_id,
                        "user_id_hash": user_hash,
                        "event_type": "assistant_reply",
                        "reply_source": "rule",
                        "rule_id": "DUMMY",
                        "model_name": "",
                        "payload": {"text": "收到", "round_media_sent_types": []},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            self.assertIsNotNone(agent.mark_reply_sent(session_id, user_name, "第二轮"))

            (conversations_dir / f"{session_id}.jsonl").unlink(missing_ok=True)

            d2 = agent.decide(session_id, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d2.media_plan, "contact_image")

    def test_media_state_recovers_from_conversation_log(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_log_recover"
            user_name = "用户L"

            log_file = (temp_dir / "conversations") / f"{session_id}.jsonl"
            records = [
                {
                    "timestamp": "2020-01-01T10:00:00",
                    "session_id": session_id,
                    "user_id_hash": agent._hash_user(user_name),
                    "event_type": "media_attempt",
                    "reply_source": "",
                    "rule_id": "",
                    "model_name": "",
                    "payload": {"type": "address_image", "path": str(temp_dir / "images" / "北京地址.jpg")},
                },
                {
                    "timestamp": "2020-01-01T10:00:01",
                    "session_id": session_id,
                    "user_id_hash": agent._hash_user(user_name),
                    "event_type": "media_result",
                    "reply_source": "",
                    "rule_id": "",
                    "model_name": "",
                    "payload": {"type": "address_image", "success": True, "result": {"ok": True}},
                },
                {
                    "timestamp": "2020-01-01T10:00:10",
                    "session_id": session_id,
                    "user_id_hash": agent._hash_user(user_name),
                    "event_type": "media_attempt",
                    "reply_source": "",
                    "rule_id": "",
                    "model_name": "",
                    "payload": {"type": "contact_image", "path": str(temp_dir / "images" / "contact.jpg")},
                },
                {
                    "timestamp": "2020-01-01T10:00:11",
                    "session_id": session_id,
                    "user_id_hash": agent._hash_user(user_name),
                    "event_type": "media_result",
                    "reply_source": "",
                    "rule_id": "",
                    "model_name": "",
                    "payload": {"type": "contact_image", "success": True, "result": {"ok": True}},
                },
            ]
            log_file.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in records) + "\n", encoding="utf-8")

            user_hash = agent._hash_user(user_name)
            agent.memory_store.update_session_state(
                session_id,
                {
                    "address_image_sent_count": 0,
                    "contact_image_sent_count": 0,
                    "last_target_store": "beijing_chaoyang",
                },
                user_hash=user_hash,
            )

            d = agent.decide(session_id, user_name, "我在门头沟", [])
            self.assertEqual(d.rule_id, "ADDR_STORE_RECOMMEND")
            self.assertEqual(d.media_plan, "address_image")
            self.assertTrue(d.media_items)


if __name__ == "__main__":
    unittest.main()
