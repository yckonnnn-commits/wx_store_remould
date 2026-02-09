"""
左侧面板
包含控制按钮、状态显示和日志区域
"""

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QWidget, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QTimer

from ..utils.constants import MAIN_STYLE_SHEET


class LeftPanel(QFrame):
    """左侧面板"""

    # 信号
    start_clicked = Signal()
    stop_clicked = Signal()
    refresh_clicked = Signal()
    grab_clicked = Signal()
    
    # 注意: model_changed 信号已移除，模型切换功能移动到了 ModelConfigTab

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LeftPanel")
        self.setFixedWidth(320)
        self._spin_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏", "⠋", "⠙"]
        self._spin_index = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.setInterval(90)
        self._spin_timer.timeout.connect(self._update_spin)
        self._setup_ui()

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # --- 1. 顶部 Header ---
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)

        logo_box = QFrame()
        logo_box.setObjectName("LogoBox")
        logo_box.setFixedSize(36, 36)
        logo_layout = QVBoxLayout(logo_box)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setAlignment(Qt.AlignCenter)
        
        # 使用图片图标替代文字
        from PySide6.QtGui import QPixmap
        from pathlib import Path
        logo_icon = QLabel()
        logo_path = Path(__file__).parent / "assets" / "logo.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            # 缩放到合适大小，保持宽高比
            scaled_pixmap = pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_icon.setPixmap(scaled_pixmap)
        else:
            # 如果图片不存在，回退到文字
            logo_icon.setText("Wx")
            logo_icon.setObjectName("LogoIcon")
        
        logo_layout.addWidget(logo_icon)
        header_layout.addWidget(logo_box)

        title_wrap = QWidget()
        title_layout = QVBoxLayout(title_wrap)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)
        
        title = QLabel("AI 控制台")
        title.setObjectName("SideTitle")
        title_layout.addWidget(title)
        
        subtitle = QLabel("智能客服助手")
        subtitle.setObjectName("SideSubtitle")
        title_layout.addWidget(subtitle)
        
        header_layout.addWidget(title_wrap)
        layout.addWidget(header)

        # --- 2. 快速操作区域 ---
        actions_widget = QWidget()
        actions_layout = QVBoxLayout(actions_widget)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(12)

        section_label = QLabel("快速操作")
        section_label.setObjectName("SectionLabel")
        actions_layout.addWidget(section_label)

        # Buttons Grid
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.start_btn = QPushButton("▶  启动 AI")
        self.start_btn.setObjectName("SidebarPrimary")
        self.start_btn.setCursor(Qt.PointingHandCursor)
        self.start_btn.setMinimumHeight(48)
        self.start_btn.clicked.connect(self.start_clicked.emit)
        grid.addWidget(self.start_btn, 0, 0, 1, 2) # Full width

        self.stop_btn = QPushButton("■  停止")
        self.stop_btn.setObjectName("SidebarDanger")
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.setMinimumHeight(44)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        grid.addWidget(self.stop_btn, 1, 0)

        self.refresh_btn = QPushButton("↻  刷新状态")
        self.refresh_btn.setObjectName("SidebarSecondary")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.setMinimumHeight(44)
        self.refresh_btn.clicked.connect(self.refresh_clicked.emit)
        grid.addWidget(self.refresh_btn, 1, 1)

        self.grab_btn = QPushButton("◎  测试抓取")
        self.grab_btn.setObjectName("SidebarSecondary")
        self.grab_btn.setCursor(Qt.PointingHandCursor)
        self.grab_btn.setMinimumHeight(44)
        self.grab_btn.clicked.connect(self.grab_clicked.emit)
        grid.addWidget(self.grab_btn, 2, 0, 1, 2) # Full width

        actions_layout.addLayout(grid)
        layout.addWidget(actions_widget)

        # --- 3. 系统状态卡片 ---
        status_card = QFrame()
        status_card.setObjectName("StatusCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(16, 16, 16, 16)
        status_layout.setSpacing(12)

        # Status Header
        s_header = QHBoxLayout()
        s_title = QLabel("系统状态")
        s_title.setObjectName("StatusTitle")
        s_header.addWidget(s_title)
        s_header.addStretch()
        self.status_badge = QLabel("● 就绪")
        self.status_badge.setObjectName("StatusBadge")
        self._apply_status_style("ready")
        s_header.addWidget(self.status_badge)
        status_layout.addLayout(s_header)

        # Session Count
        count_box = QHBoxLayout()
        count_left = QVBoxLayout()
        self.session_number = QLabel("0")
        self.session_number.setObjectName("SessionNumber")
        count_left.addWidget(self.session_number)
        
        session_lbl = QLabel("今日会话")
        session_lbl.setObjectName("SessionLabel")
        count_left.addWidget(session_lbl)
        count_box.addLayout(count_left)
        
        count_box.addStretch()
        
        # Sparklines (Static visualization)
        spark_box = self._create_spark_bars()
        count_box.addWidget(spark_box)
        
        status_layout.addLayout(count_box)
        layout.addWidget(status_card)

        layout.addStretch(1)

        # --- 4. 运行日志 ---
        log_container = QWidget()
        log_layout = QVBoxLayout(log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(8)

        log_header = QHBoxLayout()
        log_title = QLabel("运行日志")
        log_title.setObjectName("LogTitle")
        log_header.addWidget(log_title)
        log_header.addStretch()
        
        log_btn = QPushButton("🔍 查看全部 >")
        log_btn.setObjectName("LogLink")
        log_btn.setCursor(Qt.PointingHandCursor)
        log_header.addWidget(log_btn)
        log_layout.addLayout(log_header)

        self.log_view = QTextEdit()
        self.log_view.setObjectName("LogText")
        self.log_view.setReadOnly(True)
        self.log_view.setFixedHeight(250) # Increased height as requested
        self.log_view.setPlaceholderText("系统准备就绪...")
        
        # Limit lines
        from PySide6.QtGui import QTextDocument
        doc = QTextDocument(self.log_view)
        doc.setMaximumBlockCount(1000)
        self.log_view.setDocument(doc)
        
        log_layout.addWidget(self.log_view)
        layout.addWidget(log_container)

    def _create_spark_bars(self) -> QWidget:
        """创建装饰用的迷你柱状图"""
        container = QFrame()
        container.setObjectName("MiniChart")
        container.setFixedSize(140, 64)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignBottom)

        heights = [10, 18, 12, 22, 16, 24, 14]
        for h in heights:
            bar = QFrame()
            bar.setObjectName("MiniChartBar")
            bar.setFixedSize(8, h)
            layout.addWidget(bar, 0, Qt.AlignBottom)

        return container

    def _apply_status_style(self, status: str):
        """应用状态样式"""
        color_map = {
            "running": "#22c55e",
            "ready": "#22c55e",
            "stopped": "#94a3b8",
            "error": "#ef4444"
        }
        color = color_map.get(status, "#94a3b8")
        self.status_badge.setStyleSheet(f"color: {color};")
        if status == "running":
            self.status_badge.setText("● 运行中")
        elif status == "stopped":
            self.status_badge.setText("● 已停止")
        elif status == "ready":
            self.status_badge.setText("● 就绪")
        elif status == "error":
            self.status_badge.setText("● 异常")

    def _update_spin(self):
        """更新运行中按钮图标"""
        self._spin_index = (self._spin_index + 1) % len(self._spin_frames)
        self.start_btn.setText(f"🚀 {self._spin_frames[self._spin_index]}  正在运行")

    def update_status(self, status: str, message: str = None):
        """更新状态"""
        self._apply_status_style(status)
        
        if status == "running":
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.start_btn.setProperty("running", "true")
            self.start_btn.style().unpolish(self.start_btn)
            self.start_btn.style().polish(self.start_btn)
            self._spin_index = 0
            self.start_btn.setText(f"🚀 {self._spin_frames[self._spin_index]}  正在运行")
            if not self._spin_timer.isActive():
                self._spin_timer.start()
        elif status == "stopped":
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.start_btn.setProperty("running", "false")
            self.start_btn.style().unpolish(self.start_btn)
            self.start_btn.style().polish(self.start_btn)
            if self._spin_timer.isActive():
                self._spin_timer.stop()
            self.start_btn.setText("▶  启动 AI")
        
        if message:
            self.status_badge.setText(message)

    def update_session_count(self, count: int):
        """更新会话数"""
        self.session_number.setText(str(count))

    def append_log(self, message: str):
        """添加日志"""
        import html
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        raw = f"[{timestamp}] {message}"
        safe = html.escape(raw)

        # 颜色分级：成功/完成为绿色，其他为蓝色
        is_success = any(k in message for k in ["✅", "完成", "成功", "就绪"])
        color = "#22c55e" if is_success else "#60a5fa"
        self.log_view.append(f'<span style="color:{color};">{safe}</span>')
        # Build-in auto scroll usually works, but can force it:
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def clear_log(self):
        self.log_view.clear()
