"""
AI微信小店客服系统 - 主程序入口

这是一个基于 Python + PySide6 开发的 AI 智能客服系统，
专门为微信小店设计，支持多种大语言模型。
"""

import sys
import signal
from pathlib import Path

from PySide6.QtWidgets import QApplication

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent))

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


def main():
    """主函数"""
    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName("AI智能客服系统")
    app.setApplicationVersion("2.0.0")

    # 高DPI缩放在 PySide6 6.4+ 中自动处理，无需手动设置

    # 设置信号处理器
    setup_signal_handlers(app)

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
