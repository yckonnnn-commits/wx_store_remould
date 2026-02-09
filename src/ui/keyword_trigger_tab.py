"""
关键词触发图片发送标签页
管理关键词触发规则，实现自动发送分类图片
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QDialog, QLineEdit, QComboBox, QCheckBox, QFrame
)
from PySide6.QtCore import Qt, Signal


class KeywordTriggerTab(QWidget):
    """关键词触发图片发送标签页"""
    
    log_message = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.config_file = Path("config/keyword_triggers.json")
        self.categories_file = Path("config/image_categories.json")
        self.triggers = []
        self.categories = ["联系方式", "店铺地址"]
        
        self._setup_ui()
        self._load_config()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)
        
        # 顶部标题与操作
        header = self._create_header()
        layout.addWidget(header)
        
        # 规则表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["关键词", "触发分类", "状态", "操作", "ID"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setColumnHidden(4, True)  # 隐藏ID列
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                gridline-color: #f1f5f9;
            }
            QTableWidget::item {
                padding: 12px 16px;
                border-bottom: 1px solid #f1f5f9;
            }
            QTableWidget::item:selected {
                background: #eff6ff;
                color: #1e40af;
            }
            QHeaderView::section {
                background: #f8fafc;
                padding: 12px 16px;
                border: none;
                border-bottom: 2px solid #e2e8f0;
                font-weight: 600;
                color: #475569;
            }
        """)
        layout.addWidget(self.table, 1)
        
        # 底部状态
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("MutedText")
        layout.addWidget(self.status_label)
    
    def _create_header(self):
        """创建顶部标题与操作区"""
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        
        title_wrap = QVBoxLayout()
        title = QLabel("关键词触发图片发送")
        title.setObjectName("PageTitle")
        title_wrap.addWidget(title)
        subtitle = QLabel("设置关键词规则，当用户消息匹配时自动发送对应分类的图片")
        subtitle.setObjectName("PageSubtitle")
        title_wrap.addWidget(subtitle)
        header_layout.addLayout(title_wrap)
        
        header_layout.addStretch()
        
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("Secondary")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._load_config)
        header_layout.addWidget(self.refresh_btn)
        
        self.add_btn = QPushButton("添加规则")
        self.add_btn.setObjectName("Primary")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self._add_trigger)
        header_layout.addWidget(self.add_btn)
        
        return header
    
    def _load_config(self):
        """加载配置"""
        try:
            # 加载分类
            if self.categories_file.exists():
                with open(self.categories_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.categories = data.get("categories", ["联系方式", "店铺地址"])
            
            # 加载触发规则
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.triggers = data.get("triggers", [])
            else:
                self.triggers = []
            
            self._refresh_table()
            self.status_label.setText(f"共 {len(self.triggers)} 条规则")
            
        except Exception as e:
            self.log_message.emit(f"❌ 加载配置失败: {str(e)}")
    
    def _save_config(self):
        """保存配置"""
        try:
            data = {
                "version": 1,
                "updated_at": datetime.now().isoformat(),
                "triggers": self.triggers
            }
            
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            self.log_message.emit("✅ 规则配置已保存")
            
        except Exception as e:
            self.log_message.emit(f"❌ 保存配置失败: {str(e)}")
    
    def _refresh_table(self):
        """刷新表格"""
        self.table.setRowCount(0)
        
        for trigger in self.triggers:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # 关键词
            keywords = ", ".join(trigger.get("keywords", []))
            self.table.setItem(row, 0, QTableWidgetItem(keywords))
            
            # 分类
            self.table.setItem(row, 1, QTableWidgetItem(trigger.get("category", "")))
            
            # 状态
            enabled = trigger.get("enabled", True)
            status_item = QTableWidgetItem("启用" if enabled else "禁用")
            status_item.setForeground(Qt.darkGreen if enabled else Qt.darkRed)
            self.table.setItem(row, 2, status_item)
            
            # 操作按钮
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 4, 4, 4)
            action_layout.setSpacing(8)
            
            edit_btn = QPushButton("编辑")
            edit_btn.setFixedSize(60, 28)
            edit_btn.setStyleSheet("background: #3b82f6; color: white; border-radius: 4px;")
            edit_btn.clicked.connect(lambda checked, t=trigger: self._edit_trigger(t))
            action_layout.addWidget(edit_btn)
            
            toggle_btn = QPushButton("禁用" if enabled else "启用")
            toggle_btn.setFixedSize(60, 28)
            toggle_btn.setStyleSheet("background: #6b7280; color: white; border-radius: 4px;")
            toggle_btn.clicked.connect(lambda checked, t=trigger: self._toggle_trigger(t))
            action_layout.addWidget(toggle_btn)
            
            delete_btn = QPushButton("删除")
            delete_btn.setFixedSize(60, 28)
            delete_btn.setStyleSheet("background: #ef4444; color: white; border-radius: 4px;")
            delete_btn.clicked.connect(lambda checked, t=trigger: self._delete_trigger(t))
            action_layout.addWidget(delete_btn)
            
            self.table.setCellWidget(row, 3, action_widget)
            
            # 隐藏ID
            self.table.setItem(row, 4, QTableWidgetItem(trigger.get("id", "")))
    
    def _add_trigger(self):
        """添加规则"""
        dialog = TriggerEditDialog(self.categories, parent=self)
        if dialog.exec() == QDialog.Accepted:
            trigger = dialog.get_trigger()
            trigger["id"] = str(uuid.uuid4())[:8]
            self.triggers.append(trigger)
            self._save_config()
            self._refresh_table()
            self.status_label.setText(f"共 {len(self.triggers)} 条规则")
    
    def _edit_trigger(self, trigger):
        """编辑规则"""
        dialog = TriggerEditDialog(self.categories, trigger, parent=self)
        if dialog.exec() == QDialog.Accepted:
            updated = dialog.get_trigger()
            # 更新触发器
            for i, t in enumerate(self.triggers):
                if t.get("id") == trigger.get("id"):
                    updated["id"] = trigger.get("id")
                    self.triggers[i] = updated
                    break
            self._save_config()
            self._refresh_table()
    
    def _toggle_trigger(self, trigger):
        """切换启用状态"""
        for t in self.triggers:
            if t.get("id") == trigger.get("id"):
                t["enabled"] = not t.get("enabled", True)
                break
        self._save_config()
        self._refresh_table()
    
    def _delete_trigger(self, trigger):
        """删除规则"""
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除这条规则吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.triggers = [t for t in self.triggers if t.get("id") != trigger.get("id")]
            self._save_config()
            self._refresh_table()
            self.status_label.setText(f"共 {len(self.triggers)} 条规则")
    
    def get_triggers(self):
        """获取所有启用的触发规则"""
        return [t for t in self.triggers if t.get("enabled", True)]


