# -*- coding: utf-8 -*-
"""
基于 Embedding 向量的猜词游戏关联度计算器

负责：
- 词库中所有激活词条目的向量预计算与增量更新
- 实时计算 guess 与 answer 的余弦相似度
- 综合上下文（分类/提示词）做最终评分转换
"""

import os
import sys
import threading
import time
from typing import Dict, List, Optional, TYPE_CHECKING

# 打包环境下：确保内嵌 Python 的 site-packages 在 sys.path 中
def _ensure_site_packages():
    python_exe = sys.executable
    if python_exe and os.path.basename(python_exe).lower() == 'python.exe':
        python_dir = os.path.dirname(python_exe)
        site_pkg = os.path.join(python_dir, 'Lib', 'site-packages')
        if os.path.isdir(site_pkg) and site_pkg not in sys.path:
            sys.path.insert(0, site_pkg)

_ensure_site_packages()

try:
    import numpy as np
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False
    np = None  # type: ignore

if TYPE_CHECKING:
    from .embedding_engine import EmbeddingEngine
    from .models import WordBankEntry


# 余弦相似度到 0-99.9 分的线性映射区间
# BGE-zh 在语义匹配上余弦相似度通常落在 [0.3, 0.95] 区间
_SIM_LOW = 0.30
_SIM_HIGH = 0.95
_SIM_SPAN = _SIM_HIGH - _SIM_LOW


def _normalize(text: str) -> str:
    """文本标准化：去空格、转小写"""
    return text.strip().lower().replace(" ", "").replace("\t", "")


class EmbeddingSimilarity:
    """Embedding 关联度计算器"""

    def __init__(self, engine: "EmbeddingEngine"):
        self.engine = engine
        # answer -> np.ndarray
        self._word_bank_vectors: Dict[str, "np.ndarray"] = {}
        self._lock = threading.RLock()
        self._last_precompute_ms: float = 0.0
        self._last_precompute_count: int = 0

    # ===== 词库向量管理 =====

    def precompute_word_bank(self, word_bank: List["WordBankEntry"]) -> int:
        """
        批量预计算词库中所有激活词的 Embedding 向量。

        Args:
            word_bank: 词库条目列表

        Returns:
            成功预计算的条目数
        """
        if not self.engine.is_ready:
            return 0
        if not word_bank:
            return 0

        active_words = [w for w in word_bank if w.is_active and w.answer]
        if not active_words:
            return 0

        answers = [w.answer for w in active_words]
        start = time.perf_counter()
        vectors = self.engine.encode_batch(answers, use_instruction=False)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if vectors is None or len(vectors) != len(answers):
            return 0

        with self._lock:
            for ans, vec in zip(answers, vectors):
                self._word_bank_vectors[ans] = vec
            self._last_precompute_ms = elapsed_ms
            self._last_precompute_count = len(answers)

        print(
            f"[EmbeddingSim] 词库预计算完成: {len(answers)} 条, "
            f"耗时 {elapsed_ms:.1f}ms"
        )
        return len(answers)

    def update_word_vector(self, answer: str) -> bool:
        """新增/更新单个词的向量"""
        if not self.engine.is_ready or not answer:
            return False
        norm = _normalize(answer)
        if not norm:
            return False
        vec = self.engine.encode(norm, use_instruction=False)
        if vec is None:
            return False
        with self._lock:
            self._word_bank_vectors[norm] = vec
        return True

    def remove_word_vector(self, answer: str):
        """删除词的向量"""
        if not answer:
            return
        norm = _normalize(answer)
        with self._lock:
            self._word_bank_vectors.pop(norm, None)

    def has_vector(self, answer: str) -> bool:
        """检查某答案是否有预计算向量"""
        if not answer:
            return False
        return _normalize(answer) in self._word_bank_vectors

    def get_stats(self) -> Dict[str, int]:
        """返回预计算统计信息"""
        with self._lock:
            return {
                "word_bank_vector_count": len(self._word_bank_vectors),
                "last_precompute_count": self._last_precompute_count,
                "last_precompute_ms": round(self._last_precompute_ms, 1),
            }

    # ===== 关联度计算 =====

    def calculate(
        self,
        guess: str,
        answer: str,
        category: str = "",
        hints: Optional[List[str]] = None,
    ) -> float:
        """
        计算 guess 与 answer 的关联度 (0.0 - 99.9)。

        完全匹配返回 100.0（在 GameManager 入口处处理，此函数不重复判断）。
        """
        if not self.engine.is_ready:
            self.engine.record_fallback()
            return 0.0

        guess_norm = _normalize(guess)
        answer_norm = _normalize(answer)
        if not guess_norm or not answer_norm:
            return 0.0

        # 1. 编码 guess（query 侧加 BGE 指令前缀）
        guess_vec = self.engine.encode(guess_norm, use_instruction=True)
        if guess_vec is None:
            self.engine.record_fallback()
            return 0.0

        # 2. 获取 answer 的预计算向量（无则实时编码）
        with self._lock:
            answer_vec = self._word_bank_vectors.get(answer_norm)

        if answer_vec is None:
            # 词库中没有该 answer（例如临时切换），实时编码
            answer_vec = self.engine.encode(answer_norm, use_instruction=False)
            if answer_vec is None:
                self.engine.record_fallback()
                return 0.0

        # 3. 余弦相似度（已归一化，等价于点积）
        sim = self.engine.cosine_similarity(guess_vec, answer_vec)

        # 4. 线性映射到 0-99.9
        score = (sim - _SIM_LOW) / _SIM_SPAN * 99.9
        score = max(0.0, min(99.9, score))

        # 5. 上下文加成（最多 +5 分）
        bonus = self._context_bonus(guess_norm, category, hints)
        score = min(99.9, score + bonus)

        return round(score, 1)

    def _context_bonus(
        self,
        guess: str,
        category: str = "",
        hints: Optional[List[str]] = None,
    ) -> float:
        """
        上下文加成：若 guess 与 category / hints 强相关，给予最多 5 分加成。
        """
        if not category and not hints:
            return 0.0

        bonus = 0.0
        # 1. 分类加成：guess 与 category 字符重叠
        if category and guess:
            if any(ch in guess for ch in category):
                bonus += 2.0

        # 2. 提示词加成：guess 包含任一 hint
        if hints:
            for hint in hints:
                hint_norm = _normalize(hint)
                if hint_norm and hint_norm in guess:
                    bonus += 3.0
                    break

        return min(5.0, bonus)
