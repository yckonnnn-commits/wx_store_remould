"""
图片管理标签页
用于管理图片文件，支持上传和批量删除
"""

import os
import shutil
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QFileDialog,
    QAbstractItemView, QProgressBar, QCheckBox, QToolBar,
    QSplitter, QGroupBox, QGridLayout, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal, QThread
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
                    scaled_pixmap = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
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
        self.setIconSize(QPixmap(200, 200).size())
        self.setResizeMode(QListWidget.Adjust)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSpacing(10)
        self.setDragEnabled(False)


class ImageManagementTab(QWidget):
    """图片管理标签页"""
    
    log_message = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_dir = Path("images")
        self.current_images = []
        self.selected_images = []
        self.image_worker = None
        
        # 确保图片目录存在
        self.image_dir.mkdir(parents=True, exist_ok=True)
        
        self._setup_ui()
        self._load_images()
    
    def _setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 工具栏
        toolbar = self._create_toolbar()
        layout.addWidget(toolbar)
        
        # 主要内容区域
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧图片列表
        left_panel = self._create_image_panel()
        splitter.addWidget(left_panel)
        
        # 右侧预览面板
        right_panel = self._create_preview_panel()
        splitter.addWidget(right_panel)
        
        splitter.setSizes([400, 300])
        layout.addWidget(splitter)
        
        # 底部状态栏
        status_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)
        status_layout.addStretch()
        layout.addLayout(status_layout)
    
    def _create_toolbar(self):
        """创建工具栏"""
        toolbar = QToolBar()
        
        # 上传图片按钮
        self.upload_btn = QPushButton("📤 上传图片")
        self.upload_btn.clicked.connect(self._upload_images)
        toolbar.addWidget(self.upload_btn)
        
        toolbar.addSeparator()
        
        # 全选/反选
        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.clicked.connect(self._select_all)
        toolbar.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("取消选择")
        self.deselect_all_btn.clicked.connect(self._deselect_all)
        toolbar.addWidget(self.deselect_all_btn)
        
        toolbar.addSeparator()
        
        # 批量删除按钮
        self.delete_btn = QPushButton("🗑️ 批量删除")
        self.delete_btn.clicked.connect(self._batch_delete)
        self.delete_btn.setStyleSheet("QPushButton { background-color: #ff4444; color: white; }")
        toolbar.addWidget(self.delete_btn)
        
        toolbar.addSeparator()
        
        # 刷新按钮
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.clicked.connect(self._load_images)
        toolbar.addWidget(self.refresh_btn)
        
        return toolbar
    
    def _create_image_panel(self):
        """创建图片列表面板"""
        group = QGroupBox("图片列表")
        layout = QVBoxLayout(group)
        
        # 图片列表
        self.image_list = ImageListWidget()
        self.image_list.itemSelectionChanged.connect(self._on_selection_changed)
        self.image_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.image_list)
        
        return group
    
    def _create_preview_panel(self):
        """创建预览面板"""
        group = QGroupBox("预览")
        layout = QVBoxLayout(group)
        
        # 预览区域
        self.preview_label = QLabel("选择图片进行预览")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(300, 300)
        self.preview_label.setStyleSheet("QLabel { border: 1px solid #ccc; background-color: #f9f9f9; }")
        layout.addWidget(self.preview_label)
        
        # 图片信息
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        
        return group
    
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
    
    def _on_image_loaded(self, path: str, pixmap: QPixmap):
        """图片加载完成"""
        item = QListWidgetItem()
        item.setIcon(QIcon(pixmap))
        item.setText(Path(path).name)
        item.setData(Qt.UserRole, path)
        item.setToolTip(Path(path).name)
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
        
        # 更新预览
        if selected_items:
            self._update_preview(selected_items[0])
        else:
            self.preview_label.clear()
            self.preview_label.setText("选择图片进行预览")
            self.info_label.clear()
    
    def _on_item_double_clicked(self, item):
        """双击项目"""
        image_path = item.data(Qt.UserRole)
        self._open_image_external(image_path)
    
    def _update_preview(self, item):
        """更新预览"""
        image_path = item.data(Qt.UserRole)
        path_obj = Path(image_path)
        
        try:
            pixmap = QPixmap(image_path)
            if not pixmap.isNull():
                # 缩放图片以适应预览区域
                scaled_pixmap = pixmap.scaled(
                    280, 280, Qt.KeepAspectRatio, Qt.SmoothTransformation
                )
                self.preview_label.setPixmap(scaled_pixmap)
                
                # 显示图片信息
                file_size = path_obj.stat().st_size
                size_str = self._format_file_size(file_size)
                info_text = f"文件名: {path_obj.name}\n大小: {size_str}\n路径: {image_path}"
                self.info_label.setText(info_text)
            else:
                self.preview_label.setText("无法加载图片")
                self.info_label.clear()
        except Exception as e:
            self.preview_label.setText("预览失败")
            self.info_label.setText(f"错误: {str(e)}")
    
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
