import threading
import time
import psutil
import os
from collections import deque
from datetime import datetime
from typing import Optional, Callable, Dict, List


class PerformanceMonitor:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        self._initialized = True

        self._lock = threading.Lock()
        self._process = psutil.Process(os.getpid())

        self._message_count = 0
        self._message_times = deque(maxlen=1000)
        self._start_time = datetime.now()

        self._memory_history = deque(maxlen=60)
        self._fps_history = deque(maxlen=60)

        self._monitor_thread = None
        self._monitor_running = False
        self._broadcast_callback: Optional[Callable] = None

        self._start_monitor_thread()

    def _start_monitor_thread(self):
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def _stop_monitor_thread(self):
        self._monitor_running = False

    def _monitor_loop(self):
        while self._monitor_running:
            try:
                time.sleep(1)
                self._collect_metrics()
            except Exception:
                pass

    def _collect_metrics(self):
        with self._lock:
            try:
                memory_info = self._process.memory_info()
                self._memory_history.append({
                    'timestamp': datetime.now().isoformat(),
                    'rss_mb': memory_info.rss / 1024 / 1024,
                    'vms_mb': memory_info.vms / 1024 / 1024
                })
            except Exception:
                pass

    def set_broadcast_callback(self, callback: Callable):
        self._broadcast_callback = callback

    def _broadcast(self, event_type: str, data: dict):
        if self._broadcast_callback:
            try:
                self._broadcast_callback({
                    'message_type': event_type,
                    'data': data,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception:
                pass

    def record_message(self):
        with self._lock:
            self._message_count += 1
            self._message_times.append(time.time())

    def get_stats(self) -> Dict:
        with self._lock:
            uptime_seconds = (datetime.now() - self._start_time).total_seconds()

            messages_per_second = 0
            if len(self._message_times) > 1 and uptime_seconds > 0:
                messages_per_second = self._message_count / uptime_seconds

            recent_mps = 0
            if len(self._message_times) >= 2:
                now = time.time()
                recent = [t for t in self._message_times if now - t <= 60]
                if len(recent) > 0:
                    recent_mps = len(recent) / min(60, uptime_seconds)

            memory_current = {}
            if self._memory_history:
                memory_current = self._memory_history[-1]

            return {
                'uptime_seconds': uptime_seconds,
                'total_messages': self._message_count,
                'messages_per_second_avg': round(messages_per_second, 2),
                'messages_per_second_recent': round(recent_mps, 2),
                'memory_rss_mb': round(memory_current.get('rss_mb', 0), 2),
                'memory_vms_mb': round(memory_current.get('vms_mb', 0), 2),
                'memory_history': list(self._memory_history)[-30:],
                'thread_count': threading.active_count(),
                'embedding': self._get_embedding_status(),
                'similarity_perf': self._get_similarity_perf(),
            }

    def _get_embedding_status(self) -> dict:
        """从 game_manager 读取 Embedding 引擎状态（避免循环依赖）"""
        try:
            from backend.app import game_manager  # 延迟导入

            return game_manager.get_embedding_status()
        except Exception as e:
            return {
                "status": "unavailable",
                "error_message": f"无法获取状态: {e}",
            }

    def _get_similarity_perf(self) -> dict:
        """从 game_manager 读取关联度计算性能统计"""
        try:
            from backend.app import game_manager  # 延迟导入

            return game_manager.get_similarity_perf()
        except Exception:
            return {"count": 0, "avg_ms": 0.0, "max_ms": 0.0}


performance_monitor = PerformanceMonitor()
