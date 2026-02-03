import sys
import signal
import os
import json
import uuid
import threading
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QFrame, QTextEdit, QComboBox, QTabWidget,
    QLineEdit, QListWidget, QSplitter, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QFileDialog, QDialog,
    QDialogButtonBox, QFormLayout
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtCore import QUrl, QTimer, Qt


class AICustomerServiceApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI 智能客服系统 - 调试版")
        self.resize(1600, 900)

        self._load_local_env()

        self.kb_file_path = Path(__file__).resolve().parent / "knowledge_base.json"
        self.kb_items = []
        self._kb_search_text = ""
        self._kb_load()

        self.model_settings_file_path = Path(__file__).resolve().parent / "model_settings.json"
        self.model_settings = {}
        self._model_settings_current = None
        self._model_settings_load()

        self.ai_enabled = False
        self._last_poll_result = None
        self._poll_inflight = False
        self._page_ready = False
        self._reply_worker_inflight = False

        self.ai_timer = QTimer(self)
        self.ai_timer.setInterval(4000)
        self.ai_timer.timeout.connect(self.poll_unread_and_reply)

        self.chat_watch_timer = QTimer(self)
        self.chat_watch_timer.setInterval(1200)
        self.chat_watch_timer.timeout.connect(self._watch_active_chat)
        self._watch_inflight = False
        self._last_active_chat_user = None

        self.init_ui()

    def _load_local_env(self):
        try:
            env_path = Path(__file__).resolve().parent.parent / ".env"
            if not env_path.exists():
                return
            raw = env_path.read_text(encoding="utf-8", errors="ignore")
            for line in raw.splitlines():
                s = (line or "").strip()
                if not s:
                    continue
                if s.startswith("#"):
                    continue
                if "=" not in s:
                    continue
                k, v = s.split("=", 1)
                k = (k or "").strip()
                if not k:
                    continue
                v = (v or "").strip()
                if (len(v) >= 2) and ((v[0] == v[-1]) and v[0] in ('"', "'")):
                    v = v[1:-1]
                if os.getenv(k) is None:
                    os.environ[k] = v
        except Exception:
            return

    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.setStyleSheet("""
            QWidget { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif; }
            QFrame#LeftPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0f172a, stop:1 #111827);
                border-right: 1px solid rgba(255,255,255,0.08);
            }
            QFrame#Card {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 14px;
            }
            QLabel#Title {
                color: #f8fafc;
                font-size: 20px;
                font-weight: 700;
            }
            QLabel#SubTitle {
                color: rgba(248,250,252,0.72);
                font-size: 13px;
            }
            QLabel#SectionTitle {
                color: rgba(248,250,252,0.88);
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#Status {
                color: rgba(248,250,252,0.85);
                font-size: 13px;
            }
            QPushButton#Primary {
                background: #22c55e;
                color: #0b1220;
                border: none;
                border-radius: 12px;
                padding: 10px 12px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#Primary:hover { background: #16a34a; }
            QPushButton#Danger {
                background: #ef4444;
                color: #0b1220;
                border: none;
                border-radius: 12px;
                padding: 10px 12px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#Danger:hover { background: #dc2626; }
            QPushButton#Secondary {
                background: rgba(255,255,255,0.10);
                color: rgba(248,250,252,0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 12px;
                padding: 10px 12px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton#Secondary:hover { background: rgba(255,255,255,0.14); }
            QPushButton#Tiny {
                background: rgba(255,255,255,0.10);
                color: rgba(248,250,252,0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#Tiny:hover { background: rgba(255,255,255,0.14); }
            QComboBox {
                background: rgba(255,255,255,0.10);
                color: rgba(248,250,252,0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 10px;
                padding: 8px 10px;
                font-size: 13px;
            }
            QComboBox::drop-down { border: none; width: 26px; }
            QComboBox QAbstractItemView {
                background: #0b1220;
                color: rgba(248,250,252,0.92);
                selection-background-color: rgba(34,197,94,0.25);
                border: 1px solid rgba(255,255,255,0.12);
            }
            QTextEdit {
                background: #0b1220;
                color: #e5e7eb;
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
                font-family: 'Menlo', 'SF Mono', 'Monaco', monospace;
                font-size: 13px;
            }
            QTextEdit#LogText {
                font-size: 11px;
            }
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: rgba(17,24,39,0.95);
                color: rgba(248,250,252,0.80);
                border: 1px solid rgba(255,255,255,0.10);
                border-bottom: none;
                padding: 10px 14px;
                margin-right: 4px;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
            QTabBar::tab:selected {
                background: #0b1220;
                color: rgba(248,250,252,0.95);
                border-color: rgba(255,255,255,0.16);
            }
            QLineEdit {
                background: rgba(255,255,255,0.10);
                color: rgba(248,250,252,0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 10px;
                padding: 8px 10px;
                font-size: 13px;
            }
            QLineEdit::placeholder { color: rgba(248,250,252,0.55); }
            QListWidget {
                background: rgba(255,255,255,0.06);
                color: rgba(248,250,252,0.92);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
                padding: 6px;
                font-size: 13px;
            }
            QListWidget::item { padding: 8px 10px; border-radius: 10px; }
            QListWidget::item:selected { background: rgba(34,197,94,0.22); }

            QWidget#KnowledgeBasePage {
                background: #f8fafc;
                color: #0f172a;
            }
            QFrame#KbCard {
                background: #ffffff;
                border: 1px solid #e5e7eb;
                border-radius: 14px;
            }
            QLabel#KbTitle {
                color: #0f172a;
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#KbSubTitle {
                color: #64748b;
                font-size: 12px;
            }
            QLineEdit#KbSearch {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 12px;
                font-size: 12px;
            }
            QLineEdit#KbSearch::placeholder { color: #94a3b8; }
            QPushButton#KbPrimary {
                background: #f59e0b;
                color: #111827;
                border: none;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#KbPrimary:hover { background: #d97706; }
            QPushButton#KbSecondary {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 14px;
                font-size: 12px;
                font-weight: 700;
            }
            QPushButton#KbSecondary:hover { background: #f1f5f9; }
            QTableWidget#KbTable {
                background: #ffffff;
                gridline-color: #e5e7eb;
                border: 1px solid #e5e7eb;
                border-radius: 12px;
                font-size: 12px;
                selection-background-color: rgba(245, 158, 11, 0.18);
            }
            QHeaderView::section {
                background: #f8fafc;
                color: #334155;
                border: none;
                border-bottom: 1px solid #e5e7eb;
                padding: 10px 10px;
                font-size: 12px;
                font-weight: 700;
            }

            QWidget#ModelSettingsPage {
                background: #0b1220;
                color: rgba(248,250,252,0.92);
            }
            QFrame#MsHero {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #111827, stop:1 #0b1220);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 16px;
            }
            QLabel#MsTitle {
                color: #f8fafc;
                font-size: 18px;
                font-weight: 800;
            }
            QLabel#MsSubTitle {
                color: rgba(248,250,252,0.70);
                font-size: 12px;
            }
            QFrame#MsCard {
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 14px;
            }
            QListWidget#MsModelList {
                background: rgba(255,255,255,0.06);
                color: rgba(248,250,252,0.92);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 12px;
                padding: 6px;
                font-size: 13px;
            }
            QListWidget#MsModelList::item { padding: 10px 12px; border-radius: 10px; }
            QListWidget#MsModelList::item:selected { background: rgba(59, 130, 246, 0.22); }
            QLineEdit#MsInput {
                background: rgba(255,255,255,0.08);
                color: rgba(248,250,252,0.92);
                border: 1px solid rgba(255,255,255,0.12);
                border-radius: 10px;
                padding: 10px 12px;
                font-size: 13px;
            }
            QLineEdit#MsInput::placeholder { color: rgba(248,250,252,0.50); }
            QPushButton#MsPrimary {
                background: #3b82f6;
                color: #0b1220;
                border: none;
                border-radius: 12px;
                padding: 10px 14px;
                font-size: 13px;
                font-weight: 800;
            }
            QPushButton#MsPrimary:hover { background: #2563eb; }
            QPushButton#MsGhost {
                background: rgba(255,255,255,0.10);
                color: rgba(248,250,252,0.92);
                border: 1px solid rgba(255,255,255,0.14);
                border-radius: 12px;
                padding: 10px 14px;
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton#MsGhost:hover { background: rgba(255,255,255,0.14); }
        """)

        # ================= 左侧操作区 =================
        left_panel = QFrame()
        left_panel.setFixedWidth(360)
        left_panel.setObjectName("LeftPanel")

        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(12)
        left_layout.setContentsMargins(14, 14, 14, 14)

        header_card = QFrame()
        header_card.setObjectName("Card")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(14, 14, 14, 14)
        header_layout.setSpacing(6)

        title_label = QLabel("🤖 AI 客服控制台")
        title_label.setObjectName("Title")
        sub_label = QLabel("调试版 · 自动抓取会话 · 可扩展知识库")
        sub_label.setObjectName("SubTitle")
        header_layout.addWidget(title_label)
        header_layout.addWidget(sub_label)

        # 启动 / 关闭 AI
        self.start_btn = QPushButton("▶ 启动 AI 智能回复")
        self.start_btn.setObjectName("Primary")

        self.stop_btn = QPushButton("■ 关闭 AI 智能回复")
        self.stop_btn.setObjectName("Danger")

        # 状态显示
        self.status_label = QLabel("状态：未启动")
        self.status_label.setObjectName("Status")

        model_card = QFrame()
        model_card.setObjectName("Card")
        model_layout = QVBoxLayout(model_card)
        model_layout.setContentsMargins(14, 12, 14, 12)
        model_layout.setSpacing(8)

        model_title_row = QWidget()
        model_title_row_l = QHBoxLayout(model_title_row)
        model_title_row_l.setContentsMargins(0, 0, 0, 0)
        model_title_row_l.setSpacing(8)

        model_title = QLabel("模型配置")
        model_title.setObjectName("SectionTitle")
        self.model_more_btn = QPushButton("更多")
        self.model_more_btn.setObjectName("Tiny")
        self.model_more_btn.clicked.connect(self.open_model_settings)

        model_title_row_l.addWidget(model_title)
        model_title_row_l.addStretch(1)
        model_title_row_l.addWidget(self.model_more_btn)

        self.model_combo = QComboBox()
        self.model_combo.addItems(["ChatGPT", "Gemini", "阿里千问", "DeepSeek", "豆包", "kimi"])
        model_layout.addWidget(model_title_row)
        model_layout.addWidget(self.model_combo)

        action_card = QFrame()
        action_card.setObjectName("Card")
        action_layout = QVBoxLayout(action_card)
        action_layout.setContentsMargins(14, 12, 14, 12)
        action_layout.setSpacing(10)

        # 刷新按钮
        self.refresh_btn = QPushButton("🔄 刷新页面")
        self.refresh_btn.setObjectName("Secondary")

        self.test_grab_btn = QPushButton("📝 抓取聊天记录")
        self.test_grab_btn.setObjectName("Secondary")
        self.test_grab_btn.clicked.connect(self.test_grab_chat_data)

        self.kb_btn = QPushButton("📚 知识库")
        self.kb_btn.setObjectName("Secondary")
        self.kb_btn.clicked.connect(self.open_knowledge_base)

        action_layout.addWidget(self.start_btn)
        action_layout.addWidget(self.stop_btn)
        action_layout.addWidget(self.refresh_btn)
        action_layout.addWidget(self.test_grab_btn)
        action_layout.addWidget(self.kb_btn)

        # 日志区域
        log_label = QLabel("调试日志")
        log_label.setObjectName("SectionTitle")
        self.log_text = QTextEdit()
        self.log_text.setObjectName("LogText")
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(300)

        # 绑定事件
        self.start_btn.clicked.connect(self.start_ai)
        self.stop_btn.clicked.connect(self.stop_ai)
        self.refresh_btn.clicked.connect(self.refresh_browser)

        status_card = QFrame()
        status_card.setObjectName("Card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(14, 12, 14, 12)
        status_layout.setSpacing(8)
        status_title = QLabel("运行状态")
        status_title.setObjectName("SectionTitle")
        status_layout.addWidget(status_title)
        status_layout.addWidget(self.status_label)

        log_card = QFrame()
        log_card.setObjectName("Card")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(14, 12, 14, 12)
        log_layout.setSpacing(8)
        log_layout.addWidget(log_label)
        log_layout.addWidget(self.log_text)

        left_layout.addWidget(header_card)
        left_layout.addWidget(model_card)
        left_layout.addWidget(action_card)
        left_layout.addWidget(status_card)
        left_layout.addWidget(log_card)
        left_layout.addStretch(1)

        # ================= 右侧内嵌浏览器 =================
        self.browser = QWebEngineView()
        self.browser.settings().setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        self.browser.loadStarted.connect(self._on_load_started)
        self.browser.loadFinished.connect(self._on_load_finished)
        # 加载微信小店网页
        self.browser.load(QUrl("https://store.weixin.qq.com/shop/kf"))

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)

        web_container = QWidget()
        web_layout = QVBoxLayout(web_container)
        web_layout.setContentsMargins(0, 0, 0, 0)
        web_layout.setSpacing(0)
        web_layout.addWidget(self.browser)

        self.kb_page = self._build_knowledge_base_page()
        self.model_settings_page = self._build_model_settings_page()
        self.tabs.addTab(web_container, "网页")
        self.tabs.addTab(self.kb_page, "知识库")
        self.tabs.addTab(self.model_settings_page, "模型配置")

        # ================= 主布局 =================
        main_layout.addWidget(left_panel)
        main_layout.addWidget(self.tabs)

    def log(self, message):
        """添加日志到文本区域"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{timestamp}] {message}")
        print(f"[{timestamp}] {message}")

    def _on_load_started(self):
        self._page_ready = False

    def _on_load_finished(self, ok: bool):
        self._page_ready = bool(ok)
        self.log(f"页面加载完成 ok={ok}")
        if ok and (not self.chat_watch_timer.isActive()):
            self.chat_watch_timer.start()

    def start_ai(self):
        model = self.model_combo.currentText() if hasattr(self, 'model_combo') else ""
        if model:
            self.status_label.setText(f"状态：AI 已启动（模型：{model}）")
            self.log(f"启动 AI 智能回复，模型：{model}")
        else:
            self.status_label.setText("状态：AI 已启动")
            self.log("启动 AI 智能回复")

        self.ai_enabled = True
        if not self.ai_timer.isActive():
            self.ai_timer.start()
        self.poll_unread_and_reply()

    def stop_ai(self):
        self.status_label.setText("状态：AI 已关闭")
        self.log("已关闭 AI 智能回复")

        self.ai_enabled = False
        if self.ai_timer.isActive():
            self.ai_timer.stop()

    def closeEvent(self, event):
        try:
            if hasattr(self, 'ai_timer') and self.ai_timer.isActive():
                self.ai_timer.stop()
            if hasattr(self, 'chat_watch_timer') and self.chat_watch_timer.isActive():
                self.chat_watch_timer.stop()
        finally:
            super().closeEvent(event)

    def open_knowledge_base(self):
        if hasattr(self, 'tabs'):
            self.tabs.setCurrentIndex(1)

    def open_model_settings(self):
        if hasattr(self, 'tabs'):
            self.tabs.setCurrentIndex(2)

    def _build_knowledge_base_page(self):
        page = QWidget()
        page.setObjectName("KnowledgeBasePage")
        root = QVBoxLayout(page)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QFrame()
        header.setObjectName("KbCard")
        header_l = QVBoxLayout(header)
        header_l.setContentsMargins(16, 16, 16, 16)
        header_l.setSpacing(6)
        t = QLabel("业务知识库")
        t.setObjectName("KbTitle")
        s = QLabel("上传你的产品手册与QA，让 AI 更懂你的假发业务")
        s.setObjectName("KbSubTitle")
        header_l.addWidget(t)
        header_l.addWidget(s)

        toolbar = QFrame()
        toolbar.setObjectName("KbCard")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 12, 16, 12)
        tb.setSpacing(12)

        self.kb_search = QLineEdit()
        self.kb_search.setObjectName("KbSearch")
        self.kb_search.setPlaceholderText("搜索知识库条目名或内容关键字...")
        self.kb_search.textChanged.connect(self._kb_on_search_changed)

        self.kb_import_btn = QPushButton("导入文件")
        self.kb_import_btn.setObjectName("KbSecondary")
        self.kb_import_btn.clicked.connect(self._kb_import_from_file)

        self.kb_new_btn = QPushButton("＋ 新建知识条目")
        self.kb_new_btn.setObjectName("KbPrimary")
        self.kb_new_btn.clicked.connect(lambda: self._kb_open_editor(None))

        tb.addWidget(self.kb_search, 1)
        tb.addWidget(self.kb_import_btn)
        tb.addWidget(self.kb_new_btn)

        table_card = QFrame()
        table_card.setObjectName("KbCard")
        tc = QVBoxLayout(table_card)
        tc.setContentsMargins(0, 0, 0, 0)
        tc.setSpacing(0)

        self.kb_table = QTableWidget(0, 4)
        self.kb_table.setObjectName("KbTable")
        self.kb_table.setHorizontalHeaderLabels(["条目名", "类型", "内容", "操作"])
        self.kb_table.verticalHeader().setVisible(False)
        self.kb_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.kb_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.kb_table.setAlternatingRowColors(True)
        self.kb_table.setShowGrid(True)
        self.kb_table.horizontalHeader().setStretchLastSection(True)
        self.kb_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.kb_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.kb_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.kb_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.kb_table.setMinimumHeight(520)

        tc.addWidget(self.kb_table)

        root.addWidget(header)
        root.addWidget(toolbar)
        root.addWidget(table_card, 1)

        self._kb_refresh_table()
        return page

    def _kb_on_search_changed(self, text: str):
        self._kb_search_text = (text or "").strip()
        self._kb_refresh_table()

    def _kb_load(self):
        try:
            if self.kb_file_path.exists():
                data = json.loads(self.kb_file_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("items"), list):
                    self.kb_items = data.get("items", [])
                elif isinstance(data, list):
                    self.kb_items = data
                else:
                    self.kb_items = []
            else:
                self.kb_items = []
        except Exception as e:
            self.kb_items = []
            try:
                self.log(f"[KB] 读取知识库失败：{e}")
            except Exception:
                pass

    def _kb_save(self):
        payload = {
            "version": 1,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "items": self.kb_items,
        }
        self.kb_file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _kb_filtered_items(self):
        q = (self._kb_search_text or "").lower()
        if not q:
            return list(self.kb_items)
        out = []
        for it in self.kb_items:
            name = str(it.get("name", ""))
            content = str(it.get("content", ""))
            if q in name.lower() or q in content.lower():
                out.append(it)
        return out

    def _kb_refresh_table(self):
        if not hasattr(self, "kb_table"):
            return

        items = self._kb_filtered_items()
        self.kb_table.setRowCount(len(items))

        for row, it in enumerate(items):
            name = str(it.get("name", ""))
            typ = str(it.get("type", "TEXT"))
            content = str(it.get("content", ""))

            content_preview = content.replace("\n", " ").strip()
            if len(content_preview) > 80:
                content_preview = content_preview[:80] + "..."

            name_item = QTableWidgetItem(name)
            type_item = QTableWidgetItem(typ)
            content_item = QTableWidgetItem(content_preview)

            name_item.setToolTip(name)
            type_item.setToolTip(typ)
            content_item.setToolTip(content)

            self.kb_table.setItem(row, 0, name_item)
            self.kb_table.setItem(row, 1, type_item)
            self.kb_table.setItem(row, 2, content_item)

            op = QWidget()
            op_l = QHBoxLayout(op)
            op_l.setContentsMargins(6, 0, 6, 0)
            op_l.setSpacing(8)

            edit_btn = QPushButton("编辑")
            edit_btn.setObjectName("KbSecondary")
            delete_btn = QPushButton("删除")
            delete_btn.setObjectName("KbSecondary")

            item_id = it.get("id")
            edit_btn.clicked.connect(lambda _=False, iid=item_id: self._kb_open_editor(iid))
            delete_btn.clicked.connect(lambda _=False, iid=item_id: self._kb_delete_item(iid))

            op_l.addWidget(edit_btn)
            op_l.addWidget(delete_btn)
            op_l.addStretch(1)

            self.kb_table.setCellWidget(row, 3, op)

        self.kb_table.resizeRowsToContents()

    def _kb_find_item(self, item_id: str):
        for it in self.kb_items:
            if str(it.get("id")) == str(item_id):
                return it
        return None

    def _kb_open_editor(self, item_id):
        item = self._kb_find_item(item_id) if item_id else None

        dlg = QDialog(self)
        dlg.setWindowTitle("编辑知识条目" if item else "新建知识条目")
        dlg.setMinimumSize(720, 520)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        name_input = QLineEdit()
        name_input.setPlaceholderText("条目名")
        type_combo = QComboBox()
        type_combo.addItems(["TEXT", "FAQ", "POLICY", "PRODUCT", "OTHER"])
        content_input = QTextEdit()
        content_input.setPlaceholderText("条目内容")

        if item:
            name_input.setText(str(item.get("name", "")))
            cur_t = str(item.get("type", "TEXT"))
            idx = type_combo.findText(cur_t)
            if idx >= 0:
                type_combo.setCurrentIndex(idx)
            content_input.setPlainText(str(item.get("content", "")))

        layout.addWidget(QLabel("条目名"))
        layout.addWidget(name_input)
        layout.addWidget(QLabel("类型"))
        layout.addWidget(type_combo)
        layout.addWidget(QLabel("内容"))
        layout.addWidget(content_input, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel | QDialogButtonBox.Save)
        layout.addWidget(buttons)

        def do_save():
            name = name_input.text().strip()
            typ = type_combo.currentText().strip() or "TEXT"
            content = content_input.toPlainText().strip()

            if not name:
                QMessageBox.warning(self, "提示", "条目名不能为空")
                return
            if not content:
                QMessageBox.warning(self, "提示", "内容不能为空")
                return

            now = datetime.now().isoformat(timespec="seconds")
            if item:
                item["name"] = name
                item["type"] = typ
                item["content"] = content
                item["updated_at"] = now
            else:
                self.kb_items.insert(0, {
                    "id": uuid.uuid4().hex,
                    "name": name,
                    "type": typ,
                    "content": content,
                    "created_at": now,
                    "updated_at": now,
                })

            try:
                self._kb_save()
            except Exception as e:
                QMessageBox.critical(self, "保存失败", str(e))
                return

            self._kb_refresh_table()
            dlg.accept()

        buttons.rejected.connect(dlg.reject)
        buttons.accepted.connect(do_save)

        dlg.exec()

    def _kb_delete_item(self, item_id: str):
        if not item_id:
            return

        item = self._kb_find_item(item_id)
        if not item:
            return

        name = str(item.get("name", ""))
        ret = QMessageBox.question(self, "确认删除", f"确定删除条目：{name} ?")
        if ret != QMessageBox.Yes:
            return

        self.kb_items = [it for it in self.kb_items if str(it.get("id")) != str(item_id)]
        try:
            self._kb_save()
        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))
            return

        self._kb_refresh_table()

    def _kb_import_from_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "导入知识库 JSON", str(self.kb_file_path.parent), "JSON Files (*.json)")
        if not file_path:
            return

        try:
            raw = Path(file_path).read_text(encoding="utf-8")
            data = json.loads(raw)
        except Exception as e:
            QMessageBox.critical(self, "导入失败", f"无法读取文件：{e}")
            return

        if isinstance(data, dict) and isinstance(data.get("items"), list):
            items = data.get("items")
        elif isinstance(data, list):
            items = data
        else:
            QMessageBox.warning(self, "导入失败", "JSON 格式不正确：需要 list 或 {items: list}")
            return

        added = 0
        now = datetime.now().isoformat(timespec="seconds")
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            content = str(it.get("content", "")).strip()
            typ = str(it.get("type", "TEXT")).strip() or "TEXT"
            if not name or not content:
                continue

            exists = False
            for cur in self.kb_items:
                if str(cur.get("name", "")).strip() == name:
                    exists = True
                    break
            if exists:
                continue

            self.kb_items.append({
                "id": uuid.uuid4().hex,
                "name": name,
                "type": typ,
                "content": content,
                "created_at": it.get("created_at", now),
                "updated_at": it.get("updated_at", now),
            })
            added += 1

        try:
            self._kb_save()
        except Exception as e:
            QMessageBox.critical(self, "导入失败", str(e))
            return

        self._kb_refresh_table()
        QMessageBox.information(self, "导入完成", f"成功导入 {added} 条（同名条目已跳过）")

    def _kb_best_match(self, query: str):
        q = (query or "").strip()
        if not q:
            return None

        def bigrams(s: str):
            s = (s or "").strip()
            if len(s) < 2:
                return set()
            return {s[i:i+2] for i in range(len(s) - 1)}

        q2 = bigrams(q)
        best = None
        best_score = 0
        for it in self.kb_items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("name", "")).strip()
            content = str(it.get("content", "")).strip()
            if not name or not content:
                continue

            hay = (name + "\n" + content).strip()
            score = 0
            if name and name in q:
                score += 50
            if q in hay:
                score += 20
            if q2:
                h2 = bigrams(hay)
                score += len(q2.intersection(h2))
            if score > best_score:
                best_score = score
                best = it

        if best and best_score >= 8:
            return best
        return None

    def _build_customer_service_prompt(self, chat_user: str, user_messages: list[str]):
        msgs = [m.strip() for m in (user_messages or []) if isinstance(m, str) and m.strip()]
        last = msgs[-1] if msgs else ""

        system_prompt = (
            "你是一个资深客服，服务于中老年人高端假发行业（真发/高端定制）。\n"
            "目标：用简洁、专业、耐心的方式推进成交与转化。\n"
            "要求：\n"
            "1) 只根据客户消息回复，不要复述客服自己发过的话。\n"
            "2) 不要提及你是AI。\n"
            "3) 语气：礼貌、温和、可信，适合中老年客户阅读。\n"
            "4) 先解决问题，再引导客户提供关键信息（尺寸/脱发情况/预算/到店城市/联系方式）。\n"
            "5) 如需留电话/微信，用委婉方式询问。\n"
            "6) 不确定时先澄清提问，不要编造承诺。"
        )

        user_prompt = (
            f"客户昵称：{chat_user or '客户'}\n"
            "客户最近消息（仅客户发言）：\n" +
            "\n".join([f"- {m}" for m in msgs[-8:]]) +
            "\n\n"
            "请输出你作为客服要发出的回复内容（中文），不要加多余前缀。\n"
            "如果客户只是随口问'在吗/你好/多少钱/怎么买'，请先友好回应并给出下一步引导。\n"
            f"客户最后一句：{last}"
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _http_json(self, url: str, headers: dict, payload: dict, timeout: int = 40):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw)

    def _call_llm(self, provider_name: str, user_messages: list[str], chat_user: str):
        provider_name = (provider_name or "").strip()
        cfg = self.model_settings.get(provider_name) if isinstance(self.model_settings, dict) else None
        if not isinstance(cfg, dict):
            raise RuntimeError(f"未找到模型配置：{provider_name}")

        base_url = str(cfg.get("base_url", "")).strip()
        api_key = str(cfg.get("api_key", "")).strip()
        model = str(cfg.get("model", "")).strip()
        if (not api_key) and provider_name == "阿里千问":
            api_key = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
        if not base_url:
            raise RuntimeError(f"模型 {provider_name} 未配置 Base URL")
        if not api_key:
            raise RuntimeError(f"模型 {provider_name} 未配置 API Key")
        if not model:
            raise RuntimeError(f"模型 {provider_name} 未配置 Model")

        prompt_messages = self._build_customer_service_prompt(chat_user, user_messages)

        if "generativelanguage.googleapis.com" in base_url:
            url = base_url.rstrip("/") + f"/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [
                    {"role": "user", "parts": [{"text": prompt_messages[0]["content"] + "\n\n" + prompt_messages[1]["content"]}]}
                ]
            }
            data = self._http_json(url, headers={}, payload=payload, timeout=40)
            cand = (data.get("candidates") or [{}])[0]
            parts = (((cand.get("content") or {}).get("parts") or [{}]))
            text = "".join([str(p.get("text", "")) for p in parts]).strip()
            if not text:
                raise RuntimeError("Gemini 返回为空")
            return text

        if "dashscope.aliyuncs.com" in base_url:
            url = base_url.rstrip("/") + "/api/v1/services/aigc/text-generation/generation"
            payload = {
                "model": model,
                "input": {"messages": prompt_messages},
                "parameters": {"result_format": "message"}
            }
            data = self._http_json(url, headers={"Authorization": f"Bearer {api_key}"}, payload=payload, timeout=40)
            out = ((data.get("output") or {}).get("choices") or [{}])[0]
            msg = out.get("message") or {}
            text = str(msg.get("content", "")).strip()
            if not text:
                raise RuntimeError("阿里千问返回为空")
            return text

        url = base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": model,
            "messages": prompt_messages,
            "temperature": 0.6,
        }
        data = self._http_json(url, headers={"Authorization": f"Bearer {api_key}"}, payload=payload, timeout=40)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("模型返回 choices 为空")
        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        if not content:
            raise RuntimeError("模型返回 content 为空")
        return content

    def _send_reply_js(self, reply_text: str, msg_key: str, session_lock_key: str):
        rt = (reply_text or "").replace("\\", "\\\\").replace('"', '\\"')
        mk = (msg_key or "").replace("\\", "\\\\").replace('"', '\\"')
        sk = (session_lock_key or "").replace("\\", "\\\\").replace('"', '\\"')
        return rf'''(async function() {{
            function sleep(ms) {{ return new Promise(function(r) {{ setTimeout(r, ms); }}); }}
            function isVisible(el) {{
                if (!el) return false;
                var style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                var rect = el.getBoundingClientRect();
                if (!rect) return false;
                if (rect.width < 5 || rect.height < 5) return false;
                return true;
            }}
            function findComposer() {{
                var roleBox = document.querySelector('[role="textbox"]');
                if (roleBox && isVisible(roleBox)) return roleBox;
                var textareas = Array.from(document.querySelectorAll('textarea')).filter(isVisible);
                if (textareas.length) return textareas[0];
                var inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type])'))
                    .filter(function(el) {{ return isVisible(el) && !el.disabled && !el.readOnly; }});
                if (inputs.length) return inputs[0];
                var ceList = Array.from(document.querySelectorAll('[contenteditable="true"]')).filter(isVisible);
                if (ceList.length) return ceList[0];
                return null;
            }}
            function setComposerValue(el, text) {{
                if (!el) return false;
                try {{
                    el.focus();
                    if (el.isContentEditable) {{
                        try {{
                            document.execCommand('selectAll', false, null);
                            document.execCommand('insertText', false, text);
                        }} catch (e) {{
                            el.innerText = text;
                        }}
                    }} else {{
                        var proto = Object.getPrototypeOf(el);
                        var desc = Object.getOwnPropertyDescriptor(proto, 'value');
                        if (desc && desc.set) {{ desc.set.call(el, text); }} else {{ el.value = text; }}
                    }}
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }} catch (e) {{
                    return false;
                }}
            }}
            function composerText(el) {{
                if (!el) return '';
                try {{
                    if (el.isContentEditable) return (el.innerText || '').trim();
                    if (typeof el.value === 'string') return (el.value || '').trim();
                }} catch (e) {{}}
                return '';
            }}
            function clickSend(composer) {{
                if (!composer) return false;
                try {{
                    composer.focus();
                    var enterEvent = new KeyboardEvent('keydown', {{
                        bubbles: true,
                        cancelable: true,
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13
                    }});
                    composer.dispatchEvent(enterEvent);
                    return true;
                }} catch (e) {{
                    return false;
                }}
            }}
            function getRepliedMsgStore() {{
                try {{
                    return JSON.parse(localStorage.getItem('__ai_replied_msgs__') || '{{}}');
                }} catch (e) {{
                    return {{}};
                }}
            }}
            function setRepliedMsgStore(store) {{
                try {{ localStorage.setItem('__ai_replied_msgs__', JSON.stringify(store || {{}})); }} catch (e) {{}}
            }}

            var result = {{ sent: false, error: null }};
            try {{
                var composer = findComposer();
                if (!composer) {{
                    result.error = '未找到输入框';
                }} else if (!setComposerValue(composer, "{rt}")) {{
                    result.error = '写入输入框失败';
                }} else {{
                    await sleep(400);
                    var beforeText = composerText(composer);
                    if (!beforeText) {{
                        result.error = '输入框内容为空';
                    }} else {{
                        var ok = clickSend(composer);
                        if (!ok) {{
                            result.error = '触发发送失败';
                        }} else {{
                            await sleep(800);
                            var afterText = composerText(composer);
                            if (afterText) {{
                                result.error = '发送后输入框仍有内容';
                            }} else {{
                                result.sent = true;
                                var store = getRepliedMsgStore();
                                if (store && store["{mk}"]) {{
                                    store["{mk}"].status = 'done';
                                    store["{mk}"].reply = "{rt}";
                                    store["{mk}"].doneAt = new Date().toISOString();
                                    setRepliedMsgStore(store);
                                }}
                            }}
                        }}
                    }}
                }}
            }} catch (e) {{
                result.error = String(e && e.message ? e.message : e);
            }} finally {{
                try {{
                    if (window.__ai_session_lock && window.__ai_session_lock["{sk}"]) delete window.__ai_session_lock["{sk}"];
                }} catch (e) {{}}
                return result;
            }}
        }})();'''

    def _clear_pending_js(self, msg_key: str, session_lock_key: str):
        mk = (msg_key or "").replace("\\", "\\\\").replace('"', '\\"')
        sk = (session_lock_key or "").replace("\\", "\\\\").replace('"', '\\"')
        return rf'''(function() {{
            try {{
                var store = {{}};
                try {{ store = JSON.parse(localStorage.getItem('__ai_replied_msgs__') || '{{}}'); }} catch (e) {{ store = {{}}; }}
                try {{ delete store["{mk}"]; }} catch (e) {{}}
                try {{ localStorage.setItem('__ai_replied_msgs__', JSON.stringify(store || {{}})); }} catch (e) {{}}
                try {{ if (window.__ai_session_lock && window.__ai_session_lock["{sk}"]) delete window.__ai_session_lock["{sk}"]; }} catch (e) {{}}
                return {{ cleared: true }};
            }} catch (e) {{
                return {{ cleared: false, error: String(e && e.message ? e.message : e) }};
            }}
        }})()'''

    def _model_settings_defaults(self):
        return {
            "ChatGPT": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "gpt-4o-mini",
            },
            "Gemini": {
                "base_url": "https://generativelanguage.googleapis.com",
                "api_key": "",
                "model": "gemini-1.5-flash",
            },
            "阿里千问": {
                "base_url": "https://dashscope.aliyuncs.com",
                "api_key": "",
                "model": "qwen-plus",
            },
            "DeepSeek": {
                "base_url": "https://api.deepseek.com",
                "api_key": "",
                "model": "deepseek-chat",
            },
            "豆包": {
                "base_url": "",
                "api_key": "",
                "model": "",
            },
            "kimi": {
                "base_url": "https://api.moonshot.cn/v1",
                "api_key": "",
                "model": "moonshot-v1-8k",
            },
        }

    def _model_settings_load(self):
        try:
            need_create_default_file = not self.model_settings_file_path.exists()
            if not need_create_default_file:
                data = json.loads(self.model_settings_file_path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("models"), dict):
                    self.model_settings = data.get("models", {})
                else:
                    self.model_settings = {}
            else:
                self.model_settings = {}
        except Exception as e:
            self.model_settings = {}
            try:
                self.log(f"[MODEL] 读取模型配置失败：{e}")
            except Exception:
                pass

            need_create_default_file = True

        defaults = self._model_settings_defaults()
        for name, cfg in defaults.items():
            cur = self.model_settings.get(name)
            if not isinstance(cur, dict):
                self.model_settings[name] = dict(cfg)
            else:
                for k, v in cfg.items():
                    if k not in cur:
                        cur[k] = v

        if not self._model_settings_current:
            self._model_settings_current = "ChatGPT"

        if need_create_default_file:
            try:
                self._model_settings_save()
            except Exception:
                pass

    def _model_settings_save(self):
        payload = {
            "version": 1,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "models": self.model_settings,
        }
        self.model_settings_file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_model_settings_page(self):
        page = QWidget()
        page.setObjectName("ModelSettingsPage")
        root = QVBoxLayout(page)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("MsHero")
        hero_l = QHBoxLayout(hero)
        hero_l.setContentsMargins(18, 16, 18, 16)
        hero_l.setSpacing(12)

        hero_left = QWidget()
        hero_left_l = QVBoxLayout(hero_left)
        hero_left_l.setContentsMargins(0, 0, 0, 0)
        hero_left_l.setSpacing(4)
        title = QLabel("🔑 模型 API 配置")
        title.setObjectName("MsTitle")
        sub = QLabel("为每个模型配置 Base URL / API Key / 默认模型名。配置将保存到本地项目文件。")
        sub.setObjectName("MsSubTitle")
        hero_left_l.addWidget(title)
        hero_left_l.addWidget(sub)

        hero_actions = QWidget()
        ha = QHBoxLayout(hero_actions)
        ha.setContentsMargins(0, 0, 0, 0)
        ha.setSpacing(10)
        self.ms_save_btn = QPushButton("保存全部")
        self.ms_save_btn.setObjectName("MsPrimary")
        self.ms_save_btn.clicked.connect(self._ms_save_clicked)
        self.ms_reload_btn = QPushButton("重新加载")
        self.ms_reload_btn.setObjectName("MsGhost")
        self.ms_reload_btn.clicked.connect(self._ms_reload_clicked)
        ha.addWidget(self.ms_reload_btn)
        ha.addWidget(self.ms_save_btn)

        hero_l.addWidget(hero_left, 1)
        hero_l.addWidget(hero_actions)

        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)

        left_card = QFrame()
        left_card.setObjectName("MsCard")
        left_l = QVBoxLayout(left_card)
        left_l.setContentsMargins(14, 14, 14, 14)
        left_l.setSpacing(10)
        left_title = QLabel("模型列表")
        left_title.setObjectName("SectionTitle")
        self.ms_model_list = QListWidget()
        self.ms_model_list.setObjectName("MsModelList")
        for name in ["ChatGPT", "Gemini", "阿里千问", "DeepSeek", "豆包", "kimi"]:
            self.ms_model_list.addItem(name)
        self.ms_model_list.currentTextChanged.connect(self._ms_on_model_changed)
        left_l.addWidget(left_title)
        left_l.addWidget(self.ms_model_list, 1)

        right_card = QFrame()
        right_card.setObjectName("MsCard")
        right_l = QVBoxLayout(right_card)
        right_l.setContentsMargins(16, 14, 16, 14)
        right_l.setSpacing(12)

        form_title = QLabel("参数")
        form_title.setObjectName("SectionTitle")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)

        self.ms_base_url = QLineEdit()
        self.ms_base_url.setObjectName("MsInput")
        self.ms_base_url.setPlaceholderText("例如 https://api.openai.com/v1")
        self.ms_api_key = QLineEdit()
        self.ms_api_key.setObjectName("MsInput")
        self.ms_api_key.setEchoMode(QLineEdit.Password)
        self.ms_api_key.setPlaceholderText("粘贴 API Key（将保存到本地 JSON）")
        self.ms_model_name = QLineEdit()
        self.ms_model_name.setObjectName("MsInput")
        self.ms_model_name.setPlaceholderText("例如 gpt-4o-mini / qwen-plus / deepseek-chat")

        form.addRow("Base URL", self.ms_base_url)
        form.addRow("API Key", self.ms_api_key)
        form.addRow("Model", self.ms_model_name)

        hint = QLabel("提示：此页面仅负责配置与保存，不会在此处发起真实请求。")
        hint.setObjectName("MsSubTitle")

        row_actions = QWidget()
        ra = QHBoxLayout(row_actions)
        ra.setContentsMargins(0, 0, 0, 0)
        ra.setSpacing(10)
        self.ms_apply_btn = QPushButton("应用修改")
        self.ms_apply_btn.setObjectName("MsGhost")
        self.ms_apply_btn.clicked.connect(self._ms_apply_clicked)
        ra.addWidget(self.ms_apply_btn)
        ra.addStretch(1)

        right_l.addWidget(form_title)
        right_l.addLayout(form)
        right_l.addWidget(hint)
        right_l.addWidget(row_actions)
        right_l.addStretch(1)

        body.addWidget(left_card)
        body.addWidget(right_card)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 3)

        root.addWidget(hero)
        root.addWidget(body, 1)

        self.ms_model_list.setCurrentRow(0)
        return page

    def _ms_on_model_changed(self, name: str):
        if not name:
            return

        self._ms_apply_clicked(silent=True)
        self._model_settings_current = name
        cfg = self.model_settings.get(name, {}) if isinstance(self.model_settings, dict) else {}
        self.ms_base_url.setText(str(cfg.get("base_url", "")))
        api_key = str(cfg.get("api_key", ""))
        if (not api_key) and name == "阿里千问":
            api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.ms_api_key.setText(api_key)
        self.ms_model_name.setText(str(cfg.get("model", "")))

    def _ms_apply_clicked(self, silent: bool = False):
        name = self._model_settings_current
        if not name:
            return

        cfg = self.model_settings.get(name)
        if not isinstance(cfg, dict):
            cfg = {}
            self.model_settings[name] = cfg

        cfg["base_url"] = (self.ms_base_url.text() if hasattr(self, "ms_base_url") else "").strip()
        cfg["api_key"] = (self.ms_api_key.text() if hasattr(self, "ms_api_key") else "").strip()
        cfg["model"] = (self.ms_model_name.text() if hasattr(self, "ms_model_name") else "").strip()
        if (not silent) and hasattr(self, "log"):
            self.log(f"[MODEL] 已应用修改：{name}")

    def _ms_save_clicked(self):
        self._ms_apply_clicked(silent=True)
        try:
            self._model_settings_save()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return
        QMessageBox.information(self, "保存成功", f"已保存到：{self.model_settings_file_path}")

    def _ms_reload_clicked(self):
        self._model_settings_load()
        cur = self._model_settings_current or "ChatGPT"
        if hasattr(self, "ms_model_list"):
            items = self.ms_model_list.findItems(cur, Qt.MatchExactly)
            if items:
                self.ms_model_list.setCurrentItem(items[0])
            else:
                self.ms_model_list.setCurrentRow(0)

    def _watch_active_chat(self):
        if not self._page_ready:
            return
        if self._watch_inflight:
            return
        self._watch_inflight = True

        js_code = r"""
        (function() {
            function safeText(el) {
                if (!el) return "";
                return (el.textContent || el.innerText || "").trim();
            }

            function isVisible(el) {
                if (!el) return false;
                var style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                var rect = el.getBoundingClientRect();
                if (!rect || rect.width < 5 || rect.height < 5) return false;
                return true;
            }

            function isValidUserName(text) {
                if (!text || text.length < 1 || text.length > 20) return false;
                if (/\s/.test(text)) return false;
                if (/[0-9]/.test(text)) return false;
                if (/[：:？?!！。，,.]/.test(text)) return false;
                if (/^星期[一二三四五六日]/.test(text)) return false;
                if (/\d{1,2}:\d{2}/.test(text)) return false;
                var filterWords = ['转接', '结束', '接待', '开始', '继续', '回复', '进入',
                                   '用户超时', '客服已结束', '你已超过', '未回复', '会话已结束',
                                   '会话', '全部', '当前会话'];
                for (var f = 0; f < filterWords.length; f++) {
                    if (text.indexOf(filterWords[f]) !== -1) return false;
                }
                return true;
            }

            // 优先从左侧 current 会话项提取
            var selectedItems = document.querySelectorAll('[class*="current"], .selected, [aria-selected="true"]');
            var best = null;
            var bestScore = -1e9;
            for (var k = 0; k < selectedItems.length; k++) {
                var item = selectedItems[k];
                if (!isVisible(item)) continue;
                var r = item.getBoundingClientRect();
                if (r.left > 260) continue;
                if (r.top < 130) continue;

                var text = safeText(item);
                var nameSelectors = ['.name', '.nickname', '.user-name', '.title', '[class*="name"]', '[class*="title"]'];
                for (var m = 0; m < nameSelectors.length; m++) {
                    var nameEl = item.querySelector(nameSelectors[m]);
                    if (nameEl) {
                        var t = safeText(nameEl);
                        if (t) { text = t; break; }
                    }
                }

                if (!isValidUserName(text)) continue;

                var score = 0;
                try {
                    if (String(item.className || '').indexOf('current') !== -1) score += 200;
                    if (String(item.className || '').indexOf('selected') !== -1) score += 150;
                    if (item.getAttribute && item.getAttribute('aria-selected') === 'true') score += 120;
                } catch (e) {}
                score += Math.floor(r.top / 10);

                if (score > bestScore) {
                    bestScore = score;
                    best = { name: text, method: 'list-item' };
                }
            }

            if (best) {
                return JSON.stringify(best);
            }

            return JSON.stringify({ name: null, method: null });
        })()
        """

        def on_result(res):
            self._watch_inflight = False
            if not res:
                return
            try:
                data = res if isinstance(res, dict) else json.loads(res)
            except Exception:
                return

            name = data.get('name')
            if not name:
                return
            if name != self._last_active_chat_user:
                self._last_active_chat_user = name
                self.log(f"[AUTO] 检测到切换会话：{name}，自动抓取聊天记录")
                self.test_grab_chat_data()

        self.browser.page().runJavaScript(js_code, on_result)

    def probe_page_structure(self):
        """探测页面结构，帮助调试"""
        js_code = r"""
        (function() {
            var result = {
                url: location.href,
                title: document.title,
                readyState: document.readyState,
                iframeCount: document.querySelectorAll('iframe').length,
                frames: []
            };

            // 检查所有 iframe
            var iframes = document.querySelectorAll('iframe');
            for (var i = 0; i < iframes.length; i++) {
                var f = iframes[i];
                var rect = f.getBoundingClientRect();
                result.frames.push({
                    index: i,
                    src: f.src || '',
                    name: f.name || '',
                    id: f.id || '',
                    width: rect.width,
                    height: rect.height,
                    visible: rect.width > 0 && rect.height > 0
                });
            }

            // 查找可能的聊天区域
            var chatAreas = [];
            var divs = document.querySelectorAll('div');
            for (var j = 0; j < Math.min(divs.length, 100); j++) {
                var d = divs[j];
                var r = d.getBoundingClientRect();
                if (r.width > 300 && r.height > 200) {
                    chatAreas.push({
                        tag: d.tagName,
                        class: d.className || '',
                        id: d.id || '',
                        width: r.width,
                        height: r.height,
                        top: r.top,
                        left: r.left
                    });
                }
            }
            result.possibleChatAreas = chatAreas.slice(0, 10);

            // 查找包含"未读"、数字角标的元素
            var badges = [];
            var spans = document.querySelectorAll('span, div');
            for (var k = 0; k < spans.length; k++) {
                var s = spans[k];
                var text = (s.textContent || '').trim();
                if (/^[1-9]\d*$/.test(text)) {
                    var style = window.getComputedStyle(s);
                    var bg = style.backgroundColor || '';
                    badges.push({
                        text: text,
                        background: bg,
                        class: s.className || '',
                        parentClass: s.parentElement ? s.parentElement.className : ''
                    });
                }
            }
            result.possibleBadges = badges.slice(0, 10);

            // 查找输入框
            var inputs = [];
            var textareas = document.querySelectorAll('textarea');
            var contentEditables = document.querySelectorAll('[contenteditable="true"]');
            var roleTextboxes = document.querySelectorAll('[role="textbox"]');

            inputs.push({type: 'textarea', count: textareas.length});
            inputs.push({type: 'contenteditable', count: contentEditables.length});
            inputs.push({type: 'role_textbox', count: roleTextboxes.length});

            result.inputs = inputs;

            return JSON.stringify(result, null, 2);
        })()
        """

        def on_result(res):
            if res:
                self.log("=== 页面结构探测结果 ===")
                try:
                    data = json.loads(res)
                    self.log(f"URL: {data.get('url')}")
                    self.log(f"标题: {data.get('title')}")
                    self.log(f"Iframe 数量: {data.get('iframeCount')}")

                    if data.get('frames'):
                        self.log("--- Iframe 列表 ---")
                        for f in data['frames']:
                            self.log(f"  [{f['index']}] {f['name'] or f['id'] or 'unnamed'} - {f['width']}x{f['height']}")

                    if data.get('possibleChatAreas'):
                        self.log("--- 可能的聊天区域 ---")
                        for area in data['possibleChatAreas'][:5]:
                            self.log(f"  {area['tag']}.{area['class'][:30]} {area['width']}x{area['height']}")

                    if data.get('possibleBadges'):
                        self.log("--- 可能的未读角标 ---")
                        for badge in data['possibleBadges'][:5]:
                            self.log(f"  数字:{badge['text']} 背景:{badge['background'][:30]}")

                    self.log("--- 输入框检测 ---")
                    for inp in data.get('inputs', []):
                        self.log(f"  {inp['type']}: {inp['count']}个")

                except Exception as e:
                    self.log(f"解析结果出错: {e}")
                    self.log(f"原始结果: {res[:500]}")
            else:
                self.log("页面结构探测失败，无返回结果")

        self.browser.page().runJavaScript(js_code, on_result)

    def test_grab_chat_data(self):
        """测试抓取聊天数据 - 基于微信小店实际结构"""
        js_code = r"""
        (function() {
            function safeText(el) {
                if (!el) return "";
                return (el.textContent || el.innerText || "").trim();
            }

            function isVisible(el) {
                if (!el) return false;
                var style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                var rect = el.getBoundingClientRect();
                if (!rect || rect.width < 5 || rect.height < 5) return false;
                return true;
            }

            // 获取当前聊天用户名称 - 基于微信小店结构
            function getCurrentChatUser() {
                var result = {
                    name: null,
                    method: null,
                    allCandidates: []
                };

                // 过滤函数
                function isValidUserName(text) {
                    if (!text || text.length < 1 || text.length > 20) return false;
                    if (/\s/.test(text)) return false;
                    if (/[0-9]/.test(text)) return false;
                    if (/[：:？?!！。，,.]/.test(text)) return false;
                    if (/^星期[一二三四五六日]/.test(text)) return false;
                    if (/\d{1,2}:\d{2}/.test(text)) return false;
                    var filterWords = ['转接', '结束', '接待', '开始', '继续', '回复', '进入',
                                       '用户超时', '客服已结束', '你已超过', '未回复', '会话已结束',
                                       '会话', '全部', '当前会话'];
                    for (var f = 0; f < filterWords.length; f++) {
                        if (text.indexOf(filterWords[f]) !== -1) return false;
                    }
                    return true;
                }

                // 方法1: 从右侧聊天头部获取 (微信小店通常在右上角显示用户名)
                // 只在页面右侧顶部区域查找
                var headerAreas = document.querySelectorAll('.chat-header, .chat-title, .session-title, [class*="header"]');
                for (var i = 0; i < headerAreas.length; i++) {
                    var area = headerAreas[i];
                    if (!isVisible(area)) continue;
                    var r = area.getBoundingClientRect();
                    // 确保在页面右侧（主聊天区域顶部），不在左侧
                    if (r.left < 300 || r.top > 150) continue;
                    var text = safeText(area);
                    if (isValidUserName(text)) {
                        result.allCandidates.push({source: 'header', text: text});
                        if (!result.name) {
                            result.name = text;
                            result.method = 'header';
                        }
                    }
                }

                // 方法2: 从 h1-h4 标签获取（限制在右侧区域）
                var headings = document.querySelectorAll('h1, h2, h3, h4');
                for (var j = 0; j < headings.length; j++) {
                    var h = headings[j];
                    if (!isVisible(h)) continue;
                    var r = h.getBoundingClientRect();
                    // 只在右侧顶部查找
                    if (r.left < 300 || r.top > 150) continue;
                    var text = safeText(h);
                    if (isValidUserName(text)) {
                        result.allCandidates.push({source: 'heading', text: text});
                        if (!result.name) {
                            result.name = text;
                            result.method = 'heading';
                        }
                    }
                }

                // 方法3: 从当前选中的会话列表项获取（优先 current，排除顶部tab）
                var selectedItems = document.querySelectorAll('[class*="current"], .selected, [aria-selected="true"]');
                var best = null;
                var bestScore = -1e9;
                for (var k = 0; k < selectedItems.length; k++) {
                    var item = selectedItems[k];
                    if (!isVisible(item)) continue;
                    var r = item.getBoundingClientRect();
                    if (r.left > 260) continue;
                    if (r.top < 130) continue;

                    var text = safeText(item);
                    var nameSelectors = ['.name', '.nickname', '.user-name', '.title', '[class*="name"]', '[class*="title"]'];
                    for (var m = 0; m < nameSelectors.length; m++) {
                        var nameEl = item.querySelector(nameSelectors[m]);
                        if (nameEl) {
                            var t = safeText(nameEl);
                            if (t) { text = t; break; }
                        }
                    }
                    if (!isValidUserName(text)) continue;

                    var score = 0;
                    try {
                        if (String(item.className || '').indexOf('current') !== -1) score += 200;
                        if (String(item.className || '').indexOf('selected') !== -1) score += 150;
                        if (item.getAttribute && item.getAttribute('aria-selected') === 'true') score += 120;
                    } catch (e) {}
                    score += Math.floor(r.top / 10);

                    result.allCandidates.push({source: 'list-item', text: text, score: score, top: r.top});
                    if (score > bestScore) {
                        bestScore = score;
                        best = { text: text, method: 'list-item' };
                    }
                }
                if (best && !result.name) {
                    result.name = best.text;
                    result.method = best.method;
                }

                // 方法4: 从页面右侧顶部区域直接查找（兜底）
                var allDivs = document.querySelectorAll('div, span');
                for (var n = 0; n < allDivs.length; n++) {
                    var el = allDivs[n];
                    if (!isVisible(el)) continue;
                    var rect = el.getBoundingClientRect();
                    // 只在页面右侧顶部区域查找
                    if (rect.left < 300 || rect.left > 800) continue; // 太靠左或太靠右
                    if (rect.top < 20 || rect.top > 100) continue; // 不在顶部区域
                    if (rect.width < 10 || rect.width > 300) continue; // 宽度不合适

                    var text = safeText(el);
                    if (isValidUserName(text)) {
                        result.allCandidates.push({source: 'top-area', text: text, position: {top: rect.top, left: rect.left}});
                        if (!result.name) {
                            result.name = text;
                            result.method = 'top-area';
                        }
                    }
                }

                return result;
            }

            // 获取聊天消息 - 优化版，获取完整对话
            function getChatMessages() {
                var result = {
                    messages: [],           // 所有消息
                    userMessages: [],       // 用户消息
                    replyMessages: [],      // 客服回复
                    debug: []
                };

                // 找聊天区域：以输入框为锚点，向上寻找右侧会话面板
                function findComposer() {
                    var roleBox = document.querySelector('[role="textbox"]');
                    if (roleBox && isVisible(roleBox)) return roleBox;
                    var textareas = Array.from(document.querySelectorAll('textarea')).filter(isVisible);
                    if (textareas.length) return textareas[0];
                    var ceList = Array.from(document.querySelectorAll('[contenteditable="true"]')).filter(isVisible);
                    if (ceList.length) return ceList[0];
                    return null;
                }

                var composer = findComposer();
                if (!composer) {
                    result.debug.push("未找到输入框（无法定位聊天面板）");
                    return result;
                }

                var chatArea = null;
                var composerRect = composer.getBoundingClientRect();
                var cur = composer;
                var bestArea = 0;
                for (var up = 0; up < 12 && cur; up++) {
                    cur = cur.parentElement;
                    if (!cur || !isVisible(cur)) continue;
                    var r = cur.getBoundingClientRect();
                    if (r.left < 260) continue;
                    if (r.width < 320 || r.height < 300) continue;
                    var area = r.width * r.height;
                    if (area > bestArea) {
                        bestArea = area;
                        chatArea = cur;
                    }
                }

                if (!chatArea) {
                    result.debug.push("未找到聊天区域");
                    return result;
                }

                // 在聊天面板内找消息滚动区（在输入框上方，且不包含输入框）
                var chatRect = chatArea.getBoundingClientRect();
                var messageArea = null;
                var bestMsgArea = 0;
                var divs = Array.from(chatArea.querySelectorAll('div'));
                for (var i = 0; i < divs.length; i++) {
                    var el = divs[i];
                    if (!isVisible(el)) continue;
                    if (el === composer || (el.contains && el.contains(composer))) continue;
                    var r = el.getBoundingClientRect();
                    if (!r) continue;
                    if (r.left < chatRect.left - 5) continue;
                    if (r.top < chatRect.top) continue;
                    if (r.bottom > composerRect.top + 5) continue;
                    if (r.height < 200 || r.width < 300) continue;
                    var st = window.getComputedStyle(el);
                    var oy = (st && st.overflowY) ? st.overflowY : '';
                    if (oy !== 'auto' && oy !== 'scroll' && oy !== 'overlay') continue;
                    var area = r.width * r.height;
                    if (area > bestMsgArea) {
                        bestMsgArea = area;
                        messageArea = el;
                    }
                }
                if (!messageArea) messageArea = chatArea;

                var msgRect = messageArea.getBoundingClientRect();
                var centerX = msgRect.left + msgRect.width * 0.5;

                // 时间正则
                var timeRegex = /^(星期[一二三四五六日](\s*\d{1,2}:\d{2})?|\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2}|\d{2}-\d{2})$/;
                // 系统提示正则
                var systemRegex = /(用户超时未回|客服已结束|你已超.*未回复|会话已结束|两天内仍可再次联系|你撤回了一条消息|对方撤回了一条消息)/;

                // 获取所有文本节点（包括嵌套的）
                var allTexts = [];
                var walker = document.createTreeWalker(messageArea, NodeFilter.SHOW_TEXT, null, false);
                var textNode;
                while (textNode = walker.nextNode()) {
                    var parent = textNode.parentElement;
                    if (!parent || !isVisible(parent)) continue;

                    var text = textNode.textContent.trim();
                    if (!text || text.length === 0) continue;
                    text = text.replace(/^星期[一二三四五六日]\s*\d{1,2}:\d{2}\s*/,'');
                    text = text.replace(/^\d{4}-\d{2}-\d{2}\s*\d{1,2}:\d{2}\s*/,'');
                    if (timeRegex.test(text)) continue; // 跳过时间
                    if (systemRegex.test(text)) continue; // 跳过系统提示

                    var r = parent.getBoundingClientRect();
                    if (r.top < msgRect.top + 20) continue; // 跳过顶部区域
                    if (r.width < 10 || r.height < 10) continue; // 跳过太小的元素

                    // 判断消息来源：左侧是用户，右侧是客服
                    var isUser = r.right < centerX - 30;
                    var isReply = r.left > centerX + 30;

                    allTexts.push({
                        text: text,
                        isUser: isUser,
                        isReply: isReply,
                        top: r.top,
                        left: r.left,
                        right: r.right,
                        width: r.width
                    });
                }

                result.debug.push("原始文本节点: " + allTexts.length);

                // 合并相邻的文本节点（同一条消息可能被分成多个文本节点）
                var mergedMessages = [];
                var currentMsg = null;

                // 先按位置排序
                allTexts.sort(function(a, b) { return a.top - b.top; });

                for (var j = 0; j < allTexts.length; j++) {
                    var item = allTexts[j];

                    // 跳过纯数字（可能是未读数），但保留手机号（长度>5的数字）
                    if (/^\d+$/.test(item.text) && item.text.length < 5) continue;

                    if (!currentMsg) {
                        currentMsg = item;
                    } else {
                        // 判断是否属于同一条消息（垂直距离小于20，同一侧）
                        var sameSide = (item.isUser && currentMsg.isUser) || (item.isReply && currentMsg.isReply);
                        var closeVertical = Math.abs(item.top - currentMsg.top) < 25;
                        var closeHorizontal = Math.abs(item.left - currentMsg.left) < 100;

                        if (sameSide && closeVertical && closeHorizontal) {
                            // 合并文本
                            currentMsg.text += " " + item.text;
                            currentMsg.width = Math.max(currentMsg.width, item.width);
                        } else {
                            mergedMessages.push(currentMsg);
                            currentMsg = item;
                        }
                    }
                }
                if (currentMsg) {
                    mergedMessages.push(currentMsg);
                }

                result.debug.push("合并后消息: " + mergedMessages.length);

                // 过滤并分类消息
                for (var k = 0; k < mergedMessages.length; k++) {
                    var msg = mergedMessages[k];

                    // 过滤掉太短或太长的
                    if (msg.text.length < 2 || msg.text.length > 500) continue;

                    // 再次过滤系统提示
                    if (systemRegex.test(msg.text)) continue;

                    result.messages.push({
                        text: msg.text,
                        isUser: msg.isUser,
                        isReply: msg.isReply,
                        position: {top: msg.top, left: msg.left}
                    });

                    if (msg.isUser) {
                        result.userMessages.push(msg);
                    } else if (msg.isReply) {
                        result.replyMessages.push(msg);
                    }
                }

                // 按位置排序
                result.messages.sort(function(a, b) { return a.position.top - b.position.top; });

                return result;
            }

            // 执行测试
            var userResult = getCurrentChatUser();
            var msgResult = getChatMessages();

            var output = {
                timestamp: new Date().toISOString(),
                user: userResult,
                messages: msgResult
            };

            return JSON.stringify(output);
        })()
        """

        def on_result(res):
            if res:
                self.log("=== 聊天数据抓取测试结果 ===")
                try:
                    data = json.loads(res)

                    # 用户名结果
                    userResult = data.get('user', {})
                    display_user = userResult.get('name') or "用户"
                    self.log("--- 用户名抓取 ---")
                    if userResult.get('name'):
                        self.log(f"  ✅ 用户名: {userResult.get('name')}")
                        self.log(f"  方法: {userResult.get('method')}")
                    else:
                        self.log("  ❌ 未找到用户名")
                        candidates = userResult.get('allCandidates', [])
                        self.log(f"  候选数量: {len(candidates)}")
                        for c in candidates[:10]:
                            self.log(f"    - [{c.get('source')}] {c.get('text', '')[:30]}")

                    # 消息结果
                    msgResult = data.get('messages', {})
                    self.log("--- 消息抓取 ---")
                    debug = msgResult.get('debug', [])
                    for d in debug:
                        self.log(f"  调试: {d}")

                    # 显示完整对话（用户 + 客服）
                    allMessages = msgResult.get('messages', [])
                    userMessages = msgResult.get('userMessages', [])
                    replyMessages = msgResult.get('replyMessages', [])

                    self.log(f"  总消息: {len(allMessages)} | 用户: {len(userMessages)} | 客服: {len(replyMessages)}")

                    if allMessages:
                        self.log("  --- 完整对话 ---")
                        for m in allMessages[-10:]:  # 显示最后10条
                            isUser = m.get('isUser', False)
                            isReply = m.get('isReply', False)
                            text = m.get('text', '')
                            shown = text[:200] + ('...' if len(text) > 200 else '')
                            if isUser:
                                self.log(f"    👤{display_user}：{shown}")
                            elif isReply:
                                self.log(f"    🤖我：{shown}")
                            else:
                                self.log(f"    ❓{shown}")
                    else:
                        self.log("  ⚠️ 未找到消息")

                except Exception as e:
                    self.log(f"解析结果出错: {e}")
                    import traceback
                    self.log(f"堆栈: {traceback.format_exc()}")
                    self.log(f"原始结果: {str(res)[:500]}")
            else:
                self.log("❌ 测试失败，无返回结果")

        self.browser.page().runJavaScript(js_code, on_result)

    def debug_chat_state(self):
        """详细分析当前聊天状态 - 专门用于调试多用户聊天记录问题"""
        js_code = r"""
        (function() {
            function safeText(el) {
                if (!el) return "";
                return (el.textContent || el.innerText || "").trim();
            }

            function isVisible(el) {
                if (!el) return false;
                var style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                var rect = el.getBoundingClientRect();
                if (!rect || rect.width < 5 || rect.height < 5) return false;
                return true;
            }

            var result = {
                timestamp: new Date().toISOString(),
                url: location.href,
                chatAreas: [],
                userNames: [],
                selectedItems: [],
                debug: []
            };

            // 分析所有可能的聊天区域
            var allChatSelectors = ['.chat-wrap', '.chat-page', '.chat-area', '.message-list'];
            for (var s = 0; s < allChatSelectors.length; s++) {
                var selector = allChatSelectors[s];
                var elements = document.querySelectorAll(selector);
                for (var i = 0; i < elements.length; i++) {
                    var el = elements[i];
                    if (!isVisible(el)) continue;
                    var rect = el.getBoundingClientRect();
                    
                    // 检查该区域内的消息数量
                    var messageCount = 0;
                    var centerX = rect.left + rect.width * 0.5;
                    var textElements = el.querySelectorAll('*');
                    
                    for (var j = 0; j < Math.min(textElements.length, 100); j++) {
                        var textEl = textElements[j];
                        if (!isVisible(textEl)) continue;
                        var text = safeText(textEl);
                        if (!text || text.length < 2) continue;
                        
                        var elRect = textEl.getBoundingClientRect();
                        if (elRect.top < rect.top + 20) continue;
                        
                        var isUserMsg = elRect.right < centerX - 30;
                        var isReplyMsg = elRect.left > centerX + 30;
                        
                        if (isUserMsg || isReplyMsg) {
                            messageCount++;
                        }
                    }
                    
                    result.chatAreas.push({
                        selector: selector,
                        index: i,
                        rect: {
                            left: Math.round(rect.left),
                            top: Math.round(rect.top),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        },
                        area: Math.round(rect.width * rect.height),
                        messageCount: messageCount
                    });
                }
            }

            // 按消息数量排序聊天区域
            result.chatAreas.sort(function(a, b) { return b.messageCount - a.messageCount; });

            // 分析当前选中的会话项
            var activeSelectors = ['.selected', '[class*="active"]', '[class*="current"]', '[aria-selected="true"]'];
            for (var m = 0; m < activeSelectors.length; m++) {
                var items = document.querySelectorAll(activeSelectors[m]);
                for (var n = 0; n < items.length; n++) {
                    var item = items[n];
                    if (!isVisible(item)) continue;
                    var itemRect = item.getBoundingClientRect();
                    if (itemRect.left > 200) continue;
                    
                    var nameEl = item.querySelector('.name, .nickname, [class*="name"], [class*="title"]');
                    var itemText = nameEl ? safeText(nameEl) : safeText(item);
                    
                    result.selectedItems.push({
                        selector: activeSelectors[m],
                        text: itemText,
                        rect: {
                            left: Math.round(itemRect.left),
                            top: Math.round(itemRect.top),
                            width: Math.round(itemRect.width),
                            height: Math.round(itemRect.height)
                        }
                    });
                }
            }

            return JSON.stringify(result, null, 2);
        })()
        """

        def on_result(res):
            if res:
                self.log("=== 详细聊天状态分析 ===")
                try:
                    data = json.loads(res)
                    
                    # 聊天区域分析
                    chatAreas = data.get('chatAreas', [])
                    self.log(f"发现 {len(chatAreas)} 个聊天区域 (按消息数排序):")
                    for i, area in enumerate(chatAreas[:5]):
                        self.log(f"  {i+1}. {area['selector']} - 消息数:{area['messageCount']} "
                                f"位置:({area['rect']['left']},{area['rect']['top']}) "
                                f"大小:{area['rect']['width']}x{area['rect']['height']}")
                    
                    # 选中项分析
                    selectedItems = data.get('selectedItems', [])
                    self.log(f"\n发现 {len(selectedItems)} 个选中项:")
                    for i, item in enumerate(selectedItems):
                        self.log(f"  {i+1}. {item['selector']} - '{item['text']}' "
                                f"位置:({item['rect']['left']},{item['rect']['top']})")
                        
                except Exception as e:
                    self.log(f"解析结果出错: {e}")
            else:
                self.log("❌ 详细分析失败，无返回结果")

        self.browser.page().runJavaScript(js_code, on_result)

    def force_refresh_detection(self):
        """强制刷新检测 - 清除缓存并重新检测当前状态"""
        js_code = r"""
        (function() {
            try {
                // 清除所有可能的缓存
                localStorage.clear();
                sessionStorage.clear();
                
                // 清除可能的全局变量
                if (window.__ai_global_busy) delete window.__ai_global_busy;
                if (window.__ai_session_lock) delete window.__ai_session_lock;
                if (window.__last_chat_area) delete window.__last_chat_area;
                if (window.__last_user_name) delete window.__last_user_name;
                
                console.log('[DEBUG] 已清除所有缓存和全局变量');
                
                // 强制重新计算布局
                var allElements = document.querySelectorAll('*');
                for (var i = 0; i < Math.min(allElements.length, 500); i++) {
                    var el = allElements[i];
                    // 触发重新计算
                    var rect = el.getBoundingClientRect();
                }
                
                console.log('[DEBUG] 已强制重新计算元素布局');
                
                return JSON.stringify({
                    timestamp: new Date().toISOString(),
                    cleared: true,
                    elementsProcessed: Math.min(allElements.length, 500)
                });
            } catch (e) {
                console.error('[DEBUG] 强制刷新出错:', e);
                return JSON.stringify({
                    timestamp: new Date().toISOString(),
                    cleared: false,
                    error: String(e)
                });
            }
        })()
        """
        
        def on_result(res):
            if res:
                try:
                    data = res if isinstance(res, dict) else json.loads(res)
                    if data.get('cleared'):
                        self.log(f"🔄 强制刷新完成: 处理了 {data.get('elementsProcessed', 0)} 个元素")
                        
                        # 等待一秒后自动运行详细分析
                        QTimer.singleShot(1000, self.debug_chat_state)
                    else:
                        self.log(f"❌ 强制刷新失败: {data.get('error', '未知错误')}")
                except Exception as e:
                    self.log(f"强制刷新结果解析错误: {e}")
            else:
                self.log("❌ 强制刷新失败：无返回结果")
        
        self.browser.page().runJavaScript(js_code, on_result)

    def poll_unread_and_reply(self):
        if not self.ai_enabled:
            return

        if not self._page_ready:
            return

        if self._poll_inflight:
            return
        self._poll_inflight = True

        js_code = rf'''(async function() {{
            // 全局锁：确保同一时间只有一个AI回复在执行
            if (window.__ai_global_busy) {{
                return {{ ts: new Date().toISOString(), found: 0, processed: 0, skipped: 0, errors: [], debug: {{ global_busy: true }} }};
            }}
            window.__ai_global_busy = true;

            function nowTs() {{ return new Date().toISOString(); }}
            function safeText(el) {{ return (el && (el.textContent || el.innerText) || "").trim(); }}
            function sleep(ms) {{ return new Promise(function(r) {{ setTimeout(r, ms); }}); }}
            function hashStr(s) {{
                s = String(s || '');
                var h = 2166136261;
                for (var i = 0; i < s.length; i++) {{
                    h ^= s.charCodeAt(i);
                    h += (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24);
                }}
                return (h >>> 0).toString(16);
            }}

            function getReplyStore() {{
                try {{
                    return JSON.parse(localStorage.getItem('__ai_replied__') || '{{}}');
                }} catch (e) {{
                    return {{}};
                }}
            }}

            function setReplyStore(store) {{
                try {{ localStorage.setItem('__ai_replied__', JSON.stringify(store || {{}})); }} catch (e) {{}}
            }}

            function getRepliedMsgStore() {{
                try {{
                    return JSON.parse(localStorage.getItem('__ai_replied_msgs__') || '{{}}');
                }} catch (e) {{
                    return {{}};
                }}
            }}

            function setRepliedMsgStore(store) {{
                try {{ localStorage.setItem('__ai_replied_msgs__', JSON.stringify(store || {{}})); }} catch (e) {{}}
            }}

            function isVisible(el) {{
                if (!el) return false;
                var style = window.getComputedStyle(el);
                if (!style) return false;
                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
                var rect = el.getBoundingClientRect();
                if (!rect) return false;
                if (rect.width < 5 || rect.height < 5) return false;
                return true;
            }}

            function findClickableAncestor(el) {{
                var cur = el;
                for (var i = 0; i < 8 && cur; i++) {{
                    if (cur.tagName === 'LI' || cur.getAttribute('role') === 'listitem') return cur;
                    if (typeof cur.onclick === 'function') return cur;
                    var style = window.getComputedStyle(cur);
                    if (style && style.cursor === 'pointer') return cur;
                    cur = cur.parentElement;
                }}
                return el;
            }}

            function findUnreadCandidates() {{
                var candidates = [];

                // 常见：红色角标数字
                var badgeNodes = Array.from(document.querySelectorAll('span,div'))
                    .filter(function(n) {{
                        var t = safeText(n);
                        if (!t) return false;
                        if (!/^\\d+$/.test(t)) return false;
                        var num = parseInt(t, 10);
                        if (!num || num <= 0) return false;
                        var s = window.getComputedStyle(n);
                        if (!s) return false;
                        var bg = s.backgroundColor || '';
                        // 容错：红色 / 接近红色
                        if (bg.indexOf('255, 0, 0') !== -1) return true;
                        if (bg.indexOf('rgb(') === 0) {{
                            var m = bg.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
                            if (m) {{
                                var r = parseInt(m[1],10), g = parseInt(m[2],10), b = parseInt(m[3],10);
                                if (r > 200 && g < 120 && b < 120) return true;
                            }}
                        }}
                        return false;
                    }});

                badgeNodes.forEach(function(b) {{
                    var clickEl = findClickableAncestor(b);
                    if (clickEl && candidates.indexOf(clickEl) === -1) candidates.push(clickEl);
                }});

                // 兜底：包含 unread 类名
                var unreadClassNodes = Array.from(document.querySelectorAll('.unread, [class*="unread" i]'));
                unreadClassNodes.forEach(function(n) {{
                    var clickEl = findClickableAncestor(n);
                    if (clickEl && candidates.indexOf(clickEl) === -1) candidates.push(clickEl);
                }});

                return candidates;
            }}

            function sessionKeyFromElement(el) {{
                if (!el) return null;
                try {{
                    var did = el.getAttribute('data-id') || el.getAttribute('data-session-id') || el.getAttribute('data-chat-id');
                    if (did) return String(did);
                }} catch (e) {{}}
                // 兜底：用会话项展示文本（含昵称/预览）做 hash
                var txt = safeText(el);
                if (!txt) return null;
                return 't_' + hashStr(txt.slice(0, 120));
            }}

            function findComposer() {{
                // 常见输入框：textarea / input / contenteditable
                var roleBox = document.querySelector('[role="textbox"]');
                if (roleBox && isVisible(roleBox)) return roleBox;

                var textareas = Array.from(document.querySelectorAll('textarea')).filter(isVisible);
                if (textareas.length) return textareas[0];

                var inputs = Array.from(document.querySelectorAll('input[type="text"], input:not([type])'))
                    .filter(function(el) {{ return isVisible(el) && !el.disabled && !el.readOnly; }});
                if (inputs.length) return inputs[0];

                var ceList = Array.from(document.querySelectorAll('[contenteditable="true"]')).filter(isVisible);
                if (ceList.length) return ceList[0];
                return null;
            }}

            function setComposerValue(el, text) {{
                if (!el) return false;
                try {{
                    el.focus();
                    if (el.isContentEditable) {{
                        // 更像用户输入：execCommand + 兜底 innerText
                        try {{
                            document.execCommand('selectAll', false, null);
                            document.execCommand('insertText', false, text);
                        }} catch (e) {{
                            el.innerText = text;
                        }}
                    }} else {{
                        // 使用原生 value setter 触发框架监听
                        var proto = Object.getPrototypeOf(el);
                        var desc = Object.getOwnPropertyDescriptor(proto, 'value');
                        if (desc && desc.set) {{
                            desc.set.call(el, text);
                        }} else {{
                            el.value = text;
                        }}
                    }}
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }} catch (e) {{
                    return false;
                }}
            }}

            function dispatchEnter(target) {{
                if (!target) return false;
                try {{
                    var down = new KeyboardEvent('keydown', {{ bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13 }});
                    var press = new KeyboardEvent('keypress', {{ bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13 }});
                    var up = new KeyboardEvent('keyup', {{ bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13, which: 13 }});
                    target.dispatchEvent(down);
                    target.dispatchEvent(press);
                    target.dispatchEvent(up);
                    return true;
                }} catch (e) {{
                    return false;
                }}
            }}

            function clickSend(composer) {{
                // 微信小店只使用Enter发送，简化逻辑避免重复
                if (!composer) return false;

                try {{
                    composer.focus();
                    // 只按一次Enter键，避免重复触发
                    var enterEvent = new KeyboardEvent('keydown', {{
                        bubbles: true,
                        cancelable: true,
                        key: 'Enter',
                        code: 'Enter',
                        keyCode: 13,
                        which: 13
                    }});
                    composer.dispatchEvent(enterEvent);
                    return true;
                }} catch (e) {{
                    return false;
                }}
            }}

            function findAndClickAcceptButtons() {{
                // 有些会话首次需要"接待/开始接待/继续会话/回复"等操作才允许发送
                var keywords = ['接待', '开始接待', '继续会话', '继续接待', '进入会话', '回复', '开始回复'];
                var btns = Array.from(document.querySelectorAll('button, [role="button"]'))
                    .filter(function(b) {{ return isVisible(b); }});
                for (var i = 0; i < btns.length; i++) {{
                    var b = btns[i];
                    var t = safeText(b);
                    var aria = (b.getAttribute && b.getAttribute('aria-label') || '').trim();
                    var txt = (t + ' ' + aria).trim();
                    if (!txt) continue;
                    for (var k = 0; k < keywords.length; k++) {{
                        if (txt.indexOf(keywords[k]) !== -1) {{
                            try {{ b.click(); return txt; }} catch (e) {{}}
                        }}
                    }}
                }}
                return null;
            }}

            function composerText(el) {{
                if (!el) return '';
                try {{
                    if (el.isContentEditable) return (el.innerText || '').trim();
                    if (typeof el.value === 'string') return (el.value || '').trim();
                }} catch (e) {{}}
                return '';
            }}

            // ===== 改进的用户名抓取 =====
            function getChatUserName() {{
                var result = {{ method: null, name: null, candidates: [] }};

                // 过滤词 - 排除按钮和状态文字
                var filterWords = ['转接', '结束', '接待', '开始', '继续', '回复', '进入',
                                   '用户超时', '客服已结束', '你已超过', '未回复', '会话已结束',
                                   '两天内仍可再次联系', '昨天', '今天', '星期一', '星期二',
                                   '星期三', '星期四', '星期五', '星期六', '星期日', '会话'];
                function isValidName(t) {{
                    if (!t || t.length < 2 || t.length > 30) return false;
                    for (var f = 0; f < filterWords.length; f++) {{
                        if (t.indexOf(filterWords[f]) !== -1) return false;
                    }}
                    return true;
                }}

                // 方法1: 优先从当前选中的会话列表项获取用户名
                var activeSelectors = ['.selected', '[class*="active"]', '[class*="current"]', '[aria-selected="true"]'];
                var bestCandidate = null;
                var bestScore = 0;
                
                for (var m = 0; m < activeSelectors.length; m++) {{
                    var items = document.querySelectorAll(activeSelectors[m]);
                    for (var n = 0; n < items.length; n++) {{
                        var item = items[n];
                        if (!isVisible(item)) continue;
                        // 确保是会话列表中的项（靠左）
                        var r = item.getBoundingClientRect();
                        if (r.left > 200) continue;
                        
                        // 尝试从子元素找名字
                        var nameEl = item.querySelector('.name, .nickname, [class*="name"], [class*="title"]');
                        var t = nameEl ? safeText(nameEl) : safeText(item);
                        
                        // 先过滤掉通用词汇，然后再进行有效性检查
                        if (t === '会话' || t === '全部' || t === '当前会话') {{
                            console.log('[DEBUG] 过滤掉通用词汇:', t);
                            continue;
                        }}
                        
                        if (isValidName(t)) {{
                            // 计算优先级分数
                            var score = 0;
                            if (activeSelectors[m] === '.selected') score += 100;
                            else if (activeSelectors[m] === '[class*="current"]') score += 90;
                            else if (activeSelectors[m] === '[class*="active"]') score += 80;
                            else if (activeSelectors[m] === '[aria-selected="true"]') score += 70;
                            
                            // 位置越靠下（在会话列表中越靠后）分数越高
                            score += Math.floor(r.top / 10);
                            
                            console.log('[DEBUG] 找到有效用户名:', t, '选择器:', activeSelectors[m], '分数:', score, '位置:', r.top);
                            
                            result.candidates.push({{ 
                                source: 'activeItem:' + activeSelectors[m], 
                                text: t, 
                                priority: 1,
                                score: score,
                                position: {{top: r.top, left: r.left}}
                            }});
                            
                            if (score > bestScore) {{
                                bestScore = score;
                                bestCandidate = {{
                                    name: t,
                                    method: 'activeItem:' + activeSelectors[m],
                                    score: score
                                }};
                            }}
                        }} else {{
                            console.log('[DEBUG] 用户名未通过有效性检查:', t);
                        }}
                    }}
                }}
                
                // 使用最高分数的候选
                if (bestCandidate) {{
                    result.name = bestCandidate.name;
                    result.method = bestCandidate.method;
                    console.log('[DEBUG] 从选中项获取用户名:', result.name, '分数:', bestCandidate.score);
                    return result;
                }}

                // 方法2: 从页面右侧顶部区域获取用户名（当前聊天窗口的标题）
                var currentChatArea = getMainChatArea();
                if (currentChatArea) {{
                    var chatRect = currentChatArea.getBoundingClientRect();
                    var centerX = chatRect.left + chatRect.width * 0.5;
                    
                    // 在聊天区域上方查找用户名
                    var wxSelectors = [
                        '.nickname', '.username', '.user-name', '.name',
                        '[class*="nickname"]', '[class*="user-name"]', '[class*="userName"]',
                        '[class*="chat-user"]', '[class*="session-title"]', '[class*="customer-name"]'
                    ];

                    for (var i = 0; i < wxSelectors.length; i++) {{
                        var els = document.querySelectorAll(wxSelectors[i]);
                        for (var j = 0; j < els.length; j++) {{
                            var el = els[j];
                            if (!isVisible(el)) continue;
                            var r = el.getBoundingClientRect();
                            
                            // 限制在页面右侧区域且在当前聊天区域内
                            if (r.left < 300 || r.top > 150) continue;
                            // 确保用户名在当前聊天区域的水平范围内
                            if (r.left < chatRect.left - 50 || r.left > chatRect.left + chatRect.width + 50) continue;
                            
                            var t = safeText(el);
                            if (isValidName(t)) {{
                                result.candidates.push({{ source: 'selector:' + wxSelectors[i], text: t, priority: 2 }});
                                if (!result.name) {{
                                    result.name = t;
                                    result.method = wxSelectors[i];
                                }}
                            }}
                        }}
                    }}
                }}

                // 方法3: 从标题标签获取
                var headers = document.querySelectorAll('h1,h2,h3,h4');
                for (var k = 0; k < headers.length; k++) {{
                    var h = headers[k];
                    if (!isVisible(h)) continue;
                    var r = h.getBoundingClientRect();
                    if (r.left < 300 || r.top > 150) continue;
                    
                    var t = safeText(h);
                    if (isValidName(t)) {{
                        result.candidates.push({{ source: 'header', text: t, priority: 3 }});
                        if (!result.name) {{
                            result.name = t;
                            result.method = 'header';
                        }}
                    }}
                }}

                console.log('[DEBUG] 最终用户名:', result.name, '方法:', result.method);
                return result;
            }}

            function getMainChatArea() {{
                // 更精确的聊天区域识别逻辑
                var candidates = [];
                
                // 方法1: 查找包含实际消息内容的聊天区域
                var allSelectors = ['.chat-wrap', '.chat-page', '.chat-area', '.message-list'];
                for (var s = 0; s < allSelectors.length; s++) {{
                    var selector = allSelectors[s];
                    var elements = document.querySelectorAll(selector);
                    for (var i = 0; i < elements.length; i++) {{
                        var el = elements[i];
                        if (!isVisible(el)) continue;
                        var rect = el.getBoundingClientRect();
                        
                        // 基本位置和大小检查
                        if (rect.left < 300 || rect.width < 400 || rect.height < 300) continue;
                        
                        // 检查是否包含真实的消息内容
                        var hasMessages = false;
                        var messageCount = 0;
                        var recentMessageCount = 0; // 最近的消息数量
                        
                        // 查找该区域内是否有用户消息（左侧）和客服消息（右侧）
                        var centerX = rect.left + rect.width * 0.5;
                        var textElements = el.querySelectorAll('*');
                        var currentTime = Date.now();
                        
                        for (var j = 0; j < Math.min(textElements.length, 200); j++) {{
                            var textEl = textElements[j];
                            if (!isVisible(textEl)) continue;
                            var text = safeText(textEl);
                            if (!text || text.length < 2) continue;
                            
                            var elRect = textEl.getBoundingClientRect();
                            if (elRect.top < rect.top + 20) continue;
                            
                            // 判断是否为消息内容
                            var isUserMsg = elRect.right < centerX - 30;
                            var isReplyMsg = elRect.left > centerX + 30;
                            
                            if (isUserMsg || isReplyMsg) {{
                                messageCount++;
                                // 检查是否为最近的消息（在聊天区域下半部分）
                                if (elRect.top > rect.top + rect.height * 0.6) {{
                                    recentMessageCount++;
                                }}
                                if (messageCount >= 5) {{
                                    hasMessages = true;
                                    break;
                                }}
                            }}
                        }}
                        
                        if (hasMessages) {{
                            candidates.push({{
                                element: el,
                                selector: selector,
                                index: i,
                                rect: rect,
                                area: rect.width * rect.height,
                                messageCount: messageCount,
                                recentMessageCount: recentMessageCount,
                                score: messageCount + recentMessageCount * 2 // 最近消息权重更高
                            }});
                        }}
                    }}
                }}
                
                // 选择分数最高的聊天区域（优先考虑最近消息）
                if (candidates.length > 0) {{
                    candidates.sort(function(a, b) {{ return b.score - a.score; }});
                    console.log('[DEBUG] 选择的聊天区域:', candidates[0].selector, 
                               '消息数:', candidates[0].messageCount, 
                               '最近消息:', candidates[0].recentMessageCount,
                               '分数:', candidates[0].score);
                    return candidates[0].element;
                }}
                
                // 兜底方法：如果没找到，使用原来的逻辑
                console.log('[DEBUG] 未找到有效的聊天区域，使用兜底方法');
                var divs = Array.from(document.querySelectorAll('div'));
                var best = null;
                var bestArea = 0;
                for (var j = 0; j < divs.length; j++) {{
                    var el = divs[j];
                    if (!isVisible(el)) continue;
                    var r = el.getBoundingClientRect();
                    if (!r) continue;
                    if (r.left < 300) continue;
                    if (r.width < 400 || r.height < 300) continue;
                    if (el.querySelector && (el.querySelector('textarea') || el.querySelector('input') || el.querySelector('[contenteditable="true"]'))) {{
                        continue;
                    }}
                    var area = r.width * r.height;
                    if (area > bestArea) {{
                        bestArea = area;
                        best = el;
                    }}
                }}
                return best;
            }}

            // 辅助函数：过滤时间和系统提示
            function isValidMessage(text) {{
                if (!text) return false;
                // 长度检查：允许纯数字手机号（11位），过滤短数字（未读数）
                if (text.length < 2) return false;
                if (text.length > 500) return false;
                // 纯数字且长度小于5，认为是未读数，过滤掉
                if (/^\d+$/.test(text) && text.length < 5) return false;
                // 过滤时间
                if (/^(星期[一二三四五六日]|\d{1,2}:\d{2}|\d{4}-\d{2}-\d{2})$/.test(text)) return false;
                // 过滤系统提示
                if (/(用户超时未回|客服已结束|你已超.*未回复|会话已结束|两天内仍可再次联系)/.test(text)) return false;
                return true;
            }}

            function getRecentIncomingMessages(maxN) {{
                maxN = Math.max(1, Math.min(20, parseInt(maxN || 5, 10)));
                var chat = getMainChatArea();
                if (!chat) return [];
                var cr = chat.getBoundingClientRect();
                if (!cr) return [];
                var centerX = cr.left + cr.width * 0.5;

                // 获取所有文本节点
                var allTexts = [];
                var walker = document.createTreeWalker(chat, NodeFilter.SHOW_TEXT, null, false);
                var textNode;
                while (textNode = walker.nextNode()) {{
                    var parent = textNode.parentElement;
                    if (!parent || !isVisible(parent)) continue;

                    var text = textNode.textContent.trim();
                    if (!isValidMessage(text)) continue;

                    var r = parent.getBoundingClientRect();
                    if (r.top < cr.top + 20) continue;

                    // 只取左侧（用户）消息
                    if (r.right < centerX - 30) {{
                        allTexts.push({{ text: text, rect: r }});
                    }}
                }}

                // 合并相邻文本节点
                allTexts.sort(function(a, b) {{ return a.rect.top - b.rect.top; }});
                var merged = [];
                var current = null;

                for (var i = 0; i < allTexts.length; i++) {{
                    var item = allTexts[i];
                    // 跳过纯数字（可能是未读数），但保留手机号（长度>5的数字）
                    if (/^\d+$/.test(item.text) && item.text.length < 5) continue;
                    if (!current) {{
                        current = {{ text: item.text, rect: item.rect }};
                    }} else {{
                        var sameLine = Math.abs(item.rect.top - current.rect.top) < 25;
                        var closeH = Math.abs(item.rect.left - current.rect.left) < 100;
                        if (sameLine && closeH) {{
                            current.text += " " + item.text;
                        }} else {{
                            merged.push(current);
                            current = {{ text: item.text, rect: item.rect }};
                        }}
                    }}
                }}
                if (current) merged.push(current);

                // 返回最后 N 条
                return merged.slice(-maxN).map(function(m) {{ return {{ text: m.text, time: '' }}; }});
            }}

            function getLastIncomingMessage() {{
                var messages = getRecentIncomingMessages(1);
                if (messages.length === 0) return null;
                return {{ text: messages[0].text, time: '' }};
            }}

            function getSessionLockKey(uname, msg) {{
                // 用用户名+消息前30字符作为会话锁key，防止同一会话并发
                return hashStr((uname || '') + '|' + (msg || '').slice(0, 30));
            }}

            var result = {{ ts: nowTs(), found: 0, processed: 0, skipped: 0, errors: [], debug: {{}} }};
            try {{
                var repliedMsgStore = getRepliedMsgStore();
                var unreadEls = findUnreadCandidates();
                result.found = unreadEls.length;
                if (!unreadEls.length) {{
                    window.__ai_global_busy = false;
                    return result;
                }}

                // 严格去重检查：在点击前先检查是否已经回复过
                // 只取最后一个未读消息元素
                var el = unreadEls[unreadEls.length - 1];
                if (!el) {{
                    window.__ai_global_busy = false;
                    return result;
                }}

                // 预先获取用户信息和消息内容进行去重检查
                var currentUrl = window.location.href;
                var preCheckKey = hashStr(currentUrl + '_' + (el.getAttribute('data-id') || ''));

                // 检查最近5秒内是否处理过相同的未读元素
                var lastProcessed = localStorage.getItem('__ai_last_processed__');
                if (lastProcessed) {{
                    try {{
                        var lastData = JSON.parse(lastProcessed);
                        if (lastData.key === preCheckKey && (Date.now() - lastData.ts) < 5000) {{
                            result.skipped += 1;
                            result.debug.recentlyProcessed = true;
                            window.__ai_global_busy = false;
                            return result;
                        }}
                    }} catch (e) {{}}
                }}

                // 标记当前正在处理的元素
                localStorage.setItem('__ai_last_processed__', JSON.stringify({{ key: preCheckKey, ts: Date.now() }}));

                var skey = sessionKeyFromElement(el);

                // 去重：同一个元素 60 秒内只回一次
                var repliedAt = el.getAttribute('data-ai-replied-at');
                if (repliedAt) {{
                    var prev = Date.parse(repliedAt);
                    if (!isNaN(prev) && (Date.now() - prev) < 60000) {{
                        result.skipped += 1;
                        result.debug.recentlyReplied = true;
                        window.__ai_global_busy = false;
                        return result;
                    }}
                }}

                // 点击进入会话
                el.click();
                await sleep(800); // 增加等待时间确保页面完全加载

                // 尝试处理"首次接待/开始回复"等门槛
                var accepted = findAndClickAcceptButtons();
                if (accepted) {{
                    result.debug.acceptBtn = accepted;
                    await sleep(600);
                }}

                // 根本去重：抓取 用户名 + 用户最后一条消息 + 时间
                // 使用新的用户名抓取方法
                var userNameResult = getChatUserName();
                var uname = userNameResult.name || '';
                result.debug.userNameDebug = userNameResult;

                var lastIncoming = getLastIncomingMessage();
                if (!lastIncoming || !lastIncoming.text) {{
                    result.errors.push('抓取用户最后一条消息失败（无法做去重，已跳过发送）');
                    window.__ai_global_busy = false;
                    return result;
                }}

                // 返回给 Python：当前会话用户名 + 最近几条用户消息（以及最新一条）
                result.chat = {{
                    user: uname,
                    userNameMethod: userNameResult.method,
                    userNameCandidates: userNameResult.candidates.slice(0, 5),
                    messages: getRecentIncomingMessages(5),
                    last: {{ time: lastIncoming.time || '', text: lastIncoming.text || '' }}
                }};
                var msgKey = hashStr(uname + '|' + lastIncoming.time + '|' + lastIncoming.text);
                var sessionLockKey = getSessionLockKey(uname, lastIncoming.text);
                result.chat.msgKey = msgKey;
                result.chat.sessionLockKey = sessionLockKey;

                // 会话级锁：防止同一会话并发
                if (window.__ai_session_lock && window.__ai_session_lock[sessionLockKey]) {{
                    result.skipped += 1;
                    result.debug.sessionLocked = true;
                    window.__ai_global_busy = false;
                    return result;
                }}
                if (!window.__ai_session_lock) window.__ai_session_lock = {{}};
                window.__ai_session_lock[sessionLockKey] = true;

                // 已回复过这条"用户消息"则绝不再发
                var existing = repliedMsgStore[msgKey];
                if (existing) {{
                    result.skipped += 1;
                    result.debug.alreadyReplied = true;
                    delete window.__ai_session_lock[sessionLockKey];
                    window.__ai_global_busy = false;
                    return result;
                }}

                // 先占位 pending，防止并发/卡顿导致重复发送
                repliedMsgStore[msgKey] = {{ at: nowTs(), user: uname, time: lastIncoming.time, text: lastIncoming.text, status: 'pending' }};
                setRepliedMsgStore(repliedMsgStore);

                result.debug.user = uname;
                result.debug.lastUserMsg = lastIncoming.text;
                result.debug.lastUserTime = lastIncoming.time;
                result.debug.msgKey = msgKey;
                result.debug.existing = existing;
                result.debug.sessionLockKey = sessionLockKey;

                result.processed += 1;
                window.__ai_global_busy = false;
                return result;
            }} catch (e) {{
                result.errors.push(String(e && e.message ? e.message : e));
                // 确保在异常情况下也释放全局锁
                window.__ai_global_busy = false;
                return result;
            }}
        }})();'''

        def _on_js_done(res):
            self._last_poll_result = res
            self._poll_inflight = False
            if not res:
                self.log("[WARN] JS 未返回结果（可能页面未加载/被重定向/脚本被拦截）")
                return

            chat = res.get("chat") if isinstance(res, dict) else None
            if isinstance(chat, dict) and (not self._reply_worker_inflight):
                self._reply_worker_inflight = True
                threading.Thread(target=self._handle_ai_reply, args=(chat,), daemon=True).start()

            if isinstance(chat, dict):
                user = chat.get("user") or ""
                messages = chat.get("messages") or []
                last = chat.get("last") or {}

                # 记录详细的调试信息
                userNameMethod = chat.get("userNameMethod")
                candidates = chat.get("userNameCandidates", [])

                self.log("=" * 40)
                self.log("[CHAT] 抓取结果")
                if user:
                    self.log(f"[CHAT] ✅ 用户名: {user} (方法: {userNameMethod})")
                else:
                    self.log("[CHAT] ❌ 未抓取到用户名")
                    if candidates:
                        self.log(f"[CHAT] 候选用户名 ({len(candidates)}个):")
                        for c in candidates[:5]:
                            self.log(f"       - [{c.get('source')}] {c.get('text', '')}")

                if isinstance(last, dict) and last.get("text"):
                    self.log(f"[CHAT] ✅ 最新消息: {last.get('text', '')[:50]}")
                else:
                    self.log("[CHAT] ❌ 未抓取到最新消息")

                self.log("=" * 40)

            found = res.get("found")
            processed = res.get("processed")
            errors = res.get("errors", [])
            ts = res.get("ts")

            status_emoji = "✅" if processed and processed > 0 else "⏭️" if res.get("skipped") else "❌"
            self.log(f"{status_emoji} [AI] {ts} found={found} processed={processed} errors={errors}")

        def _on_js_error(_):
            self._poll_inflight = False

        self.browser.page().runJavaScript(js_code, _on_js_done)

    def _handle_ai_reply(self, chat: dict):
        try:
            user = str(chat.get("user") or "")
            msgs = chat.get("messages") or []
            user_msgs = []
            if isinstance(msgs, list):
                for m in msgs:
                    if isinstance(m, dict) and m.get("text"):
                        user_msgs.append(str(m.get("text")))

            last = chat.get("last") or {}
            last_text = str(last.get("text") or "")
            msg_key = str(chat.get("msgKey") or "")
            session_lock_key = str(chat.get("sessionLockKey") or "")

            if not last_text:
                raise RuntimeError("未抓取到客户消息")

            kb_hit = self._kb_best_match(last_text)
            if kb_hit:
                reply = str(kb_hit.get("content", "")).strip()
                if user and reply and ("?" not in reply) and ("？" not in reply):
                    reply = reply + "\n\n请问您更关注的是材质、尺寸还是佩戴舒适度？我可以按您的情况推荐。"
                self.log(f"[KB] 命中知识库：{kb_hit.get('name','')}")
            else:
                model_name = self.model_combo.currentText() if hasattr(self, 'model_combo') else "ChatGPT"
                reply = self._call_llm(model_name, user_msgs, user)
                self.log(f"[LLM] 使用模型：{model_name}")

            if not reply:
                raise RuntimeError("回复内容为空")

            js_send = self._send_reply_js(reply, msg_key, session_lock_key)

            def on_sent(res):
                if isinstance(res, dict) and res.get("sent"):
                    self.log(f"✅ [AI] 已发送回复给 {user or '客户'}")
                else:
                    err = None
                    if isinstance(res, dict):
                        err = res.get("error")
                    self.log(f"❌ [AI] 发送失败: {err or res}")
                    js_clear = self._clear_pending_js(msg_key, session_lock_key)
                    self.browser.page().runJavaScript(js_clear)
                self._reply_worker_inflight = False

            self.browser.page().runJavaScript(js_send, on_sent)

        except Exception as e:
            self.log(f"❌ [AI] 回复流程失败：{e}")
            msg_key = str(chat.get("msgKey") or "")
            session_lock_key = str(chat.get("sessionLockKey") or "")
            if msg_key or session_lock_key:
                js_clear = self._clear_pending_js(msg_key, session_lock_key)
                self.browser.page().runJavaScript(js_clear)
            self._reply_worker_inflight = False

    def refresh_browser(self):
        """刷新浏览器页面，用于解决扫码错误时无法再次扫码的问题"""
        self.status_label.setText("状态：正在刷新页面...")
        self.log("[INFO] 刷新页面")

        # 重新加载当前页面
        self.browser.reload()

        # 恢复状态显示
        current_status = self.status_label.text()
        if "正在刷新页面" in current_status:
            self.status_label.setText("状态：未启动")


if __name__ == "__main__":
    app = QApplication(sys.argv)

    try:
        signal.signal(signal.SIGINT, lambda *_: app.quit())
    except Exception:
        pass

    window = AICustomerServiceApp()
    window.show()
    sys.exit(app.exec())
