"""
浏览器标签页
包含QWebEngineView浏览器控件
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QProgressBar, QFrame, QLabel
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
from PySide6.QtCore import QUrl, Qt, Signal


class CustomWebEnginePage(QWebEnginePage):
    """支持预设文件上传的 WebEnginePage"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.next_file_selection = []

    def chooseFiles(self, mode, old_files, accepted_mime_types):
        if self.next_file_selection:
            files = self.next_file_selection
            self.next_file_selection = []
            return files
        return super().chooseFiles(mode, old_files, accepted_mime_types)


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
        layout.setContentsMargins(0, 0, 0, 0) # No margin for full browser feel
        layout.setSpacing(0)
        
        # Container - full width browser view
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Browser Chrome (Header)
        nav_bar = QFrame()
        nav_bar.setObjectName("BrowserBar")
        nav_bar.setFixedHeight(50)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(16, 0, 16, 0)
        nav_layout.setSpacing(12)

        # Traffic Lights
        dot_wrap = QWidget()
        dot_layout = QHBoxLayout(dot_wrap)
        dot_layout.setContentsMargins(0, 0, 0, 0)
        dot_layout.setSpacing(8)
        for color in ("#f87171", "#facc15", "#4ade80"):
            dot = QFrame()
            dot.setFixedSize(10, 10)
            dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
            dot_layout.addWidget(dot)
        nav_layout.addWidget(dot_wrap)
        
        # URL Display (Read-onlyish style)
        url_box = QFrame()
        url_box.setStyleSheet("background: #f1f5f9; border-radius: 8px; padding: 4px 12px;")
        url_layout = QHBoxLayout(url_box)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.setSpacing(8)
        
        lock_icon = QLabel("🔒")
        lock_icon.setStyleSheet("color: #64748b; font-size: 10px;")
        url_layout.addWidget(lock_icon)
        
        self.url_input = QLineEdit()
        self.url_input.setObjectName("AddressInput")
        self.url_input.setPlaceholderText("https://store.weixin.qq.com/shop/kf")
        self.url_input.setStyleSheet("background: transparent; border: none; padding: 0;")
        self.url_input.returnPressed.connect(self._on_navigate)
        url_layout.addWidget(self.url_input, 1)
        
        nav_layout.addWidget(url_box, 1)

        # Actions
        self.back_btn = QPushButton("◀")
        self.back_btn.setObjectName("IconButton")
        self.back_btn.setFixedSize(28, 28)
        self.back_btn.clicked.connect(self._on_back)
        nav_layout.addWidget(self.back_btn)

        self.refresh_btn = QPushButton("↻")
        self.refresh_btn.setObjectName("IconButton")
        self.refresh_btn.setFixedSize(28, 28)
        self.refresh_btn.clicked.connect(self._on_refresh)
        nav_layout.addWidget(self.refresh_btn)

        container_layout.addWidget(nav_bar)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximumHeight(2)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("QProgressBar { background: transparent; border: none; } QProgressBar::chunk { background: #3b82f6; }")
        container_layout.addWidget(self.progress_bar)

        # Web View Frame
        view_card = QFrame()
        view_card.setObjectName("BrowserViewCard")
        # Remove top border radius/border since header is attached
        view_card.setStyleSheet(""" 
            QFrame#BrowserViewCard {
                border-top-left-radius: 0;
                border-top-right-radius: 0;
                border-top: none;
            }
        """)
        view_layout = QVBoxLayout(view_card)
        view_layout.setContentsMargins(0, 0, 0, 0)
        
        self.web_view = QWebEngineView()
        self.web_view.setPage(CustomWebEnginePage(self.web_view))
        
        settings = self.web_view.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)

        view_layout.addWidget(self.web_view)
        
        container_layout.addWidget(view_card, 1)
        layout.addWidget(container)

        # Connect signals
        self.web_view.loadProgress.connect(self._on_load_progress)
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.web_view.urlChanged.connect(self._on_url_changed)

    def _on_navigate(self):
        url = self.url_input.text().strip()
        if url:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            self.load_url(url)

    def _on_back(self):
        self.web_view.back()

    def _on_refresh(self):
        self.web_view.reload()

    def _on_load_progress(self, progress: int):
        self.progress_bar.setValue(progress)
        self.load_progress.emit(progress)

    def _on_load_finished(self, success: bool):
        self.progress_bar.setValue(100 if success else 0)
        if success:
            # Hide progress bar after delay? For now just keep it full or 0
            self.progress_bar.setValue(0) 
        self.load_finished.emit(success)

    def _on_url_changed(self, url: QUrl):
        url_str = url.toString()
        self.url_input.setText(url_str)
        self.url_changed.emit(url_str)

    def load_url(self, url: str):
        self.web_view.setUrl(QUrl(url))

    def get_web_view(self) -> QWebEngineView:
        return self.web_view

    def get_current_url(self) -> str:
        return self.web_view.url().toString()

    def run_javascript(self, script: str, callback=None):
        self.web_view.page().runJavaScript(script, callback)

    def reload(self):
        self.web_view.reload()

    def stop(self):
        self.web_view.stop()
