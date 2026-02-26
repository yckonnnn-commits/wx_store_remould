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
        self.calls = 0
        self.prompt = ""

    def set_system_prompt(self, prompt: str):
        self.prompt = prompt

    def generate_reply_sync(self, user_message: str, conversation_history=None):
        self.calls += 1
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
        )
        return agent, knowledge_service, repository, llm_service

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

    def test_contact_image_frequency_and_whitelist(self):
        with tempfile.TemporaryDirectory() as td:
            white_session = "chat_white"
            agent, _, _, _ = self._build_agent(Path(td), whitelist_sessions=[white_session])
            user_name = "用户C"

            s1 = "chat_normal"
            d1 = agent.decide(s1, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d1.media_plan, "contact_image")
            self.assertTrue(d1.media_items)
            agent.mark_media_sent(s1, user_name, d1.media_items[0], success=True)

            d2 = agent.decide(s1, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d2.media_plan, "none")
            self.assertFalse(d2.media_items)

            d3 = agent.decide(white_session, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d3.media_plan, "contact_image")
            self.assertTrue(d3.media_items)
            agent.mark_media_sent(white_session, user_name, d3.media_items[0], success=True)

            d4 = agent.decide(white_session, user_name, "我在黑龙江怎么买", [])
            self.assertEqual(d4.media_plan, "contact_image")
            self.assertTrue(d4.media_items)

    def test_video_user_once(self):
        with tempfile.TemporaryDirectory() as td:
            agent, _, _, _ = self._build_agent(Path(td), whitelist_sessions=["chat_a", "chat_b"])
            user_name = "用户D"

            d1 = agent.decide("chat_a", user_name, "我在黑龙江怎么买", [])
            agent.mark_media_sent("chat_a", user_name, d1.media_items[0], success=True)

            self.assertIsNone(agent.mark_reply_sent("chat_a", user_name, "好的"))
            video_item = agent.mark_reply_sent("chat_a", user_name, "继续说")
            self.assertIsNotNone(video_item)
            self.assertEqual(video_item.get("type"), "delayed_video")
            agent.mark_media_sent("chat_a", user_name, video_item, success=True)

            d2 = agent.decide("chat_b", user_name, "我在黑龙江怎么买", [])
            agent.mark_media_sent("chat_b", user_name, d2.media_items[0], success=True)
            self.assertIsNone(agent.mark_reply_sent("chat_b", user_name, "再问一个问题"))
            self.assertIsNone(agent.mark_reply_sent("chat_b", user_name, "再追问一次"))


if __name__ == "__main__":
    unittest.main()

