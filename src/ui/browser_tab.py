"""
浏览器标签页
包含QWebEngineView浏览器控件
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QProgressBar
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtCore import QUrl, Qt
from PySide6.QtCore import Signal


class BrowserTab(QWidget):
    """浏览器标签页"""

    url_changed = Signal(str)
    load_progress = Signal(int)
    load_finished = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 导航栏
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(8)

        # URL输入框
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("输入网址...")
        self.url_input.returnPressed.connect(self._on_navigate)
        nav_layout.addWidget(self.url_input, 1)

        # 导航按钮
        self.back_btn = QPushButton("◀")
        self.back_btn.setFixedWidth(40)
        self.back_btn.clicked.connect(self._on_back)
        nav_layout.addWidget(self.back_btn)

        self.forward_btn = QPushButton("▶")
        self.forward_btn.setFixedWidth(40)
        self.forward_btn.clicked.connect(self._on_forward)
        nav_layout.addWidget(self.forward_btn)

        self.refresh_btn = QPushButton("🔄")
        self.refresh_btn.setFixedWidth(50)
        self.refresh_btn.clicked.connect(self._on_refresh)
        nav_layout.addWidget(self.refresh_btn)

        self.go_btn = QPushButton("前往")
        self.go_btn.setFixedWidth(60)
        self.go_btn.clicked.connect(self._on_navigate)
        nav_layout.addWidget(self.go_btn)

        layout.addLayout(nav_layout)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(3)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.progress_bar)

        # 浏览器视图
        self.web_view = QWebEngineView()

        # 配置浏览器设置
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)

        layout.addWidget(self.web_view, 1)

        # 连接信号
        self.web_view.loadProgress.connect(self._on_load_progress)
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.web_view.urlChanged.connect(self._on_url_changed)

    def _on_navigate(self):
        """导航到指定URL"""
        url = self.url_input.text().strip()
        if url:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            self.load_url(url)

    def _on_back(self):
        """后退"""
        self.web_view.back()

    def _on_forward(self):
        """前进"""
        self.web_view.forward()

    def _on_refresh(self):
        """刷新"""
        self.web_view.reload()

    def _on_load_progress(self, progress: int):
        """加载进度"""
        self.progress_bar.setValue(progress)
        self.load_progress.emit(progress)

    def _on_load_finished(self, success: bool):
        """加载完成"""
        self.progress_bar.setValue(100 if success else 0)
        self.load_finished.emit(success)

    def _on_url_changed(self, url: QUrl):
        """URL变更"""
        url_str = url.toString()
        self.url_input.setText(url_str)
        self.url_changed.emit(url_str)

    def load_url(self, url: str):
        """加载指定URL"""
        self.web_view.setUrl(QUrl(url))

    def get_web_view(self) -> QWebEngineView:
        """获取浏览器视图"""
        return self.web_view

    def get_current_url(self) -> str:
        """获取当前URL"""
        return self.web_view.url().toString()

    def run_javascript(self, script: str, callback=None):
        """执行JavaScript"""
        self.web_view.page().runJavaScript(script, callback)

    def go_back(self):
        """后退"""
        self.web_view.back()

    def go_forward(self):
        """前进"""
        self.web_view.forward()

    def reload(self):
        """刷新页面"""
        self.web_view.reload()

    def stop(self):
        """停止加载"""
        self.web_view.stop()
