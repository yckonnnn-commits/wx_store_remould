"""
轻量RAG服务
基于关键词检索 + 简单切片，生成可拼接的知识库上下文
"""

import re
from typing import List, Dict

from ..services.knowledge_service import KnowledgeService
from ..data.knowledge_repository import KnowledgeItem


class RagService:
    """轻量RAG服务"""

    def __init__(self, knowledge_service: KnowledgeService):
        self.knowledge_service = knowledge_service

    def retrieve(self, query: str, top_k: int = 3, chunk_chars: int = 200) -> List[Dict[str, str]]:
        """检索并切片

        Returns:
            [{question, answer}, ...]
        """
        if not query:
            return []

        items = self.knowledge_service.search(query)
        chunks: List[Dict[str, str]] = []

        for item in items:
            for chunk in self._chunk_item(item, chunk_chars):
                chunks.append({"question": item.question, "answer": chunk})
                if len(chunks) >= top_k:
                    return chunks

        return chunks

    def build_context(self, chunks: List[Dict[str, str]], max_chars: int = 700) -> str:
        """构建上下文文本"""
        if not chunks:
            return ""

        lines = []
        total = 0
        for idx, chunk in enumerate(chunks, start=1):
            q = self._truncate(chunk.get("question", "").strip(), 60)
            a = self._truncate(chunk.get("answer", "").strip(), 260)
            entry = f"[{idx}] 问题: {q}\n答案: {a}"
            if total + len(entry) > max_chars:
                if not lines:
                    lines.append(self._truncate(entry, max_chars))
                break
            lines.append(entry)
            total += len(entry)

        return "\n\n".join(lines)

    def _chunk_item(self, item: KnowledgeItem, chunk_chars: int) -> List[str]:
        """对答案做简单切片"""
        answer = (item.answer or "").strip()
        if len(answer) <= chunk_chars:
            return [answer] if answer else []

        # 以中文/英文标点切分，再拼成片段
        sentences = [s.strip() for s in re.split(r"[。！？.!?]\\s*", answer) if s.strip()]
        chunks = []
        current = ""
        for s in sentences:
            if not current:
                current = s
                continue
            if len(current) + len(s) + 1 <= chunk_chars:
                current = f"{current}。{s}"
            else:
                chunks.append(current)
                current = s
        if current:
            chunks.append(current)

        return chunks or [answer[:chunk_chars]]

    @staticmethod
    def _truncate(text: str, max_len: int) -> str:
        if len(text) <= max_len:
            return text
        return text[: max(0, max_len - 3)] + "..."
