import sqlite3
import json
import os
import threading
from datetime import datetime
from typing import Optional

from .config_manager import config_manager


class GameDatabase:
    """SQLite 数据库管理器 — 猜词游戏数据持久化

    自动从旧 JSON 文件迁移数据，后续全部通过 SQLite 读写。
    线程安全：所有写操作通过 threading.Lock() 保护。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._data_dir = os.path.join(config_manager.get_project_root(), "data", "game")
        self._db_path = os.path.join(self._data_dir, "game.db")
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()
        self._migrate_from_json()

    # ==================== 连接管理 ====================

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._get_conn().execute(sql, params)

    def _commit(self):
        self._get_conn().commit()

    # ==================== 建表 ====================

    def _init_db(self):
        os.makedirs(self._data_dir, exist_ok=True)
        with self._lock:
            conn = self._get_conn()
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS word_bank (
                    id          TEXT PRIMARY KEY,
                    answer      TEXT NOT NULL,
                    hints       TEXT DEFAULT '[]',
                    category    TEXT DEFAULT '',
                    difficulty  TEXT DEFAULT 'medium',
                    sort_order  INTEGER DEFAULT 0,
                    is_active   INTEGER DEFAULT 1,
                    created_at  TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS game_config (
                    id                      INTEGER PRIMARY KEY CHECK (id = 1),
                    total_rounds            INTEGER DEFAULT 5,
                    round_time_limit        INTEGER DEFAULT 7200,
                    similarity_algorithm    TEXT DEFAULT 'hybrid',
                    ranking_display_count   INTEGER DEFAULT 20,
                    auto_next_round         INTEGER DEFAULT 1,
                    popup_duration          INTEGER DEFAULT 10,
                    hint_penalty            REAL DEFAULT 0.05,
                    qa_enabled              INTEGER DEFAULT 1,
                    updated_at              TEXT DEFAULT (datetime('now'))
                );
                INSERT OR IGNORE INTO game_config (id) VALUES (1);

                CREATE TABLE IF NOT EXISTS game_state (
                    id                  INTEGER PRIMARY KEY CHECK (id = 1),
                    status              TEXT DEFAULT 'idle',
                    current_round       INTEGER DEFAULT 0,
                    current_word_id     TEXT,
                    current_answer      TEXT,
                    current_hints       TEXT DEFAULT '[]',
                    current_hints_shown INTEGER DEFAULT 0,
                    round_start_time    TEXT,
                    round_end_time      TEXT,
                    time_remaining      INTEGER DEFAULT 0,
                    used_word_ids       TEXT DEFAULT '[]',
                    updated_at          TEXT DEFAULT (datetime('now'))
                );
                INSERT OR IGNORE INTO game_state (id) VALUES (1);

                CREATE TABLE IF NOT EXISTS game_history (
                    round_id        TEXT PRIMARY KEY,
                    round_number    INTEGER NOT NULL,
                    answer          TEXT NOT NULL,
                    winner          TEXT,
                    winner_guess    TEXT,
                    total_guesses   INTEGER DEFAULT 0,
                    start_time      TEXT,
                    end_time        TEXT
                );

                CREATE TABLE IF NOT EXISTS guess_records (
                    id              TEXT PRIMARY KEY,
                    round_id        TEXT NOT NULL,
                    user_name       TEXT NOT NULL,
                    guess_content   TEXT NOT NULL,
                    similarity_score REAL DEFAULT 0.0,
                    is_correct      INTEGER DEFAULT 0,
                    timestamp       TEXT,
                    FOREIGN KEY (round_id) REFERENCES game_history(round_id)
                );

                CREATE TABLE IF NOT EXISTS meta (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );
                INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', '2');
                INSERT OR IGNORE INTO meta (key, value) VALUES ('migrated', '0');
            """)
            conn.commit()

    # ==================== JSON 迁移 ====================

    def _migrate_from_json(self):
        """首次启动时从旧 JSON 文件导入数据到 SQLite"""
        cursor = self._execute("SELECT value FROM meta WHERE key = 'migrated'")
        row = cursor.fetchone()
        if row and row["value"] == "1":
            return

        imported = False

        # --- 迁移词库 ---
        wb_path = os.path.join(self._data_dir, "word_bank.json")
        if os.path.exists(wb_path) and not wb_path.endswith(".bak"):
            try:
                with open(wb_path, "r", encoding="utf-8") as f:
                    words = json.load(f)
                for idx, w in enumerate(words):
                    hints_json = json.dumps(w.get("hints", []), ensure_ascii=False)
                    self._execute(
                        """INSERT OR REPLACE INTO word_bank
                           (id, answer, hints, category, difficulty, sort_order,
                            is_active, created_at)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            w["id"],
                            w["answer"],
                            hints_json,
                            w.get("category", ""),
                            w.get("difficulty", "medium"),
                            idx + 1,
                            1 if w.get("is_active", True) else 1,
                            w.get("created_at", datetime.now().isoformat()),
                        ),
                    )
                self._commit()
                os.rename(wb_path, wb_path + ".bak")
                print(f"[Database] 词库迁移完成: {len(words)} 条")
                imported = True
            except Exception as e:
                print(f"[Database] 词库迁移失败: {e}")

        # --- 迁移配置 ---
        cfg_path = os.path.join(self._data_dir, "config.json")
        if os.path.exists(cfg_path) and not cfg_path.endswith(".bak"):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self._execute(
                    """UPDATE game_config SET
                       total_rounds=?, round_time_limit=?, similarity_algorithm=?,
                       ranking_display_count=?, auto_next_round=?, popup_duration=?,
                       hint_penalty=?, qa_enabled=?, updated_at=?
                       WHERE id=1""",
                    (
                        cfg.get("total_rounds", 5),
                        cfg.get("round_time_limit", 7200),
                        cfg.get("similarity_algorithm", "hybrid"),
                        cfg.get("ranking_display_count", 20),
                        1 if cfg.get("auto_next_round", True) else 0,
                        cfg.get("popup_duration", 10),
                        cfg.get("hint_penalty", 0.05),
                        1 if cfg.get("qa_enabled", True) else 0,
                        datetime.now().isoformat(),
                    ),
                )
                self._commit()
                os.rename(cfg_path, cfg_path + ".bak")
                print("[Database] 配置迁移完成")
                imported = True
            except Exception as e:
                print(f"[Database] 配置迁移失败: {e}")

        # --- 迁移状态 ---
        st_path = os.path.join(self._data_dir, "state.json")
        if os.path.exists(st_path) and not st_path.endswith(".bak"):
            try:
                with open(st_path, "r", encoding="utf-8") as f:
                    st = json.load(f)
                self._execute(
                    """UPDATE game_state SET
                       status=?, current_round=?, current_word_id=?,
                       current_answer=?, current_hints=?, current_hints_shown=?,
                       round_start_time=?, round_end_time=?, time_remaining=?,
                       used_word_ids=?, updated_at=?
                       WHERE id=1""",
                    (
                        st.get("status", "idle"),
                        st.get("current_round", 0),
                        st.get("current_word_id"),
                        st.get("current_answer"),
                        json.dumps(st.get("current_hints", []), ensure_ascii=False),
                        st.get("current_hints_shown", 0),
                        st.get("round_start_time"),
                        st.get("round_end_time"),
                        st.get("time_remaining", 0),
                        json.dumps(st.get("used_word_ids", []), ensure_ascii=False),
                        datetime.now().isoformat(),
                    ),
                )
                self._commit()
                os.rename(st_path, st_path + ".bak")
                print("[Database] 状态迁移完成")
                imported = True
            except Exception as e:
                print(f"[Database] 状态迁移失败: {e}")

        # --- 迁移历史 ---
        hist_path = os.path.join(self._data_dir, "history.json")
        if os.path.exists(hist_path) and not hist_path.endswith(".bak"):
            try:
                with open(hist_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
                for record in history:
                    self._execute(
                        """INSERT OR REPLACE INTO game_history
                           (round_id, round_number, answer, winner, winner_guess,
                            total_guesses, start_time, end_time)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            record["round_id"],
                            record["round_number"],
                            record["answer"],
                            record.get("winner"),
                            record.get("winner_guess"),
                            record.get("total_guesses", 0),
                            record.get("start_time"),
                            record.get("end_time"),
                        ),
                    )
                    for guess in record.get("guesses", []):
                        self._execute(
                            """INSERT OR REPLACE INTO guess_records
                               (id, round_id, user_name, guess_content,
                                similarity_score, is_correct, timestamp)
                               VALUES (?, ?, ?, ?, ?, ?, ?)""",
                            (
                                guess["id"],
                                guess.get("round_id", record["round_id"]),
                                guess["user_name"],
                                guess["guess_content"],
                                guess.get("similarity_score", 0.0),
                                1 if guess.get("is_correct", False) else 0,
                                guess.get("timestamp", ""),
                            ),
                        )
                self._commit()
                os.rename(hist_path, hist_path + ".bak")
                print(f"[Database] 历史迁移完成: {len(history)} 轮")
                imported = True
            except Exception as e:
                print(f"[Database] 历史迁移失败: {e}")

        if imported:
            self._execute("UPDATE meta SET value = '1' WHERE key = 'migrated'")
            self._commit()
            print("[Database] ✅ 数据迁移全部完成")
        else:
            self._execute("UPDATE meta SET value = '1' WHERE key = 'migrated'")
            self._commit()
            print("[Database] 无需迁移（已是最新）")

    # ==================== 词库 CRUD ====================

    def load_word_bank(self) -> list:
        """返回 list[dict]，按 sort_order 排序，兼容旧 JSON 结构"""
        with self._lock:
            cursor = self._execute(
                "SELECT * FROM word_bank ORDER BY sort_order ASC, created_at ASC"
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                d["hints"] = json.loads(d.get("hints", "[]"))
                d["is_active"] = bool(d["is_active"])
                result.append(d)
            return result

    def save_word_bank(self, words: list):
        """全量保存词库（先清空后写入）"""
        with self._lock:
            self._execute("DELETE FROM word_bank")
            for idx, w in enumerate(words):
                hints_json = json.dumps(w.get("hints", []), ensure_ascii=False)
                self._execute(
                    """INSERT INTO word_bank
                       (id, answer, hints, category, difficulty, sort_order,
                        is_active, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        w["id"],
                        w["answer"],
                        hints_json,
                        w.get("category", ""),
                        w.get("difficulty", "medium"),
                        idx + 1,
                        1 if w.get("is_active", True) else 0,
                        w.get("created_at", datetime.now().isoformat()),
                    ),
                )
            self._commit()

    def add_word(self, word: dict) -> dict:
        """添加单个词条，自动分配 sort_order"""
        with self._lock:
            cursor = self._execute("SELECT COALESCE(MAX(sort_order), 0) FROM word_bank")
            max_order = cursor.fetchone()[0]
            word["sort_order"] = max_order + 1
            hints_json = json.dumps(word.get("hints", []), ensure_ascii=False)
            self._execute(
                """INSERT INTO word_bank
                   (id, answer, hints, category, difficulty, sort_order, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    word["id"],
                    word["answer"],
                    hints_json,
                    word.get("category", ""),
                    word.get("difficulty", "medium"),
                    word["sort_order"],
                    1 if word.get("is_active", True) else 0,
                    word.get("created_at", datetime.now().isoformat()),
                ),
            )
            self._commit()
            return word

    # ==================== 配置 ====================

    def load_config(self) -> dict:
        with self._lock:
            cursor = self._execute("SELECT * FROM game_config WHERE id = 1")
            row = cursor.fetchone()
            if not row:
                return {}
            d = dict(row)
            d.pop("id", None)
            d.pop("updated_at", None)
            d["auto_next_round"] = bool(d["auto_next_round"])
            d["qa_enabled"] = bool(d["qa_enabled"])
            return d

    def save_config(self, config: dict):
        with self._lock:
            self._execute(
                """UPDATE game_config SET
                   total_rounds=?, round_time_limit=?, similarity_algorithm=?,
                   ranking_display_count=?, auto_next_round=?, popup_duration=?,
                   hint_penalty=?, qa_enabled=?, updated_at=?
                   WHERE id=1""",
                (
                    config.get("total_rounds", 5),
                    config.get("round_time_limit", 7200),
                    config.get("similarity_algorithm", "hybrid"),
                    config.get("ranking_display_count", 20),
                    1 if config.get("auto_next_round", True) else 0,
                    config.get("popup_duration", 10),
                    config.get("hint_penalty", 0.05),
                    1 if config.get("qa_enabled", True) else 0,
                    datetime.now().isoformat(),
                ),
            )
            self._commit()

    # ==================== 状态 ====================

    def load_state(self) -> dict:
        with self._lock:
            cursor = self._execute("SELECT * FROM game_state WHERE id = 1")
            row = cursor.fetchone()
            if not row:
                return {}
            d = dict(row)
            d.pop("id", None)
            d.pop("updated_at", None)
            d["current_hints"] = json.loads(d.get("current_hints", "[]"))
            d["used_word_ids"] = json.loads(d.get("used_word_ids", "[]"))
            return d

    def save_state(self, state: dict):
        with self._lock:
            self._execute(
                """UPDATE game_state SET
                   status=?, current_round=?, current_word_id=?,
                   current_answer=?, current_hints=?, current_hints_shown=?,
                   round_start_time=?, round_end_time=?, time_remaining=?,
                   used_word_ids=?, updated_at=?
                   WHERE id=1""",
                (
                    state.get("status", "idle"),
                    state.get("current_round", 0),
                    state.get("current_word_id"),
                    state.get("current_answer"),
                    json.dumps(state.get("current_hints", []), ensure_ascii=False),
                    state.get("current_hints_shown", 0),
                    state.get("round_start_time"),
                    state.get("round_end_time"),
                    state.get("time_remaining", 0),
                    json.dumps(state.get("used_word_ids", []), ensure_ascii=False),
                    datetime.now().isoformat(),
                ),
            )
            self._commit()

    def clear_state(self):
        with self._lock:
            self._execute(
                """UPDATE game_state SET
                status='idle', current_round=0, current_word_id=NULL,
                current_answer=NULL, current_hints='[]', current_hints_shown=0,
                round_start_time=NULL, round_end_time=NULL, time_remaining=0,
                used_word_ids='[]', updated_at=? WHERE id=1""",
                (datetime.now().isoformat(),),
            )
            self._commit()

    # ==================== 历史记录 ====================

    def load_history(self) -> list:
        """返回 list[dict]，含 guesses 子列表，兼容旧 JSON 结构"""
        with self._lock:
            cursor = self._execute(
                "SELECT * FROM game_history ORDER BY round_number DESC"
            )
            rows = cursor.fetchall()
            result = []
            for row in rows:
                d = dict(row)
                g_cursor = self._execute(
                    "SELECT * FROM guess_records WHERE round_id = ? ORDER BY timestamp",
                    (d["round_id"],),
                )
                guesses = [dict(g) for g in g_cursor.fetchall()]
                for g in guesses:
                    g["is_correct"] = bool(g["is_correct"])
                d["guesses"] = guesses
                result.append(d)
            return result

    def save_history(self, history: list):
        """全量保存历史记录"""
        with self._lock:
            self._execute("DELETE FROM guess_records")
            self._execute("DELETE FROM game_history")
            for record in history:
                self._execute(
                    """INSERT INTO game_history
                       (round_id, round_number, answer, winner, winner_guess,
                        total_guesses, start_time, end_time)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record["round_id"],
                        record["round_number"],
                        record["answer"],
                        record.get("winner"),
                        record.get("winner_guess"),
                        record.get("total_guesses", 0),
                        record.get("start_time"),
                        record.get("end_time"),
                    ),
                )
                for guess in record.get("guesses", []):
                    self._execute(
                        """INSERT INTO guess_records
                           (id, round_id, user_name, guess_content,
                            similarity_score, is_correct, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            guess["id"],
                            guess.get("round_id", record["round_id"]),
                            guess["user_name"],
                            guess["guess_content"],
                            guess.get("similarity_score", 0.0),
                            1 if guess.get("is_correct", False) else 0,
                            guess.get("timestamp", ""),
                        ),
                    )
            self._commit()

    def append_history(self, record: dict):
        """追加一条历史记录及猜词记录"""
        with self._lock:
            self._execute(
                """INSERT INTO game_history
                   (round_id, round_number, answer, winner, winner_guess,
                    total_guesses, start_time, end_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record["round_id"],
                    record["round_number"],
                    record["answer"],
                    record.get("winner"),
                    record.get("winner_guess"),
                    record.get("total_guesses", 0),
                    record.get("start_time"),
                    record.get("end_time"),
                ),
            )
            for guess in record.get("guesses", []):
                self._execute(
                    """INSERT INTO guess_records
                       (id, round_id, user_name, guess_content,
                        similarity_score, is_correct, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        guess["id"],
                        guess.get("round_id", record["round_id"]),
                        guess["user_name"],
                        guess["guess_content"],
                        guess.get("similarity_score", 0.0),
                        1 if guess.get("is_correct", False) else 0,
                        guess.get("timestamp", ""),
                    ),
                )
            self._commit()

    def clear_history(self):
        with self._lock:
            self._execute("DELETE FROM guess_records")
            self._execute("DELETE FROM game_history")
            self._commit()


# 全局单例
db = GameDatabase()
