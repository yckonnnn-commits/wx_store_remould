"""
知识库存储模块
负责知识库的加载、保存、搜索和管理
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from PySide6.QtCore import QObject, Signal


class KnowledgeItem:
    """知识库条目"""

    def __init__(self, question: str = "", answer: str = "", item_id: str = None,
                 category: str = "", tags: Optional[List[str]] = None):
        self.id = item_id or str(uuid.uuid4())
        self.question = question.strip() if question else ""
        self.answer = answer.strip() if answer else ""
        self.category = category.strip() if category else ""
        self.tags = [t.strip() for t in (tags or []) if t.strip()]
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "answer": self.answer,
            "category": self.category,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeItem":
        item = cls()
        item.id = data.get("id", str(uuid.uuid4()))
        item.question = data.get("question", "")
        item.answer = data.get("answer", "")
        item.category = data.get("category", "")
        item.tags = data.get("tags", []) or []
        item.created_at = data.get("created_at", datetime.now().isoformat())
        item.updated_at = data.get("updated_at", datetime.now().isoformat())
        return item


class KnowledgeRepository(QObject):
    """知识库仓库，负责知识库数据的管理"""

    data_changed = Signal()  # 数据变更信号

    def __init__(self, data_file: Path = None):
        super().__init__()
        self.data_file = data_file
        self._items: List[KnowledgeItem] = []
        self._search_cache: Dict[str, List[KnowledgeItem]] = {}
        self.load()

    def load(self) -> bool:
        """从文件加载知识库"""
        try:
            if self.data_file and self.data_file.exists():
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._items = [KnowledgeItem.from_dict(item) for item in data]
                    else:
                        self._items = []
            else:
                self._items = []
            self._search_cache.clear()
            return True
        except Exception as e:
            print(f"[KnowledgeRepository] 加载知识库失败: {e}")
            self._items = []
            return False

    def save(self) -> bool:
        """保存知识库到文件"""
        try:
            if self.data_file:
                self.data_file.parent.mkdir(parents=True, exist_ok=True)
                data = [item.to_dict() for item in self._items]
                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[KnowledgeRepository] 保存知识库失败: {e}")
            return False

    def get_all(self) -> List[KnowledgeItem]:
        """获取所有知识库条目"""
        return self._items.copy()

    def get_by_id(self, item_id: str) -> Optional[KnowledgeItem]:
        """根据ID获取条目"""
        for item in self._items:
            if item.id == item_id:
                return item
        return None

    def add(self, question: str, answer: str, category: str = "", tags: Optional[List[str]] = None) -> KnowledgeItem:
        """添加新条目"""
        item = KnowledgeItem(question=question, answer=answer, category=category, tags=tags)
        self._items.append(item)
        self._search_cache.clear()
        self.data_changed.emit()
        self.save()
        return item

    def update(self, item_id: str, question: str = None, answer: str = None,
               category: str = None, tags: Optional[List[str]] = None) -> bool:
        """更新条目"""
        item = self.get_by_id(item_id)
        if not item:
            return False

        if question is not None:
            item.question = question.strip()
        if answer is not None:
            item.answer = answer.strip()
        if category is not None:
            item.category = category.strip()
        if tags is not None:
            item.tags = [t.strip() for t in tags if t.strip()]
        item.updated_at = datetime.now().isoformat()

        self._search_cache.clear()
        self.data_changed.emit()
        self.save()
        return True

    def delete(self, item_id: str) -> bool:
        """删除条目"""
        for i, item in enumerate(self._items):
            if item.id == item_id:
                self._items.pop(i)
                self._search_cache.clear()
                self.data_changed.emit()
                self.save()
                return True
        return False

    def search(self, query: str) -> List[KnowledgeItem]:
        """搜索知识库"""
        if not query:
            return self._items.copy()

        # 检查缓存
        cache_key = query.lower()
        if cache_key in self._search_cache:
            return self._search_cache[cache_key].copy()

        results = []
        keywords = query.lower().split()

        for item in self._items:
            # 计算匹配分数
            score = 0
            question_lower = item.question.lower()
            answer_lower = item.answer.lower()

            for keyword in keywords:
                if keyword in question_lower:
                    score += 10  # 问题匹配权重高
                if keyword in answer_lower:
                    score += 5   # 答案匹配权重低

            if score > 0:
                results.append((score, item))

        # 按分数排序
        results.sort(key=lambda x: x[0], reverse=True)
        result_items = [item for _, item in results]

        # 缓存结果
        self._search_cache[cache_key] = result_items
        return result_items

    def find_best_match(self, user_message: str, threshold: float = 0.6) -> Optional[Tuple[str, float]]:
        """找到最佳匹配的知识库答案

        Args:
            user_message: 用户消息
            threshold: 匹配阈值 (0-1)

        Returns:
            (answer, score) 或 None
        """
        if not user_message or not self._items:
            return None

        user_lower = user_message.lower()
        best_match = None
        best_score = 0.0

        for item in self._items:
            question_lower = item.question.lower()

            # 精确匹配
            if user_lower == question_lower:
                return (item.answer, 1.0)

            # 包含匹配
            if user_lower in question_lower or question_lower in user_lower:
                score = 0.8
                if score > best_score:
                    best_score = score
                    best_match = item.answer
                continue

            # 关键词匹配
            user_words = set(re.findall(r'\w+', user_lower))
            question_words = set(re.findall(r'\w+', question_lower))

            if user_words and question_words:
                intersection = user_words & question_words
                union = user_words | question_words
                if union:
                    score = len(intersection) / len(union)
                    if score > best_score:
                        best_score = score
                        best_match = item.answer

        if best_match and best_score >= threshold:
            return (best_match, best_score)

        return None

    def import_from_file(self, file_path: Path) -> Tuple[int, int]:
        """从文件导入知识库

        Returns:
            (成功数量, 失败数量)
        """
        success = 0
        failed = 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                for item_data in data:
                    try:
                        if isinstance(item_data, dict):
                            question = item_data.get('question') or item_data.get('q')
                            answer = item_data.get('answer') or item_data.get('a')
                            category = item_data.get('category', '')
                            tags = item_data.get('tags', []) or []
                            if question and answer:
                                self.add(question, answer, category=category, tags=tags)
                                success += 1
                            else:
                                failed += 1
                        elif isinstance(item_data, (list, tuple)) and len(item_data) >= 2:
                            self.add(str(item_data[0]), str(item_data[1]))
                            success += 1
                    except Exception:
                        failed += 1

            self.save()
            return (success, failed)

        except Exception as e:
            print(f"[KnowledgeRepository] 导入失败: {e}")
            return (0, 1)

    def export_to_file(self, file_path: Path) -> bool:
        """导出知识库到文件"""
        try:
            data = [item.to_dict() for item in self._items]
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[KnowledgeRepository] 导出失败: {e}")
            return False

    def clear(self) -> None:
        """清空知识库"""
        self._items.clear()
        self._search_cache.clear()
        self.data_changed.emit()
        self.save()

    def count(self) -> int:
        """获取条目数量"""
        return len(self._items)
