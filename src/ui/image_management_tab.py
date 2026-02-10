"""
图片与视频管理标签页
用于管理图片/视频文件，支持上传和批量删除
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QFileDialog,
    QAbstractItemView, QProgressBar, QFrame, QTabBar, QInputDialog
)
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QPixmap, QIcon


class ImageLoadWorker(QThread):
    """媒体加载工作线程"""
    progress_updated = Signal(int, int)  # current, total
    image_loaded = Signal(str, QPixmap)  # path, pixmap
    finished = Signal()
    
    def __init__(self, media_paths, image_extensions):
        super().__init__()
        self.media_paths = media_paths
        self.image_extensions = image_extensions
        self._running = True
    
    def run(self):
        """加载媒体"""
        total = len(self.media_paths)
        for i, path in enumerate(self.media_paths):
            if not self._running:
                break
            
            try:
                suffix = Path(path).suffix.lower()
                if suffix in self.image_extensions:
                    pixmap = QPixmap(path)
                    if not pixmap.isNull():
                        scaled_pixmap = pixmap.scaled(180, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.image_loaded.emit(path, scaled_pixmap)
                else:
                    self.image_loaded.emit(path, QPixmap())
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
    """图片与视频管理标签页"""
    
    log_message = Signal(str)
    categories_updated = Signal(list)
    ALL_TAB_NAME = "全部"
    IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff'}
    VIDEO_EXTENSIONS = {'.mp4', '.mov', '.m4v', '.avi', '.mkv', '.wmv', '.flv', '.webm'}
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_dir = Path("images")
        self.categories_file = Path("config/image_categories.json")
        self.current_images = []
        self.selected_images = []
        self.image_worker = None
        self.categories = ["联系方式", "店铺地址"]
        self.image_categories = {}  # {filename: category}
        self.image_cities = {}  # {filename: city}
        self.current_filter = self.ALL_TAB_NAME
        self.current_city_filter = ""
        self.visible_image_count = 0
        
        # 确保图片目录存在
        self.image_dir.mkdir(parents=True, exist_ok=True)
        
        self._load_categories()
        if self.current_filter != self.ALL_TAB_NAME and self.current_filter not in self.categories:
            self.current_filter = self.ALL_TAB_NAME
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
        
        # 分类Tab
        tabs = self._create_tabs_bar()
        layout.addWidget(tabs)

        # 店铺地址城市筛选（仅店铺地址分类显示）
        self.city_filter_wrap = self._create_city_filter_bar()
        layout.addWidget(self.city_filter_wrap)
        self._update_city_filter_visibility()
        
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
        title = QLabel("图片与视频素材库")
        title.setObjectName("PageTitle")
        title_wrap.addWidget(title)
        subtitle = QLabel("管理 AI 客服在对话中使用的商品图片与视频素材")
        subtitle.setObjectName("PageSubtitle")
        title_wrap.addWidget(subtitle)
        header_layout.addLayout(title_wrap)

        header_layout.addStretch()

        self.select_all_btn = QPushButton("全选")
        self.select_all_btn.setObjectName("Secondary")
        self.select_all_btn.setCursor(Qt.PointingHandCursor)
        self.select_all_btn.clicked.connect(self._select_all)
        header_layout.addWidget(self.select_all_btn)

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

        self.upload_video_btn = QPushButton("上传视频")
        self.upload_video_btn.setObjectName("Primary")
        self.upload_video_btn.setCursor(Qt.PointingHandCursor)
        self.upload_video_btn.clicked.connect(self._upload_videos)
        header_layout.addWidget(self.upload_video_btn)

        return header

    def _create_tabs_bar(self):
        """创建分类Tab栏"""
        tabs_wrap = QWidget()
        tabs_layout = QHBoxLayout(tabs_wrap)
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(8)

        self.category_tabs = QTabBar()
        self.category_tabs.setExpanding(False)
        self.category_tabs.setMovable(False)
        self.category_tabs.setElideMode(Qt.ElideRight)
        self.category_tabs.currentChanged.connect(self._on_tab_changed)
        self.category_tabs.setStyleSheet("""
            QTabBar::tab {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 8px 16px;
                color: #334155;
                margin-right: 6px;
            }
            QTabBar::tab:selected {
                background: #0ea5e9;
                border-color: #0284c7;
                color: #ffffff;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background: #eef2ff;
            }
        """)
        tabs_layout.addWidget(self.category_tabs)

        self.add_tab_btn = QPushButton("+")
        self.add_tab_btn.setObjectName("Secondary")
        self.add_tab_btn.setCursor(Qt.PointingHandCursor)
        self.add_tab_btn.setFixedSize(36, 36)
        self.add_tab_btn.clicked.connect(self._add_category_tab)
        tabs_layout.addWidget(self.add_tab_btn)

        self.delete_tab_btn = QPushButton("删除Tab")
        self.delete_tab_btn.setObjectName("Secondary")
        self.delete_tab_btn.setCursor(Qt.PointingHandCursor)
        self.delete_tab_btn.clicked.connect(self._delete_category_tab)
        tabs_layout.addWidget(self.delete_tab_btn)

        tabs_layout.addStretch()

        self._refresh_category_tabs(select_category=self.current_filter)
        return tabs_wrap

    def _create_city_filter_bar(self):
        """创建城市筛选栏（店铺地址专用）"""
        wrap = QWidget()
        layout = QHBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        city_label = QLabel("城市:")
        city_label.setObjectName("MutedText")
        layout.addWidget(city_label)

        self.city_sh_btn = QPushButton("上海")
        self.city_sh_btn.setObjectName("Secondary")
        self.city_sh_btn.setCheckable(True)
        self.city_sh_btn.setCursor(Qt.PointingHandCursor)
        self.city_sh_btn.clicked.connect(lambda: self._on_city_filter_click("上海"))
        layout.addWidget(self.city_sh_btn)

        self.city_bj_btn = QPushButton("北京")
        self.city_bj_btn.setObjectName("Secondary")
        self.city_bj_btn.setCheckable(True)
        self.city_bj_btn.setCursor(Qt.PointingHandCursor)
        self.city_bj_btn.clicked.connect(lambda: self._on_city_filter_click("北京"))
        layout.addWidget(self.city_bj_btn)

        layout.addStretch()
        wrap.setVisible(False)
        return wrap
    
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
                    self.image_cities = data.get("cities", {}) or {}
                    for category in images_data.keys():
                        if category not in self.categories:
                            self.categories.append(category)
                    # 转换为 filename -> category 映射
                    self.image_categories = {}
                    for category, filenames in images_data.items():
                        for filename in filenames:
                            self.image_categories[filename] = category
            else:
                self.categories = ["联系方式", "店铺地址"]
                self.image_categories = {}
                self.image_cities = {}
            self.categories = [c.strip() for c in self.categories if c and c.strip()]
            if not self.categories:
                self.categories = ["联系方式", "店铺地址"]
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
                "images": images_data,
                "cities": self.image_cities
            }
            
            self.categories_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.categories_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.categories_updated.emit(self.categories)
            
        except Exception as e:
            self.log_message.emit(f"❌ 保存分类配置失败: {str(e)}")
    
    def _refresh_category_tabs(self, select_category: str = ""):
        """刷新分类Tab"""
        if not hasattr(self, "category_tabs"):
            return
        self.category_tabs.blockSignals(True)
        while self.category_tabs.count() > 0:
            self.category_tabs.removeTab(0)
        self.category_tabs.addTab(self.ALL_TAB_NAME)
        for category in self.categories:
            self.category_tabs.addTab(category)
        self.category_tabs.blockSignals(False)

        valid_targets = [self.ALL_TAB_NAME] + self.categories
        target = select_category if select_category in valid_targets else self.ALL_TAB_NAME
        self.current_filter = target
        if target:
            index = -1
            for i in range(self.category_tabs.count()):
                if self.category_tabs.tabText(i) == target:
                    index = i
                    break
            if index >= 0:
                self.category_tabs.setCurrentIndex(index)

    def _on_tab_changed(self, index):
        """Tab切换"""
        if index < 0:
            return
        self.current_filter = self.category_tabs.tabText(index)
        self._update_city_filter_visibility()
        self._load_images()

    def _update_city_filter_visibility(self):
        if not hasattr(self, "city_filter_wrap"):
            return
        show = self.current_filter == "店铺地址"
        self.city_filter_wrap.setVisible(show)
        if not show:
            self.current_city_filter = ""
            if hasattr(self, "city_sh_btn"):
                self.city_sh_btn.setChecked(False)
            if hasattr(self, "city_bj_btn"):
                self.city_bj_btn.setChecked(False)

    def _on_city_filter_click(self, city: str):
        if self.current_city_filter == city:
            self.current_city_filter = ""
            self.city_sh_btn.setChecked(False)
            self.city_bj_btn.setChecked(False)
        else:
            self.current_city_filter = city
            self.city_sh_btn.setChecked(city == "上海")
            self.city_bj_btn.setChecked(city == "北京")
        self._load_images()

    def _add_category_tab(self):
        """新增分类Tab"""
        category_name, ok = QInputDialog.getText(self, "新增分类", "请输入分类名称：")
        if not ok:
            return
        category_name = category_name.strip()
        if not category_name:
            QMessageBox.warning(self, "警告", "分类名称不能为空")
            return
        if category_name in self.categories:
            QMessageBox.information(self, "提示", "该分类已存在")
            return
        if category_name == self.ALL_TAB_NAME:
            QMessageBox.warning(self, "警告", "“全部”是系统保留Tab名称")
            return
        self.categories.append(category_name)
        self._save_categories()
        self._refresh_category_tabs(select_category=category_name)
        self._load_images()
        self.log_message.emit(f"✅ 新增分类: {category_name}")

    def _delete_category_tab(self):
        """删除分类Tab（仅删除分类，不删除图片）"""
        if not self.categories:
            QMessageBox.information(self, "提示", "当前没有可删除的分类Tab")
            return

        category_name, ok = QInputDialog.getItem(
            self,
            "删除Tab",
            "请选择要删除的Tab：",
            self.categories,
            0,
            True
        )
        if not ok:
            return
        category_name = category_name.strip()
        if not category_name:
            return
        if category_name == self.ALL_TAB_NAME:
            QMessageBox.warning(self, "警告", "“全部”Tab不能删除")
            return
        if category_name not in self.categories:
            QMessageBox.warning(self, "警告", "未找到对应的分类Tab")
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除分类 Tab [{category_name}] 吗？\n\n仅删除Tab，不会删除图片文件。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        self.categories = [cat for cat in self.categories if cat != category_name]
        for filename, category in list(self.image_categories.items()):
            if category == category_name:
                self.image_categories.pop(filename, None)
                self.image_cities.pop(filename, None)
        self._save_categories()
        self._refresh_category_tabs(select_category=self.ALL_TAB_NAME)
        self._load_images()
        self.log_message.emit(f"✅ 已删除分类 Tab: {category_name}（图片保留在“全部”中可见）")
    
    def _load_images(self):
        """加载图片和视频"""
        self.status_label.setText("正在加载素材...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.visible_image_count = 0
        
        # 清空当前列表
        self.image_list.clear()
        self.current_images.clear()
        
        # 获取媒体文件
        media_paths = []
        
        for ext in self.IMAGE_EXTENSIONS | self.VIDEO_EXTENSIONS:
            media_paths.extend(self.image_dir.glob(f"*{ext}"))
            media_paths.extend(self.image_dir.glob(f"*{ext.upper()}"))
        
        self.current_images = [str(path) for path in media_paths]
        
        if not self.current_images:
            self.status_label.setText("没有找到素材文件")
            self.progress_bar.setVisible(False)
            return
        
        # 使用工作线程加载素材
        self.image_worker = ImageLoadWorker(self.current_images, self.IMAGE_EXTENSIONS)
        self.image_worker.image_loaded.connect(self._on_image_loaded)
        self.image_worker.progress_updated.connect(self._on_progress_updated)
        self.image_worker.finished.connect(self._on_load_finished)
        self.image_worker.start()
    
    def _should_show_image(self, filename):
        """根据当前筛选判断是否显示图片"""
        if not self.current_filter or self.current_filter == self.ALL_TAB_NAME:
            return True
        if self.image_categories.get(filename) != self.current_filter:
            return False
        if self.current_filter == "店铺地址" and self.current_city_filter:
            return self.image_cities.get(filename, "") == self.current_city_filter
        return True
    
    def _on_image_loaded(self, path: str, pixmap: QPixmap):
        """图片加载完成"""
        filename = Path(path).name
        
        # 应用筛选
        if not self._should_show_image(filename):
            return
        
        item = QListWidgetItem()
        if pixmap.isNull():
            placeholder = QPixmap(180, 220)
            placeholder.fill(Qt.transparent)
            item.setIcon(QIcon(placeholder))
            display_text = f"🎬 {filename}"
        else:
            item.setIcon(QIcon(pixmap))
            display_text = filename
        
        # 显示文件名和分类
        category = self.image_categories.get(filename, "")
        if category:
            display_text += f" [{category}]"
        city = self.image_cities.get(filename, "")
        if city:
            display_text += f" ({city})"
        
        item.setText(display_text)
        item.setData(Qt.UserRole, path)
        tooltip = f"{filename}\n分类: {category if category else '未分类'}"
        if city:
            tooltip += f"\n城市: {city}"
        item.setToolTip(tooltip)
        self.image_list.addItem(item)
        self.visible_image_count += 1
    
    def _on_progress_updated(self, current: int, total: int):
        """更新进度"""
        progress = int((current / total) * 100)
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"加载中... {current}/{total}")
    
    def _on_load_finished(self):
        """加载完成"""
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"当前Tab[{self.current_filter}] 显示 {self.visible_image_count} 个素材（库内共 {len(self.current_images)} 个）")
        self.log_message.emit(f"✅ 素材加载完成，当前Tab[{self.current_filter}] {self.visible_image_count} 个")
    
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
                    if self.current_filter in self.categories:
                        self.image_categories[dst_path.name] = self.current_filter
                        if self.current_filter == "店铺地址" and self.current_city_filter:
                            self.image_cities[dst_path.name] = self.current_city_filter
                    copied_count += 1
                    
                except Exception as e:
                    self.log_message.emit(f"❌ 复制文件失败: {src_path.name} - {str(e)}")
            
            if copied_count > 0:
                self._save_categories()
                self.log_message.emit(f"✅ 成功上传 {copied_count} 张图片")
                self._load_images()
            else:
                self.log_message.emit("❌ 没有成功上传任何图片")

    def _upload_videos(self):
        """上传视频"""
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_dialog.setNameFilter("视频文件 (*.mp4 *.mov *.m4v *.avi *.mkv *.wmv *.flv *.webm)")

        if file_dialog.exec():
            files = file_dialog.selectedFiles()
            if not files:
                return

            copied_count = 0
            for file_path in files:
                try:
                    src_path = Path(file_path)
                    dst_path = self.image_dir / src_path.name

                    counter = 1
                    while dst_path.exists():
                        stem = src_path.stem
                        suffix = src_path.suffix
                        dst_path = self.image_dir / f"{stem}_{counter}{suffix}"
                        counter += 1

                    shutil.copy2(src_path, dst_path)
                    if self.current_filter in self.categories:
                        self.image_categories[dst_path.name] = self.current_filter
                        if self.current_filter == "店铺地址" and self.current_city_filter:
                            self.image_cities[dst_path.name] = self.current_city_filter
                    copied_count += 1
                except Exception as e:
                    self.log_message.emit(f"❌ 复制视频失败: {src_path.name} - {str(e)}")

            if copied_count > 0:
                self._save_categories()
                self.log_message.emit(f"✅ 成功上传 {copied_count} 个视频")
                self._load_images()
            else:
                self.log_message.emit("❌ 没有成功上传任何视频")
    
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
            QMessageBox.warning(self, "警告", "请先选择要删除的素材")
            return
        
        count = len(selected_items)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {count} 个素材吗？\n\n此操作不可撤销！",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            deleted_count = 0
            for item in selected_items:
                image_path = item.data(Qt.UserRole)
                try:
                    filename = Path(image_path).name
                    os.remove(image_path)
                    self.image_categories.pop(filename, None)
                    self.image_cities.pop(filename, None)
                    deleted_count += 1
                except Exception as e:
                    self.log_message.emit(f"❌ 删除失败: {image_path} - {str(e)}")
            
            if deleted_count > 0:
                self._save_categories()
                self.log_message.emit(f"✅ 成功删除 {deleted_count} 个素材")
                self._load_images()
            else:
                self.log_message.emit("❌ 没有成功删除任何素材")
    
    def _on_selection_changed(self):
        """选择变更"""
        selected_items = self.image_list.selectedItems()
        self.selected_images = [item.data(Qt.UserRole) for item in selected_items]
    
    def _on_item_double_clicked(self, item):
        """双击项目"""
        image_path = item.data(Qt.UserRole)
        self._open_image_external(image_path)
    
    def _open_image_external(self, image_path):
        """使用外部程序打开媒体文件"""
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
            self.log_message.emit(f"❌ 无法打开文件: {str(e)}")
    
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
