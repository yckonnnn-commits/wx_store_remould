"""
图片管理标签页
用于管理图片文件，支持上传和批量删除
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QFileDialog,
    QAbstractItemView, QProgressBar, QFrame, QComboBox, QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QPixmap, QIcon


class ImageLoadWorker(QThread):
    """图片加载工作线程"""
    progress_updated = Signal(int, int)  # current, total
    image_loaded = Signal(str, QPixmap)  # path, pixmap
    finished = Signal()
    
    def __init__(self, image_paths):
        super().__init__()
        self.image_paths = image_paths
        self._running = True
    
    def run(self):
        """加载图片"""
        total = len(self.image_paths)
        for i, path in enumerate(self.image_paths):
            if not self._running:
                break
            
            try:
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    # 缩放图片以适应显示
                    scaled_pixmap = pixmap.scaled(180, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.image_loaded.emit(path, scaled_pixmap)
            except Exception:
                pass
            
            self.progress_updated.emit(i + 1, total)
        
        self.finished.emit()
    
    def stop(self):
        """停止加载"""
        self._running = False


class ImageListWidget(QListWidget):
    """图片列表控件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(QSize(180, 220))
        self.setGridSize(QSize(190, 260))
        self.setResizeMode(QListWidget.Adjust)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSpacing(12)
        self.setDragEnabled(False)
        self.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 4px;
            }
            QListWidget::item:selected {
                background: #eff6ff;
                border: 2px solid #3b82f6;
            }
            QListWidget::item:hover {
                border-color: #cbd5e1;
            }
        """)


class ImageManagementTab(QWidget):
    """图片管理标签页"""
    
    log_message = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_dir = Path("images")
        self.categories_file = Path("config/image_categories.json")
        self.current_images = []
        self.selected_images = []
        self.image_worker = None
        self.categories = ["联系方式", "店铺地址"]
        self.image_categories = {}  # {filename: category}
        self.current_filter = "全部"
        
        # 确保图片目录存在
        self.image_dir.mkdir(parents=True, exist_ok=True)
        
        self._load_categories()
        self._setup_ui()
        self._load_images()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(24)

        # 顶部标题与操作
        header = self._create_header()
        layout.addWidget(header)
        
        # 分类筛选
        filter_layout = QHBoxLayout()
        filter_label = QLabel("分类筛选：")
        filter_label.setStyleSheet("font-weight: 600; color: #475569;")
        filter_layout.addWidget(filter_label)
        
        self.category_filter = QComboBox()
        self.category_filter.addItems(["全部"] + self.categories + ["未分类"])
        self.category_filter.currentTextChanged.connect(self._on_filter_changed)
        self.category_filter.setFixedWidth(200)
        self.category_filter.setStyleSheet("""
            QComboBox {
                padding: 8px 12px;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                background: white;
            }
        """)
        filter_layout.addWidget(self.category_filter)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)
        
        # 图片列表面板
        image_panel = self._create_image_panel()
        layout.addWidget(image_panel, 1)
        
        # 底部状态栏
        status_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setObjectName("MutedText")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setFixedWidth(200)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)
        status_layout.addStretch()
        layout.addLayout(status_layout)
    
    def _create_header(self):
        """创建顶部标题与操作区"""
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)

        title_wrap = QVBoxLayout()
        title = QLabel("图片素材库")
        title.setObjectName("PageTitle")
        title_wrap.addWidget(title)
        subtitle = QLabel("管理 AI 客服在对话中使用的商品图片与素材")
        subtitle.setObjectName("PageSubtitle")
        title_wrap.addWidget(subtitle)
        header_layout.addLayout(title_wrap)

        header_layout.addStretch()

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setObjectName("Secondary")
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_btn.clicked.connect(self._select_all)
        header_layout.addWidget(self.select_all_btn)
        
        # 快捷分类按钮
        for category in self.categories:
            cat_btn = QPushButton(f"设为{category}")
            cat_btn.setObjectName("Secondary")
            cat_btn.setCursor(Qt.PointingHandCursor)
            cat_btn.clicked.connect(lambda checked, cat=category: self._quick_set_category(cat))
            cat_btn.setStyleSheet("""
                QPushButton {
                    background: #10b981;
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 6px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background: #059669;
                }
            """)
            header_layout.addWidget(cat_btn)
        
        self.set_category_btn = QPushButton("更多分类")
        self.set_category_btn.setObjectName("Secondary")
        self.set_category_btn.setCursor(Qt.PointingHandCursor)
        self.set_category_btn.clicked.connect(self._set_category)
        header_layout.addWidget(self.set_category_btn)

        self.deselect_all_btn = QPushButton("取消选择")
        self.deselect_all_btn.setObjectName("Secondary")
        self.deselect_all_btn.setCursor(Qt.PointingHandCursor)
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        header_layout.addWidget(self.deselect_all_btn)

        self.delete_btn = QPushButton("批量删除")
        self.delete_btn.setObjectName("Danger")
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.clicked.connect(self._batch_delete)
        header_layout.addWidget(self.delete_btn)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("Secondary")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self._load_images)
        header_layout.addWidget(self.refresh_btn)

        self.upload_btn = QPushButton("上传新图片")
        self.upload_btn.setObjectName("Primary")
        self.upload_btn.setCursor(Qt.PointingHandCursor)
        self.upload_btn.clicked.connect(self._upload_images)
        header_layout.addWidget(self.upload_btn)

        return header
    
    def _create_image_panel(self):
        """创建图片列表面板"""
        group = QFrame()
        group.setStyleSheet("background: transparent; border: none;") # Container itself invisible
        layout = QVBoxLayout(group)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        # 图片列表
        self.image_list = ImageListWidget()
        self.image_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.image_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.image_list)
        
        return group
    
    def _load_categories(self):
        """加载分类配置"""
        try:
            if self.categories_file.exists():
                with open(self.categories_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.categories = data.get("categories", ["联系方式", "店铺地址"])
                    images_data = data.get("images", {})
                    # 转换为 filename -> category 映射
                    self.image_categories = {}
                    for category, filenames in images_data.items():
                        for filename in filenames:
                            self.image_categories[filename] = category
        except Exception as e:
            self.log_message.emit(f"❌ 加载分类配置失败: {str(e)}")
    
    def _save_categories(self):
        """保存分类配置"""
        try:
            # 转换为 category -> [filenames] 格式
            images_data = {cat: [] for cat in self.categories}
            for filename, category in self.image_categories.items():
                if category in images_data:
                    images_data[category].append(filename)
            
            data = {
                "version": 1,
                "updated_at": datetime.now().isoformat(),
                "categories": self.categories,
                "images": images_data
            }
            
            self.categories_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.categories_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            self.log_message.emit(f"❌ 保存分类配置失败: {str(e)}")
    
    def _on_filter_changed(self, filter_text):
        """分类筛选变更"""
        self.current_filter = filter_text
        self._load_images()
    
    def _load_images(self):
        """加载图片"""
        self.status_label.setText("正在加载图片...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # 清空当前列表
        self.image_list.clear()
        self.current_images.clear()
        
        # 获取图片文件
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
        image_paths = []
        
        for ext in image_extensions:
            image_paths.extend(self.image_dir.glob(f"*{ext}"))
            image_paths.extend(self.image_dir.glob(f"*{ext.upper()}"))
        
        self.current_images = [str(path) for path in image_paths]
        
        if not self.current_images:
            self.status_label.setText("没有找到图片文件")
            self.progress_bar.setVisible(False)
            return
        
        # 使用工作线程加载图片
        self.image_worker = ImageLoadWorker(self.current_images)
        self.image_worker.image_loaded.connect(self._on_image_loaded)
        self.image_worker.progress_updated.connect(self._on_progress_updated)
        self.image_worker.finished.connect(self._on_load_finished)
        self.image_worker.start()
    
    def _should_show_image(self, filename):
        """根据当前筛选判断是否显示图片"""
        if self.current_filter == "全部":
            return True
        elif self.current_filter == "未分类":
            return filename not in self.image_categories
        else:
            return self.image_categories.get(filename) == self.current_filter
    
    def _on_image_loaded(self, path: str, pixmap: QPixmap):
        """图片加载完成"""
        filename = Path(path).name
        
        # 应用筛选
        if not self._should_show_image(filename):
            return
        
        item = QListWidgetItem()
        item.setIcon(QIcon(pixmap))
        
        # 显示文件名和分类
        category = self.image_categories.get(filename, "")
        display_text = filename
        if category:
            display_text += f" [{category}]"
        
        item.setText(display_text)
        item.setData(Qt.UserRole, path)
        item.setToolTip(f"{filename}\n分类: {category if category else '未分类'}")
        self.image_list.addItem(item)
    
    def _on_progress_updated(self, current: int, total: int):
        """更新进度"""
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"加载中... {current}/{total}")
    
    def _on_load_finished(self):
        """加载完成"""
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"共加载 {len(self.current_images)} 张图片")
        self.log_message.emit(f"✅ 图片加载完成，共 {len(self.current_images)} 张")
    
    def _set_category(self):
        """设置选中图片的分类"""
        selected_items = self.image_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要设置分类的图片")
            return
        
        dialog = CategorySelectDialog(self.categories, parent=self)
        if dialog.exec() == QDialog.Accepted:
            category = dialog.get_category()
            if category == "移除分类":
                category = None
            
            for item in selected_items:
                image_path = item.data(Qt.UserRole)
                filename = Path(image_path).name
                
                if category:
                    self.image_categories[filename] = category
                else:
                    self.image_categories.pop(filename, None)
            
            self._save_categories()
            self._load_images()
            self.log_message.emit(f"✅ 已设置 {len(selected_items)} 张图片的分类")
    
    def _quick_set_category(self, category: str):
        """快捷设置分类"""
        selected_items = self.image_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要设置分类的图片")
            return
        
        for item in selected_items:
            image_path = item.data(Qt.UserRole)
            filename = Path(image_path).name
            self.image_categories[filename] = category
        
        self._save_categories()
        self._load_images()
        self.log_message.emit(f"✅ 已将 {len(selected_items)} 张图片设置为 [{category}]")
    
    def _upload_images(self):
        """上传图片"""
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_dialog.setNameFilter("图片文件 (*.jpg *.jpeg *.png *.gif *.bmp *.webp *.tiff)")
        
        if file_dialog.exec():
            files = file_dialog.selectedFiles()
            if not files:
                return
            
            copied_count = 0
            for file_path in files:
                try:
                    src_path = Path(file_path)
                    dst_path = self.image_dir / src_path.name
                    
                    # 避免文件名冲突
                    counter = 1
                    while dst_path.exists():
                        stem = src_path.stem
                        suffix = src_path.suffix
                        dst_path = self.image_dir / f"{stem}_{counter}{suffix}"
                        counter += 1
                    
                    shutil.copy2(src_path, dst_path)
                    copied_count += 1
                    
                except Exception as e:
                    self.log_message.emit(f"❌ 复制文件失败: {src_path.name} - {str(e)}")
            
            if copied_count > 0:
                self.log_message.emit(f"✅ 成功上传 {copied_count} 张图片")
                self._load_images()
            else:
                self.log_message.emit("❌ 没有成功上传任何图片")
    
    def _select_all(self):
        """全选"""
        self.image_list.selectAll()
    
    def _deselect_all(self):
        """取消选择"""
        self.image_list.clearSelection()
    
    def _batch_delete(self):
        """批量删除"""
        selected_items = self.image_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "警告", "请先选择要删除的图片")
            return
        
        count = len(selected_items)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {count} 张图片吗？\n\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            deleted_count = 0
            for item in selected_items:
                image_path = item.data(Qt.UserRole)
                try:
                    os.remove(image_path)
                    deleted_count += 1
                except Exception as e:
                    self.log_message.emit(f"❌ 删除失败: {image_path} - {str(e)}")
            
            if deleted_count > 0:
                self.log_message.emit(f"✅ 成功删除 {deleted_count} 张图片")
                self._load_images()
            else:
                self.log_message.emit("❌ 没有成功删除任何图片")
    
    def _on_selection_changed(self):
        """选择变更"""
        selected_items = self.image_list.selectedItems()
        self.selected_images = [item.data(Qt.UserRole) for item in selected_items]
    
    def _on_item_double_clicked(self, item):
        """双击项目"""
        image_path = item.data(Qt.UserRole)
        self._open_image_external(image_path)
    
    def _open_image_external(self, image_path):
        """使用外部程序打开图片"""
        import subprocess
        import platform
        
        try:
            if platform.system() == "Darwin":  # macOS
                subprocess.run(["open", image_path])
            elif platform.system() == "Windows":
                os.startfile(image_path)
            else:  # Linux
                subprocess.run(["xdg-open", image_path])
        except Exception as e:
            self.log_message.emit(f"❌ 无法打开图片: {str(e)}")
    
    def _format_file_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class CategorySelectDialog(QDialog):
    """分类选择对话框"""
    
    def __init__(self, categories, parent=None):
        super().__init__(parent)
        self.categories = categories
        
        self.setWindowTitle("选择分类")
        self.setFixedSize(300, 200)
        self._setup_ui()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        
        label = QLabel("请选择图片分类：")
        label.setStyleSheet("font-weight: 600; color: #334155;")
        layout.addWidget(label)
        
        self.category_combo = QComboBox()
        self.category_combo.addItems(self.categories + ["移除分类"])
        self.category_combo.setStyleSheet("""
            QComboBox {
                padding: 10px 12px;
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                font-size: 14px;
            }
        """)
        layout.addWidget(self.category_combo)
        
        layout.addStretch()
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_category(self):
        """获取选中的分类"""
        return self.category_combo.currentText()
