"""
主窗口
整合 PySide6 多标签页与单一 Agent 主链路。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..core.message_processor import MessageProcessor
from ..core.private_cs_agent import CustomerServiceAgent
from ..core.session_manager import SessionManager
from ..data.config_manager import ConfigManager
from ..data.knowledge_repository import KnowledgeRepository
from ..data.memory_store import MemoryStore
from ..services.browser_service import BrowserService
from ..services.knowledge_service import KnowledgeService
from ..services.llm_service import LLMService
from ..utils.constants import MAIN_STYLE_SHEET, WECHAT_STORE_URL
from .agent_status_tab import AgentStatusTab
from .browser_tab import BrowserTab
from .image_management_tab import ImageManagementTab
from .knowledge_tab import KnowledgeTab
from .left_panel import LeftPanel
from .model_config_tab import ModelConfigTab


class MainWindow(QWidget):
    """主窗口"""

    def __init__(self, config_manager: ConfigManager, knowledge_repository: KnowledgeRepository, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 智能客服系统")
        self.resize(1600, 900)

        self.config_manager = config_manager
        self.knowledge_repository = knowledge_repository

        self._init_services()
        self._setup_ui()
        self._connect_signals()
        self._load_wechat_store()

    def _init_services(self):
        self.browser_service = None

        self.knowledge_service = KnowledgeService(self.knowledge_repository)
        self.llm_service = LLMService(self.config_manager)
        self.session_manager = SessionManager()

        self.memory_store = MemoryStore(Path("config") / "agent_memory.json")
        self.agent = CustomerServiceAgent(
            knowledge_service=self.knowledge_service,
            llm_service=self.llm_service,
            memory_store=self.memory_store,
            images_dir=Path("images"),
            image_categories_path=Path("config") / "image_categories.json",
            system_prompt_doc_path=Path("docs") / "system_prompt_private_ai_customer_service.md",
            playbook_doc_path=Path("docs") / "private_ai_customer_service_playbook.md",
        )
        self.message_processor = None

    def _setup_ui(self):
        self.setStyleSheet(MAIN_STYLE_SHEET)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.left_panel = LeftPanel(self)
        main_layout.addWidget(self.left_panel)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        top_bar = QFrame()
        top_bar.setObjectName("TopBar")
        top_bar.setFixedHeight(56)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(16, 0, 16, 0)
        top_layout.setSpacing(4)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        nav_items = [
            ("shop", "微信小店"),
            ("knowledge", "知识库管理"),
            ("model", "模型配置"),
            ("images", "图片与视频管理"),
            ("agent", "Agent策略/状态"),
        ]
        self.nav_buttons = {}
        for index, (key, label) in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setObjectName("NavTab")
            if index == 0:
                btn.setChecked(True)
            self.nav_group.addButton(btn, index)
            self.nav_buttons[key] = btn
            top_layout.addWidget(btn)

        top_layout.addStretch()

        self.model_badge = QLabel()
        self.model_badge.setObjectName("ModelBadge")
        top_layout.addWidget(self.model_badge)
        content_layout.addWidget(top_bar)

        self.stack = QStackedWidget()

        self.browser_tab = BrowserTab()
        self.stack.addWidget(self.browser_tab)

        self.knowledge_tab = KnowledgeTab(self.knowledge_repository)
        self.stack.addWidget(self.knowledge_tab)

        self.model_config_tab = ModelConfigTab(self.config_manager)
        self.stack.addWidget(self.model_config_tab)

        self.image_management_tab = ImageManagementTab()
        self.stack.addWidget(self.image_management_tab)

        self.agent_tab = AgentStatusTab()
        self.stack.addWidget(self.agent_tab)

        content_layout.addWidget(self.stack, 1)
        main_layout.addWidget(content, 1)

        self.browser_service = BrowserService(self.browser_tab.get_web_view())
        self.message_processor = MessageProcessor(
            browser_service=self.browser_service,
            session_manager=self.session_manager,
            agent=self.agent,
        )

        self._update_model_badge()
        self._refresh_agent_tab_status()

    def _connect_signals(self):
        self.left_panel.start_clicked.connect(self._on_start)
        self.left_panel.stop_clicked.connect(self._on_stop)
        self.left_panel.refresh_clicked.connect(self._on_refresh)
        self.left_panel.grab_clicked.connect(self._on_grab_test)

        self.nav_group.buttonClicked.connect(lambda btn: self.stack.setCurrentIndex(self.nav_group.id(btn)))

        self.browser_service.page_loaded.connect(self._on_page_loaded)

        self.message_processor.status_changed.connect(self._on_status_changed)
        self.message_processor.log_message.connect(self._on_log_message)
        self.message_processor.reply_sent.connect(self._on_reply_sent)
        self.message_processor.error_occurred.connect(self._on_error)
        self.message_processor.decision_ready.connect(self.agent_tab.append_decision)

        self.model_config_tab.config_saved.connect(self._on_config_saved)
        self.model_config_tab.log_message.connect(self._on_log_message)
        self.model_config_tab.current_model_changed.connect(self._on_model_changed)

        self.image_management_tab.log_message.connect(self._on_log_message)
        self.image_management_tab.categories_updated.connect(lambda _cats: self.message_processor.reload_media_config())
        self.image_management_tab.categories_updated.connect(lambda _cats: self._refresh_agent_tab_status())

        self.agent_tab.reload_prompt_clicked.connect(self._on_reload_agent_prompt)
        self.agent_tab.reload_media_clicked.connect(self._on_reload_agent_media)
        self.agent_tab.options_changed.connect(self._on_agent_options_changed)

    def _load_wechat_store(self):
        self.browser_tab.load_url(WECHAT_STORE_URL)
        self.left_panel.append_log("🌐 正在加载微信小店...")

    def _on_start(self):
        if not self.browser_service.is_ready():
            self.left_panel.append_log("⚠️ 页面未就绪，请等待加载完成")
            return
        self.message_processor.start()

    def _on_stop(self):
        self.message_processor.stop()

    def _on_refresh(self):
        self.browser_tab.reload()
        self.left_panel.append_log("🔄 刷新页面...")

    def _on_grab_test(self):
        self.left_panel.append_log("开始抓取聊天记录...")
        self.message_processor.grab_and_display_chat_history(auto_reply=False)

    def _on_model_changed(self, model_name: str):
        self.config_manager.set_current_model(model_name)
        self.config_manager.save()
        self.left_panel.append_log(f"🤖 切换到模型: {model_name}")
        self._update_model_badge()
        self.model_config_tab.set_current_model(model_name)

    def _on_page_loaded(self, success: bool):
        if success:
            self.left_panel.append_log("✅ 页面加载完成")
            self.left_panel.update_status("ready")
        else:
            self.left_panel.append_log("❌ 页面加载失败")
            self.left_panel.update_status("error")

    def _on_status_changed(self, status: str):
        self.left_panel.update_status(status)

    def _on_log_message(self, message: str):
        self.left_panel.append_log(message)
        stats = self.session_manager.get_stats()
        self.left_panel.update_session_count(stats.get("total_sessions", 0))

    def _on_reply_sent(self, session_id: str, reply_text: str):
        self._refresh_agent_tab_status()

    def _on_error(self, error: str):
        self.left_panel.append_log(f"❌ 错误: {error}")

    def _on_config_saved(self):
        self._update_model_badge()
        self.model_config_tab.set_current_model(self.config_manager.get_current_model())

    def _on_reload_agent_prompt(self):
        self.message_processor.reload_prompt_docs()
        self._refresh_agent_tab_status()

    def _on_reload_agent_media(self):
        self.message_processor.reload_media_config()
        self._refresh_agent_tab_status()

    def _on_agent_options_changed(self, use_kb: bool, threshold: float):
        self.agent.set_options(use_knowledge_first=use_kb, knowledge_threshold=threshold)
        self.left_panel.append_log(f"⚙️ Agent参数已更新: use_kb={use_kb}, threshold={threshold:.2f}")
        self._refresh_agent_tab_status()

    def _update_model_badge(self):
        self.model_badge.setText(self.config_manager.get_current_model())

    def _refresh_agent_tab_status(self):
        self.agent_tab.update_status(self.agent.get_status())

    def closeEvent(self, event):
        if self.message_processor and self.message_processor.is_running():
            self.message_processor.stop()

        self.llm_service.cleanup()
        self.memory_store.save()
        self.config_manager.save()
        event.accept()
