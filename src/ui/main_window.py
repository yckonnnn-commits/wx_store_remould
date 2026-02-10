"""
主窗口
整合所有UI组件的主界面
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QFrame, QPushButton, QLabel, QButtonGroup
)

from ..utils.constants import MAIN_STYLE_SHEET, WECHAT_STORE_URL
from ..data.config_manager import ConfigManager
from ..data.knowledge_repository import KnowledgeRepository
from ..services.browser_service import BrowserService
from ..services.knowledge_service import KnowledgeService
from ..services.llm_service import LLMService
from ..core.session_manager import SessionManager
from ..core.reply_coordinator import ReplyCoordinator
from ..core.message_processor import MessageProcessor

from .left_panel import LeftPanel
from .browser_tab import BrowserTab
from .knowledge_tab import KnowledgeTab
from .model_config_tab import ModelConfigTab
from .image_management_tab import ImageManagementTab
from .keyword_trigger_tab import KeywordTriggerTab


class MainWindow(QWidget):
    """主窗口"""

    def __init__(self, config_manager: ConfigManager,
                 knowledge_repository: KnowledgeRepository,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 智能客服系统")
        self.resize(1600, 900)

        # 保存管理器
        self.config_manager = config_manager
        self.knowledge_repository = knowledge_repository

        # 初始化服务
        self._init_services()

        # 设置UI
        self._setup_ui()
        self._connect_signals()

        # 加载微信小店
        self._load_wechat_store()

    def _init_services(self):
        """初始化服务"""
        # 浏览器服务 (在UI创建后初始化)
        self.browser_service = None

        # 其他服务
        self.knowledge_service = KnowledgeService(self.knowledge_repository)
        self.llm_service = LLMService(self.config_manager)
        self.session_manager = SessionManager()
        self.reply_coordinator = ReplyCoordinator(
            self.knowledge_service,
            self.llm_service,
            self.session_manager
        )
        self.message_processor = None

    def _setup_ui(self):
        """设置UI"""
        self.setStyleSheet(MAIN_STYLE_SHEET)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧面板
        self.left_panel = LeftPanel(self)
        main_layout.addWidget(self.left_panel)

        # 右侧内容区
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # 顶部导航栏
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
            ("keywords", "关键词触发图片发送")
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

        # 页面容器
        self.stack = QStackedWidget()

        self.browser_tab = BrowserTab()
        self.stack.addWidget(self.browser_tab)

        self.knowledge_tab = KnowledgeTab(self.knowledge_repository)
        self.stack.addWidget(self.knowledge_tab)

        self.model_config_tab = ModelConfigTab(self.config_manager)
        self.stack.addWidget(self.model_config_tab)

        self.image_management_tab = ImageManagementTab()
        self.stack.addWidget(self.image_management_tab)

        self.keyword_trigger_tab = KeywordTriggerTab()
        self.stack.addWidget(self.keyword_trigger_tab)

        content_layout.addWidget(self.stack, 1)

        main_layout.addWidget(content, 1)

        # 初始化浏览器服务
        self.browser_service = BrowserService(self.browser_tab.get_web_view())
        self.message_processor = MessageProcessor(
            self.browser_service,
            self.knowledge_service,
            self.llm_service,
            self.session_manager,
            self.reply_coordinator
        )

        # 设置当前模型
        # 设置当前模型
        current_model = self.config_manager.get_current_model()
        self._update_model_badge()

    def _connect_signals(self):
        """连接信号"""
        # 左侧面板信号
        self.left_panel.start_clicked.connect(self._on_start)
        self.left_panel.stop_clicked.connect(self._on_stop)
        self.left_panel.refresh_clicked.connect(self._on_refresh)
        self.left_panel.grab_clicked.connect(self._on_grab_test)


        # 顶部导航
        self.nav_group.buttonClicked.connect(
            lambda btn: self.stack.setCurrentIndex(self.nav_group.id(btn))
        )

        # 浏览器信号
        self.browser_service.page_loaded.connect(self._on_page_loaded)

        # 消息处理器信号
        self.message_processor.status_changed.connect(self._on_status_changed)
        self.message_processor.log_message.connect(self._on_log_message)
        self.message_processor.reply_sent.connect(self._on_reply_sent)
        self.message_processor.error_occurred.connect(self._on_error)

        # 模型配置保存
        self.model_config_tab.config_saved.connect(self._on_config_saved)
        self.model_config_tab.log_message.connect(self._on_log_message)
        self.model_config_tab.current_model_changed.connect(self._on_model_changed)

        # 图片管理日志
        self.image_management_tab.log_message.connect(self._on_log_message)
        self.image_management_tab.categories_updated.connect(lambda _cats: self.keyword_trigger_tab._load_config())
        self.image_management_tab.categories_updated.connect(lambda _cats: self.message_processor.reload_keyword_config())

        # 关键词触发日志
        self.keyword_trigger_tab.log_message.connect(self._on_log_message)
        self.keyword_trigger_tab.config_updated.connect(self.message_processor.reload_keyword_config)

    def _load_wechat_store(self):
        """加载微信小店"""
        self.browser_tab.load_url(WECHAT_STORE_URL)
        self.left_panel.append_log("🌐 正在加载微信小店...")

    def _on_start(self):
        """启动AI客服"""
        if not self.browser_service.is_ready():
            self.left_panel.append_log("⚠️ 页面未就绪，请等待加载完成")
            return

        self.message_processor.start()

    def _on_stop(self):
        """停止AI客服"""
        self.message_processor.stop()

    def _on_refresh(self):
        """刷新页面"""
        self.browser_tab.reload()
        self.left_panel.append_log("🔄 刷新页面...")

    def _on_grab_test(self):
        """测试抓取 - 调用格式化显示方法（不自动回复）"""
        self.left_panel.append_log("开始抓取聊天记录...")
        self.message_processor.grab_and_display_chat_history(auto_reply=False)

    def _on_model_changed(self, model_name: str):
        """模型变更"""
        self.config_manager.set_current_model(model_name)
        self.config_manager.save()
        self.left_panel.append_log(f"🤖 切换到模型: {model_name}")
        self._update_model_badge()
        self.model_config_tab.set_current_model(model_name)

    def _on_page_loaded(self, success: bool):
        """页面加载完成"""
        if success:
            self.left_panel.append_log("✅ 页面加载完成")
            self.left_panel.update_status("ready")
        else:
            self.left_panel.append_log("❌ 页面加载失败")
            self.left_panel.update_status("error")

    def _on_status_changed(self, status: str):
        """状态变更"""
        self.left_panel.update_status(status)

    def _on_log_message(self, message: str):
        """日志消息"""
        self.left_panel.append_log(message)

        # 更新会话统计
        stats = self.session_manager.get_stats()
        self.left_panel.update_session_count(stats.get("total_sessions", 0))

    def _on_reply_sent(self, session_id: str, reply_text: str):
        """回复已发送"""
        # 可以在这里添加额外的处理
        pass

    def _on_error(self, error: str):
        """错误处理"""
        self.left_panel.append_log(f"❌ 错误: {error}")

    def _on_config_saved(self):
        """配置已保存"""
        # 重新加载模型配置
        # 重新加载模型配置
        current_model = self.config_manager.get_current_model()
        self._update_model_badge()
        self.model_config_tab.set_current_model(current_model)

    def _update_model_badge(self):
        """更新顶部模型徽标"""
        current_model = self.config_manager.get_current_model()
        self.model_badge.setText(current_model)

    def closeEvent(self, event):
        """关闭事件"""
        # 停止服务
        if self.message_processor and self.message_processor.is_running():
            self.message_processor.stop()

        # 保存配置
        self.config_manager.save()

        event.accept()
