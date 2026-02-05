"""
模型配置标签页
用于配置各个AI模型的API参数
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFormLayout, QComboBox,
    QMessageBox, QGroupBox, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal

from ..data.config_manager import ConfigManager


class ModelConfigTab(QWidget):
    """模型配置标签页"""

    config_saved = Signal()
    log_message = Signal(str)

    def __init__(self, config_manager: ConfigManager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self._model_inputs = {}
        self._model_test_buttons = {}
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # 标题
        title = QLabel("AI 模型配置")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        # 当前模型选择
        current_layout = QHBoxLayout()
        current_label = QLabel("当前使用模型:")
        current_label.setObjectName("MutedText")
        current_layout.addWidget(current_label)

        self.current_model_combo = QComboBox()
        self.current_model_combo.addItems([
            "ChatGPT", "Gemini", "阿里千问", "DeepSeek", "豆包", "kimi"
        ])
        self.current_model_combo.currentTextChanged.connect(self._on_current_model_changed)
        current_layout.addWidget(self.current_model_combo)

        current_layout.addStretch()
        layout.addLayout(current_layout)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("background: #e7ddcd; max-height: 1px;")
        layout.addWidget(line)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(16)

        # 为每个模型创建配置组
        models = ["ChatGPT", "Gemini", "阿里千问", "DeepSeek", "豆包", "kimi"]
        for model_name in models:
            group = self._create_model_group(model_name)
            scroll_layout.addWidget(group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        # 保存按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.save_btn = QPushButton("💾 保存配置")
        self.save_btn.setObjectName("Primary")
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)

        layout.addLayout(btn_layout)

    def _create_model_group(self, model_name: str) -> QGroupBox:
        """创建模型配置组"""
        group = QGroupBox(model_name)
        group.setStyleSheet("""
            QGroupBox {
                color: #2a231b;
                font-weight: 600;
                background: #f2e9da;
                border: 1px solid rgba(0,0,0,0.10);
                border-radius: 12px;
                margin-top: 12px;
                padding-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 8px;
                background: #f6f2ea;
            }
        """)

        form_layout = QFormLayout(group)
        form_layout.setSpacing(12)

        # Base URL
        base_url_input = QLineEdit()
        base_url_input.setPlaceholderText("https://api.example.com/v1")
        form_layout.addRow("API地址:", base_url_input)

        # API Key
        api_key_input = QLineEdit()
        api_key_input.setPlaceholderText("sk-xxxxxxxxxxxxxxxx")
        api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow("API密钥:", api_key_input)

        # Model
        model_input = QLineEdit()
        model_input.setPlaceholderText("model-name")
        form_layout.addRow("模型名称:", model_input)

        # 测试按钮
        test_btn = QPushButton("🧪 测试连接")
        test_btn.setObjectName("Secondary")
        test_btn.clicked.connect(lambda checked=False, name=model_name: self._on_test_model(name))
        form_layout.addRow("连接测试:", test_btn)

        # 保存引用
        self._model_inputs[model_name] = {
            "base_url": base_url_input,
            "api_key": api_key_input,
            "model": model_input
        }
        self._model_test_buttons[model_name] = test_btn

        return group

    def _load_settings(self):
        """加载配置"""
        # 当前模型
        current = self.config_manager.get_current_model()
        index = self.current_model_combo.findText(current)
        if index >= 0:
            self.current_model_combo.setCurrentIndex(index)

        # 各模型配置
        for model_name, inputs in self._model_inputs.items():
            config = self.config_manager.get_model_config(model_name)
            inputs["base_url"].setText(config.get("base_url", ""))
            inputs["api_key"].setText(config.get("api_key", ""))
            inputs["model"].setText(config.get("model", ""))

    def _on_current_model_changed(self, model_name: str):
        """当前模型变更"""
        self.config_manager.set_current_model(model_name)

    def _on_save(self):
        """保存配置"""
        # 更新各模型配置
        for model_name, inputs in self._model_inputs.items():
            config = {
                "base_url": inputs["base_url"].text().strip(),
                "api_key": inputs["api_key"].text().strip(),
                "model": inputs["model"].text().strip()
            }
            self.config_manager.set_model_config(model_name, config)

        # 保存到文件
        if self.config_manager.save():
            QMessageBox.information(self, "保存成功", "配置已保存")
            self.config_saved.emit()
        else:
            QMessageBox.warning(self, "保存失败", "配置保存失败")

    def _on_test_model(self, model_name: str):
        """测试指定模型连接"""

        # 保存当前配置
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

        # 显示测试中
        test_btn = self._model_test_buttons.get(model_name)
        if test_btn:
            test_btn.setEnabled(False)
            test_btn.setText("🧪 测试中...")

        # 使用 LLMService 测试
        from ..services.llm_service import LLMService

        # 临时创建测试
        class TempConfig:
            def get_current_model(self): return model_name
            def get_model_config(self, name): return config

        temp_service = LLMService(TempConfig())

        def test():
            success, message = temp_service.test_connection(model_name)

            if test_btn:
                test_btn.setEnabled(True)
                test_btn.setText("🧪 测试连接")

            if success:
                QMessageBox.information(self, "测试成功", message)
                self.log_message.emit(f"✅ {model_name} 测试成功: {message}")
            else:
                QMessageBox.warning(self, "测试失败", message)
                self.log_message.emit(f"❌ {model_name} 测试失败: {message}")

        # 延迟执行
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, test)