class TriggerEditDialog(QDialog):
    """规则编辑对话框"""
    
    def __init__(self, categories, trigger=None, parent=None):
        super().__init__(parent)
        self.categories = categories
        self.trigger = trigger or {}
        
        self.setWindowTitle("编辑规则" if trigger else "添加规则")
        self.setFixedSize(500, 300)
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        # 关键词输入
        keywords_label = QLabel("关键词（多个用逗号分隔）")
        keywords_label.setStyleSheet("font-weight: 600; color: #334155;")
        layout.addWidget(keywords_label)
        
        self.keywords_input = QLineEdit()
        self.keywords_input.setPlaceholderText("例如: 电话, 联系方式, 怎么联系")
        self.keywords_input.setText(", ".join(self.trigger.get("keywords", [])))
        self.keywords_input.setStyleSheet("""
            QLineEdit {
                padding: 10px 12px;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #3b82f6;
            }
        """)
        layout.addWidget(self.keywords_input)
        
        # 分类选择
        category_label = QLabel("触发分类")
        category_label.setStyleSheet("font-weight: 600; color: #334155;")
        layout.addWidget(category_label)
        
        self.category_combo = QComboBox()
        self.category_combo.addItems(self.categories)
        if self.trigger.get("category"):
            index = self.category_combo.findText(self.trigger.get("category"))
            if index >= 0:
                self.category_combo.setCurrentIndex(index)
        self.category_combo.setStyleSheet("""
            QComboBox {
                padding: 10px 12px;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                font-size: 14px;
            }
        """)
        layout.addWidget(self.category_combo)
        
        # 启用状态
        self.enabled_checkbox = QCheckBox("启用此规则")
        self.enabled_checkbox.setChecked(self.trigger.get("enabled", True))
        layout.addWidget(self.enabled_checkbox)
        
        layout.addStretch()
        
        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("Secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        save_btn = QPushButton("保存")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._save)
        btn_layout.addWidget(save_btn)
        
        layout.addLayout(btn_layout)
    
    def _save(self):
        """保存"""
        keywords_text = self.keywords_input.text().strip()
        if not keywords_text:
            QMessageBox.warning(self, "警告", "请输入关键词")
            return
        
        self.accept()
    
    def get_trigger(self):
        """获取规则数据"""
        keywords_text = self.keywords_input.text().strip()
        keywords = [k.strip() for k in keywords_text.replace("，", ",").split(",") if k.strip()]
        
        return {
            "keywords": keywords,
            "category": self.category_combo.currentText(),
            "enabled": self.enabled_checkbox.isChecked()
        }
