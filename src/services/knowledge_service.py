"""
知识库服务模块
提供知识库相关的业务逻辑封装
"""

import re
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
    STORE_DETAILS = {
        "beijing_chaoyang": {
            "city": "beijing",
            "store_name": "北京朝阳门店",
            "store_address": "朝阳区建外SOHO东区"
        },
        "sh_jingan": {
            "city": "shanghai",
            "store_name": "上海静安门店",
            "store_address": "静安区愚园路172号环球世界大厦A座"
        },
        "sh_renmin": {
            "city": "shanghai",
            "store_name": "上海人民广场门店",
            "store_address": "黄埔区汉口路650号亚洲大厦"
        },
        "sh_hongkou": {
            "city": "shanghai",
            "store_name": "上海虹口门店",
            "store_address": "虹口区花园路16号嘉和国际大厦东楼"
        },
        "sh_wujiaochang": {
            "city": "shanghai",
            "store_name": "上海五角场门店",
            "store_address": "政通路177号，万达广场E栋C座"
        },
        "sh_xuhui": {
            "city": "shanghai",
            "store_name": "上海徐汇门店",
            "store_address": "徐汇区漕溪北路45号中航德必大厦"
        }
    }
    SHANGHAI_DISTRICT_STORE_MAP = {
        "闵行": "sh_xuhui",
        "长宁": "sh_jingan",
        "虹口": "sh_hongkou",
        "杨浦": "sh_wujiaochang",
        "五角场": "sh_wujiaochang",
        "黄浦": "sh_renmin",
        "黄埔": "sh_renmin",
        "人民广场": "sh_renmin",
        "人广": "sh_renmin",
        "徐汇": "sh_xuhui",
        "静安": "sh_jingan",
        "浦东": "sh_renmin",
        "青浦": "sh_renmin",
        "金山": "sh_renmin",
        "崇明": "sh_renmin",
        "宝山": "sh_hongkou",
        "普陀": "sh_jingan",
        "松江": "sh_xuhui",
        "嘉定": "sh_xuhui",
        "奉贤": "sh_xuhui",
    }
    NON_COVERAGE_REGION_HINTS = (
        "新疆", "西藏", "青海", "宁夏", "甘肃", "云南", "贵州", "广西", "海南",
        "黑龙江", "吉林", "辽宁", "山东", "山西", "陕西", "河南", "湖北", "湖南",
        "江西", "福建", "广东", "四川", "重庆", "安徽",
        "大连", "沈阳", "哈尔滨", "长春", "呼和浩特", "兰州", "乌鲁木齐", "拉萨",
        "西宁", "银川", "昆明", "南宁", "海口", "郑州", "武汉", "长沙", "南昌",
        "福州", "厦门", "广州", "深圳", "成都", "重庆市"
    )
    PURCHASE_INTENT_KEYWORDS = (
        "怎么买",
        "怎么购买",
        "我想买",
        "能买到吗",
        "在哪里买",
        "怎么下单",
        "怎么订",
    )
    PRICE_KEYWORDS = ("价格", "多少钱", "价位", "报价", "收费", "预算", "贵", "便宜")
    WEARING_KEYWORDS = (
        "佩戴", "麻烦", "闷", "热", "自然", "掉", "会掉吗", "材质", "真人发",
        "好打理", "清洗", "梳", "售后", "保养", "透气"
    )
    GENERIC_PREFIXES = (
        "好的", "好", "嗯", "额", "那个", "请问", "想问下", "想问一下",
        "我想问", "麻烦问下", "麻烦问一下"
    )

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
        query = (user_message or "").strip()
        if not query:
            return None

        result = self.repository.find_best_match(query, threshold)
        if result:
            return result[0]  # 返回答案文本

        normalized_query = self._normalize_for_kb(query)
        if normalized_query and normalized_query != query:
            relaxed_threshold = max(0.35, float(threshold) - 0.2)
            result = self.repository.find_best_match(normalized_query, relaxed_threshold)
            if result:
                return result[0]

        intent_fallback = self._find_answer_by_intent_hint(normalized_query or query)
        if intent_fallback:
            return intent_fallback
        return None

    def _normalize_for_kb(self, text: str) -> str:
        normalized = (text or "").strip()
        if not normalized:
            return ""

        for prefix in self.GENERIC_PREFIXES:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):].strip()

        normalized = re.sub(r"[，。！？、,.!?~\s]+", "", normalized)
        normalized = normalized.replace("是多少", "多少").replace("什么价格", "价格多少")
        return normalized

    def _find_answer_by_intent_hint(self, query: str) -> Optional[str]:
        text = (query or "").strip()
        if not text:
            return None

        intents: List[str] = []
        if any(k in text for k in self.PRICE_KEYWORDS):
            intents.append("price")
        if self.is_address_query(text):
            intents.append("address")
        if any(k in text for k in self.WEARING_KEYWORDS):
            intents.append("wearing")
        if not intents:
            intents.append("general")

        items = self.repository.get_all()
        for intent in intents:
            candidates = [item for item in items if (item.intent or "").lower() == intent]
            if not candidates:
                continue

            best_item = None
            best_score = -1.0
            for item in candidates:
                score = self._simple_overlap_score(text, item.question)
                if score > best_score:
                    best_score = score
                    best_item = item

            min_score = 0.15 if intent == "general" else 0.05
            if best_item and best_item.answer and best_score >= min_score:
                return best_item.answer
        return None

    def _simple_overlap_score(self, a: str, b: str) -> float:
        na = self._normalize_for_kb(a)
        nb = self._normalize_for_kb(b)
        if not na or not nb:
            return 0.0
        if na == nb:
            return 1.0
        if na in nb or nb in na:
            return 0.9

        set_a = set(na)
        set_b = set(nb)
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    def is_address_query(self, text: str) -> bool:
        """是否为地址相关咨询"""
        text = (text or "").strip()
        return bool(text) and any(keyword in text for keyword in self.ADDRESS_KEYWORDS)

    def is_purchase_intent(self, text: str) -> bool:
        """是否包含明确购买意图关键词"""
        normalized = re.sub(r"\s+", "", (text or ""))
        if not normalized:
            return False
        return any(keyword in normalized for keyword in self.PURCHASE_INTENT_KEYWORDS)

    def resolve_store_recommendation(self, user_text: str) -> dict:
        """根据用户地理位置解析推荐门店（仅路由，不生成文案）"""
        text = (user_text or "").strip()
        if not text:
            return {"city": "unknown", "target_store": "unknown", "reason": "unknown", "store_address": None}

        neg_beijing = any(k in text for k in ("不在北京", "不是北京", "不去北京"))
        neg_shanghai = any(k in text for k in ("不在上海", "不是上海", "不去上海"))
        # 北京：任何北京区县都只推荐朝阳
        beijing_markers = (
            "北京", "朝阳", "海淀", "丰台", "通州", "顺义", "门头沟", "大兴", "昌平",
            "石景山", "西城", "东城", "房山", "怀柔", "平谷", "密云", "延庆"
        )
        if not neg_beijing and any(k in text for k in beijing_markers):
            return self._build_route("beijing_chaoyang", "beijing_all_district")

        # 京津冀 + 内蒙古 -> 北京
        if any(k in text for k in ("天津", "河北", "内蒙古")):
            return self._build_route("beijing_chaoyang", "north_fallback_beijing")

        # 上海明确区映射
        for district, store_key in self.SHANGHAI_DISTRICT_STORE_MAP.items():
            if district in text:
                return self._build_route(store_key, f"sh_district_map:{district}")

        # 只说上海未带区：追问区，不直接给门店
        if not neg_shanghai and "上海" in text:
            return {"city": "shanghai", "target_store": "unknown", "reason": "shanghai_need_district", "store_address": None}

        # 江浙地区 -> 上海人民广场
        if any(k in text for k in (
            "江苏", "浙江", "苏州", "无锡", "常州", "南通", "南京", "宁波",
            "杭州", "绍兴", "嘉兴", "湖州", "金华", "温州"
        )):
            return self._build_route("sh_renmin", "jiangzhe_to_sh_renmin")

        # 其他明确地区（如新疆/大连）-> 非覆盖地区固定话术
        detected_region = self._extract_region_mention(text)
        if detected_region:
            return {
                "city": "unknown",
                "target_store": "unknown",
                "reason": "out_of_coverage",
                "store_address": None,
                "detected_region": detected_region
            }

        # 未识别地区 -> unknown（走追问）
        return {"city": "unknown", "target_store": "unknown", "reason": "unknown", "store_address": None}

    def _build_route(self, target_store: str, reason: str) -> dict:
        detail = self.STORE_DETAILS.get(target_store, {})
        return {
            "city": detail.get("city", "unknown"),
            "target_store": target_store,
            "reason": reason,
            "store_address": detail.get("store_address"),
            "store_name": detail.get("store_name", "")
        }

    def get_store_display(self, target_store: str) -> dict:
        detail = self.STORE_DETAILS.get(target_store, {})
        return {
            "target_store": target_store,
            "store_name": detail.get("store_name", ""),
            "store_address": detail.get("store_address")
        }

    def _extract_region_mention(self, text: str) -> str:
        text = (text or "").strip()
        if not text:
            return ""

        # 优先命中已知非覆盖地区词典
        for region in self.NON_COVERAGE_REGION_HINTS:
            if region in text:
                return region

        # 兜底：识别常见地名后缀，如“XX省/XX市/XX区/XX县/XX州”
        m = re.search(r"([\u4e00-\u9fa5]{2,8}(?:省|市|区|县|州|盟|旗))", text)
        if m:
            return m.group(1)
        return ""

    def add_item(self, question: str, answer: str, intent: str = "", tags: Optional[List[str]] = None,
                 category: Optional[str] = None) -> Optional[str]:
        """添加知识库条目

        Returns:
            新条目的ID，失败返回None
        """
        if not question or not answer:
            return None

        item = self.repository.add(question, answer, intent=intent, tags=tags, category=category)
        self.item_added.emit(item.id)
        return item.id

    def update_item(self, item_id: str, question: str = None, answer: str = None,
                    intent: str = None, tags: Optional[List[str]] = None,
                    category: Optional[str] = None) -> bool:
        """更新知识库条目"""
        success = self.repository.update(item_id, question, answer, intent=intent, tags=tags, category=category)
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
