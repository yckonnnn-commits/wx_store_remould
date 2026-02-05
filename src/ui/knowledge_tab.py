"""
知识库标签页
用于管理知识库条目
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QFileDialog,
    QDialog, QDialogButtonBox, QFormLayout, QTextEdit, QComboBox
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
            "购买方式", "地址门店", "选购建议", "品牌介绍", "价格报价", "异议处理",
            "预约到店", "佩戴体验", "产品介绍", "售后政策", "护理建议",
            "引导私域", "促销规则", "需求探索", "转介绍会员", "使用寿命"
        ]
        self._categories = categories or default_categories
        self._tags = tags or []
        self.setWindowTitle("编辑知识库" if item else "添加知识库")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(16)

        # 分类
        self.category_input = QComboBox()
        self.category_input.addItems(self._categories)
        self.category_input.setEditable(True)
        self.category_input.setCurrentText(self.item.category or "")
        layout.addRow("分类:", self.category_input)

        # 标签
        self.tags_input = QComboBox()
        self.tags_input.setEditable(True)
        self.tags_input.addItems(self._tags)
        self.tags_input.lineEdit().setPlaceholderText("如：价格,异议处理,售前话术")
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
        self.answer_input.setPlaceholderText("输入答案...")
        self.answer_input.setText(self.item.answer)
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
        answer = self.answer_input.toPlainText().strip()
        category = self.category_input.currentText().strip()
        tags_raw = self.tags_input.currentText().strip()
        tags = [t.strip() for t in re.split(r"[，,、;；\\s]+", tags_raw) if t.strip()]

        if not question:
            QMessageBox.warning(self, "警告", "问题不能为空")
            return

        if not answer:
            QMessageBox.warning(self, "警告", "答案不能为空")
            return

        self.item.question = question
        self.item.answer = answer
        self.item.category = category
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
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # 标题和操作栏
        header_layout = QHBoxLayout()

        title = QLabel("知识库管理")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("🔍 搜索知识库...")
        self.search_input.setFixedWidth(300)
        self.search_input.textChanged.connect(self._on_search)
        header_layout.addWidget(self.search_input)

        # 操作按钮
        self.add_btn = QPushButton("➕ 添加")
        self.add_btn.setObjectName("Secondary")
        self.add_btn.clicked.connect(self._on_add)
        header_layout.addWidget(self.add_btn)

        self.import_btn = QPushButton("📥 导入")
        self.import_btn.setObjectName("Secondary")
        self.import_btn.clicked.connect(self._on_import)
        header_layout.addWidget(self.import_btn)

        self.export_btn = QPushButton("📤 导出")
        self.export_btn.setObjectName("Secondary")
        self.export_btn.clicked.connect(self._on_export)
        header_layout.addWidget(self.export_btn)

        layout.addLayout(header_layout)

        # 统计信息
        self.stats_label = QLabel("共 0 条")
        self.stats_label.setObjectName("MutedText")
        layout.addWidget(self.stats_label)

        # 表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["分类", "标签", "问题", "答案", "操作"])

        header_category = QTableWidgetItem("分类")
        header_category.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setHorizontalHeaderItem(0, header_category)

        header_tags = QTableWidgetItem("标签")
        header_tags.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setHorizontalHeaderItem(1, header_tags)

        header_question = QTableWidgetItem("问题")
        header_question.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setHorizontalHeaderItem(2, header_question)

        header_answer = QTableWidgetItem("答案")
        header_answer.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setHorizontalHeaderItem(3, header_answer)

        header_action = QTableWidgetItem("操作")
        header_action.setTextAlignment(Qt.AlignCenter)
        self.table.setHorizontalHeaderItem(4, header_action)

        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setDefaultSectionSize(150)
        self.table.setColumnWidth(0, 120)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(4, 220)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(52)
        self.table.setStyleSheet("""
            QTableWidget {
                alternate-background-color: #f2e9da;
            }
        """)
        layout.addWidget(self.table, 1)

    def _load_data(self):
        """加载数据到表格"""
        if self._search_text:
            items = self.repository.search(self._search_text)
        else:
            items = self.repository.get_all()

        self.table.setRowCount(len(items))

        for i, item in enumerate(items):
            # 分类
            category_item = QTableWidgetItem(item.category or "-")
            category_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            category_item.setToolTip(item.category or "-")
            self.table.setItem(i, 0, category_item)

            # 标签
            tags_text = "、".join(item.tags) if item.tags else "-"
            tags_item = QTableWidgetItem(tags_text)
            tags_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            tags_item.setToolTip(tags_text)
            self.table.setItem(i, 1, tags_item)

            # 问题
            question_item = QTableWidgetItem(item.question)
            question_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            question_item.setData(Qt.ItemDataRole.UserRole, item.id)
            question_item.setToolTip(item.question)
            self.table.setItem(i, 2, question_item)

            # 答案
            answer_item = QTableWidgetItem(item.answer)
            answer_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            answer_item.setToolTip(item.answer)
            self.table.setItem(i, 3, answer_item)

            # 操作按钮
            btn_widget = QWidget()
            btn_layout = QHBoxLayout(btn_widget)
            btn_layout.setContentsMargins(4, 4, 4, 4)
            btn_layout.setSpacing(8)
            btn_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

            edit_btn = QPushButton("✏️ 编辑")
            edit_btn.setFixedWidth(70)
            edit_btn.setMinimumHeight(30)
            edit_btn.setObjectName("Ghost")
            edit_btn.setProperty("item_id", item.id)
            edit_btn.clicked.connect(lambda checked, id=item.id: self._on_edit(id))
            btn_layout.addWidget(edit_btn)

            delete_btn = QPushButton("🗑️ 删除")
            delete_btn.setFixedWidth(70)
            delete_btn.setMinimumHeight(30)
            delete_btn.setObjectName("GhostDanger")
            delete_btn.setProperty("item_id", item.id)
            delete_btn.clicked.connect(lambda checked, id=item.id: self._on_delete(id))
            btn_layout.addWidget(delete_btn)

            self.table.setCellWidget(i, 4, btn_widget)

        self.stats_label.setText(f"共 {len(items)} 条")

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
            self.repository.add(item.question, item.answer, category=item.category, tags=item.tags)
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
            self.repository.update(item_id, updated.question, updated.answer,
                                   category=updated.category, tags=updated.tags)
            self.data_changed.emit()

    def _collect_meta(self):
        """收集已有分类与标签，用于下拉建议"""
        items = self.repository.get_all()
        categories = sorted({i.category for i in items if getattr(i, "category", "").strip()})
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
            self, "导入知识库", "", "JSON Files (*.json);;All Files (*.*)"
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
