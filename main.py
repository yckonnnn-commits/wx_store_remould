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
    BASE_DIR = Path(sys._MEIPASS)
    app_data_dir = Path('~/Library/Application Support/Annel AI客服').expanduser()
    app_data_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(str(app_data_dir))
else:
    BASE_DIR = Path(__file__).parent

# 添加 src 到路径
sys.path.insert(0, str(BASE_DIR))

from src.data.config_manager import ConfigManager
from src.data.knowledge_repository import KnowledgeRepository
from src.ui.main_window import MainWindow
from src.utils.constants import (
    MODEL_SETTINGS_FILE,
    KNOWLEDGE_BASE_FILE,
    ENV_FILE,
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

    config_files = [
        'image_categories.json',
    ]

    config_dir = Path('config')
    config_dir.mkdir(parents=True, exist_ok=True)

    images_dir = Path('images')
    images_dir.mkdir(parents=True, exist_ok=True)

    if getattr(sys, 'frozen', False):
        source_config_dir = BASE_DIR / 'config'
        for config_file in config_files:
            dest_file = config_dir / config_file
            source_file = source_config_dir / config_file

            if not dest_file.exists() and source_file.exists():
                shutil.copy2(source_file, dest_file)
                print(f"✅ 已复制默认配置: {config_file}")


def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setApplicationName("AI智能客服系统")
    app.setApplicationVersion("2.0.0")

    setup_signal_handlers(app)
    init_default_configs()

    MODEL_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)

    config_manager = ConfigManager(
        config_file=MODEL_SETTINGS_FILE,
        env_file=ENV_FILE,
    )
    knowledge_repository = KnowledgeRepository(
        data_file=KNOWLEDGE_BASE_FILE,
    )

    window = MainWindow(config_manager, knowledge_repository)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
