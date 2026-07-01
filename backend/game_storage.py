"""猜词游戏数据持久化 — SQLite 实现

保持与旧版完全相同的接口，内部委托给 database.GameDatabase。
game_manager.py 无需任何改动。
"""

from .database import db


class GameStorage:
    """猜词游戏数据持久化 — 委托给 SQLite 数据库"""

    # ===== 词库操作 =====

    def load_word_bank(self) -> list:
        """加载词库（按 sort_order 排序）"""
        return db.load_word_bank()

    def save_word_bank(self, words: list):
        """保存词库"""
        db.save_word_bank(words)

    # ===== 游戏配置 =====

    def load_config(self) -> dict:
        """加载游戏配置"""
        return db.load_config()

    def save_config(self, config: dict):
        """保存游戏配置"""
        db.save_config(config)

    # ===== 游戏状态 =====

    def load_state(self) -> dict:
        """加载游戏状态"""
        return db.load_state()

    def save_state(self, state: dict):
        """保存游戏状态"""
        db.save_state(state)

    def clear_state(self):
        """清除游戏状态"""
        db.clear_state()

    # ===== 历史记录 =====

    def load_history(self) -> list:
        """加载历史记录"""
        return db.load_history()

    def save_history(self, history: list):
        """保存历史记录"""
        db.save_history(history)

    def append_history(self, record: dict):
        """追加一条历史记录"""
        db.append_history(record)

    def clear_history(self):
        """清空历史记录"""
        db.clear_history()


# 全局实例 — 保持与旧版相同的导出名
game_storage = GameStorage()
