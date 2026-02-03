"""
主窗口
整合所有UI组件的主界面
"""

from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout, QTabWidget
)
from PySide6.QtCore import Qt, Signal

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

        # 右侧标签页
        self.tab_widget = QTabWidget()

        # 网页标签
        self.browser_tab = BrowserTab()
        self.tab_widget.addTab(self.browser_tab, "🌐 微信小店")

        # 知识库标签
        self.knowledge_tab = KnowledgeTab(self.knowledge_repository)
        self.tab_widget.addTab(self.knowledge_tab, "📚 知识库")

        # 模型配置标签
        self.model_config_tab = ModelConfigTab(self.config_manager)
        self.tab_widget.addTab(self.model_config_tab, "⚙️ 模型配置")

        main_layout.addWidget(self.tab_widget, 1)

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
        current_model = self.config_manager.get_current_model()
        self.left_panel.set_model(current_model)

    def _connect_signals(self):
        """连接信号"""
        # 左侧面板信号
        self.left_panel.start_clicked.connect(self._on_start)
        self.left_panel.stop_clicked.connect(self._on_stop)
        self.left_panel.refresh_clicked.connect(self._on_refresh)
        self.left_panel.grab_clicked.connect(self._on_grab_test)
        self.left_panel.model_changed.connect(self._on_model_changed)

        # 浏览器信号
        self.browser_service.page_loaded.connect(self._on_page_loaded)

        # 消息处理器信号
        self.message_processor.status_changed.connect(self._on_status_changed)
        self.message_processor.log_message.connect(self._on_log_message)
        self.message_processor.reply_sent.connect(self._on_reply_sent)
        self.message_processor.error_occurred.connect(self._on_error)

        # 模型配置保存
        self.model_config_tab.config_saved.connect(self._on_config_saved)

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
        """测试抓取 - 调用格式化显示方法"""
        self.left_panel.append_log("开始抓取聊天记录...")
        self.message_processor.grab_and_display_chat_history()

    def _on_model_changed(self, model_name: str):
        """模型变更"""
        self.config_manager.set_current_model(model_name)
        self.config_manager.save()
        self.left_panel.append_log(f"🤖 切换到模型: {model_name}")

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
        current_model = self.config_manager.get_current_model()
        self.left_panel.set_model(current_model)

    def closeEvent(self, event):
        """关闭事件"""
        # 停止服务
        if self.message_processor and self.message_processor.is_running():
            self.message_processor.stop()

        # 保存配置
        self.config_manager.save()

        event.accept()
