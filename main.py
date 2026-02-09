"""
AI微信小店客服系统 - 主程序入口

这是一个基于 Python + PySide6 开发的 AI 智能客服系统，
专门为微信小店设计，支持多种大语言模型。
"""

import sys
import os
import signal
from pathlib import Path

from PySide6.QtWidgets import QApplication

# PyInstaller 打包后的路径处理
if getattr(sys, 'frozen', False):
    # 运行在 PyInstaller 打包的应用中
    # sys._MEIPASS 是 PyInstaller 解压资源的临时目录
    BASE_DIR = Path(sys._MEIPASS)
    # 确保应用数据目录存在
    app_data_dir = Path('~/Library/Application Support/Annel AI客服').expanduser()
    app_data_dir.mkdir(parents=True, exist_ok=True)
    # 切换工作目录到应用数据目录
    # 这样 config/ 和 images/ 等目录可以在用户的文档目录中创建
    os.chdir(str(app_data_dir))
else:
    # 开发模式
    BASE_DIR = Path(__file__).parent

# 添加 src 到路径
sys.path.insert(0, str(BASE_DIR))

from src.data.config_manager import ConfigManager
from src.data.knowledge_repository import KnowledgeRepository
from src.ui.main_window import MainWindow
from src.utils.constants import (
    MODEL_SETTINGS_FILE, KNOWLEDGE_BASE_FILE, ENV_FILE
)


def setup_signal_handlers(app: QApplication):
    """设置信号处理器"""
    def signal_handler(signum, frame):
        print("\n收到终止信号，正在退出...")
        app.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def init_default_configs():
    """初始化默认配置文件"""
    import shutil
    
    # 配置文件列表
    config_files = [
        'keyword_triggers.json',
        'image_categories.json',
    ]
    
    # 确保 config 目录存在
    config_dir = Path('config')
    config_dir.mkdir(parents=True, exist_ok=True)
    
    # 确保 images 目录存在
    images_dir = Path('images')
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # 如果在打包环境中，从 Resources 复制默认配置
    if getattr(sys, 'frozen', False):
        source_config_dir = BASE_DIR / 'config'
        for config_file in config_files:
            dest_file = config_dir / config_file
            source_file = source_config_dir / config_file
            
            # 如果目标文件不存在且源文件存在，则复制
            if not dest_file.exists() and source_file.exists():
                shutil.copy2(source_file, dest_file)
                print(f"✅ 已复制默认配置: {config_file}")


def main():
    """主函数"""
    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName("AI智能客服系统")
    app.setApplicationVersion("2.0.0")

    # 高DPI缩放在 PySide6 6.4+ 中自动处理，无需手动设置

    # 设置信号处理器
    setup_signal_handlers(app)

    # 初始化默认配置文件
    init_default_configs()

    # 确保配置目录存在
    MODEL_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 初始化数据层
    config_manager = ConfigManager(
        config_file=MODEL_SETTINGS_FILE,
        env_file=ENV_FILE
    )
    knowledge_repository = KnowledgeRepository(
        data_file=KNOWLEDGE_BASE_FILE
    )

    # 创建主窗口
    window = MainWindow(config_manager, knowledge_repository)
    window.show()

    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
