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
    ADDRESS_KEYWORDS = ("地址", "位置", "门店", "店铺", "在哪", "哪里", "怎么去")

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

    def is_address_query(self, text: str) -> bool:
        """是否为地址相关咨询"""
        text = (text or "").strip()
        return bool(text) and any(keyword in text for keyword in self.ADDRESS_KEYWORDS)

    def resolve_store_recommendation(self, user_text: str) -> dict:
        """根据用户地理位置解析推荐门店（仅路由，不生成文案）"""
        text = (user_text or "").strip()
        if not text:
            return {"city": "unknown", "target_store": "unknown", "reason": "unknown"}

        neg_beijing = any(k in text for k in ("不在北京", "不是北京", "不去北京"))
        neg_shanghai = any(k in text for k in ("不在上海", "不是上海", "不去上海"))

        # 北京与周边
        if not neg_beijing and any(k in text for k in ("北京", "天津", "河北", "门头沟", "朝阳", "海淀", "丰台", "通州", "顺义")):
            return {"city": "beijing", "target_store": "beijing_chaoyang", "reason": "jingjinji"}

        # 上海区级
        if "闵行" in text:
            return {"city": "shanghai", "target_store": "sh_xuhui", "reason": "minhang_map"}
        if "长宁" in text:
            return {"city": "shanghai", "target_store": "sh_jingan", "reason": "changning_map"}
        if "虹口" in text:
            return {"city": "shanghai", "target_store": "sh_hongkou", "reason": "same_district"}
        if "杨浦" in text or "五角场" in text:
            return {"city": "shanghai", "target_store": "sh_wujiaochang", "reason": "same_district"}
        if "黄浦" in text or "人民广场" in text or "人广" in text:
            return {"city": "shanghai", "target_store": "sh_renmin", "reason": "same_district"}
        if "徐汇" in text:
            return {"city": "shanghai", "target_store": "sh_xuhui", "reason": "same_district"}
        if "静安" in text:
            return {"city": "shanghai", "target_store": "sh_jingan", "reason": "same_district"}

        # 上海其他区
        if not neg_shanghai and any(k in text for k in ("上海", "浦东", "宝山", "普陀", "青浦", "松江", "嘉定", "奉贤", "金山", "崇明")):
            return {"city": "shanghai", "target_store": "sh_renmin", "reason": "fallback_renmin"}

        # 江浙沪周边默认推荐上海
        if any(k in text for k in (
            "江苏", "浙江", "苏州", "无锡", "常州", "南通", "南京", "宁波",
            "杭州", "绍兴", "嘉兴", "湖州", "金华", "温州"
        )):
            return {"city": "shanghai", "target_store": "sh_renmin", "reason": "jiangzhehu"}

        return {"city": "unknown", "target_store": "unknown", "reason": "unknown"}

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
