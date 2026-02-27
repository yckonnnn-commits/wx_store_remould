import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from src.core.message_processor import MessageProcessor
from src.core.session_manager import SessionManager
from src.data.memory_store import MemoryStore


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


if __name__ == "__main__":
    unittest.main()
