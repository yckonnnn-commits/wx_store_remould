"""
知识库服务模块
提供知识库相关的业务逻辑封装
"""

from pathlib import Path
from typing import Optional, List, Tuple
from PySide6.QtCore import QObject, Signal

from ..data.knowledge_repository import KnowledgeRepository, KnowledgeItem


class KnowledgeService(QObject):
    """知识库服务，封装知识库的业务操作"""

    # 信号
    item_added = Signal(str)        # 条目添加 (item_id)
    item_updated = Signal(str)      # 条目更新 (item_id)
    item_deleted = Signal(str)      # 条目删除 (item_id)
    data_imported = Signal(int)     # 数据导入 (count)
    data_exported = Signal(str)     # 数据导出 (file_path)
    search_completed = Signal(list) # 搜索完成 (results)

    def __init__(self, repository: KnowledgeRepository):
        super().__init__()
        self.repository = repository

        # 连接仓库信号
        self.repository.data_changed.connect(self._on_data_changed)

    def _on_data_changed(self):
        """数据变更处理"""
        pass  # 可以在需要时添加通用处理

    def search(self, query: str) -> List[KnowledgeItem]:
        """搜索知识库"""
        results = self.repository.search(query)
        self.search_completed.emit([item.to_dict() for item in results])
        return results

    def find_answer(self, user_message: str, threshold: float = 0.6) -> Optional[str]:
        """根据用户消息查找最佳答案

        Args:
            user_message: 用户消息
            threshold: 匹配阈值 (0-1)

        Returns:
            匹配到的答案，如果没有则返回 None
        """
        result = self.repository.find_best_match(user_message, threshold)
        if result:
            return result[0]  # 返回答案文本
        return None

    def add_item(self, question: str, answer: str, category: str = "", tags: Optional[List[str]] = None) -> Optional[str]:
        """添加知识库条目

        Returns:
            新条目的ID，失败返回None
        """
        if not question or not answer:
            return None

        item = self.repository.add(question, answer, category=category, tags=tags)
        self.item_added.emit(item.id)
        return item.id

    def update_item(self, item_id: str, question: str = None, answer: str = None,
                    category: str = None, tags: Optional[List[str]] = None) -> bool:
        """更新知识库条目"""
        success = self.repository.update(item_id, question, answer, category=category, tags=tags)
        if success:
            self.item_updated.emit(item_id)
        return success

    def delete_item(self, item_id: str) -> bool:
        """删除知识库条目"""
        success = self.repository.delete(item_id)
        if success:
            self.item_deleted.emit(item_id)
        return success

    def get_all_items(self) -> List[KnowledgeItem]:
        """获取所有条目"""
        return self.repository.get_all()

    def get_item_by_id(self, item_id: str) -> Optional[KnowledgeItem]:
        """根据ID获取条目"""
        return self.repository.get_by_id(item_id)

    def import_from_file(self, file_path: Path) -> Tuple[int, int]:
        """从文件导入知识库

        Returns:
            (成功数量, 失败数量)
        """
        success, failed = self.repository.import_from_file(file_path)
        if success > 0:
            self.data_imported.emit(success)
        return success, failed

    def export_to_file(self, file_path: Path) -> bool:
        """导出知识库到文件"""
        success = self.repository.export_to_file(file_path)
        if success:
            self.data_exported.emit(str(file_path))
        return success

    def clear_all(self) -> bool:
        """清空所有知识库数据"""
        try:
            self.repository.clear()
            return True
        except Exception:
            return False

    def get_count(self) -> int:
        """获取条目总数"""
        return self.repository.count()

    def get_quick_answers(self, keywords: List[str]) -> List[Tuple[str, str]]:
        """获取快速回复选项

        Args:
            keywords: 关键词列表

        Returns:
            [(question, answer), ...]
        """
        results = []
        for keyword in keywords:
            items = self.repository.search(keyword)
            for item in items[:3]:  # 每个关键词取前3个结果
                results.append((item.question, item.answer))
        return results
