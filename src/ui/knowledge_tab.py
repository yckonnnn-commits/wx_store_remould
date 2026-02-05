"""
知识库标签页
用于管理知识库条目
"""

from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QMessageBox, QFileDialog,
    QDialog, QDialogButtonBox, QFormLayout, QTextEdit
)
from PySide6.QtCore import Qt, Signal

from ..data.knowledge_repository import KnowledgeRepository, KnowledgeItem


class KnowledgeEditDialog(QDialog):
    """知识库编辑对话框"""

    def __init__(self, item: KnowledgeItem = None, parent=None):
        super().__init__(parent)
        self.item = item or KnowledgeItem()
        self.setWindowTitle("编辑知识库" if item else "添加知识库")
        self.setMinimumWidth(500)
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(16)

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

        if not question:
            QMessageBox.warning(self, "警告", "问题不能为空")
            return

        if not answer:
            QMessageBox.warning(self, "警告", "答案不能为空")
            return

        self.item.question = question
        self.item.answer = answer
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
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["问题", "答案", "操作"])
        # 头部左对齐（问题/答案），操作列居中
        header_question = QTableWidgetItem("问题")
        header_question.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setHorizontalHeaderItem(0, header_question)

        header_answer = QTableWidgetItem("答案")
        header_answer.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.setHorizontalHeaderItem(1, header_answer)

        header_action = QTableWidgetItem("操作")
        header_action.setTextAlignment(Qt.AlignCenter)
        self.table.setHorizontalHeaderItem(2, header_action)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setDefaultSectionSize(150)
        self.table.setColumnWidth(2, 200)
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
            # 问题
            question_item = QTableWidgetItem(item.question)
            question_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            question_item.setData(Qt.ItemDataRole.UserRole, item.id)
            question_item.setToolTip(item.question)
            self.table.setItem(i, 0, question_item)

            # 答案
            answer_item = QTableWidgetItem(item.answer)
            answer_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            answer_item.setToolTip(item.answer)
            self.table.setItem(i, 1, answer_item)

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

            self.table.setCellWidget(i, 2, btn_widget)

        self.stats_label.setText(f"共 {len(items)} 条")

    def _on_search(self, text: str):
        """搜索"""
        self._search_text = text.strip()
        self._load_data()

    def _on_add(self):
        """添加条目"""
        dialog = KnowledgeEditDialog(parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            item = dialog.get_item()
            self.repository.add(item.question, item.answer)
            self.data_changed.emit()

    def _on_edit(self, item_id: str):
        """编辑条目"""
        item = self.repository.get_by_id(item_id)
        if not item:
            QMessageBox.warning(self, "错误", "条目不存在")
            return

        dialog = KnowledgeEditDialog(item, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            updated = dialog.get_item()
            self.repository.update(item_id, updated.question, updated.answer)
            self.data_changed.emit()

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
