"""
左侧面板
包含控制按钮、状态显示和日志区域
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QComboBox, QWidget
)
from PySide6.QtCore import Qt, Signal

from ..utils.constants import MAIN_STYLE_SHEET


class LeftPanel(QFrame):
    """左侧面板"""

    # 信号
    start_clicked = Signal()
    stop_clicked = Signal()
    refresh_clicked = Signal()
    grab_clicked = Signal()
    model_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LeftPanel")
        self.setFixedWidth(360)
        self._setup_ui()

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题卡片
        title_card = self._create_card()
        title_layout = QVBoxLayout(title_card)
        title_layout.setSpacing(4)

        title = QLabel("AI 客服控制台")
        title.setObjectName("Title")
        title_layout.addWidget(title)

        subtitle = QLabel("微信小店智能客服系统")
        subtitle.setObjectName("SubTitle")
        title_layout.addWidget(subtitle)

        layout.addWidget(title_card)

        # 模型选择卡片
        model_card = self._create_card()
        model_layout = QVBoxLayout(model_card)

        model_label = QLabel("选择AI模型")
        model_label.setObjectName("SectionTitle")
        model_layout.addWidget(model_label)

        self.model_combo = QComboBox()
        self.model_combo.addItems([
            "ChatGPT", "Gemini", "阿里千问", "DeepSeek", "豆包", "kimi"
        ])
        self.model_combo.currentTextChanged.connect(self.model_changed.emit)
        model_layout.addWidget(self.model_combo)

        layout.addWidget(model_card)

        # 操作按钮卡片
        buttons_card = self._create_card()
        buttons_layout = QVBoxLayout(buttons_card)
        buttons_layout.setSpacing(12)

        btn_label = QLabel("操作控制")
        btn_label.setObjectName("SectionTitle")
        buttons_layout.addWidget(btn_label)

        # 启动/停止按钮
        btn_row1 = QHBoxLayout()

        self.start_btn = QPushButton("▶ 启动 AI")
        self.start_btn.setObjectName("Primary")
        self.start_btn.clicked.connect(self.start_clicked.emit)
        btn_row1.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setObjectName("Danger")
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        self.stop_btn.setEnabled(False)
        btn_row1.addWidget(self.stop_btn)

        buttons_layout.addLayout(btn_row1)

        # 刷新和抓取按钮
        btn_row2 = QHBoxLayout()

        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setObjectName("Secondary")
        self.refresh_btn.clicked.connect(self.refresh_clicked.emit)
        btn_row2.addWidget(self.refresh_btn)

        self.grab_btn = QPushButton("📥 测试抓取")
        self.grab_btn.setObjectName("Secondary")
        self.grab_btn.clicked.connect(self.grab_clicked.emit)
        btn_row2.addWidget(self.grab_btn)

        buttons_layout.addLayout(btn_row2)

        layout.addWidget(buttons_card)

        # 状态卡片
        status_card = self._create_card()
        status_layout = QVBoxLayout(status_card)

        status_label = QLabel("系统状态")
        status_label.setObjectName("SectionTitle")
        status_layout.addWidget(status_label)

        self.status_text = QLabel("⏸️ 已停止")
        self.status_text.setObjectName("Status")
        status_layout.addWidget(self.status_text)

        self.session_count = QLabel("会话数: 0")
        self.session_count.setObjectName("Status")
        status_layout.addWidget(self.session_count)

        layout.addWidget(status_card)

        # 日志区域
        log_label = QLabel("运行日志")
        log_label.setObjectName("SectionTitle")
        log_label.setStyleSheet("color: rgba(248,250,252,0.88);")
        layout.addWidget(log_label)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("LogText")
        self.log_view.setReadOnly(True)
        # PySide6 中通过 document 设置最大块数
        from PySide6.QtGui import QTextDocument
        doc = QTextDocument(self.log_view)
        doc.setMaximumBlockCount(500)
        self.log_view.setDocument(doc)
        layout.addWidget(self.log_view, 1)

        layout.addStretch(0)

    def _create_card(self) -> QFrame:
        """创建一个卡片容器"""
        card = QFrame()
        card.setObjectName("Card")
        return card

    def update_status(self, status: str, message: str = None):
        """更新状态显示"""
        if status == "running":
            self.status_text.setText("▶️ 运行中")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
        elif status == "stopped":
            self.status_text.setText("⏸️ 已停止")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
        elif status == "ready":
            self.status_text.setText("✅ 就绪")
        elif status == "error":
            self.status_text.setText("❌ 错误")
        elif message:
            self.status_text.setText(message)

    def update_session_count(self, count: int):
        """更新会话数量"""
        self.session_count.setText(f"会话数: {count}")

    def append_log(self, message: str):
        """添加日志"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{timestamp}] {message}")

    def clear_log(self):
        """清空日志"""
        self.log_view.clear()

    def set_model(self, model_name: str):
        """设置当前模型"""
        index = self.model_combo.findText(model_name)
        if index >= 0:
            self.model_combo.setCurrentIndex(index)

    def get_current_model(self) -> str:
        """获取当前选中的模型"""
        return self.model_combo.currentText()
