import json
import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.core.message_processor import MessageProcessor
from src.core.private_cs_agent import AgentDecision
from src.core.session_manager import SessionManager
from src.data.memory_store import MemoryStore
from src.services.conversation_logger import ConversationLogger


class DummyBrowser(QObject):
    page_loaded = Signal(bool)
    url_changed = Signal(str)

    def find_and_click_first_unread(self, callback):
        del callback

    def grab_chat_data(self, callback):
        del callback

    def send_message(self, text, callback):
        del text, callback

    def send_image(self, media_path, callback):
        del media_path, callback


class DummyAgent:
    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store

    def reload_media_library(self):
        return None

    def reload_rule_configs(self):
        return None

    def reload_prompt_docs(self):
        return True


class DummyBrowserFlow(QObject):
    page_loaded = Signal(bool)
    url_changed = Signal(str)

    def find_and_click_first_unread(self, callback):
        del callback

    def grab_chat_data(self, callback):
        del callback

    def send_message(self, text, callback):
        del text
        callback(True, {"ok": True})

    def send_image(self, media_path, callback):
        del media_path
        callback(True, {"ok": True})


class DummyAgentFlow:
    def __init__(self, memory_store: MemoryStore):
        self.memory_store = memory_store

    def reload_media_library(self):
        return None

    def reload_rule_configs(self):
        return None

    def reload_prompt_docs(self):
        return True

    def decide(self, session_id: str, user_name: str, latest_user_text: str, conversation_history=None):
        del session_id, user_name, latest_user_text, conversation_history
        return AgentDecision(
            reply_text="姐姐我马上帮您安排～🌹",
            intent="purchase",
            route_reason="known_geo_context",
            reply_goal="推进购买意图",
            media_plan="contact_image",
            media_items=[{"type": "contact_image", "path": "dummy.jpg"}],
            reply_source="rule",
            rule_id="PURCHASE_TEST",
            rule_applied=True,
            geo_context_source="session_last_target_store",
            media_skip_reason="",
            both_images_sent_state=True,
        )

    def mark_reply_sent(self, session_id: str, user_name: str, reply_text: str):
        del session_id, user_name, reply_text
        return None

    def mark_media_sent(self, session_id: str, user_name: str, media_item, success: bool):
        del session_id, user_name, media_item, success
        return None


class MessageProcessorSessionIdTestCase(unittest.TestCase):
    def test_fallback_session_id_splits_by_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            memory_store = MemoryStore(Path(td) / "memory.json")
            browser = DummyBrowser()
            sessions = SessionManager()
            agent = DummyAgent(memory_store)
            processor = MessageProcessor(browser, sessions, agent)

            user_name = "同名用户"

            base_session = processor._build_session_id(
                user_name=user_name,
                chat_session_key="",
                chat_session_fingerprint="fp_a",
            )
            self.assertTrue(base_session.startswith("user_"))

            user_hash = processor._build_user_hash(user_name=user_name, session_id=base_session)
            memory_store.update_session_state(
                session_id=base_session,
                updates={"session_fingerprint": "fp_a"},
                user_hash=user_hash,
            )

            same_fp_session = processor._build_session_id(
                user_name=user_name,
                chat_session_key="",
                chat_session_fingerprint="fp_a",
            )
            self.assertEqual(same_fp_session, base_session)

            split_session = processor._build_session_id(
                user_name=user_name,
                chat_session_key="",
                chat_session_fingerprint="fp_b",
            )
            self.assertNotEqual(split_session, base_session)
            self.assertTrue(split_session.startswith(base_session + "_"))

            keyed_session = processor._build_session_id(
                user_name=user_name,
                chat_session_key="real_session_key",
                chat_session_fingerprint="fp_b",
            )
            self.assertTrue(keyed_session.startswith("chat_"))

    def test_decision_and_assistant_log_media_aggregates(self):
        with tempfile.TemporaryDirectory() as td:
            memory_store = MemoryStore(Path(td) / "memory.json")
            browser = DummyBrowserFlow()
            sessions = SessionManager()
            agent = DummyAgentFlow(memory_store)
            processor = MessageProcessor(browser, sessions, agent)
            processor.conversation_logger = ConversationLogger(Path(td) / "conversations")

            payload = {
                "user_name": "日志用户",
                "chat_session_key": "",
                "chat_session_method": "fallback",
                "chat_session_fingerprint": "fp_log",
                "messages": [
                    {"text": "历史客服", "is_user": False},
                    {"text": "需要预约吗？", "is_user": True},
                ],
            }

            processor._on_chat_data(True, payload, auto_reply=True)
            processor._send_pending_decision()

            session_id = processor._build_session_id("日志用户", "", "fp_log")
            log_path = processor.conversation_logger._session_file(session_id)
            lines = [json.loads(x) for x in log_path.read_text(encoding="utf-8").splitlines() if x.strip()]

            decision_events = [x for x in lines if x.get("event_type") == "decision_snapshot"]
            assistant_events = [x for x in lines if x.get("event_type") == "assistant_reply"]
            self.assertTrue(decision_events)
            self.assertTrue(assistant_events)

            decision_payload = decision_events[-1].get("payload", {})
            self.assertIn("round_media_blocked", decision_payload)
            self.assertIn("round_media_block_reason", decision_payload)
            self.assertIn("round_media_planned_types", decision_payload)
            self.assertIn("both_images_sent_state", decision_payload)

            assistant_payload = assistant_events[-1].get("payload", {})
            self.assertIn("round_media_sent", assistant_payload)
            self.assertIn("round_media_sent_types", assistant_payload)
            self.assertIn("round_media_failed_types", assistant_payload)
            self.assertTrue(assistant_payload.get("round_media_sent"))
            self.assertIn("contact_image", assistant_payload.get("round_media_sent_types", []))


if __name__ == "__main__":
    unittest.main()
