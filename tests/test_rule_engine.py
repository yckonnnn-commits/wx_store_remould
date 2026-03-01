import json
import tempfile
import unittest
from datetime import datetime
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

    def _append_assistant_reply_log(
        self,
        conversations_dir: Path,
        session_id: str,
        user_id_hash: str,
        ts: str,
        text: str = "收到",
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
        records.append(
            {
                "timestamp": ts,
                "session_id": session_id,
                "user_id_hash": user_id_hash,
                "event_type": "assistant_reply",
                "reply_source": "rule",
                "rule_id": "DUMMY",
                "model_name": "",
                "payload": {"text": text, "round_media_sent_types": []},
            }
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

            neg_sh_only = service.resolve_store_recommendation("我不在上海")
            self.assertEqual(neg_sh_only.get("reason"), "out_of_coverage")
            self.assertEqual(neg_sh_only.get("route_type"), "non_coverage")
            self.assertEqual(neg_sh_only.get("detected_region"), "非上海地区")

            neg_bj_only = service.resolve_store_recommendation("我不在北京")
            self.assertEqual(neg_bj_only.get("reason"), "out_of_coverage")
            self.assertEqual(neg_bj_only.get("route_type"), "non_coverage")
            self.assertEqual(neg_bj_only.get("detected_region"), "非北京地区")

            neg_both = service.resolve_store_recommendation("我不在北京和上海")
            self.assertEqual(neg_both.get("reason"), "out_of_coverage")
            self.assertEqual(neg_both.get("route_type"), "non_coverage")
            self.assertEqual(neg_both.get("detected_region"), "非沪京地区")

            normal_price_route = service.resolve_store_recommendation("不同价格有什么区别啊？")
            self.assertEqual(normal_price_route.get("reason"), "unknown")

    def test_not_in_shanghai_or_beijing_should_not_fallback_to_llm(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, llm = self._build_agent(temp_dir)
            user_name = "用户负向城市"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_neg_city",
                user_id_hash=user_hash,
                ts="2026-02-27T09:35:00",
            )

            d1 = agent.decide("chat_not_in_sh", user_name, "不在上海怎么做？", [])
            self.assertNotEqual(d1.reply_source, "llm")
            self.assertNotEqual(d1.rule_id, "LLM_GENERAL")
            self.assertEqual(d1.route_reason, "out_of_coverage")

            d2 = agent.decide("chat_not_in_bj", user_name, "不在北京怎么做？", [])
            self.assertNotEqual(d2.reply_source, "llm")
            self.assertNotEqual(d2.rule_id, "LLM_GENERAL")
            self.assertEqual(d2.route_reason, "out_of_coverage")
            self.assertEqual(llm.calls, 0)

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

    def test_address_query_shanghai_asks_district(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, _ = self._build_agent(Path(td))

            d = agent.decide("chat_detail_sh", "用户地址1", "你们上海店的地址在哪", [])
            self.assertEqual(d.rule_id, "ADDR_ASK_DISTRICT_R1")
            self.assertEqual(d.media_plan, "none")
            self.assertNotIn("门店地址：", d.reply_text)

    def test_address_query_cityless_asks_region(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, _ = self._build_agent(Path(td))

            d = agent.decide("chat_detail_both", "用户地址2", "具体地址在哪", [])
            self.assertEqual(d.rule_id, "ADDR_ASK_REGION_R1")
            self.assertEqual(d.media_plan, "none")
            self.assertNotIn("上海店详细地址", d.reply_text)
            self.assertNotIn("北京店详细地址", d.reply_text)

    def test_address_query_out_of_coverage_still_rule(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, _ = self._build_agent(Path(td))

            d = agent.decide("chat_detail_out", "用户地址4", "黑龙江门店具体地址在哪", [])
            self.assertEqual(d.rule_id, "ADDR_OUT_OF_COVERAGE")

    def test_address_query_known_store_still_recommend(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, _ = self._build_agent(Path(td))

            d = agent.decide("chat_detail_known", "用户地址5", "我在门头沟，地址在哪", [])
            self.assertEqual(d.rule_id, "ADDR_STORE_RECOMMEND")

    def test_not_in_beijing_and_shanghai_routes_out_of_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            user_name = "用户地址6"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_addr6",
                user_id_hash=user_hash,
                ts="2026-02-27T09:36:00",
            )

            d = agent.decide("chat_not_bj_sh", user_name, "我不在北京和上海", [])
            self.assertEqual(d.rule_id, "ADDR_OUT_OF_COVERAGE")
            self.assertEqual(d.media_plan, "contact_image")
            self.assertTrue(d.media_items)

    def test_not_in_beijing_and_shanghai_after_address_query_not_loop(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            user_name = "用户地址7"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_addr7",
                user_id_hash=user_hash,
                ts="2026-02-27T09:37:00",
            )

            d1 = agent.decide("chat_addr_loop_break", user_name, "地址在哪", [])
            self.assertIn(d1.rule_id, ("ADDR_ASK_REGION_R1", "ADDR_ASK_DISTRICT_R1"))

            d2 = agent.decide("chat_addr_loop_break", user_name, "我不在北京和上海", [])
            self.assertEqual(d2.rule_id, "ADDR_OUT_OF_COVERAGE")
            self.assertEqual(d2.media_plan, "contact_image")

    def test_kb_first_then_llm(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, repository, llm = self._build_agent(Path(td))
            repository.add("透气吗", "姐姐，我们这款透气性很好🌹", intent="wearing", tags=["佩戴体验"])

            d1 = agent.decide("chat_kb", "用户B", "透气吗", [])
            self.assertEqual(d1.reply_source, "knowledge")
            self.assertEqual(llm.calls, 0)

            d2 = agent.decide("chat_kb", "用户B", "你们营业到几点", [])
            self.assertEqual(d2.reply_source, "llm")
            self.assertEqual(llm.calls, 1)

    def test_repository_match_detail_returns_tags_and_item_id(self):
        with tempfile.TemporaryDirectory() as td:
            kb_file = Path(td) / "knowledge.json"
            kb_file.write_text("[]", encoding="utf-8")
            repository = KnowledgeRepository(kb_file)
            item = repository.add("好的谢谢", "不客气姐姐🌹", intent="general", tags=["礼貌", "结束语"])

            detail = repository.find_best_match_detail("好的谢谢", threshold=0.6)
            self.assertTrue(detail.get("matched"))
            self.assertIn("tags", detail)
            self.assertIn("item_id", detail)
            self.assertEqual(detail.get("item_id"), item.id)
            self.assertIn("礼貌", detail.get("tags", []))
            self.assertEqual(detail.get("answers"), ["不客气姐姐🌹"])

    def test_repository_legacy_answer_backfills_answers(self):
        with tempfile.TemporaryDirectory() as td:
            kb_file = Path(td) / "knowledge.json"
            kb_file.write_text(
                json.dumps(
                    [
                        {
                            "intent": "wearing",
                            "question": "会掉吗",
                            "answer": "不会掉，佩戴很稳。",
                            "tags": ["佩戴体验"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            repository = KnowledgeRepository(kb_file)
            detail = repository.find_best_match_detail("会掉吗", threshold=0.6)
            self.assertTrue(detail.get("matched"))
            self.assertEqual(detail.get("answer"), "不会掉，佩戴很稳。")
            self.assertEqual(detail.get("answers"), ["不会掉，佩戴很稳。"])

    def test_polite_closing_kb_requires_exact_match(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, repository, llm = self._build_agent(Path(td))
            repository.add("好的谢谢", "不客气姐姐🌹", intent="general", tags=["礼貌", "结束语"])

            d1 = agent.decide("chat_polite_exact", "用户礼貌1", "好的谢谢", [])
            self.assertEqual(d1.reply_source, "knowledge")
            self.assertEqual(d1.reply_text, "不客气姐姐🌹")
            self.assertFalse(d1.kb_blocked_by_polite_guard)
            self.assertEqual(d1.kb_polite_guard_reason, "")

            d2 = agent.decide("chat_polite_mixed", "用户礼貌2", "好的，但是我还想再了解一下", [])
            self.assertEqual(d2.reply_source, "llm")
            self.assertTrue(d2.kb_blocked_by_polite_guard)
            self.assertEqual(d2.kb_polite_guard_reason, "polite_not_exact")
            self.assertNotEqual(d2.reply_text, "不客气姐姐🌹")
            self.assertGreaterEqual(llm.calls, 1)

            d3 = agent.decide("chat_polite_mixed_region", "用户礼貌4", "好的，但是我不在上海怎么办啊？", [])
            self.assertNotEqual(d3.reply_source, "knowledge")
            self.assertTrue(d3.kb_blocked_by_polite_guard)
            self.assertEqual(d3.kb_polite_guard_reason, "polite_mixed_query")

    def test_polite_closing_blocked_in_intent_hint_path(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, repository, llm = self._build_agent(Path(td))
            repository.add("嗯", "好的姐姐，有任何问题随时问我哦，我一直都在呢🌷", intent="general", tags=["礼貌", "结束语"])

            d = agent.decide("chat_polite_hint", "用户礼貌3", "嗯嗯", [])
            self.assertEqual(d.reply_source, "llm")
            self.assertTrue(d.kb_blocked_by_polite_guard)
            self.assertEqual(d.kb_polite_guard_reason, "polite_not_exact")
            self.assertGreaterEqual(llm.calls, 1)

    def test_kb_variant_rotation_then_fallback_to_llm(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            agent, _, repository, llm = self._build_agent(temp_dir)
            repository.add(
                "会掉吗头发？会掉吗？",
                "非常牢固，我们有客户戴着做过山车都没问题！🎢",
                answers=[
                    "非常牢固，我们有客户戴着做过山车都没问题！🎢",
                    "结论先说：佩戴很稳，日常活动基本不会掉发。",
                    "您放心，这款固定性很好，正常活动不容易掉。",
                    "核心结论是不容易掉，贴合后稳定性很高。",
                    "简单说就是很牢固，佩戴后不容易松动或掉发。",
                ],
                intent="wearing",
                tags=["佩戴体验"],
            )

            user_name = "用户KB"
            session_id = "chat_kb_exact"
            seen = []
            for _ in range(5):
                d = agent.decide(session_id, user_name, "会掉吗？", [])
                self.assertEqual(d.reply_source, "knowledge")
                self.assertEqual(d.kb_variant_total, 5)
                self.assertGreaterEqual(d.kb_variant_selected_index, 0)
                self.assertFalse(d.kb_variant_fallback_llm)
                seen.append(d.reply_text)
                agent.mark_reply_sent(session_id, user_name, d.reply_text)

            self.assertEqual(len(set(seen)), 5)
            self.assertEqual(llm.calls, 0)

            llm.reply_text = "结论先说：佩戴很稳，正常活动不会掉发。"
            d6 = agent.decide(session_id, user_name, "会掉吗？", [])
            self.assertEqual(d6.reply_source, "llm")
            self.assertEqual(d6.rule_id, "LLM_KB_VARIANT_FALLBACK")
            self.assertTrue(d6.kb_variant_fallback_llm)
            self.assertEqual(d6.kb_variant_total, 5)
            self.assertGreaterEqual(llm.calls, 1)

    def test_llm_normalize_only_single_trailing_emoji(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, _ = self._build_agent(Path(td))
            normalized = agent._normalize_reply_text("放心戴🌹蹦迪跳舞都不掉哦～💃🌹")
            self.assertTrue(normalized.endswith("。🌹"))
            self.assertEqual(normalized.count("🌹"), 1)
            self.assertNotIn("💃", normalized)
            self.assertNotIn("～", normalized)

    def test_llm_normalize_enforces_brevity_limit(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, _ = self._build_agent(Path(td))
            normalized = agent._normalize_reply_text(
                "姐姐我们目前门店在北京朝阳和上海5家店（静安、人广、虹口、五角场、徐汇），外地暂时没有门店；如果您方便来店，我可以帮您安排试戴和购买流程。"
            )
            self.assertTrue(normalized.endswith("。🌹"))
            self.assertLessEqual(len(normalized) - 1, 33)

    def test_shipping_terms_hard_blocked(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, llm = self._build_agent(Path(td))
            llm.reply_text = "姐姐我们全国包邮到家呢～📦"

            d = agent.decide("chat_shipping_block", "用户物流", "物流怎么发", [])
            self.assertEqual(d.reply_source, "llm")
            self.assertEqual(d.reply_text, "姐姐我们是到店定制哦。🌹")

    def test_north_fallback_purchase_recommends_beijing_when_no_contact_sent(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_north_beijing"
            user_name = "北方用户A"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_north_a",
                user_id_hash=user_hash,
                ts="2026-02-27T10:00:00",
            )

            d = agent.decide(session_id, user_name, "我在内蒙古怎么买？", [])
            self.assertEqual(d.rule_id, "ADDR_STORE_RECOMMEND")
            self.assertEqual(d.route_reason, "north_fallback_beijing")
            self.assertEqual(d.media_plan, "address_image")
            self.assertTrue(d.media_items)
            self.assertIn("北京朝阳门店", d.reply_text)

    def test_north_fallback_purchase_after_contact_sent_uses_circle_remind(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_north_contact_sent"
            user_name = "北方用户B"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_north_b",
                user_id_hash=user_hash,
                ts="2026-02-27T10:00:00",
            )
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="contact_image",
                media_path=str(temp_dir / "images" / "contact.jpg"),
                ts="2026-02-27T10:01:00",
                user_id_hash=user_hash,
            )

            d = agent.decide(session_id, user_name, "我在内蒙古怎么买？", [])
            self.assertEqual(d.rule_id, "PURCHASE_REMOTE_CONTACT_REMIND_ONLY")
            self.assertEqual(d.route_reason, "north_fallback_beijing")
            self.assertEqual(d.media_plan, "none")
            self.assertFalse(d.media_items)
            self.assertIn("画圈", d.reply_text)

    def test_first_turn_purchase_unknown_routes_to_addr_ask_region(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            agent, _, _, _ = self._build_agent(temp_dir)

            d = agent.decide("chat_first_purchase_unknown", "用户首轮购买", "姐姐你好，我想买假发", [])
            self.assertEqual(d.rule_id, "ADDR_ASK_REGION_R1")
            self.assertTrue(d.is_first_turn_global)
            self.assertEqual(d.media_plan, "none")
            self.assertFalse(d.media_items)

    def test_first_turn_global_blocks_contact_image(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            agent, _, _, _ = self._build_agent(temp_dir)

            d = agent.decide("chat_first_contact", "用户首轮", "我在门头沟怎么买", [])
            self.assertEqual(d.rule_id, "PURCHASE_CONTACT_FROM_KNOWN_GEO")
            self.assertTrue(d.is_first_turn_global)
            self.assertTrue(d.first_turn_media_guard_applied)
            self.assertEqual(d.media_plan, "none")
            self.assertEqual(d.media_skip_reason, "first_turn_global_no_media")
            self.assertFalse(d.media_items)

    def test_first_turn_global_blocks_address_image(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            agent, _, _, _ = self._build_agent(temp_dir)

            d = agent.decide("chat_first_address", "用户首轮地址", "我在门头沟", [])
            self.assertEqual(d.rule_id, "ADDR_STORE_RECOMMEND")
            self.assertTrue(d.is_first_turn_global)
            self.assertTrue(d.first_turn_media_guard_applied)
            self.assertEqual(d.media_plan, "none")
            self.assertEqual(d.media_skip_reason, "first_turn_global_no_media")
            self.assertFalse(d.media_items)

    def test_after_first_turn_allows_media_across_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            user_name = "用户跨会话"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_cross",
                user_id_hash=user_hash,
                ts="2026-02-27T09:00:00",
            )

            d = agent.decide("chat_next_session", user_name, "我在门头沟怎么买", [])
            self.assertFalse(d.is_first_turn_global)
            self.assertFalse(d.first_turn_media_guard_applied)
            self.assertEqual(d.rule_id, "PURCHASE_CONTACT_FROM_KNOWN_GEO")
            self.assertEqual(d.media_plan, "contact_image")
            self.assertTrue(d.media_items)

    def test_contact_image_frequency_and_whitelist(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            white_session = "chat_white"
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir, whitelist_sessions=[white_session])
            user_name = "用户C"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_c",
                user_id_hash=user_hash,
                ts="2026-02-27T09:30:00",
            )

            s1 = "chat_normal"
            d1 = agent.decide(s1, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d1.media_plan, "contact_image")
            self.assertTrue(d1.media_items)
            agent.mark_media_sent(s1, user_name, d1.media_items[0], success=True)
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
            self.assertEqual(d2.rule_id, "ADDR_OUT_OF_COVERAGE_REMIND_ONLY")

            d2b = agent.decide(s1, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d2b.media_plan, "none")
            self.assertFalse(d2b.media_items)
            self.assertEqual(d2b.rule_id, "ADDR_OUT_OF_COVERAGE_REMIND_ONLY")

            d2c = agent.decide(s1, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d2c.media_plan, "none")
            self.assertFalse(d2c.media_items)
            self.assertEqual(d2c.rule_id, "ADDR_OUT_OF_COVERAGE_REMIND_ONLY")

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

    def test_shipping_kb_match_appends_contact_image_with_3x_limit(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, repository, _ = self._build_agent(temp_dir)
            repository.add(
                "那我怎么购买呢？可以寄吗？可以邮寄吗？快递可以吗？寄快递",
                "姐姐，我们是假发私人定制的，您可以加我，我远程给您定制😊",
                intent="purchase",
                tags=["邮寄"],
                answers=[
                    "姐姐，我们是假发私人定制的，您可以加我，我远程给您定制😊",
                    "姐姐可以寄的，不过需要先定制，您加我我给您详细对接一下😊",
                ],
            )

            user_name = "用户邮寄"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_shipping_user",
                user_id_hash=user_hash,
                ts="2026-02-27T10:20:00",
            )
            session_id = "chat_shipping_kb"

            d1 = agent.decide(session_id, user_name, "不同价格有什么区别，可以邮寄吗", [])
            self.assertEqual(d1.reply_source, "knowledge")
            self.assertEqual(d1.rule_id, "KB_MATCH_CONTACT_IMAGE")
            self.assertEqual(d1.reply_text, "姐姐，我们是假发私人定制的，您可以加我，我远程给您定制😊")
            self.assertEqual(d1.media_plan, "contact_image")
            self.assertTrue(d1.media_items)
            agent.mark_media_sent(session_id, user_name, d1.media_items[0], success=True)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="contact_image",
                media_path=d1.media_items[0]["path"],
                ts="2999-01-01T00:10:00",
                user_id_hash=user_hash,
            )

            d2 = agent.decide(session_id, user_name, "不同价格有什么区别，可以邮寄吗", [])
            self.assertEqual(d2.reply_source, "knowledge")
            self.assertEqual(d2.rule_id, "KB_MATCH_CONTACT_IMAGE")
            self.assertEqual(d2.media_plan, "contact_image")
            self.assertTrue(d2.media_items)
            agent.mark_media_sent(session_id, user_name, d2.media_items[0], success=True)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="contact_image",
                media_path=d2.media_items[0]["path"],
                ts="2999-01-01T00:10:30",
                user_id_hash=user_hash,
            )

            d3 = agent.decide(session_id, user_name, "不同价格有什么区别，可以邮寄吗", [])
            self.assertEqual(d3.reply_source, "knowledge")
            self.assertEqual(d3.rule_id, "KB_MATCH_CONTACT_IMAGE")
            self.assertEqual(d3.media_plan, "contact_image")
            self.assertTrue(d3.media_items)
            agent.mark_media_sent(session_id, user_name, d3.media_items[0], success=True)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="contact_image",
                media_path=d3.media_items[0]["path"],
                ts="2999-01-01T00:11:00",
                user_id_hash=user_hash,
            )

            d4 = agent.decide(session_id, user_name, "不同价格有什么区别，可以邮寄吗", [])
            self.assertEqual(d4.reply_source, "knowledge")
            self.assertEqual(d4.rule_id, "KB_MATCH_CONTACT_IMAGE")
            self.assertEqual(d4.media_plan, "none")
            self.assertFalse(d4.media_items)
            self.assertEqual(d4.media_skip_reason, "contact_image_already_sent")

    def test_shipping_kb_match_first_turn_still_blocked_by_global_media_guard(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            agent, _, repository, _ = self._build_agent(temp_dir)
            repository.add(
                "可以邮寄吗",
                "姐姐，我们是假发私人定制的，您可以加我，我远程给您定制😊",
                intent="purchase",
                tags=["邮寄"],
            )

            d = agent.decide("chat_shipping_first_turn", "用户首轮邮寄", "可以邮寄吗", [])
            self.assertEqual(d.reply_source, "knowledge")
            self.assertEqual(d.rule_id, "KB_MATCH_CONTACT_IMAGE")
            self.assertEqual(d.media_plan, "none")
            self.assertTrue(d.is_first_turn_global)
            self.assertTrue(d.first_turn_media_guard_applied)
            self.assertEqual(d.media_skip_reason, "first_turn_global_no_media")
            self.assertFalse(d.media_items)

    def test_appointment_kb_priority_over_purchase_rule(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, repository, _ = self._build_agent(temp_dir)
            repository.add(
                "怎么预约？如何预约？需要预约吗？",
                "姐姐，我们是预约制的呢，避免您跑空您看看图上红框框加我预约🌷",
                intent="appointment",
                tags=["预约"],
                answers=[
                    "姐姐我们这边是预约制的～您可以看看红框内容加我预约🌷",
                ],
            )

            user_name = "用户预约优先"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_appoint_priority",
                user_id_hash=user_hash,
                ts="2026-02-27T10:40:00",
            )

            d = agent.decide("chat_appoint_priority", user_name, "怎么预约？", [])
            self.assertEqual(d.reply_source, "knowledge")
            self.assertEqual(d.rule_id, "KB_MATCH_CONTACT_IMAGE")
            self.assertEqual(d.media_plan, "contact_image")
            self.assertTrue(d.media_items)

    def test_appointment_kb_contact_image_limit_3(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, repository, _ = self._build_agent(temp_dir)
            repository.add(
                "怎么预约？如何预约？需要预约吗？",
                "姐姐，我们是预约制的呢，避免您跑空您看看图上红框框加我预约🌷",
                intent="appointment",
                tags=["预约"],
                answers=[
                    "姐姐我们这边是预约制的～您可以看看红框内容加我预约🌷",
                    "需要预约的姐姐～您什么时间方便？您可以看看红框内容+我😊",
                ],
            )

            user_name = "用户预约上限"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_appoint_limit",
                user_id_hash=user_hash,
                ts="2026-02-27T10:45:00",
            )
            session_id = "chat_appoint_limit"

            for idx, ts in enumerate(("2999-01-01T00:20:00", "2999-01-01T00:20:30", "2999-01-01T00:21:00"), start=1):
                d = agent.decide(session_id, user_name, "需要预约吗？", [])
                self.assertEqual(d.reply_source, "knowledge")
                self.assertEqual(d.rule_id, "KB_MATCH_CONTACT_IMAGE")
                self.assertEqual(d.media_plan, "contact_image")
                self.assertTrue(d.media_items)
                agent.mark_media_sent(session_id, user_name, d.media_items[0], success=True)
                self._append_media_success_log(
                    conversations_dir=conversations_dir,
                    session_id=session_id,
                    media_type="contact_image",
                    media_path=d.media_items[0]["path"],
                    ts=ts,
                    user_id_hash=user_hash,
                )

            d4 = agent.decide(session_id, user_name, "需要预约吗？", [])
            self.assertEqual(d4.reply_source, "knowledge")
            self.assertEqual(d4.rule_id, "KB_MATCH_CONTACT_IMAGE")
            self.assertEqual(d4.media_plan, "none")
            self.assertFalse(d4.media_items)
            self.assertEqual(d4.media_skip_reason, "contact_image_already_sent")

    def test_appointment_first_turn_global_guard_blocks_media(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            agent, _, repository, _ = self._build_agent(temp_dir)
            repository.add(
                "怎么预约？如何预约？需要预约吗？",
                "姐姐，我们是预约制的呢，避免您跑空您看看图上红框框加我预约🌷",
                intent="appointment",
                tags=["预约"],
            )

            d = agent.decide("chat_appoint_first_turn", "用户预约首轮", "怎么预约？", [])
            self.assertEqual(d.reply_source, "knowledge")
            self.assertEqual(d.rule_id, "KB_MATCH_CONTACT_IMAGE")
            self.assertEqual(d.media_plan, "none")
            self.assertTrue(d.is_first_turn_global)
            self.assertTrue(d.first_turn_media_guard_applied)
            self.assertEqual(d.media_skip_reason, "first_turn_global_no_media")
            self.assertFalse(d.media_items)

    def test_kb_match_without_shipping_keeps_media_none(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, repository, _ = self._build_agent(temp_dir)
            repository.add(
                "价格是多少",
                "姐姐，主要看发质和工艺，价格区间我可以给您详细讲解😊",
                intent="price",
                tags=["价格"],
            )

            user_name = "用户普通KB"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_normal_kb",
                user_id_hash=user_hash,
                ts="2026-02-27T10:30:00",
            )

            d = agent.decide("chat_normal_kb", user_name, "价格是多少", [])
            self.assertEqual(d.reply_source, "knowledge")
            self.assertEqual(d.rule_id, "KB_MATCH")
            self.assertEqual(d.media_plan, "none")
            self.assertFalse(d.media_items)

    def test_video_session_once_with_log_driven_state(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            user_name = "用户D"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_d",
                user_id_hash=user_hash,
                ts="2026-02-27T09:40:00",
            )

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
            # 联系方式图之后的第1条用户消息，不触发视频
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
                + "\n",
                encoding="utf-8",
            )
            self.assertIsNone(agent.mark_reply_sent("chat_a", user_name, "第一轮回复"))

            # 联系方式图之后第2条用户消息，触发视频
            (conversations_dir / "chat_a.jsonl").write_text(
                (conversations_dir / "chat_a.jsonl").read_text(encoding="utf-8")
                + json.dumps(
                    {
                        "timestamp": "2026-02-27T10:00:03",
                        "session_id": "chat_a",
                        "user_id_hash": user_hash,
                        "event_type": "user_message",
                        "reply_source": "",
                        "rule_id": "",
                        "model_name": "",
                        "payload": {"text": "我再问下"},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            video_item = agent.mark_reply_sent("chat_a", user_name, "第二轮回复")
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
            self.assertEqual(d2.media_plan, "contact_image")
            self.assertTrue(d2.media_items)
            self.assertIsNone(agent.mark_reply_sent("chat_a", user_name, "再追问一次"))

    def test_video_media_fallback_when_config_name_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            agent, _, _, _ = self._build_agent(temp_dir)

            bad_config = {
                "version": 1,
                "categories": ["联系方式", "店铺地址", "视频素材"],
                "images": {
                    "联系方式": ["contact.jpg"],
                    "店铺地址": ["北京地址.jpg"],
                    "视频素材": ["配置里不存在的视频名.mp4"],
                },
            }
            (temp_dir / "image_categories.json").write_text(
                json.dumps(bad_config, ensure_ascii=False),
                encoding="utf-8",
            )
            agent.reload_media_library()
            status = agent.get_status()
            self.assertGreater(status.get("video_media_count", 0), 0)
            self.assertTrue(agent._pick_video_media())

    def test_purchase_known_geo_contact_then_remind(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_geo"
            user_name = "用户E"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_e",
                user_id_hash=user_hash,
                ts="2026-02-27T09:50:00",
            )

            d0 = agent.decide(session_id, user_name, "我在长宁", [])
            self.assertEqual(d0.rule_id, "ADDR_STORE_RECOMMEND")

            d1 = agent.decide(session_id, user_name, "怎么买啊", [])
            self.assertEqual(d1.rule_id, "PURCHASE_CONTACT_FROM_KNOWN_GEO")
            self.assertEqual(d1.media_plan, "contact_image")
            self.assertTrue(d1.media_items)
            agent.mark_media_sent(session_id, user_name, d1.media_items[0], success=True)
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

    def test_not_in_shanghai_purchase_sends_contact_if_not_sent(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_not_in_sh"
            user_name = "用户E2"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_e2",
                user_id_hash=user_hash,
                ts="2026-02-27T09:51:00",
            )

            d0 = agent.decide(session_id, user_name, "我在长宁", [])
            self.assertEqual(d0.rule_id, "ADDR_STORE_RECOMMEND")

            d1 = agent.decide(session_id, user_name, "不在上海怎么买？", [])
            self.assertEqual(d1.rule_id, "PURCHASE_REMOTE_CONTACT_IMAGE")
            self.assertEqual(d1.media_plan, "contact_image")
            self.assertTrue(d1.media_items)

    def test_not_in_shanghai_purchase_remind_if_contact_already_sent(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_not_in_sh_sent"
            user_name = "用户E3"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_e3",
                user_id_hash=user_hash,
                ts="2026-02-27T09:52:00",
            )

            d0 = agent.decide(session_id, user_name, "我在长宁", [])
            self.assertEqual(d0.rule_id, "ADDR_STORE_RECOMMEND")

            d1 = agent.decide(session_id, user_name, "怎么预约？", [])
            self.assertEqual(d1.rule_id, "PURCHASE_CONTACT_FROM_KNOWN_GEO")
            self.assertEqual(d1.media_plan, "contact_image")
            self.assertTrue(d1.media_items)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="contact_image",
                media_path=d1.media_items[0]["path"],
                ts="2026-02-27T10:02:00",
                user_id_hash=user_hash,
            )

            d2 = agent.decide(session_id, user_name, "不在上海怎么买？", [])
            self.assertEqual(d2.rule_id, "PURCHASE_REMOTE_CONTACT_REMIND_ONLY")
            self.assertEqual(d2.media_plan, "none")
            self.assertIn("远程定制", d2.reply_text)

    def test_purchase_known_geo_not_blocked_by_legacy_contact_count(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_geo_legacy"
            user_name = "用户G"

            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_g",
                user_id_hash=user_hash,
                ts="2026-02-27T09:55:00",
            )
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
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_f",
                user_id_hash=user_hash,
                ts="2026-02-27T09:58:00",
            )

            d1 = agent.decide(session_id, user_name, "我在门头沟", [])
            self.assertEqual(d1.rule_id, "ADDR_STORE_RECOMMEND")
            self.assertEqual(d1.media_plan, "address_image")
            self.assertTrue(d1.media_items)
            agent.mark_media_sent(session_id, user_name, d1.media_items[0], success=True)
            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="address_image",
                media_path=d1.media_items[0]["path"],
                ts=datetime.now().isoformat(timespec="seconds"),
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
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_h",
                user_id_hash=user_hash,
                ts="2020-01-01T10:29:00",
            )

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

    def test_llm_prompt_includes_structured_conversation_context(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, llm = self._build_agent(temp_dir)
            user_name = "用户上下文"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_context",
                user_id_hash=user_hash,
                ts="2026-02-27T11:00:00",
            )

            history = [
                {"role": "user", "content": "我在上海，想看看门店"},
                {"role": "assistant", "content": "好的姐姐，您在上海哪个区呢"},
                {"role": "user", "content": "我不在上海，先了解下区别"},
            ]
            d = agent.decide(
                session_id="chat_context_prompt",
                user_name=user_name,
                latest_user_text="你们和其他家的主要差别是什么？",
                conversation_history=history,
            )
            self.assertEqual(d.reply_source, "llm")
            self.assertIn("【对话上下文】", llm.prompt)
            self.assertIn("1. 用户:", llm.prompt)
            self.assertIn("用户(当前): 你们和其他家的主要差别是什么？", llm.prompt)

    def test_after_sales_out_of_coverage_should_not_send_contact_image(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            user_name = "用户售后"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_after_sales",
                user_id_hash=user_hash,
                ts="2026-02-27T11:10:00",
            )

            d = agent.decide(
                session_id="chat_after_sales_remote",
                user_name=user_name,
                latest_user_text="我不在上海，售后怎么处理？",
                conversation_history=[],
            )
            self.assertEqual(d.rule_id, "AFTER_SALES_REMOTE_SUPPORT")
            self.assertEqual(d.media_plan, "none")
            self.assertFalse(d.media_items)

    def test_after_sales_followup_should_not_fallback_to_generic_kb(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, repository, _ = self._build_agent(temp_dir)
            repository.add(
                "毛躁怎么办",
                "可以的姐姐，不影响佩戴🥰",
                intent="wearing",
                tags=["佩戴体验"],
            )

            user_name = "用户售后跟进"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_after_sales_followup",
                user_id_hash=user_hash,
                ts="2026-02-27T11:20:00",
            )
            session_id = "chat_after_sales_followup"

            d1 = agent.decide(
                session_id=session_id,
                user_name=user_name,
                latest_user_text="我不在上海怎么清洗？我在山东",
                conversation_history=[],
            )
            self.assertEqual(d1.rule_id, "AFTER_SALES_REMOTE_SUPPORT")

            d2 = agent.decide(
                session_id=session_id,
                user_name=user_name,
                latest_user_text="我那个假发现在有点毛躁，佩戴了大概有半个月了",
                conversation_history=[{"role": "assistant", "content": d1.reply_text}],
            )
            self.assertEqual(d2.rule_id, "AFTER_SALES_DETAIL_GUIDE")
            self.assertNotIn("不影响佩戴", d2.reply_text)
            self.assertEqual(d2.media_plan, "none")

            d3 = agent.decide(
                session_id=session_id,
                user_name=user_name,
                latest_user_text="我已经告诉你问题了，按这个情况怎么处理",
                conversation_history=[{"role": "assistant", "content": d2.reply_text}],
            )
            self.assertIn(d3.rule_id, ("AFTER_SALES_DETAIL_GUIDE", "AFTER_SALES_FOLLOWUP"))
            self.assertNotEqual(d3.reply_source, "knowledge")
            self.assertEqual(d3.media_plan, "none")

    def test_after_sales_session_should_not_trigger_delayed_video(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, _ = self._build_agent(temp_dir)
            user_name = "用户售后视频"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_after_sales_video",
                user_id_hash=user_hash,
                ts="2026-02-27T11:30:00",
            )
            session_id = "chat_after_sales_video"

            self._append_media_success_log(
                conversations_dir=conversations_dir,
                session_id=session_id,
                media_type="contact_image",
                media_path=str(temp_dir / "images" / "contact.jpg"),
                ts="2026-02-27T11:31:00",
                user_id_hash=user_hash,
            )

            session_log_file = conversations_dir / f"{session_id}.jsonl"
            session_log_file.write_text(
                session_log_file.read_text(encoding="utf-8")
                + json.dumps(
                    {
                        "timestamp": "2026-02-27T11:31:10",
                        "session_id": session_id,
                        "user_id_hash": user_hash,
                        "event_type": "user_message",
                        "reply_source": "",
                        "rule_id": "",
                        "model_name": "",
                        "payload": {"text": "第一条"},
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "timestamp": "2026-02-27T11:31:20",
                        "session_id": session_id,
                        "user_id_hash": user_hash,
                        "event_type": "user_message",
                        "reply_source": "",
                        "rule_id": "",
                        "model_name": "",
                        "payload": {"text": "第二条"},
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            agent.memory_store.update_session_state(
                session_id,
                {
                    "last_question_type": "after_sales",
                    "after_sales_session_locked": True,
                },
                user_hash=user_hash,
            )

            video_item = agent.mark_reply_sent(session_id, user_name, "售后回复")
            self.assertIsNone(video_item)

    def test_both_images_strong_intent_first_fixed_then_llm(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, _, llm = self._build_agent(temp_dir)
            session_id = "chat_lock_purchase"
            user_name = "用户I"
            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_i",
                user_id_hash=user_hash,
                ts="2026-02-27T10:39:00",
            )

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

    def test_both_images_first_hint_ignores_legacy_strong_count_and_second_hits_kb(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            conversations_dir = temp_dir / "conversations"
            agent, _, repository, _ = self._build_agent(temp_dir)
            session_id = "chat_lock_purchase_legacy_count"
            user_name = "用户Legacy"
            user_hash = agent._hash_user(user_name)

            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_legacy",
                user_id_hash=user_hash,
                ts="2026-02-27T10:39:00",
            )
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
                {
                    "last_target_store": "beijing_chaoyang",
                    "strong_intent_after_both_count": 18,
                    "purchase_both_first_hint_sent": False,
                },
                user_hash=user_hash,
            )
            repository.add(
                "怎么预约",
                "结论先说：可以预约到店，我现在就帮您安排。",
                answers=[
                    "结论先说：可以预约到店，我现在就帮您安排。",
                    "可以预约的姐姐，您告诉我方便时间我来登记。",
                    "您这边可以直接预约到店，我帮您对接门店时间。",
                    "没问题，预约到店这边可以安排，您说下时间偏好。",
                    "支持预约到店，我这边马上给您走预约流程。",
                ],
                intent="purchase",
                tags=["预约"],
            )

            d1 = agent.decide(session_id, user_name, "怎么预约", [])
            self.assertEqual(d1.reply_source, "knowledge")
            self.assertEqual(d1.rule_id, "KB_MATCH_CONTACT_IMAGE")
            self.assertEqual(d1.media_plan, "contact_image")
            self.assertFalse(d1.kb_variant_fallback_llm)

            d2 = agent.decide(session_id, user_name, "怎么预约", [])
            self.assertEqual(d2.reply_source, "knowledge")
            self.assertEqual(d2.rule_id, "KB_MATCH_CONTACT_IMAGE")
            self.assertEqual(d2.media_plan, "contact_image")
            self.assertFalse(d2.kb_variant_fallback_llm)

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

            d = agent.decide(session_id, user_name, "你们有活动吗", [])
            self.assertNotEqual(agent._normalize_for_dedupe(d.reply_text), normalized)
            self.assertIn(d.reply_text, agent._dedupe_reply_pool)

    def test_log_deleted_resets_stale_media_state(self):
        with tempfile.TemporaryDirectory() as td:
            temp_dir = Path(td)
            agent, _, _, _ = self._build_agent(temp_dir)
            session_id = "chat_reset_by_log_delete"
            user_name = "用户K"
            conversations_dir = temp_dir / "conversations"

            user_hash = agent._hash_user(user_name)
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_k",
                user_id_hash=user_hash,
                ts="2026-02-27T10:10:00",
            )
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
            self._append_assistant_reply_log(
                conversations_dir=conversations_dir,
                session_id="seed_user_v",
                user_id_hash=user_hash,
                ts="2026-02-27T09:59:00",
            )

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
                        "timestamp": "2026-02-27T10:00:03",
                        "session_id": session_id,
                        "user_id_hash": user_hash,
                        "event_type": "user_message",
                        "reply_source": "",
                        "rule_id": "",
                        "model_name": "",
                        "payload": {"text": "再问一次"},
                    },
                    ensure_ascii=False,
                )
                + "\n"
                + json.dumps(
                    {
                        "timestamp": "2026-02-27T10:00:04",
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
                {
                    "timestamp": "2020-01-01T10:00:12",
                    "session_id": session_id,
                    "user_id_hash": agent._hash_user(user_name),
                    "event_type": "assistant_reply",
                    "reply_source": "rule",
                    "rule_id": "DUMMY",
                    "model_name": "",
                    "payload": {"text": "收到", "round_media_sent_types": []},
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
