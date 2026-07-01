# -*- coding: utf-8 -*-
"""
Embedding 模型管理引擎

负责 BAAI/bge-small-zh-v1.5 模型的本地加载、自动下载、推理、缓存与降级。
单例模式确保全进程只加载一次模型。
"""

import os
import sys
import threading
import time
from collections import OrderedDict
from typing import List, Optional, Dict, Any

# 打包环境下：确保内嵌 Python 的 site-packages 在 sys.path 中
# 嵌入式 Python 的 ._pth 文件存在时，PYTHONPATH 环境变量会被忽略，
# 需要手动将 site-packages 添加到 sys.path
def _ensure_site_packages():
    """检测并添加内嵌 Python 的 site-packages 到 sys.path"""
    # 通过 sys.executable 推断内嵌 Python 的 site-packages 路径
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


# BGE 中文模型 query 侧指令前缀
_BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索中文文档："


class EmbeddingEngine:
    """Embedding 模型管理引擎（单例）"""

    MODEL_NAME = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_DIM = 512
    CACHE_SIZE = 500
    BATCH_SIZE = 32
    DOWNLOAD_TIMEOUT = 300  # 秒
    ENCODE_TIMEOUT = 5.0  # 单次编码超时

    def __init__(self):
        # 模型存放路径：backend/models/bge-small-zh-v1.5
        self.LOCAL_DIR = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "models",
            "bge-small-zh-v1.5",
        )

        self._model = None
        self._status = "unloaded"  # unloaded/downloading/loading/ready/failed
        self._error_message: Optional[str] = None
        self._lock = threading.Lock()
        self._load_lock = threading.Lock()  # 防止并发加载

        # 性能统计
        self._stats = {
            "encode_count": 0,
            "encode_total_ms": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "fallback_count": 0,
        }

        # LRU 缓存：text -> np.ndarray
        self._guess_cache: "OrderedDict[str, np.ndarray]" = OrderedDict()
        self._cache_size = self.CACHE_SIZE

        # 依赖可用性标记
        self._st_loaded = False
        try:
            import sentence_transformers  # noqa: F401
            self._st_loaded = True
        except ImportError:
            self._st_loaded = False

    # ===== 状态查询 =====

    @property
    def is_ready(self) -> bool:
        """模型是否就绪可推理"""
        return self._status == "ready" and self._model is not None

    @property
    def status(self) -> Dict[str, Any]:
        """返回模型状态字典（供前端/性能监控使用）"""
        encode_count = self._stats["encode_count"]
        avg_ms = (
            self._stats["encode_total_ms"] / encode_count
            if encode_count > 0
            else 0.0
        )
        cache_total = self._stats["cache_hits"] + self._stats["cache_misses"]
        hit_rate = (
            self._stats["cache_hits"] / cache_total * 100
            if cache_total > 0
            else 0.0
        )
        return {
            "status": self._status,
            "model_name": self.MODEL_NAME,
            "local_path": self.LOCAL_DIR,
            "embedding_dim": self.EMBEDDING_DIM,
            "error_message": self._error_message,
            "dependencies_available": self._st_loaded and _NUMPY_AVAILABLE,
            "encode_count": encode_count,
            "encode_avg_ms": round(avg_ms, 2),
            "cache_size": len(self._guess_cache),
            "cache_hit_rate": round(hit_rate, 2),
            "fallback_count": self._stats["fallback_count"],
        }

    def record_fallback(self):
        """记录一次降级"""
        with self._lock:
            self._stats["fallback_count"] += 1

    # ===== 加载/下载 =====

    def ensure_loaded(self, timeout: float = 60.0) -> bool:
        """
        确保模型已加载（线程安全）。
        首次调用时若本地不存在则自动下载。

        Args:
            timeout: 总超时秒数

        Returns:
            True 表示加载成功，False 表示失败（可降级）
        """
        if self.is_ready:
            return True

        with self._load_lock:
            # 双重检查
            if self.is_ready:
                return True

            # 检查依赖
            if not self._st_loaded or not _NUMPY_AVAILABLE:
                self._status = "failed"
                self._error_message = (
                    "缺少依赖：sentence-transformers 或 numpy 未安装"
                )
                print(f"[Embedding] {self._error_message}")
                return False

            # 下载（如需要）
            if not self._is_model_local():
                self._status = "downloading"
                print(f"[Embedding] 模型不存在，开始下载: {self.MODEL_NAME}")
                if not self._download_model():
                    self._status = "failed"
                    self._error_message = "模型下载失败"
                    return False

            # 加载
            self._status = "loading"
            print(f"[Embedding] 正在加载模型: {self.LOCAL_DIR}")
            try:
                from sentence_transformers import SentenceTransformer

                self._model = SentenceTransformer(
                    self.LOCAL_DIR,
                    device="cpu",  # 默认 CPU 推理
                )
                # 预热
                self._warmup()
                self._status = "ready"
                self._error_message = None
                print(f"[Embedding] 模型加载完成，维度={self.EMBEDDING_DIM}")
                return True
            except Exception as e:
                self._status = "failed"
                self._error_message = f"模型加载失败: {e}"
                print(f"[Embedding] {self._error_message}")
                return False

    def _is_model_local(self) -> bool:
        """检查本地模型文件是否完整"""
        if not os.path.isdir(self.LOCAL_DIR):
            return False
        # 检查关键文件
        required = [
            "config.json",
            "modules.json",
            "sentence_bert_config.json",
        ]
        for f in required:
            if not os.path.exists(os.path.join(self.LOCAL_DIR, f)):
                return False
        # 检查权重（pytorch_model.bin 或 model.safetensors）
        has_weight = (
            os.path.exists(os.path.join(self.LOCAL_DIR, "pytorch_model.bin"))
            or os.path.exists(os.path.join(self.LOCAL_DIR, "model.safetensors"))
        )
        return has_weight

    def _download_model(self) -> bool:
        """从 HuggingFace 下载模型到本地"""
        try:
            from huggingface_hub import snapshot_download

            os.makedirs(os.path.dirname(self.LOCAL_DIR), exist_ok=True)
            snapshot_download(
                repo_id=self.MODEL_NAME,
                local_dir=self.LOCAL_DIR,
                local_dir_use_symlinks=False,
                tqdm_class=None,
            )
            print(f"[Embedding] 模型下载完成: {self.LOCAL_DIR}")
            return True
        except Exception as e:
            print(f"[Embedding] 模型下载失败: {e}")
            return False

    def _warmup(self):
        """预热推理（首次推理较慢）"""
        if self._model is None:
            return
        try:
            _ = self._model.encode(
                ["测试"],
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as e:
            print(f"[Embedding] 预热失败（可忽略）: {e}")

    # ===== 推理 =====

    def encode(self, text: str, use_instruction: bool = True) -> Optional["np.ndarray"]:
        """
        编码单个文本为向量（已归一化）。

        Args:
            text: 输入文本
            use_instruction: 是否添加 BGE query 指令前缀

        Returns:
            shape=(EMBEDDING_DIM,) 的 float32 归一化向量；失败返回 None
        """
        if not self.is_ready:
            return None
        if not text or not text.strip():
            return None

        # 缓存命中检查
        cache_key = f"{use_instruction}::{text}"
        if cache_key in self._guess_cache:
            with self._lock:
                self._stats["cache_hits"] += 1
            # 移动到末尾（LRU）
            self._guess_cache.move_to_end(cache_key)
            return self._guess_cache[cache_key]

        with self._lock:
            self._stats["cache_misses"] += 1

        # BGE query 侧加指令前缀
        input_text = (_BGE_QUERY_INSTRUCTION + text) if use_instruction else text

        start = time.perf_counter()
        try:
            vec = self._model.encode(
                [input_text],
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                self._stats["encode_count"] += 1
                self._stats["encode_total_ms"] += elapsed_ms

            result = vec[0] if vec is not None and len(vec) > 0 else None
            if result is not None:
                self._put_cache(cache_key, result)
            return result
        except Exception as e:
            print(f"[Embedding] 编码失败: {e}")
            return None

    def encode_batch(
        self, texts: List[str], use_instruction: bool = False
    ) -> Optional["np.ndarray"]:
        """
        批量编码。

        Args:
            texts: 文本列表
            use_instruction: 是否添加 BGE query 指令前缀（词库文档侧一般不加）

        Returns:
            shape=(N, EMBEDDING_DIM) 的 float32 归一化向量；失败返回 None
        """
        if not self.is_ready or not texts:
            return None

        # 过滤空字符串
        valid_texts = [t if (t and t.strip()) else "未知" for t in texts]
        input_texts = (
            [(_BGE_QUERY_INSTRUCTION + t) for t in valid_texts]
            if use_instruction
            else valid_texts
        )

        start = time.perf_counter()
        try:
            vectors = self._model.encode(
                input_texts,
                batch_size=self.BATCH_SIZE,
                normalize_embeddings=True,
                show_progress_bar=False,
                convert_to_numpy=True,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            with self._lock:
                self._stats["encode_count"] += len(texts)
                self._stats["encode_total_ms"] += elapsed_ms
            return vectors
        except Exception as e:
            print(f"[Embedding] 批量编码失败: {e}")
            return None

    def cosine_similarity(self, a: "np.ndarray", b: "np.ndarray") -> float:
        """
        计算两个向量的余弦相似度。
        因输入已 L2 归一化，直接计算点积即可。
        """
        if a is None or b is None:
            return 0.0
        try:
            return float(np.dot(a, b))
        except Exception:
            return 0.0

    def _put_cache(self, key: str, vec: "np.ndarray"):
        """放入 LRU 缓存"""
        with self._lock:
            if key in self._guess_cache:
                self._guess_cache.move_to_end(key)
                return
            self._guess_cache[key] = vec
            # 淘汰最旧
            while len(self._guess_cache) > self._cache_size:
                self._guess_cache.popitem(last=False)

    def clear_cache(self):
        """清空 LRU 缓存"""
        with self._lock:
            self._guess_cache.clear()
            self._stats["cache_hits"] = 0
            self._stats["cache_misses"] = 0


# 全局单例
embedding_engine = EmbeddingEngine()
