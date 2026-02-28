"""
知识库标签页
用于管理知识库条目
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QFileDialog,
    QDialog, QDialogButtonBox, QFormLayout, QTextEdit, QComboBox, QFrame
)
from PySide6.QtCore import Qt, Signal

from ..data.knowledge_repository import KnowledgeRepository, KnowledgeItem
import re


class KnowledgeEditDialog(QDialog):
    """知识库编辑对话框"""

    def __init__(self, item: KnowledgeItem = None, parent=None,
                 categories: list = None, tags: list = None):
        super().__init__(parent)
        self.item = item or KnowledgeItem()
        default_categories = [
            "general", "address", "price", "wearing"
        ]
        self._categories = categories or default_categories
        self._tags = tags or []
        self.setWindowTitle("编辑知识库" if item else "添加知识库")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(16)

        # 意图
        self.category_input = QComboBox()
        self.category_input.addItems(self._categories)
        self.category_input.setEditable(True)
        self.category_input.setCurrentText(self.item.intent or "")
        layout.addRow("意图:", self.category_input)

        # 标签
        self.tags_input = QComboBox()
        self.tags_input.setEditable(True)
        self.tags_input.addItems(self._tags)
        self.tags_input.lineEdit().setPlaceholderText("如：地址,门店,上海")
        self.tags_input.setCurrentText("、".join(self.item.tags) if self.item.tags else "")
        layout.addRow("标签:", self.tags_input)

        # 问题输入
        self.question_input = QTextEdit()
        self.question_input.setPlaceholderText("输入问题...")
        self.question_input.setMaximumHeight(80)
        self.question_input.setText(self.item.question)
        layout.addRow("问题:", self.question_input)

        # 答案输入
        self.answer_input = QTextEdit()
        self.answer_input.setPlaceholderText("一行一个备选答案（最多5条）...")
        current_answers = self.item.answers if getattr(self.item, "answers", None) else ([self.item.answer] if self.item.answer else [])
        self.answer_input.setText("\n".join(current_answers))
        layout.addRow("答案:", self.answer_input)

        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _on_save(self):
        question = self.question_input.toPlainText().strip()
        raw_answer_block = self.answer_input.toPlainText().strip()
        answers = [line.strip() for line in raw_answer_block.splitlines() if line.strip()]
        category = self.category_input.currentText().strip()
        tags_raw = self.tags_input.currentText().strip()
        tags = [t.strip() for t in re.split(r"[，,、;；\\s]+", tags_raw) if t.strip()]

        if not question:
            QMessageBox.warning(self, "警告", "问题不能为空")
            return

        if not answers:
            QMessageBox.warning(self, "警告", "答案不能为空")
            return
        if len(answers) > 5:
            QMessageBox.warning(self, "警告", "备选答案最多 5 条")
            return
        if len(answers) < 5:
            reply = QMessageBox.question(
                self,
                "提示",
                f"当前仅设置了 {len(answers)} 条备选答案，建议补齐到 5 条用于轮换测试。\n是否继续保存？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.item.question = question
        self.item.set_answers(answers)
        self.item.intent = category
        self.item.tags = tags
        self.accept()

    def get_item(self) -> KnowledgeItem:
        return self.item


class KnowledgeTab(QWidget):
    """知识库标签页"""

    data_changed = Signal()

    def __init__(self, repository: KnowledgeRepository, parent=None):
        super().__init__(parent)
        self.repository = repository
        self._search_text = ""
        self._setup_ui()
        self._load_data()

        # 连接仓库信号
        self.repository.data_changed.connect(self._load_data)

    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # --- Header ---
        header_layout = QHBoxLayout()

        title_wrap = QVBoxLayout()
        title_wrap.setSpacing(4)
        title = QLabel("知识库管理")
        title.setObjectName("PageTitle")
        title_wrap.addWidget(title)
        
        subtitle = QLabel("维护 AI 的回复逻辑与业务话术")
        subtitle.setObjectName("PageSubtitle")
        title_wrap.addWidget(subtitle)

        header_layout.addLayout(title_wrap)
        header_layout.addStretch()

        # Action Buttons
        self.export_btn = QPushButton("导出")
        self.export_btn.setObjectName("Secondary")
        self.export_btn.setCursor(Qt.PointingHandCursor)
        self.export_btn.clicked.connect(self._on_export)
        header_layout.addWidget(self.export_btn)

        self.import_btn = QPushButton("批量导入")
        self.import_btn.setObjectName("Secondary")
        self.import_btn.setCursor(Qt.PointingHandCursor)
        self.import_btn.clicked.connect(self._on_import)
        header_layout.addWidget(self.import_btn)

        self.add_btn = QPushButton("添加话术")
        self.add_btn.setObjectName("Primary")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self._on_add)
        header_layout.addWidget(self.add_btn)

        layout.addLayout(header_layout)

        # --- Content Area ---
        content_card = QFrame()
        content_card.setObjectName("TableCard")
        content_layout = QVBoxLayout(content_card)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # Toolbar inside card
        toolbar = QFrame()
        toolbar.setStyleSheet("border-bottom: 1px solid #e2e8f0; background: #f8fafc; border-top-left-radius: 16px; border-top-right-radius: 16px;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(16, 12, 16, 12)
        
        # Search Box
        search_wrap = QWidget()
        search_wrap.setObjectName("SearchBox")
        search_wrap.setMaximumWidth(400)
        search_layout = QHBoxLayout(search_wrap)
        search_layout.setContentsMargins(12, 6, 12, 6)
        
        search_icon = QLabel("🔍")
        search_icon.setStyleSheet("color: #94a3b8; font-size: 14px;")
        search_layout.addWidget(search_icon)
        
        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("搜索关键词、标签或问题...")
        self.search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self.search_input)
        
        toolbar_layout.addWidget(search_wrap)
        toolbar_layout.addStretch()
        
        self.stats_label = QLabel("共 0 条")
        self.stats_label.setObjectName("MutedText")
        toolbar_layout.addWidget(self.stats_label)

        content_layout.addWidget(toolbar)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["意图", "标签", "问题", "答案", "操作"])

        # Setup header
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(4, 180)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(60)

        # Custom Table Style
        self.table.setStyleSheet("""
            QTableWidget {
                background: #ffffff;
                border: none;
                gridline-color: transparent;
            }
            QTableWidget::item {    
                padding: 12px 16px;
                border-bottom: 1px solid #f1f5f9;
            }
            QHeaderView::section {
                background: #ffffff;
                color: #f97316;
                font-size: 13px;
                font-weight: 700;
                border: none;
                border-bottom: 2px solid #f1f5f9;
                padding: 12px 16px;
            }
        """)

        content_layout.addWidget(self.table)

        layout.addWidget(content_card)

    def _load_data(self):
        """加载数据到表格"""
        if self._search_text:
            items = self.repository.search(self._search_text)
        else:
            items = self.repository.get_all()

        self.table.setRowCount(len(items))

        for i, item in enumerate(items):
            # 意图
            cat_widget = QWidget()
            cat_layout = QHBoxLayout(cat_widget)
            cat_layout.setContentsMargins(8, 0, 8, 0)
            cat_label = QLabel(item.intent or "general")
            cat_label.setStyleSheet("""
                background: #eff6ff; color: #2563eb; 
                padding: 4px 8px; border-radius: 6px; 
                font-size: 11px; font-weight: 600;
            """)
            cat_layout.addWidget(cat_label)
            cat_layout.addStretch()
            self.table.setCellWidget(i, 0, cat_widget)

            # 标签
            tags_widget = QWidget()
            tags_layout = QHBoxLayout(tags_widget)
            tags_layout.setContentsMargins(8, 0, 8, 0)
            tags_layout.setSpacing(4)
            for tag in (item.tags[:2] if item.tags else []):
                t_label = QLabel(tag)
                t_label.setStyleSheet("""
                    background: #f1f5f9; color: #64748b;
                    padding: 2px 6px; border-radius: 4px;
                    font-size: 10px;
                """)
                tags_layout.addWidget(t_label)
            if item.tags and len(item.tags) > 2:
                more = QLabel(f"+{len(item.tags)-2}")
                more.setStyleSheet("color: #94a3b8; font-size: 10px;")
                tags_layout.addWidget(more)
            tags_layout.addStretch()
            self.table.setCellWidget(i, 1, tags_widget)

            # 问题
            q_item = QTableWidgetItem(item.question)
            q_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            q_item.setToolTip(item.question)
            font = q_item.font()
            font.setBold(True)
            q_item.setFont(font)
            self.table.setItem(i, 2, q_item)

            # 答案
            answer_preview = item.answer
            variant_total = len(item.answers or [])
            if variant_total > 1:
                answer_preview = f"{item.answer}（备选{variant_total}）"
            a_item = QTableWidgetItem(answer_preview)
            a_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            if variant_total > 1:
                tooltip = "\n".join([f"{idx + 1}. {ans}" for idx, ans in enumerate(item.answers)])
                a_item.setToolTip(tooltip)
            else:
                a_item.setToolTip(item.answer)
            self.table.setItem(i, 3, a_item)

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(0, 0, 16, 0)
            btn_layout.setSpacing(8)
            btn_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            edit_btn = QPushButton("✍️")
            edit_btn.setFixedSize(32, 32)
            edit_btn.setCursor(Qt.PointingHandCursor)
            edit_btn.setStyleSheet("""
                QPushButton { background: transparent; border: none; font-size: 16px; }
                QPushButton:hover { background: #eff6ff; border-radius: 6px; }
            """)
            edit_btn.setToolTip("编辑")
            edit_btn.clicked.connect(lambda checked, id=item.id: self._on_edit(id))
            btn_layout.addWidget(edit_btn)

            delete_btn = QPushButton("🗑️")
            delete_btn.setFixedSize(32, 32)
            delete_btn.setCursor(Qt.PointingHandCursor)
            delete_btn.setStyleSheet("""
                QPushButton { background: transparent; border: none; font-size: 16px; }
                QPushButton:hover { background: #fee2e2; border-radius: 6px; }
            """)
            delete_btn.setToolTip("删除")
            delete_btn.clicked.connect(lambda checked, id=item.id: self._on_delete(id))
            btn_layout.addWidget(delete_btn)

            self.table.setCellWidget(i, 4, btn_widget)

        self.stats_label.setText(f"共 {len(items)} 条数据")

    def _on_search(self, text: str):
        """搜索"""
        self._search_text = text.strip()
        self._load_data()

    def _on_add(self):
        """添加条目"""
        categories, tags = self._collect_meta()
        dialog = KnowledgeEditDialog(parent=self, categories=categories, tags=tags)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            item = dialog.get_item()
            self.repository.add(item.question, item.answer, intent=item.intent, tags=item.tags, answers=item.answers)
            self.data_changed.emit()

    def _on_edit(self, item_id: str):
        """编辑条目"""
        item = self.repository.get_by_id(item_id)
        if not item:
            QMessageBox.warning(self, "错误", "条目不存在")
            return

        categories, tags = self._collect_meta()
        dialog = KnowledgeEditDialog(item, parent=self, categories=categories, tags=tags)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated = dialog.get_item()
            self.repository.update(
                item_id,
                updated.question,
                updated.answer,
                intent=updated.intent,
                tags=updated.tags,
                answers=updated.answers,
            )
            self.data_changed.emit()

    def _collect_meta(self):
        """收集已有分类与标签，用于下拉建议"""
        items = self.repository.get_all()
        categories = sorted({i.intent for i in items if getattr(i, "intent", "").strip()})
        tags = sorted({t for i in items for t in (getattr(i, "tags", []) or []) if t.strip()})
        return categories, tags

    def _on_delete(self, item_id: str):
        """删除条目"""
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除这条知识库吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.repository.delete(item_id)
            self.data_changed.emit()

    def _on_import(self):
        """导入知识库"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入知识库", "", "Knowledge Files (*.json *.xlsx);;JSON Files (*.json);;Excel Files (*.xlsx);;All Files (*.*)"
        )
        if file_path:
            success, failed = self.repository.import_from_file(Path(file_path))
            QMessageBox.information(
                self, "导入完成",
                f"导入完成\n成功: {success} 条\n失败: {failed} 条"
            )
            self.data_changed.emit()

    def _on_export(self):
        """导出知识库"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出知识库", "knowledge_base.json",
            "JSON Files (*.json);;All Files (*.*)"
        )
        if file_path:
            success = self.repository.export_to_file(Path(file_path))
            if success:
                QMessageBox.information(self, "导出成功", f"知识库已导出到:\n{file_path}")
            else:
                QMessageBox.warning(self, "导出失败", "导出知识库时发生错误")

    def refresh(self):
        """刷新数据"""
        self._load_data()
