"""
模型配置标签页
用于配置各个AI模型的API参数
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QMessageBox, QScrollArea,
    QFrame, QGridLayout
)
from PySide6.QtCore import Signal, Qt

from ..data.config_manager import ConfigManager


class ModelConfigTab(QWidget):
    """模型配置标签页"""

    config_saved = Signal()
    log_message = Signal(str)
    current_model_changed = Signal(str)

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._model_inputs = {}
        self._model_test_buttons = {}
        self._model_cards = {}
        self._model_status_labels = {}
        self._model_switch_buttons = {}
        self._model_icons = {}
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # --- Header ---
        header_layout = QHBoxLayout()
        title_wrap = QVBoxLayout()
        title = QLabel("AI 模型配置")
        title.setObjectName("PageTitle")
        title_wrap.addWidget(title)
        subtitle = QLabel("管理大模型 API 密钥与端点，支持多引擎切换")
        subtitle.setObjectName("PageSubtitle")
        title_wrap.addWidget(subtitle)
        header_layout.addLayout(title_wrap)
        header_layout.addStretch()

        self.save_btn = QPushButton("保存全局配置")
        self.save_btn.setObjectName("Primary")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.clicked.connect(self._on_save)
        header_layout.addWidget(self.save_btn)
        
        layout.addLayout(header_layout)

        # --- Scroll Area ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0) # No margin inside scroll
        scroll_layout.setSpacing(16)

        models = ["ChatGPT", "Gemini", "阿里千问", "DeepSeek", "豆包", "kimi"]
        # Use grid for cards? Or list. List is safer for width.
        # But prototype uses list.
        
        for model_name in models:
            card = self._create_model_card(model_name)
            scroll_layout.addWidget(card)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

    def _create_model_card(self, model_name: str) -> QFrame:
        """创建模型配置卡片"""
        card = QFrame()
        card.setObjectName("ModelCard")
        card.setProperty("active", "false")
        
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(20)

        # Top Row: Icon + Name + Status + Switch
        top_layout = QHBoxLayout()
        
        # Icon placeholder (just a colored box for now)
        icon_box = QLabel(model_name[0])
        icon_box.setFixedSize(40, 40)
        icon_box.setAlignment(Qt.AlignCenter)
        icon_box.setStyleSheet("background: #f1f5f9; color: #64748b; border-radius: 12px; font-weight: bold; font-size: 18px;")
        self._model_icons[model_name] = icon_box
        top_layout.addWidget(icon_box)

        name_wrap = QVBoxLayout()
        name_wrap.setSpacing(4)
        name_label = QLabel(model_name)
        name_label.setObjectName("ModelName")
        name_wrap.addWidget(name_label)
        
        status_label = QLabel("待命")
        status_label.setObjectName("ModelStatus")
        self._model_status_labels[model_name] = status_label
        name_wrap.addWidget(status_label)
        top_layout.addLayout(name_wrap)

        top_layout.addStretch()

        switch_btn = QPushButton("切换到此模型")
        switch_btn.setObjectName("Ghost")
        switch_btn.setCursor(Qt.PointingHandCursor)
        switch_btn.clicked.connect(lambda checked=False, name=model_name: self._on_switch_model(name))
        self._model_switch_buttons[model_name] = switch_btn
        top_layout.addWidget(switch_btn)

        card_layout.addLayout(top_layout)

        # Fields Grid
        fields_layout = QGridLayout()
        fields_layout.setHorizontalSpacing(24)
        fields_layout.setVerticalSpacing(12)

        # Base URL
        base_label = QLabel("API 地址 (Base URL)")
        base_label.setObjectName("FieldLabel")
        fields_layout.addWidget(base_label, 0, 0)
        
        base_url_input = QLineEdit()
        base_url_input.setPlaceholderText("https://api.example.com/v1")
        fields_layout.addWidget(base_url_input, 1, 0)

        # Model ID
        model_label = QLabel("模型名称 (Model ID)")
        model_label.setObjectName("FieldLabel")
        fields_layout.addWidget(model_label, 0, 1)

        model_input = QLineEdit()
        model_input.setPlaceholderText("model-name")
        fields_layout.addWidget(model_input, 1, 1)

        # API Key
        api_label = QLabel("API 密钥 (API Key)")
        api_label.setObjectName("FieldLabel")
        fields_layout.addWidget(api_label, 2, 0, 1, 2) # Span 2 columns

        api_key_input = QLineEdit()
        api_key_input.setPlaceholderText("sk-xxxxxxxxxxxxxxxx")
        api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        fields_layout.addWidget(api_key_input, 3, 0, 1, 2)

        card_layout.addLayout(fields_layout)

        # Actions
        actions_layout = QHBoxLayout()
        test_btn = QPushButton("验证连接")
        test_btn.setObjectName("Secondary")
        test_btn.setCursor(Qt.PointingHandCursor)
        test_btn.clicked.connect(lambda checked=False, name=model_name: self._on_test_model(name))
        actions_layout.addWidget(test_btn)
        
        actions_layout.addStretch()
        
        wiki_btn = QPushButton("官方文档 ↗")
        wiki_btn.setObjectName("Ghost")
        wiki_btn.setCursor(Qt.PointingHandCursor)
        actions_layout.addWidget(wiki_btn)
        
        card_layout.addLayout(actions_layout)

        self._model_inputs[model_name] = {
            "base_url": base_url_input,
            "api_key": api_key_input,
            "model": model_input
        }
        self._model_test_buttons[model_name] = test_btn
        self._model_cards[model_name] = card

        return card

    def _load_settings(self):
        """加载配置"""
        for model_name, inputs in self._model_inputs.items():
            config = self.config_manager.get_model_config(model_name)
            inputs["base_url"].setText(config.get("base_url", ""))
            inputs["api_key"].setText(config.get("api_key", ""))
            inputs["model"].setText(config.get("model", ""))
        self._refresh_active_state()

    def set_current_model(self, model_name: str):
        """外部设置当前模型"""
        self.config_manager.set_current_model(model_name)
        self._refresh_active_state()

    def _on_switch_model(self, model_name: str):
        """切换当前模型"""
        self.config_manager.set_current_model(model_name)
        self.current_model_changed.emit(model_name)
        self._refresh_active_state()

    def _refresh_active_state(self):
        """刷新卡片的激活状态"""
        current = self.config_manager.get_current_model()
        for model_name, card in self._model_cards.items():
            is_active = model_name == current
            card.setProperty("active", "true" if is_active else "false")
            card.style().unpolish(card)
            card.style().polish(card)

            # Update Labels & Buttons
            status_label = self._model_status_labels.get(model_name)
            if status_label:
                status_label.setText("当前使用模型" if is_active else "待命")
                status_label.setStyleSheet(
                    "color: #2563eb;" if is_active else "color: #94a3b8;"
                )

            switch_btn = self._model_switch_buttons.get(model_name)
            if switch_btn:
                switch_btn.setVisible(not is_active)
            
            # Icon Color
            icon_box = self._model_icons.get(model_name)
            if icon_box:
                icon_box.setStyleSheet(
                    f"background: {'#3b82f6' if is_active else '#f1f5f9'}; "
                    f"color: {'#ffffff' if is_active else '#64748b'}; "
                    "border-radius: 12px; font-weight: bold; font-size: 18px;"
                )

    def _on_save(self):
        """保存配置"""
        for model_name, inputs in self._model_inputs.items():
            config = {
                "base_url": inputs["base_url"].text().strip(),
                "api_key": inputs["api_key"].text().strip(),
                "model": inputs["model"].text().strip()
            }
            self.config_manager.set_model_config(model_name, config)

        if self.config_manager.save():
            QMessageBox.information(self, "保存成功", "配置已保存")
            self.config_saved.emit()
        else:
            QMessageBox.warning(self, "保存失败", "配置保存失败")

    def _on_test_model(self, model_name: str):
        """测试指定模型连接"""
        inputs = self._model_inputs.get(model_name, {})
        config = {
            "base_url": inputs.get("base_url", QLineEdit()).text().strip(),
            "api_key": inputs.get("api_key", QLineEdit()).text().strip(),
            "model": inputs.get("model", QLineEdit()).text().strip()
        }

        if not config["api_key"]:
            QMessageBox.warning(self, "测试失败", f"{model_name} 的API密钥未配置")
            return

        if not config["base_url"]:
            QMessageBox.warning(self, "测试失败", f"{model_name} 的API地址未配置")
            return

        test_btn = self._model_test_buttons.get(model_name)
        if test_btn:
            test_btn.setEnabled(False)
            test_btn.setText("🧪 测试中...")

        from ..services.llm_service import LLMService

        class TempConfig:
            def get_current_model(self): return model_name
            def get_model_config(self, name): return config

        temp_service = LLMService(TempConfig())

        def test():
            success, message = temp_service.test_connection(model_name)

            if test_btn:
                test_btn.setEnabled(True)
                test_btn.setText("验证连接")

            if success:
                QMessageBox.information(self, "测试成功", message)
                self.log_message.emit(f"✅ {model_name} 测试成功: {message}")
            else:
                QMessageBox.warning(self, "测试失败", message)
                self.log_message.emit(f"❌ {model_name} 测试失败: {message}")

        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, test)
