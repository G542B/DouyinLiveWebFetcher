import re
import uuid
import threading
import time
from datetime import datetime
from typing import Optional, List, Dict, Callable

from .models import (
    WordBankEntry,
    GameConfigModel,
    GameStateModel,
    GuessRecord,
    RankingEntry,
    GameRoundRecord,
    UserGameStats,
)
from .game_storage import game_storage


def _try_import_embedding():
    """懒加载 Embedding 模块（避免 sentence-transformers 缺失时阻塞其他功能）"""
    try:
        from .embedding_engine import embedding_engine
        from .embedding_similarity import EmbeddingSimilarity

        return embedding_engine, EmbeddingSimilarity
    except Exception as e:
        print(f"[GameManager] Embedding 模块加载失败: {e}")
        return None, None


class GameManager:
    """猜词游戏管理器"""

    def __init__(self, message_callback: Optional[Callable] = None):
        self.message_callback = message_callback

        # 词库
        self.word_bank: List[WordBankEntry] = []
        # 游戏配置
        self.config: GameConfigModel = GameConfigModel()
        # 游戏状态
        self.state: GameStateModel = GameStateModel()
        # 当前轮次猜词记录
        self.current_round_guesses: List[GuessRecord] = []
        # 当前排行榜
        self.current_rankings: List[RankingEntry] = []
        # 用户游戏统计（跨轮次累积）
        self.user_stats: Dict[str, UserGameStats] = {}
        # 历史记录
        self.game_history: List[GameRoundRecord] = []
        # 当前轮次记录
        self.current_round_record: Optional[GameRoundRecord] = None
        # 倒计时线程控制
        self._timer_running = False
        self._timer_thread: Optional[threading.Thread] = None

        # Embedding 引擎（懒加载，可能为 None）
        self._embedding_engine = None
        self._embedding_similarity = None
        self._embedding_init_lock = threading.Lock()
        self._embedding_initialized = False

        # 关联度计算性能监控
        self._sim_perf = {
            "last_ms": 0.0,
            "avg_ms": 0.0,
            "max_ms": 0.0,
            "count": 0,
            "by_algo": {},  # algorithm -> {count, avg_ms, max_ms}
        }

        # 从持久化加载数据
        self._load_data()

        # 启动异步 Embedding 初始化（不阻塞构造）
        self._schedule_embedding_init()

    # ===== 数据加载与保存 =====

    def _load_data(self):
        """从持久化存储加载数据"""
        # 加载词库
        words_data = game_storage.load_word_bank()
        self.word_bank = [WordBankEntry(**w) for w in words_data]

        # 加载配置
        config_data = game_storage.load_config()
        if config_data:
            self.config = GameConfigModel(**config_data)

        # 加载历史记录
        history_data = game_storage.load_history()
        self.game_history = [GameRoundRecord(**h) for h in history_data]

        # 加载游戏状态（运行时恢复）
        state_data = game_storage.load_state()
        if state_data:
            # 运行中的状态不自动恢复，重置为idle
            if state_data.get("status") == "running":
                state_data["status"] = "idle"
            self.state = GameStateModel(**state_data)

        # 游戏结束后重启，必须重置轮次和已用词库
        # 确保从第一轮开始，而不是停留在上一局的轮次
        if self.state.status in ("finished", "idle"):
            self.state.current_round = 0
            self.state.used_word_ids = []
            self.state.current_word_id = None
            self.state.current_answer = None
            self.state.current_hints = []
            self.state.current_hints_shown = 0

    def _save_word_bank(self):
        game_storage.save_word_bank([w.model_dump() for w in self.word_bank])

    def _save_config(self):
        game_storage.save_config(self.config.model_dump())

    def _save_state(self):
        game_storage.save_state(self.state.model_dump())

    def _save_history(self):
        game_storage.save_history([h.model_dump() for h in self.game_history])

    # ===== Embedding 引擎管理 =====

    def _schedule_embedding_init(self):
        """后台异步初始化 Embedding（避免阻塞 GameManager 构造）"""
        if not self.config.embedding_enabled:
            return
        thread = threading.Thread(
            target=self._async_init_embedding, daemon=True, name="embedding-init"
        )
        thread.start()

    def _async_init_embedding(self):
        """后台线程：加载模型 + 预计算词库向量"""
        with self._embedding_init_lock:
            if self._embedding_initialized:
                return
            engine_cls, sim_cls = _try_import_embedding()
            if engine_cls is None:
                return
            self._embedding_engine = engine_cls
            try:
                if self._embedding_engine.ensure_loaded(timeout=120):
                    self._embedding_similarity = sim_cls(self._embedding_engine)
                    # 预计算词库向量
                    active = [w for w in self.word_bank if w.is_active]
                    if active:
                        self._embedding_similarity.precompute_word_bank(active)
                else:
                    print(
                        "[GameManager] Embedding 引擎加载失败，"
                        "embedding 算法将自动降级"
                    )
            except Exception as e:
                print(f"[GameManager] Embedding 初始化异常: {e}")
            finally:
                self._embedding_initialized = True

    def _schedule_embedding_update(self, answer: str):
        """词库新增/更新某词后，异步更新其向量"""
        if not answer or not self._embedding_similarity:
            return

        def _update():
            try:
                self._embedding_similarity.update_word_vector(answer)
            except Exception as e:
                print(f"[GameManager] 更新 Embedding 向量失败: {e}")

        threading.Thread(target=_update, daemon=True).start()

    def _schedule_embedding_remove(self, answer: str):
        """词库删除某词后，移除其向量"""
        if not answer or not self._embedding_similarity:
            return
        try:
            self._embedding_similarity.remove_word_vector(answer)
        except Exception as e:
            print(f"[GameManager] 移除 Embedding 向量失败: {e}")

    def get_embedding_status(self) -> dict:
        """返回 Embedding 引擎状态字典"""
        if self._embedding_engine is None:
            return {
                "status": "unavailable",
                "model_name": self.config.embedding_model_name,
                "error_message": "Embedding 模块未加载",
            }
        status = self._embedding_engine.status.copy()
        if self._embedding_similarity is not None:
            sim_stats = self._embedding_similarity.get_stats()
            status.update(sim_stats)
        return status

    def _record_similarity_perf(self, algorithm: str, elapsed_ms: float):
        """记录单次关联度计算性能"""
        with self._embedding_init_lock:
            self._sim_perf["count"] += 1
            self._sim_perf["last_ms"] = round(elapsed_ms, 2)
            # 更新平均
            prev_avg = self._sim_perf["avg_ms"]
            n = self._sim_perf["count"]
            self._sim_perf["avg_ms"] = round(
                (prev_avg * (n - 1) + elapsed_ms) / n, 2
            )
            if elapsed_ms > self._sim_perf["max_ms"]:
                self._sim_perf["max_ms"] = round(elapsed_ms, 2)
            # 按算法分组
            by_algo = self._sim_perf["by_algo"]
            if algorithm not in by_algo:
                by_algo[algorithm] = {"count": 0, "avg_ms": 0.0, "max_ms": 0.0}
            entry = by_algo[algorithm]
            entry["count"] += 1
            entry["avg_ms"] = round(
                (entry["avg_ms"] * (entry["count"] - 1) + elapsed_ms)
                / entry["count"],
                2,
            )
            if elapsed_ms > entry["max_ms"]:
                entry["max_ms"] = round(elapsed_ms, 2)

    def get_similarity_perf(self) -> dict:
        """返回关联度计算性能统计"""
        return {
            "last_ms": self._sim_perf["last_ms"],
            "avg_ms": self._sim_perf["avg_ms"],
            "max_ms": self._sim_perf["max_ms"],
            "count": self._sim_perf["count"],
            "by_algo": {
                k: v.copy() for k, v in self._sim_perf["by_algo"].items()
            },
        }

    # ===== 词库管理 =====

    def add_word(
        self,
        answer: str,
        hints: List[str] = None,
        category: str = "",
        difficulty: str = "medium",
    ) -> WordBankEntry:
        """添加词库条目"""
        entry = WordBankEntry(
            id=str(uuid.uuid4()),
            answer=answer,
            hints=hints or [],
            category=category,
            difficulty=difficulty,
            created_at=datetime.now(),
        )
        self.word_bank.append(entry)
        self._save_word_bank()
        # 异步更新 Embedding 向量
        self._schedule_embedding_update(answer)
        return entry

    def remove_word(self, word_id: str) -> bool:
        """删除词库条目"""
        for i, w in enumerate(self.word_bank):
            if w.id == word_id:
                removed = self.word_bank.pop(i)
                self._save_word_bank()
                # 同步移除 Embedding 向量
                self._schedule_embedding_remove(removed.answer)
                return True
        return False

    def update_word(self, word_id: str, **kwargs) -> Optional[WordBankEntry]:
        """更新词库条目"""
        for w in self.word_bank:
            if w.id == word_id:
                old_answer = w.answer
                for key, value in kwargs.items():
                    if value is not None and hasattr(w, key):
                        setattr(w, key, value)
                self._save_word_bank()
                # 若答案变化，重新计算 Embedding 向量
                if "answer" in kwargs and kwargs["answer"] != old_answer:
                    self._schedule_embedding_remove(old_answer)
                    self._schedule_embedding_update(w.answer)
                return w
        return None

    def get_all_words(self) -> List[WordBankEntry]:
        """获取所有词库条目"""
        return self.word_bank.copy()

    def get_active_words(self) -> List[WordBankEntry]:
        """获取所有启用的词库条目"""
        return [w for w in self.word_bank if w.is_active]

    def batch_import(self, words_data: list) -> int:
        """批量导入词库，返回导入数量"""
        count = 0
        new_answers = []
        for item in words_data:
            entry = WordBankEntry(
                id=str(uuid.uuid4()),
                answer=item.get("answer", ""),
                hints=item.get("hints", []),
                category=item.get("category", ""),
                difficulty=item.get("difficulty", "medium"),
                created_at=datetime.now(),
            )
            if entry.answer:
                self.word_bank.append(entry)
                new_answers.append(entry.answer)
                count += 1
        self._save_word_bank()
        # 批量更新 Embedding 向量（一次性 encode_batch 更高效）
        if new_answers and self._embedding_similarity is not None:
            def _batch_update():
                for ans in new_answers:
                    try:
                        self._embedding_similarity.update_word_vector(ans)
                    except Exception as e:
                        print(
                            f"[GameManager] 批量更新 Embedding 向量失败: {e}"
                        )

            threading.Thread(target=_batch_update, daemon=True).start()
        return count

    # ===== 游戏控制 =====

    def is_running(self) -> bool:
        """游戏是否在运行中"""
        return self.state.status == "running"

    def start_game(self) -> bool:
        """开始游戏"""
        if self.state.status == "running":
            return False

        active_words = self.get_active_words()
        if not active_words:
            return False

        self.state = GameStateModel(status="running")
        self.current_round_guesses = []
        self.current_rankings = []
        self.user_stats = {}
        self._save_state()

        # 开始第一轮
        self._start_new_round()
        self._broadcast_game_update(
            "game_start",
            {"status": "running", "total_rounds": self.config.total_rounds},
        )
        return True

    def pause_game(self) -> bool:
        """暂停游戏"""
        if self.state.status != "running":
            return False
        self.state.status = "paused"
        self._stop_timer()
        self._save_state()
        self._broadcast_game_update(
            "game_state_update",
            {"status": "paused", "current_round": self.state.current_round},
        )
        return True

    def resume_game(self) -> bool:
        """恢复游戏"""
        if self.state.status != "paused":
            return False
        self.state.status = "running"
        self._start_timer()
        self._save_state()
        self._broadcast_game_update(
            "game_state_update",
            {"status": "running", "current_round": self.state.current_round},
        )
        return True

    def stop_game(self) -> bool:
        """结束游戏"""
        if self.state.status == "idle":
            return False

        # 保存当前轮次
        if self.current_round_record and self.state.status in ("running", "paused"):
            self._finish_current_round(winner=None)

        self._stop_timer()
        self.state.status = "finished"
        self._save_state()

        self._broadcast_game_update(
            "game_state_update",
            {"status": "finished", "current_round": self.state.current_round},
        )
        return True

    def next_round(self) -> bool:
        """手动切换下一轮"""
        if self.state.status not in ("running", "paused"):
            return False

        # 保存当前轮次（无人猜中）
        self._finish_current_round(winner=None)

        # 检查是否已达到最大轮次
        if self.state.current_round >= self.config.total_rounds:
            self.state.status = "finished"
            self._save_state()
            self._broadcast_game_update(
                "game_state_update",
                {"status": "finished", "current_round": self.state.current_round},
            )
            return True

        # 开始新一轮
        self._start_new_round()
        return True

    def show_hint(self) -> Optional[str]:
        """显示下一个提示"""
        if not self.state.current_answer:
            return None
        word = self._get_current_word()
        if not word or not word.hints:
            return None

        if self.state.current_hints_shown < len(word.hints):
            hint = word.hints[self.state.current_hints_shown]
            self.state.current_hints_shown += 1
            self.state.current_hints = word.hints[: self.state.current_hints_shown]
            self._save_state()

            self._broadcast_game_update(
                "game_state_update",
                {
                    "status": self.state.status,
                    "current_round": self.state.current_round,
                    "hints_shown": self.state.current_hints,
                    "hints_shown_count": self.state.current_hints_shown,
                },
            )
            return hint
        return None

    def _start_new_round(self):
        """开始新一轮"""
        # 必须先检查是否已达到最大轮次，再递增轮次
        if self.state.current_round >= self.config.total_rounds:
            self.state.status = "finished"
            self._save_state()
            return

        self.state.current_round += 1
        self.current_round_guesses = []

        # 随机选择一个未使用的词
        word = self._select_next_word()
        if not word:
            self.state.status = "finished"
            self._save_state()
            return

        self.state.current_word_id = word.id
        self.state.current_answer = word.answer
        self.state.current_hints = []
        self.state.current_hints_shown = 0
        self.state.round_start_time = datetime.now().isoformat()
        self.state.round_end_time = None
        self.state.time_remaining = self.config.round_time_limit
        self.state.used_word_ids.append(word.id)

        # 创建轮次记录
        self.current_round_record = GameRoundRecord(
            round_id=str(uuid.uuid4()),
            round_number=self.state.current_round,
            answer=word.answer,
            start_time=datetime.now().isoformat(),
        )

        self._save_state()
        self._start_timer()

        self._broadcast_game_update(
            "game_new_round",
            {
                "status": "running",
                "current_round": self.state.current_round,
                "total_rounds": self.config.total_rounds,
                "answer_masked": "*" * len(word.answer),
                "answer_length": len(word.answer),
                "hints_available": len(word.hints),
                "time_remaining": self.config.round_time_limit,
                "category": word.category,
                "difficulty": word.difficulty,
                "hints": word.hints,
            },
        )

    def _select_next_word(self) -> Optional[WordBankEntry]:
        """按 sort_order 顺序选择下一个未使用的词"""
        active_words = self.get_active_words()
        # 按 sort_order 排序（没有 sort_order 的按 answer 排序作为 fallback）
        active_words.sort(key=lambda w: getattr(w, "sort_order", 9999) or 9999)

        unused_words = [w for w in active_words if w.id not in self.state.used_word_ids]

        if not unused_words:
            # 所有词都已使用过，重置顺序
            self.state.used_word_ids = []
            unused_words = active_words

        if not unused_words:
            return None

        # 取第一个（sort_order 最小的）
        return unused_words[0]

    def _get_current_word(self) -> Optional[WordBankEntry]:
        """获取当前词库条目"""
        if not self.state.current_word_id:
            return None
        for w in self.word_bank:
            if w.id == self.state.current_word_id:
                return w
        return None

    def _finish_current_round(
        self, winner: Optional[str] = None, winner_guess: Optional[str] = None
    ):
        """结束当前轮次"""
        self._stop_timer()

        if self.current_round_record:
            self.current_round_record.end_time = datetime.now().isoformat()
            self.current_round_record.winner = winner
            self.current_round_record.winner_guess = winner_guess
            self.current_round_record.total_guesses = len(self.current_round_guesses)
            self.current_round_record.guesses = self.current_round_guesses.copy()

            # 追加到历史
            self.game_history.append(self.current_round_record)
            self._save_history()

        self.state.round_end_time = datetime.now().isoformat()

    # ===== 观众问答处理 =====

    # 提问句式正则：匹配"是XXX吗"、"能XXX吗"、"可以XXX吗"、"属于XXX吗"、"算XXX吗"
    _QUESTION_PATTERN = re.compile(r"^(是|能|可以|属于|算)(.+?)吗[？?]?$")

    # 常见属性词到分类的映射（用于"能吃吗"、"能喝吗"等属性类提问）
    _ATTRIBUTE_CATEGORY_MAP = {
        "吃": {"食物"},
        "喝": {"饮品", "食物"},
        "穿": {"服装"},
        "用": {"工具", "电器", "家具"},
        "坐": {"家具"},
        "睡": {"家具"},
        "飞": {"动物", "交通"},
        "游": {"动物"},
        "跑": {"动物", "交通"},
        "看": {"电器"},
        "听": {"乐器", "电器"},
        "弹": {"乐器"},
        "骑": {"交通", "动物"},
        "开": {"交通", "电器"},
        "画": {"职业"},
        "写": {"工具", "职业"},
        "种": {"自然", "食物"},
        "养": {"动物"},
        "煮": {"食物", "工具"},
        "洗": {"电器", "工具"},
        "吹": {"乐器"},
    }

    def is_question(self, content: str) -> bool:
        """判断弹幕内容是否为提问类句式"""
        if not content or not content.strip():
            return False
        return bool(self._QUESTION_PATTERN.match(content.strip()))

    def _extract_question_keyword(self, content: str) -> str:
        """从提问内容中提取关键词（去掉句式前缀和疑问后缀）"""
        match = self._QUESTION_PATTERN.match(content.strip())
        if match:
            return match.group(2).strip()
        return ""

    def answer_question(self, content: str) -> str:
        """根据当前答案的分类，对提问自动回答'是'/'不是'/'不确定'"""
        if not self.state.current_answer:
            return "不确定"

        keyword = self._extract_question_keyword(content)
        if not keyword:
            return "不确定"

        # 获取提问关键词所属分类
        question_categories = self._get_categories(keyword)

        # 如果关键词本身就是分类名称，直接加入
        if keyword in self._SEMANTIC_CATEGORIES:
            question_categories.add(keyword)

        # 如果关键词是属性词，加入属性映射的分类
        if keyword in self._ATTRIBUTE_CATEGORY_MAP:
            question_categories.update(self._ATTRIBUTE_CATEGORY_MAP[keyword])

        # 获取当前答案所属分类
        answer_categories = self._get_categories(self.state.current_answer)

        if not question_categories:
            return "不确定"

        if not answer_categories:
            return "不确定"

        # 两个分类有交集 → "是"，无交集 → "不是"
        if question_categories & answer_categories:
            return "是"
        else:
            return "不是"

    def process_question(self, user_name: str, content: str) -> Optional[dict]:
        """处理观众提问弹幕，返回问答记录并广播"""
        if not self.is_running() or not self.state.current_answer:
            return None

        if not self.config.qa_enabled:
            return None

        answer_text = self.answer_question(content)

        qa_record = {
            "user_name": user_name,
            "question": content.strip(),
            "answer_text": answer_text,
            "timestamp": datetime.now().isoformat(),
        }

        print(f"[QA] 用户:{user_name} 提问:{content.strip()} → 回答:{answer_text}")

        # 广播问答消息给前端
        self._broadcast_game_update("game_new_question", qa_record)

        return qa_record

    # ===== 猜词处理 =====

    def process_guess(self, user_name: str, content: str) -> Optional[GuessRecord]:
        """处理用户猜词"""
        if not self.is_running() or not self.state.current_answer:
            return None

        if not content or not content.strip():
            return None

        guess = content.strip()
        answer = self.state.current_answer

        # 计算关联度（传入当前轮次的分类和提示词，用于语义算法的上下文相关性计算）
        category = ""
        hints = []
        if self.state.current_word_id:
            for word in self.word_bank:
                if word.id == self.state.current_word_id:
                    category = word.category or ""
                    hints = (
                        self.state.current_hints[: self.state.current_hints_shown]
                        if self.state.current_hints_shown > 0
                        else []
                    )
                    break
        similarity = self.calculate_similarity(
            guess, answer, category=category, hints=hints
        )
        is_correct = self._check_correct_answer(guess, answer)

        # 创建猜词记录
        record = GuessRecord(
            id=str(uuid.uuid4()),
            round_id=self.current_round_record.round_id
            if self.current_round_record
            else "",
            user_name=user_name,
            guess_content=guess,
            similarity_score=similarity,
            is_correct=is_correct,
            timestamp=datetime.now().isoformat(),
        )

        self.current_round_guesses.append(record)

        # 检测重复猜词
        guess_norm = self._normalize(guess)
        for existing in self.current_round_guesses[:-1]:
            if self._normalize(existing.guess_content) == guess_norm:
                self._broadcast_game_update(
                    "game_duplicate_guess",
                    {
                        "user_name": user_name,
                        "previous_user": existing.user_name,
                        "guess_content": guess,
                    },
                )
                break

        # 更新用户统计
        self._update_user_stats(user_name, similarity, is_correct, guess)

        # 更新排行榜
        self._update_rankings()

        # 广播新猜词（包含完整记录）
        self._broadcast_game_update("game_new_guess", record.model_dump())

        # 广播排行榜更新
        self._broadcast_game_update(
            "game_ranking_update",
            {
                "rankings": [
                    r.model_dump()
                    for r in self.current_rankings[: self.config.ranking_display_count]
                ]
            },
        )

        # 如果猜中
        if is_correct:
            self._handle_correct_answer(user_name, guess)

        return record

    def _check_correct_answer(self, guess: str, answer: str) -> bool:
        """检查是否完全匹配"""
        return self._normalize(guess) == self._normalize(answer)

    def _normalize(self, text: str) -> str:
        """文本标准化：去空格、转小写"""
        return text.strip().lower().replace(" ", "").replace("\t", "")

    def _handle_correct_answer(self, user_name: str, guess: str):
        """处理猜中事件"""
        self._finish_current_round(winner=user_name, winner_guess=guess)

        # 广播猜中事件
        self._broadcast_game_update(
            "game_correct_answer",
            {
                "user_name": user_name,
                "answer": self.state.current_answer,
                "guess_content": guess,
                "round_id": self.current_round_record.round_id
                if self.current_round_record
                else "",
                "popup_duration": self.config.popup_duration,
            },
        )

        # 检查是否还有下一轮
        if self.state.current_round >= self.config.total_rounds:
            # 游戏结束
            self.state.status = "finished"
            self._save_state()
            self._broadcast_game_update(
                "game_state_update",
                {"status": "finished", "current_round": self.state.current_round},
            )
            return

        # 自动下一轮或等待手动操作
        if self.config.auto_next_round:
            # 延迟开始下一轮（给弹窗显示时间）
            delay = self.config.popup_duration
            threading.Timer(delay, self._auto_next_round).start()
        else:
            self.state.status = "paused"
            self._save_state()

    def _auto_next_round(self):
        """自动开始下一轮"""
        if self.state.status in ("finished", "idle"):
            return
        self._start_new_round()

    # ===== 语义资源 =====

    # 偏旁部首映射表：常用汉字 → 偏旁部首
    _RADICAL_MAP = {
        # 木部（家具/植物相关）
        "椅": "木",
        "桌": "木",
        "凳": "木",
        "柜": "木",
        "床": "木",
        "板": "木",
        "树": "木",
        "林": "木",
        "森": "木",
        "桥": "木",
        "楼": "木",
        "梯": "木",
        "栏": "木",
        "杆": "木",
        "枝": "木",
        "根": "木",
        "桃": "木",
        "李": "木",
        "梅": "木",
        "柳": "木",
        "杨": "木",
        "松": "木",
        "柏": "木",
        "枫": "木",
        "桐": "木",
        "棉": "木",
        "棋": "木",
        "桶": "木",
        "棒": "木",
        "棕": "木",
        "槽": "木",
        "槽": "木",
        "橙": "木",
        "桂": "木",
        "檀": "木",
        "梳": "木",
        "检": "木",
        "查": "木",
        "核": "木",
        "样": "木",
        "格": "木",
        "根": "木",
        "框": "木",
        "梁": "木",
        "梢": "木",
        "梭": "木",
        "棚": "木",
        "棠": "木",
        "梨": "木",
        "柿": "木",
        "樱": "木",
        "榆": "木",
        "榕": "木",
        "樟": "木",
        "檀": "木",
        # 水部（液体/河流相关）
        "酒": "水",
        "汁": "水",
        "汤": "水",
        "河": "水",
        "湖": "水",
        "海": "水",
        "洋": "水",
        "江": "水",
        "溪": "水",
        "池": "水",
        "波": "水",
        "浪": "水",
        "潮": "水",
        "洗": "水",
        "清": "水",
        "洁": "水",
        "湿": "水",
        "满": "水",
        "漂": "水",
        "游": "水",
        "泳": "水",
        "汗": "水",
        "泪": "水",
        "滴": "水",
        "油": "水",
        "漆": "水",
        "漫": "水",
        "没": "水",
        "沉": "水",
        "浮": "水",
        "淡": "水",
        "深": "水",
        "浅": "水",
        "温": "水",
        "凉": "水",
        "冷": "水",
        "冰": "水",
        "冻": "水",
        "沸": "水",
        "泡": "水",
        "沫": "水",
        "泥": "水",
        "沙": "水",
        "滩": "水",
        "港": "水",
        "湾": "水",
        "汽": "水",
        "渴": "水",
        "洒": "水",
        "泼": "水",
        "浇": "水",
        "灌": "水",
        "汛": "水",
        "泄": "水",
        "洪": "水",
        # 火部（热/光相关）
        "火": "火",
        "灯": "火",
        "炉": "火",
        "烟": "火",
        "烧": "火",
        "烤": "火",
        "炒": "火",
        "炸": "火",
        "爆": "火",
        "燃": "火",
        "焰": "火",
        "烛": "火",
        "烘": "火",
        "烦": "火",
        "烫": "火",
        "热": "火",
        "暖": "火",
        "照": "火",
        "耀": "火",
        "辉": "火",
        "煌": "火",
        "煤": "火",
        "炭": "火",
        "炎": "火",
        "炫": "火",
        "烁": "火",
        "烽": "火",
        # 土部（地面/建筑相关）
        "地": "土",
        "场": "土",
        "城": "土",
        "墙": "土",
        "塔": "土",
        "基": "土",
        "堆": "土",
        "块": "土",
        "坛": "土",
        "坡": "土",
        "坎": "土",
        "坝": "土",
        "填": "土",
        "塞": "土",
        "墨": "土",
        "壁": "土",
        "墩": "土",
        "墓": "土",
        "尘": "土",
        "境": "土",
        "增": "土",
        "塑": "土",
        "垫": "土",
        "垫": "土",
        # 金部（金属/工具相关）
        "铁": "金",
        "钢": "金",
        "铜": "金",
        "银": "金",
        "钱": "金",
        "针": "金",
        "钉": "金",
        "锅": "金",
        "刀": "金",
        "剑": "金",
        "锁": "金",
        "链": "金",
        "钟": "金",
        "铃": "金",
        "镜": "金",
        "钻": "金",
        "锤": "金",
        "铲": "金",
        "钩": "金",
        "钮": "金",
        "锋": "金",
        "锡": "金",
        "铝": "金",
        "铅": "金",
        "铸": "金",
        "锻": "金",
        "镶": "金",
        "锋": "金",
        # 丝部（纺织/颜色相关）
        "红": "丝",
        "绿": "丝",
        "蓝": "丝",
        "紫": "丝",
        "白": "丝",
        "黑": "丝",
        "黄": "丝",
        "灰": "丝",
        "粉": "丝",
        "线": "丝",
        "绳": "丝",
        "织": "丝",
        "绣": "丝",
        "绸": "丝",
        "缎": "丝",
        "纱": "丝",
        "绢": "丝",
        "绘": "丝",
        "绑": "丝",
        "缝": "丝",
        "缠": "丝",
        "编": "丝",
        "维": "丝",
        "纲": "丝",
        "纲": "丝",
        # 口部（嘴/吃喝相关）
        "吃": "口",
        "喝": "口",
        "唱": "口",
        "叫": "口",
        "喊": "口",
        "吹": "口",
        "咬": "口",
        "味": "口",
        "吐": "口",
        "吸": "口",
        "呼": "口",
        "叹": "口",
        "吵": "口",
        "告": "口",
        "听": "口",
        "问": "口",
        "答": "口",
        "嘴": "口",
        "唇": "口",
        "喉": "口",
        "吻": "口",
        "咖": "口",
        "啡": "口",
        "啤": "口",
        "喂": "口",
        "吗": "口",
        "呢": "口",
        "呀": "口",
        # 手部（动作相关）
        "打": "手",
        "抓": "手",
        "拿": "手",
        "推": "手",
        "拉": "手",
        "提": "手",
        "按": "手",
        "拍": "手",
        "摸": "手",
        "抱": "手",
        "摔": "手",
        "拔": "手",
        "挑": "手",
        "指": "手",
        "掌": "手",
        "拳": "手",
        "握": "手",
        "托": "手",
        "扶": "手",
        "搓": "手",
        "揉": "手",
        "捏": "手",
        "掐": "手",
        "扔": "手",
        "投": "手",
        "接": "手",
        "扣": "手",
        "挂": "手",
        # 足部（行走相关）
        "跑": "足",
        "走": "足",
        "跳": "足",
        "踢": "足",
        "踩": "足",
        "踏": "足",
        "跨": "足",
        "跃": "足",
        "跌": "足",
        "跪": "足",
        "蹲": "足",
        "蹈": "足",
        "践": "足",
        "踪": "足",
        "路": "足",
        "跟": "足",
        "蹄": "足",
        "距": "足",
        # 日部（时间/太阳相关）
        "明": "日",
        "暗": "日",
        "晴": "日",
        "晨": "日",
        "晚": "日",
        "昨": "日",
        "今": "日",
        "时": "日",
        "间": "日",
        "期": "日",
        "星": "日",
        "春": "日",
        "夏": "日",
        "秋": "日",
        "冬": "日",
        "旱": "日",
        "晒": "日",
        "暖": "日",
        "曙": "日",
        "暮": "日",
        "昼": "日",
        # 月部（月亮/肉相关）
        "月": "月",
        "脑": "月",
        "腿": "月",
        "脚": "月",
        "脸": "月",
        "背": "月",
        "肚": "月",
        "臂": "月",
        "肩": "月",
        "肝": "月",
        "胆": "月",
        "肠": "月",
        "胃": "月",
        "肾": "月",
        "胖": "月",
        "肥": "月",
        "胶": "月",
        "腊": "月",
        "朦": "月",
        "胧": "月",
        # 草部（植物相关）
        "花": "草",
        "草": "草",
        "茶": "草",
        "药": "草",
        "菜": "草",
        "果": "草",
        "苗": "草",
        "莲": "草",
        "荷": "草",
        "菊": "草",
        "兰": "草",
        "芦": "草",
        "蕉": "草",
        "芒": "草",
        "菇": "草",
        "葱": "草",
        "蒜": "草",
        "蓝": "草",
        "苦": "草",
        "甜": "草",
        "芬": "草",
        "芳": "草",
        "芽": "草",
        "茂": "草",
        "茎": "草",
        "藤": "草",
        "萝": "草",
        "葡": "草",
        # 石部（石头/矿物相关）
        "石": "石",
        "岩": "石",
        "矿": "石",
        "砖": "石",
        "碑": "石",
        "碗": "石",
        "碟": "石",
        "砚": "石",
        "砂": "石",
        "碎": "石",
        "硬": "石",
        "确": "石",
        "破": "石",
        "砸": "石",
        # 虫部（昆虫相关）
        "虫": "虫",
        "蝶": "虫",
        "蜂": "虫",
        "蚁": "虫",
        "蚊": "虫",
        "蝇": "虫",
        "蛇": "虫",
        "蛙": "虫",
        "虾": "虫",
        "蟹": "虫",
        "蛛": "虫",
        "蝉": "虫",
        "蚕": "虫",
        "蛾": "虫",
        # 鸟部（鸟类相关）
        "鸡": "鸟",
        "鸭": "鸟",
        "鹅": "鸟",
        "鸽": "鸟",
        "鹰": "鸟",
        "燕": "鸟",
        "鹤": "鸟",
        "雀": "鸟",
        "鸦": "鸟",
        "鸥": "鸟",
        "鹦": "鸟",
        "鹊": "鸟",
        "雁": "鸟",
        # 鱼部（鱼类相关）
        "鱼": "鱼",
        "鲤": "鱼",
        "鲨": "鱼",
        "鲸": "鱼",
        "鲜": "鱼",
        "鲍": "鱼",
        "鳗": "鱼",
        "鳞": "鱼",
        "鳍": "鱼",
        "鳃": "鱼",
        # 车部（交通相关）
        "车": "车",
        "轮": "车",
        "轨": "车",
        "转": "车",
        "载": "车",
        "辆": "车",
        "驾": "车",
        "驶": "车",
        "输": "车",
        "轿": "车",
        "辆": "车",
        "辙": "车",
        # 门部（门/建筑相关）
        "门": "门",
        "窗": "门",
        "闭": "门",
        "开": "门",
        "关": "门",
        "闪": "门",
        "闯": "门",
        "阁": "门",
        "阔": "门",
        "闸": "门",
        "阅": "门",
        # 心部（情感相关）
        "心": "心",
        "情": "心",
        "爱": "心",
        "恨": "心",
        "想": "心",
        "念": "心",
        "思": "心",
        "意": "心",
        "愿": "心",
        "愁": "心",
        "怒": "心",
        "惊": "心",
        "怕": "心",
        "忆": "心",
        "懂": "心",
        "懒": "心",
        "惯": "心",
        "慢": "心",
        "息": "心",
        "悦": "心",
        "惜": "心",
        "悲": "心",
        "愁": "心",
        "慧": "心",
        "慰": "心",
        "恳": "心",
        # 食部（食物相关）
        "饭": "食",
        "饼": "食",
        "饵": "食",
        "饺": "食",
        "馒": "食",
        "饲": "食",
        "饰": "食",
        "馆": "食",
        "餐": "食",
        "馈": "食",
        # 衣部（服装相关）
        "衣": "衣",
        "裤": "衣",
        "裙": "衣",
        "衫": "衣",
        "袍": "衣",
        "被": "衣",
        "衬": "衣",
        "袜": "衣",
        "袖": "衣",
        "领": "衣",
        "袋": "衣",
        "装": "衣",
        "裹": "衣",
        "初": "衣",
        # 竹部（竹制品相关）
        "竹": "竹",
        "笔": "竹",
        "筒": "竹",
        "篮": "竹",
        "筐": "竹",
        "笛": "竹",
        "竿": "竹",
        "笋": "竹",
        "箩": "竹",
        "筷": "竹",
        "筛": "竹",
        "简": "竹",
        "篇": "竹",
        "籍": "竹",
        # 犬部（动物相关）
        "狗": "犬",
        "猫": "犬",
        "猪": "犬",
        "狼": "犬",
        "狐": "犬",
        "狮": "犬",
        "猎": "犬",
        "猛": "犬",
        "兽": "犬",
        # 女部（女性相关）
        "女": "女",
        "妈": "女",
        "姐": "女",
        "妹": "女",
        "奶": "女",
        "姑": "女",
        "娘": "女",
        "姨": "女",
        "嫂": "女",
        "妇": "女",
        "婚": "女",
        "嫁": "女",
        "娇": "女",
        "妙": "女",
        # 雨部（天气相关）
        "雨": "雨",
        "雪": "雨",
        "雷": "雨",
        "雾": "雨",
        "露": "雨",
        "霜": "雨",
        "霞": "雨",
        "霸": "雨",
        "零": "雨",
        "需": "雨",
        "震": "雨",
        # 贝部（财物相关）
        "财": "贝",
        "贵": "贝",
        "贪": "贝",
        "贫": "贝",
        "货": "贝",
        "购": "贝",
        "贩": "贝",
        "赚": "贝",
        "赔": "贝",
        "赠": "贝",
        "赏": "贝",
        "赐": "贝",
        "贼": "贝",
        "赋": "贝",
        # 禾部（农作物相关）
        "禾": "禾",
        "稻": "禾",
        "穗": "禾",
        "秧": "禾",
        "稼": "禾",
        "秋": "禾",
        "种": "禾",
        "积": "禾",
        "程": "禾",
        "秀": "禾",
        "秒": "禾",
        "秘": "禾",
        "租": "禾",
        # 马部（马/速度相关）
        "马": "马",
        "骑": "马",
        "驾": "马",
        "驰": "马",
        "骏": "马",
        "骤": "马",
        "骄": "马",
        "验": "马",
        "骗": "马",
        "腾": "马",
    }

    # 语义类别词典：类别名 → 代表词集合
    _SEMANTIC_CATEGORIES = {
        "家具": {
            "椅",
            "桌",
            "凳",
            "柜",
            "床",
            "沙发",
            "书架",
            "茶几",
            "衣柜",
            "鞋柜",
            "梳妆",
            "屏风",
            "架",
            "案",
            "榻",
            "垫",
            "席",
            "枕",
            "被",
            "毯",
        },
        "食物": {
            "饭",
            "面",
            "米",
            "肉",
            "鱼",
            "鸡",
            "鸭",
            "菜",
            "汤",
            "饼",
            "饺",
            "包",
            "糕",
            "糖",
            "果",
            "蛋",
            "奶",
            "茶",
            "粥",
            "粉",
            "虾",
            "蟹",
            "牛",
            "羊",
            "猪",
            "豆腐",
            "肠",
            "翅",
            "腿",
            "排",
            # 水果类补充
            "苹果",
            "橘子",
            "橙子",
            "梨子",
            "香蕉",
            "葡萄",
            "西瓜",
            "草莓",
            "桃子",
            "李子",
            "杏子",
            "樱桃",
            "芒果",
            "菠萝",
            "柚子",
            "柿子",
            "柠檬",
            "荔枝",
            "龙眼",
            "榴莲",
            "猕猴桃",
            "枣",
        },
        "饮品": {
            "水",
            "酒",
            "茶",
            "汁",
            "奶",
            "咖啡",
            "啤",
            "饮料",
            "汤",
            "浆",
            "醋",
            "油",
            "酱",
        },
        "颜色": {
            "红",
            "绿",
            "蓝",
            "黄",
            "白",
            "黑",
            "紫",
            "灰",
            "粉",
            "橙",
            "棕",
            "青",
            "金",
            "银",
            "彩",
            "色",
        },
        "动物": {
            "狗",
            "猫",
            "鸟",
            "鱼",
            "马",
            "牛",
            "羊",
            "猪",
            "鸡",
            "鸭",
            "虎",
            "龙",
            "蛇",
            "兔",
            "鼠",
            "猴",
            "象",
            "狮",
            "豹",
            "鹿",
            "熊",
            "狼",
            "狐",
            "鹰",
            "鹤",
            "蝶",
            "蜂",
            "蚁",
            "蚊",
            "蛙",
        },
        "交通": {
            "车",
            "船",
            "飞机",
            "火车",
            "地铁",
            "公交",
            "自行车",
            "摩托",
            "出租",
            "桥",
            "路",
            "站",
            "港",
            "轨",
            "轮",
            "驾",
        },
        "服装": {
            "衣",
            "裤",
            "裙",
            "帽",
            "鞋",
            "袜",
            "衫",
            "袍",
            "领",
            "袖",
            "带",
            "巾",
            "围",
            "手套",
            "背心",
            "外套",
            "大衣",
            "西装",
        },
        "天气": {
            "晴",
            "阴",
            "雨",
            "雪",
            "风",
            "云",
            "雷",
            "雾",
            "霜",
            "露",
            "冰",
            "虹",
            "霞",
            "暴",
            "旱",
            "涝",
        },
        "建筑": {
            "房",
            "楼",
            "塔",
            "桥",
            "墙",
            "门",
            "窗",
            "院",
            "亭",
            "阁",
            "殿",
            "庙",
            "寺",
            "宫",
            "堡",
            "坝",
            "堤",
            "井",
        },
        "工具": {
            "刀",
            "锤",
            "钳",
            "锯",
            "钉",
            "针",
            "线",
            "绳",
            "尺",
            "秤",
            "锁",
            "钥匙",
            "铲",
            "斧",
            "扳手",
            "刷",
            "胶",
            "漆",
        },
        "身体": {
            "头",
            "手",
            "脚",
            "眼",
            "耳",
            "鼻",
            "口",
            "心",
            "腿",
            "臂",
            "肩",
            "背",
            "腰",
            "肚",
            "脸",
            "发",
            "指",
            "掌",
            "拳",
            "骨",
        },
        "自然": {
            "山",
            "水",
            "河",
            "湖",
            "海",
            "树",
            "花",
            "草",
            "石",
            "土",
            "沙",
            "冰",
            "火",
            "风",
            "云",
            "雨",
            "雪",
            "日",
            "月",
            "星",
            "天",
            "地",
            "泉",
            "瀑",
            "岛",
            "谷",
            "洞",
            "林",
            "森",
        },
        "电器": {
            "灯",
            "电视",
            "冰箱",
            "空调",
            "电脑",
            "手机",
            "风扇",
            "洗衣机",
            "微波",
            "烤箱",
            "热水",
            "音响",
            "相机",
            "钟",
            "表",
        },
        "乐器": {
            "琴",
            "鼓",
            "笛",
            "箫",
            "筝",
            "琵琶",
            "吉他",
            "号",
            "铃",
            "锣",
            "钹",
            "笙",
            "埙",
            "二胡",
            "提琴",
        },
        "职业": {
            "医生",
            "老师",
            "警察",
            "工人",
            "农民",
            "司机",
            "厨师",
            "律师",
            "记者",
            "演员",
            "歌手",
            "画家",
            "作家",
            "工程师",
            "护士",
        },
    }

    # 同义词/近义词组
    _SYNONYM_GROUPS = [
        {"凳", "椅", "座", "座位"},
        {"桌", "台", "案"},
        {"床", "铺", "榻"},
        {"柜", "橱", "箱"},
        {"房", "屋", "室", "宅"},
        {"车", "辆", "驾"},
        {"船", "舟", "艇"},
        {"刀", "剑", "刃"},
        {"狗", "犬"},
        {"猪", "豕"},
        {"牛", "犊"},
        {"马", "驹"},
        {"饭", "餐", "食"},
        {"酒", "酿", "醇"},
        {"茶", "茗"},
        {"衣", "服", "裳"},
        {"鞋", "履"},
        {"帽", "冠"},
        {"路", "道", "途", "径"},
        {"河", "江", "溪"},
        {"海", "洋"},
        {"山", "岭", "峰", "岳"},
        {"树", "木", "林"},
        {"花", "朵", "葩"},
        {"草", "卉"},
        {"石", "岩", "矿"},
        {"红", "赤"},
        {"绿", "青", "翠"},
        {"蓝", "靛"},
        {"白", "素"},
        {"黑", "乌", "墨"},
        {"黄", "金"},
        {"大", "巨", "伟"},
        {"小", "微", "细"},
        {"好", "佳", "优"},
        {"坏", "差", "劣"},
        {"快", "速", "疾"},
        {"慢", "缓", "迟"},
        {"高", "耸"},
        {"低", "矮"},
        {"长", "久"},
        {"短", "暂"},
        {"新", "鲜"},
        {"旧", "老", "陈"},
        {"热", "烫", "炎"},
        {"冷", "凉", "寒", "冰"},
        {"笑", "乐", "欢"},
        {"哭", "泣", "泪"},
        {"跑", "奔"},
        {"走", "行"},
        {"看", "观", "视", "望"},
        {"听", "闻"},
        {"说", "讲", "言", "语", "道"},
        {"吃", "食", "餐"},
        {"喝", "饮"},
        {"买", "购"},
        {"卖", "售"},
    ]

    # ===== 增强版关联度计算 =====

    def calculate_similarity(
        self,
        guess: str,
        answer: str,
        category: str = "",
        hints: Optional[List[str]] = None,
    ) -> float:
        """
        综合关联度计算 (0-100分)

        支持五种算法：
        - hybrid: 混合加权算法（编辑距离+拼音+子串+长度）
        - semantic: 语义算法（语义相似度+关键词匹配+拼音+编辑距离+上下文+长度）
        - enhanced: 增强语义算法（多维度关联+场景关联+权重优化）
        - edit_distance: 纯编辑距离
        - pinyin: 纯拼音匹配
        - embedding: 本地 Embedding 模型（BGE-zh 向量余弦相似度）
        """
        # 完全匹配
        if self._normalize(guess) == self._normalize(answer):
            return 100.0

        guess_norm = self._normalize(guess)
        answer_norm = self._normalize(answer)

        if not guess_norm or not answer_norm:
            return 0.0

        algorithm = self.config.similarity_algorithm

        # 性能计时
        start = time.perf_counter()
        try:
            if algorithm == "embedding":
                # 走 Embedding 路径，未就绪则降级到 enhanced
                if (
                    self._embedding_similarity is not None
                    and self._embedding_engine is not None
                    and self._embedding_engine.is_ready
                ):
                    score = self._embedding_similarity.calculate(
                        guess_norm, answer_norm, category, hints
                    )
                else:
                    score = self._enhanced_score(guess_norm, answer_norm, category, hints)
            elif algorithm == "enhanced":
                # 增强语义算法：多维度关联+场景关联+权重优化
                score = self._enhanced_score(guess_norm, answer_norm, category, hints)
            elif algorithm == "edit_distance":
                score = self._edit_distance_similarity(guess_norm, answer_norm)
            elif algorithm == "pinyin":
                score = self._pinyin_similarity(guess_norm, answer_norm)
            elif algorithm == "semantic":
                # 语义算法：6维度加权（传统版）
                score = self._semantic_score_legacy(guess_norm, answer_norm, category, hints)
            else:
                # hybrid 混合算法
                score = self._hybrid_score(guess_norm, answer_norm)

            # 最高99.9，保留100给完全匹配
            final_score = round(min(score, 99.9), 1)
            return final_score
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            self._record_similarity_perf(algorithm, elapsed_ms)

    def _enhanced_score(
        self,
        guess_norm: str,
        answer_norm: str,
        category: str = "",
        hints: Optional[List[str]] = None,
    ) -> float:
        """
        增强语义算法：多维度关联+场景关联+权重优化

        权重设计理念：
        - 同义词关联 (25%): 高权重，语义关联的核心信号
        - 类别归属 (20%): 中高权重，类别匹配是强关联
        - 场景关联 (15%): 新增维度，生活场景关联
        - 提示词匹配 (15%): 上下文引导
        - 拼音相似度 (10%): 语音层面的关联
        - 编辑距离 (10%): 字形层面的关联
        - 偏旁部首 (5%): 辅助识别，权重降低
        """
        # 1. 同义词关联 (0-100)
        synonym_score = self._synonym_similarity(guess_norm, answer_norm) * 0.25

        # 2. 语义类别归属 (0-100)
        category_score = self._category_similarity(guess_norm, answer_norm) * 0.20

        # 3. 场景关联 (0-100) - 新增
        scene_score = self._scene_association_score(guess_norm, answer_norm) * 0.15

        # 4. 提示词匹配 (0-100)
        hint_score = self._hint_match_score(guess_norm, answer_norm, category, hints) * 0.15

        # 5. 拼音相似度 (0-100)
        pinyin_score = self._pinyin_similarity(guess_norm, answer_norm) * 0.10

        # 6. 编辑距离 (0-100)
        edit_score = self._edit_distance_similarity(guess_norm, answer_norm) * 0.10

        # 7. 偏旁部首 (0-100) - 降低权重
        radical_score = self._radical_similarity(guess_norm, answer_norm) * 0.05

        # 组合得分
        raw_score = (
            synonym_score
            + category_score
            + scene_score
            + hint_score
            + pinyin_score
            + edit_score
            + radical_score
        )

        # 跨类别惩罚
        penalty = self._cross_category_penalty(guess_norm, answer_norm)
        score = raw_score * penalty

        # ===== 优先级处理：特殊关联给予高分 =====
        # 1. 同义词匹配：直接返回高分（目标70分）
        if synonym_score >= 18.75:  # 75 * 0.25
            # 同义词基础分65，加上类别和编辑辅助（控制在70分左右）
            category_bonus = self._category_similarity(guess_norm, answer_norm) * 0.05
            edit_bonus = self._edit_distance_similarity(guess_norm, answer_norm) * 0.03
            score = max(score, 65.0 + category_bonus + edit_bonus)

        # 2. 场景强关联：权重提升（目标40分）
        elif scene_score >= 10.5:  # 70 * 0.15
            scene_base = self._scene_association_score(guess_norm, answer_norm)
            if scene_base >= 70.0:
                # 场景强关联，权重55%
                category_bonus = self._category_similarity(guess_norm, answer_norm) * 0.10
                edit_bonus = self._edit_distance_similarity(guess_norm, answer_norm) * 0.05
                score = max(score, scene_base * 0.55 + category_bonus + edit_bonus)

        # 3. 跨类别但有偏旁关联：给予部分关联分（目标30分）
        elif penalty < 1.0 and radical_score >= 4.0:  # 80 * 0.05
            radical_base = self._radical_similarity(guess_norm, answer_norm)
            if radical_base >= 80.0:
                # 跨类别但有共同偏旁，给予25分基础关联
                char_overlap = self._char_overlap_score_internal(guess_norm, answer_norm) * 0.08
                edit_bonus = self._edit_distance_similarity(guess_norm, answer_norm) * 0.03
                score = max(score, 25.0 + radical_score + edit_bonus + char_overlap)

        return min(99.9, score)

    def _char_overlap_score_internal(self, s1: str, s2: str) -> float:
        """字符重叠度得分（内部方法）"""
        if not s1 or not s2:
            return 0.0
        set1 = set(s1)
        set2 = set(s2)
        overlap = len(set1 & set2)
        total = len(set1 | set2)
        if total == 0:
            return 0.0
        return (overlap / total) * 100

    def _semantic_score_legacy(
        self,
        guess_norm: str,
        answer_norm: str,
        category: str = "",
        hints: Optional[List[str]] = None,
    ) -> float:
        """语义算法（传统版）：6维度加权"""
        semantic_score = self._semantic_similarity(guess_norm, answer_norm) * 0.25
        keyword_score = self._keyword_match_score(guess_norm, answer_norm) * 0.20
        pinyin_score = self._pinyin_similarity(guess_norm, answer_norm) * 0.20
        edit_score = self._edit_distance_similarity(guess_norm, answer_norm) * 0.15
        context_score = (
            self._context_relevance_score(guess_norm, answer_norm, category, hints)
            * 0.10
        )
        length_score = self._length_similarity(guess_norm, answer_norm) * 0.10
        score = (
            semantic_score
            + keyword_score
            + pinyin_score
            + edit_score
            + context_score
            + length_score
        )
        penalty = self._cross_category_penalty(guess_norm, answer_norm)
        return score * penalty

    # ===== 增强维度：场景关联 =====

    def _scene_association_score(self, guess: str, answer: str) -> float:
        """
        场景关联得分：基于生活场景的关联性

        场景关联指两个词在日常生活中经常一起出现或有因果关系
        例如：医院-生病、餐厅-吃饭、教室-学习
        """
        # 场景关联词典：主场景词 -> 关联词集合
        SCENE_ASSOCIATIONS = {
            "餐厅": {"吃饭", "厨师", "菜单", "餐具", "桌椅", "菜单", "订餐", "外卖", "美食", "品尝", "烹饪", "厨房", "菜", "肉", "汤", "面", "饭", "吃", "喝"},
            "医院": {"生病", "医生", "护士", "药品", "手术", "病房", "挂号", "体检", "治疗", "感冒", "发烧", "伤口", "检查", "看病", "药", "针", "病床"},
            "学校": {"学习", "老师", "学生", "教室", "课本", "考试", "作业", "上课", "下课", "操场", "图书", "课堂", "黑板", "课桌", "椅", "笔", "本子"},
            "超市": {"购物", "付款", "购物车", "商品", "货架", "收银", "食品", "日用品", "蔬菜", "水果", "饮料", "零食", "买", "推车", "排队"},
            "家庭": {"客厅", "卧室", "厨房", "浴室", "沙发", "床", "电视", "空调", "冰箱", "洗衣机", "家具", "家人", "吃饭", "睡觉", "休息", "住"},
            "办公": {"电脑", "文件", "会议", "打印机", "电话", "办公桌", "椅子", "同事", "老板", "工作", "加班", "处理", "签字", "合同", "报告"},
            "交通": {"汽车", "火车", "飞机", "公交", "地铁", "自行车", "出租", "驾驶", "乘客", "车站", "机场", "站台", "票", "座位", "路", "行驶"},
            "运动": {"跑步", "篮球", "足球", "游泳", "健身", "操场", "球场", "教练", "比赛", "运动员", "体育", "锻炼", "体能", "运动", "跑", "跳"},
            "娱乐": {"电影", "音乐", "游戏", "电视", "综艺", "演唱会", "追剧", "影城", "KTV", "剧场", "观看", "欣赏", "播放", "演员", "剧情"},
            "旅行": {"酒店", "机票", "景点", "拍照", "行李", "地图", "导游", "护照", "签证", "海滩", "山", "城市", "观光", "度假", "风景", "游客"},
            "自然": {"天空", "大地", "山河", "树木", "花草", "动物", "空气", "阳光", "雨水", "云", "风", "四季", "季节", "春天", "夏天", "秋天", "冬天"},
            "水果": {"苹果", "香蕉", "橙子", "葡萄", "西瓜", "草莓", "桃子", "梨", "樱桃", "芒果", "柚子", "荔枝", "新鲜", "甜", "酸", "多汁", "果肉"},
            "蔬菜": {"白菜", "萝卜", "黄瓜", "番茄", "土豆", "茄子", "青椒", "豆角", "菠菜", "芹菜", "油菜", "生菜", "西兰花", "菜", "绿色", "新鲜"},
            "动物": {"猫", "狗", "鸟", "鱼", "兔子", "乌龟", "仓鼠", "宠物", "家养", "野生", "可爱", "毛", "羽毛", "爪子", "尾巴", "奔跑", "飞翔"},
            "天气": {"晴天", "雨天", "阴天", "雪天", "刮风", "雷电", "彩虹", "温度", "气温", "气候", "季节", "闷热", "寒冷", "凉爽", "温暖", "暴风雨"},
            "颜色": {"红色", "蓝色", "绿色", "黄色", "白色", "黑色", "紫色", "粉色", "橙色", "棕色", "彩色", "鲜艳", "暗淡", "明亮", "深", "浅"},
            "职业": {"医生", "老师", "警察", "工程师", "律师", "护士", "厨师", "司机", "农民", "工人", "记者", "演员", "歌手", "画家", "作家", "消防员"},
            "电器": {"电视", "冰箱", "空调", "洗衣机", "电脑", "手机", "风扇", "微波炉", "烤箱", "热水器", "音响", "相机", "开关", "电源", "遥控"},
            "家具": {"桌子", "椅子", "沙发", "床", "衣柜", "书架", "茶几", "柜子", "凳子", "橱柜", "梳妆台", "屏风", "床垫", "沙发", "靠垫", "窗帘"},
            "服装": {"衣服", "裤子", "裙子", "鞋子", "帽子", "袜子", "外套", "内衣", "衬衫", "T恤", "西装", "大衣", "羽绒服", "运动服", "穿戴", "时尚"},
        }

        score = 0.0

        # 双向检查：guess的场景关联词是否包含answer，或answer的场景关联词是否包含guess
        for scene, related_words in SCENE_ASSOCIATIONS.items():
            # 场景词本身匹配
            if guess == scene or answer == scene:
                if guess in related_words or answer in related_words:
                    return 70.0

            # 双向关联检查
            guess_in_scene = guess in related_words
            answer_in_scene = answer in related_words
            same_scene = (guess in SCENE_ASSOCIATIONS and answer in SCENE_ASSOCIATIONS.get(guess, set())) or \
                         (answer in SCENE_ASSOCIATIONS and guess in SCENE_ASSOCIATIONS.get(answer, set()))

            if guess_in_scene and answer_in_scene:
                # 同一场景的关联词
                score = max(score, 60.0)
            elif same_scene:
                score = max(score, 50.0)

        # 检查是否有共同的场景
        guess_scenes = {scene for scene, words in SCENE_ASSOCIATIONS.items()
                       if guess in words or scene == guess}
        answer_scenes = {scene for scene, words in SCENE_ASSOCIATIONS.items()
                       if answer in words or scene == answer}

        common_scenes = guess_scenes & answer_scenes
        if common_scenes:
            score = max(score, 55.0)

        return min(score, 70.0)

    def _hint_match_score(
        self,
        guess: str,
        answer: str,
        category: str = "",
        hints: Optional[List[str]] = None,
    ) -> float:
        """提示词匹配得分（优化版）"""
        score = 0.0

        # 1. 分类相关性（提供上下文线索）
        if category:
            guess_cats = self._get_categories(guess)
            answer_cats = self._get_categories(answer)
            # 猜词属于答案的类别
            if guess in answer_cats or any(cat in guess for cat in [category] if category in guess_cats):
                score += 35.0
            # 答案属于猜词的类别
            elif answer in guess_cats:
                score += 25.0
            # 同类别
            elif guess_cats and answer_cats and guess_cats & answer_cats:
                score += 15.0

        # 2. 提示词相关性（更精细的匹配）
        if hints:
            matched_hints = 0
            for hint in hints:
                hint_norm = self._normalize(hint)
                if not hint_norm:
                    continue

                # 完全包含
                if hint_norm in guess:
                    score += 25.0
                    matched_hints += 1
                # 部分字符匹配
                elif any(c in guess for c in hint_norm if len(c) > 1):
                    score += 10.0
                    matched_hints += 0.5
                # 反向匹配：猜词包含提示
                elif guess in hint_norm:
                    score += 15.0
                    matched_hints += 0.5

            # 多个提示词匹配bonus
            if matched_hints >= 2:
                score *= 1.2

        return min(score, 90.0)

    def _hybrid_score(self, guess_norm: str, answer_norm: str) -> float:
        """hybrid 混合算法（独立方法，供 embedding 降级复用）"""
        edit_score = self._edit_distance_similarity(guess_norm, answer_norm) * 0.4
        pinyin_score = self._pinyin_similarity(guess_norm, answer_norm) * 0.3
        contain_score = self._containment_score(guess_norm, answer_norm) * 0.2
        length_score = self._length_similarity(guess_norm, answer_norm) * 0.1
        return edit_score + pinyin_score + contain_score + length_score

    def _semantic_similarity(self, s1: str, s2: str) -> float:
        """基于偏旁部首和语义类别的语义相似度（重构版）"""
        if not s1 or not s2:
            return 0.0

        # 1. 偏旁部首关联（降低权重：0.4→0.2，避免偏旁误判）
        radical_score = self._radical_similarity(s1, s2)

        # 2. 语义类别关联（提高权重：0.35→0.45，类别是更可靠的信号）
        category_score = self._category_similarity(s1, s2)

        # 3. 同义词关联（保持不变）
        synonym_score = self._synonym_similarity(s1, s2)

        # 组合得分（跨类别惩罚已移至 calculate_similarity 最终得分层统一处理）
        base_score = max(
            radical_score * 0.2 + category_score * 0.45 + synonym_score * 0.35,
            synonym_score,  # 同义词直接取最高
        )

        return base_score

    def _radical_similarity(self, s1: str, s2: str) -> float:
        """基于偏旁部首的相似度（优化版：添加类别校验）"""
        # 获取两个字符串中每个字的偏旁
        radicals1 = [self._RADICAL_MAP.get(c) for c in s1 if c in self._RADICAL_MAP]
        radicals2 = [self._RADICAL_MAP.get(c) for c in s2 if c in self._RADICAL_MAP]

        if not radicals1 or not radicals2:
            return 0.0

        # 计算共同偏旁比例
        set1 = set(radicals1)
        set2 = set(radicals2)
        common = set1 & set2

        if not common:
            return 0.0

        # 共同偏旁占较小集合的比例
        overlap_ratio = len(common) / min(len(set1), len(set2))

        # 类别校验：如果偏旁相同但语义类别不同，大幅降低得分
        # 例如"凳"(木部家具)和"橘"(木部水果)共享木偏旁但语义无关
        cats1 = self._get_categories(s1)
        cats2 = self._get_categories(s2)
        if cats1 and cats2 and not (cats1 & cats2):
            overlap_ratio *= 0.3  # 惩罚为原得分的30%

        return overlap_ratio * 80  # 最高80分（保留空间给完全同偏旁但不同字）

    def _category_similarity(self, s1: str, s2: str) -> float:
        """基于语义类别的相似度"""
        cats1 = self._get_categories(s1)
        cats2 = self._get_categories(s2)

        if not cats1 or not cats2:
            return 0.0

        # 共同类别
        common_cats = cats1 & cats2
        if not common_cats:
            return 0.0

        # 共同类别占比较
        overlap_ratio = len(common_cats) / min(len(cats1), len(cats2))
        return overlap_ratio * 70  # 最高70分

    def _get_categories(self, text: str) -> set:
        """获取文本所属的语义类别"""
        categories = set()
        for cat_name, words in self._SEMANTIC_CATEGORIES.items():
            for word in words:
                if word in text or text in word:
                    categories.add(cat_name)
                    break
            # 也检查每个字
            for char in text:
                if char in words:
                    categories.add(cat_name)
                    break
        return categories

    def _synonym_similarity(self, s1: str, s2: str) -> float:
        """基于同义词组的相似度"""
        for group in self._SYNONYM_GROUPS:
            s1_in = any(w in s1 or s1 in w for w in group)
            s2_in = any(w in s2 or s2 in w for w in group)
            if s1_in and s2_in:
                # 两个词在同一同义词组中
                # 如果完全相同词则不在此处（已由完全匹配处理）
                return 75.0
        return 0.0

    def _cross_category_penalty(self, s1: str, s2: str) -> float:
        """
        跨类别惩罚系数 (0.0 - 1.0)
        当两个词属于不同语义类别时返回低系数，大幅降低最终得分
        解决"凳子vs橘子"因共享木部首而返回不合理高分的问题
        """
        cats1 = self._get_categories(s1)
        cats2 = self._get_categories(s2)

        # 任一词无法分类 → 不惩罚
        if not cats1 or not cats2:
            return 1.0

        # 有共同类别 → 无惩罚
        common = cats1 & cats2
        if common:
            return 1.0

        # 定义互斥类别组（属于不同组的类别应该有强惩罚）
        mutually_exclusive_groups = [
            {"家具", "食物", "饮品", "服装"},  # 生活用品 vs 消费品
            {"动物", "电器", "交通工具", "工具"},  # 生物 vs 人造物
            {"自然", "建筑", "职业"},  # 抽象类别
            {"颜色", "身体", "乐器", "天气"},  # 特殊类别
        ]

        # 检查是否属于同一互斥组
        for group in mutually_exclusive_groups:
            c1_in_group = bool(cats1 & group)
            c2_in_group = bool(cats2 & group)
            if c1_in_group and c2_in_group:
                # 同一互斥组内但不同类别 → 强惩罚（只保留15%分数）
                return 0.15

        # 不同大组之间 → 中等惩罚
        return 0.30

    def _keyword_match_score(self, s1: str, s2: str) -> float:
        """关键词匹配得分（增强版子串匹配）"""
        if not s1 or not s2:
            return 0.0

        # 1. 精确子串匹配
        if s1 in s2 or s2 in s1:
            shorter = min(len(s1), len(s2))
            longer = max(len(s1), len(s2))
            return (shorter / longer) * 90

        # 2. 逐字符匹配（带位置权重）
        matched_chars = 0
        total_weight = 0.0
        weighted_match = 0.0

        for i, char in enumerate(s2):
            # 位置权重：越靠前越重要
            position_weight = 1.0 - (i / max(len(s2), 1)) * 0.5
            total_weight += position_weight
            if char in s1:
                matched_chars += 1
                weighted_match += position_weight

        if total_weight == 0:
            return 0.0

        # 字符匹配率 * 权重匹配率 * 缩放
        char_match_ratio = matched_chars / len(s2)
        weighted_match_ratio = weighted_match / total_weight if total_weight > 0 else 0
        combined = char_match_ratio * 0.6 + weighted_match_ratio * 0.4

        # 3. 最长公共子串加分
        common_len = self._longest_common_substring_length(s1, s2)
        max_len = max(len(s1), len(s2))
        lcs_ratio = common_len / max_len if max_len > 0 else 0

        return combined * 60 + lcs_ratio * 30

    def _context_relevance_score(
        self,
        guess: str,
        answer: str,
        category: str = "",
        hints: Optional[List[str]] = None,
    ) -> float:
        """上下文相关性得分"""
        score = 0.0

        # 1. 分类相关性
        if category:
            guess_cats = self._get_categories(guess)
            if category in guess_cats:
                score += 60.0

        # 2. 提示词相关性
        if hints:
            for hint in hints:
                hint_norm = self._normalize(hint)
                if hint_norm and hint_norm in guess:
                    score += 30.0
                    break  # 只加一次

        return min(score, 90.0)

    def _edit_distance_similarity(self, s1: str, s2: str) -> float:
        """基于编辑距离的相似度"""
        if not s1 or not s2:
            return 0.0

        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 100.0

        distance = self._levenshtein_distance(s1, s2)
        similarity = (1 - distance / max_len) * 100
        return max(0, similarity)

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """计算Levenshtein编辑距离"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]

    def _pinyin_similarity(self, s1: str, s2: str) -> float:
        """基于拼音的相似度（完整拼音匹配）"""
        try:
            from pypinyin import lazy_pinyin, Style

            # 完整拼音匹配
            pinyin1_full = "".join(lazy_pinyin(s1))
            pinyin2_full = "".join(lazy_pinyin(s2))

            if not pinyin1_full or not pinyin2_full:
                return 0.0

            # 拼音完全匹配
            if pinyin1_full == pinyin2_full:
                return 95.0

            # 拼音首字母匹配
            pinyin1_initial = "".join([p[0] for p in lazy_pinyin(s1) if p])
            pinyin2_initial = "".join([p[0] for p in lazy_pinyin(s2) if p])

            if pinyin1_initial == pinyin2_initial:
                return 80.0

            # 完整拼音的编辑距离相似度
            full_pinyin_sim = (
                self._edit_distance_similarity(pinyin1_full, pinyin2_full) * 0.6
            )
            # 首字母的编辑距离相似度
            initial_pinyin_sim = (
                self._edit_distance_similarity(pinyin1_initial, pinyin2_initial) * 0.4
            )

            return max(full_pinyin_sim, initial_pinyin_sim)
        except ImportError:
            # pypinyin未安装，使用简单字符匹配
            return self._char_overlap_score(s1, s2)

    def _char_overlap_score(self, s1: str, s2: str) -> float:
        """字符重叠度"""
        if not s1 or not s2:
            return 0.0
        set1 = set(s1)
        set2 = set(s2)
        overlap = len(set1 & set2)
        total = len(set1 | set2)
        if total == 0:
            return 0.0
        return (overlap / total) * 70

    def _containment_score(self, s1: str, s2: str) -> float:
        """子串包含关系得分（hybrid算法使用）"""
        if s1 in s2 or s2 in s1:
            shorter = min(len(s1), len(s2))
            longer = max(len(s1), len(s2))
            return (shorter / longer) * 90

        # 检查共同子串
        common_len = self._longest_common_substring_length(s1, s2)
        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 0.0
        return (common_len / max_len) * 60

    def _longest_common_substring_length(self, s1: str, s2: str) -> int:
        """最长公共子串长度"""
        if not s1 or not s2:
            return 0
        m, n = len(s1), len(s2)
        max_len = 0
        # 优化空间复杂度
        prev = [0] * (n + 1)
        for i in range(1, m + 1):
            curr = [0] * (n + 1)
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    curr[j] = prev[j - 1] + 1
                    max_len = max(max_len, curr[j])
            prev = curr
        return max_len

    def _length_similarity(self, s1: str, s2: str) -> float:
        """长度相似度（优化版：添加门控机制）"""
        if not s1 or not s2:
            return 0.0

        ratio = min(len(s1), len(s2)) / max(len(s1), len(s2))
        base_score = ratio * 100

        # 门控机制：仅当两词有任意共同字符时才给予完整长度分
        # 这避免了对完全无关的同长度词对（如"凳子"vs"橘子"）给予奖励
        if not (set(s1) & set(s2)):
            base_score *= 0.1  # 无共同字符时只给10%长度分

        return base_score

    # ===== 排行榜 =====

    def _update_user_stats(
        self, user_name: str, similarity: float, is_correct: bool, guess: str
    ):
        """更新用户游戏统计"""
        if user_name not in self.user_stats:
            self.user_stats[user_name] = UserGameStats(user_name=user_name)

        stats = self.user_stats[user_name]
        stats.total_guesses += 1
        stats.similarity_records.append(similarity)

        # 更新最高关联度及对应猜词内容
        if similarity > stats.best_similarity:
            stats.best_similarity = similarity
            stats.best_guess = guess

        # 重新计算平均关联度
        stats.avg_similarity = sum(stats.similarity_records) / len(
            stats.similarity_records
        )

        # 重新计算稳定性分
        stats.stability_score = self._calc_stability_score(stats.similarity_records)

        # 如果猜中，更新猜中相关统计
        if is_correct:
            round_id = (
                self.current_round_record.round_id if self.current_round_record else ""
            )
            # 避免同一轮次重复计分
            if round_id not in stats.correct_round_ids:
                stats.correct_count += 1
                stats.correct_round_ids.append(round_id)

                # 计算答题速度
                speed_ratio = self._calc_speed_ratio()
                stats.speed_records.append(speed_ratio)
                stats.speed_score = (
                    sum(stats.speed_records) / len(stats.speed_records) * 100
                )

        # 重新计算综合关联度
        stats.composite_score = self._calc_composite_score(stats)

    def _calc_speed_ratio(self) -> float:
        """计算当前猜中的速度比例（0-1，越快越高）"""
        if not self.state.round_start_time:
            return 0.5
        try:
            round_start = datetime.fromisoformat(self.state.round_start_time)
            elapsed = (datetime.now() - round_start).total_seconds()
            total_time = self.config.round_time_limit
            return max(0.0, min(1.0, 1 - elapsed / total_time))
        except (ValueError, TypeError):
            return 0.5

    def _calc_stability_score(self, records: List[float]) -> float:
        """计算稳定性分（0-100）"""
        if not records:
            return 0.0
        if len(records) == 1:
            return 50.0  # 中性值
        # 计算标准差
        avg = sum(records) / len(records)
        variance = sum((x - avg) ** 2 for x in records) / len(records)
        std_dev = variance**0.5
        return max(0.0, 100 - std_dev * 2)

    def _calc_composite_score(self, stats: UserGameStats) -> float:
        """计算综合关联度 = 平均关联度*0.4 + 速度分*0.3 + 稳定性分*0.3"""
        return (
            stats.avg_similarity * 0.4
            + stats.speed_score * 0.3
            + stats.stability_score * 0.3
        )

    def _update_rankings(self):
        """根据用户统计重建排行榜（双重指标排序）"""
        self.current_rankings = []

        for user_name, stats in self.user_stats.items():
            self.current_rankings.append(
                RankingEntry(
                    rank=0,
                    user_name=user_name,
                    correct_count=stats.correct_count,
                    composite_score=round(stats.composite_score, 1),
                    avg_similarity=round(stats.avg_similarity, 1),
                    speed_score=round(stats.speed_score, 1),
                    stability_score=round(stats.stability_score, 1),
                    best_similarity=round(stats.best_similarity, 1),
                    guess_content=stats.best_guess,
                    similarity_score=round(stats.best_similarity, 1),
                    timestamp=datetime.now().isoformat(),
                )
            )

        # 双重指标排序：先按猜中次数降序，再按综合关联度降序
        self.current_rankings.sort(
            key=lambda x: (x.correct_count, x.composite_score), reverse=True
        )

        # 更新排名
        for i, r in enumerate(self.current_rankings):
            r.rank = i + 1

    def _get_user_rank(self, user_name: str) -> int:
        """获取用户当前排名"""
        for r in self.current_rankings:
            if r.user_name == user_name:
                return r.rank
        return len(self.current_rankings) + 1

    def get_rankings(self, limit: int = None) -> List[RankingEntry]:
        """获取排行榜"""
        limit = limit or self.config.ranking_display_count
        return self.current_rankings[:limit]

    # ===== 倒计时 =====

    def _start_timer(self):
        """启动倒计时"""
        self._stop_timer()
        self._timer_running = True
        self._timer_thread = threading.Thread(target=self._timer_worker, daemon=True)
        self._timer_thread.start()

    def _stop_timer(self):
        """停止倒计时"""
        self._timer_running = False
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_thread.join(timeout=2)
        self._timer_thread = None

    def _timer_worker(self):
        """倒计时工作线程"""
        while self._timer_running and self.state.time_remaining > 0:
            time.sleep(1)
            if not self._timer_running:
                break
            if self.state.status != "running":
                continue

            self.state.time_remaining -= 1

            # 每5秒广播一次时间更新
            if self.state.time_remaining % 5 == 0 or self.state.time_remaining <= 10:
                self._broadcast_game_update(
                    "game_state_update",
                    {
                        "status": self.state.status,
                        "current_round": self.state.current_round,
                        "time_remaining": self.state.time_remaining,
                    },
                )

            # 时间到
            if self.state.time_remaining <= 0:
                self._timer_running = False
                self._handle_round_timeout()
                break

    def _handle_round_timeout(self):
        """处理轮次超时"""
        self._finish_current_round(winner=None)

        self._broadcast_game_update(
            "game_round_timeout",
            {
                "answer": self.state.current_answer,
                "current_round": self.state.current_round,
            },
        )

        # 检查是否还有下一轮
        if self.state.current_round >= self.config.total_rounds:
            self.state.status = "finished"
            self._save_state()
            self._broadcast_game_update(
                "game_state_update",
                {"status": "finished", "current_round": self.state.current_round},
            )
            return

        if self.config.auto_next_round:
            self._start_new_round()
        else:
            self.state.status = "paused"
            self._save_state()

    # ===== 历史记录 =====

    def get_history(self, page: int = 1, page_size: int = 20) -> dict:
        """获取游戏历史记录（分页）"""
        total = len(self.game_history)
        start = (page - 1) * page_size
        end = start + page_size
        records = self.game_history[start:end]

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "records": [r.model_dump() for r in records],
        }

    def get_round_detail(self, round_id: str) -> Optional[dict]:
        """获取单轮详情"""
        for r in self.game_history:
            if r.round_id == round_id:
                return r.model_dump()
        return None

    def clear_history(self):
        """清空历史记录"""
        self.game_history = []
        self._save_history()

    # ===== 获取游戏状态 =====

    def get_state(self) -> dict:
        """获取当前游戏状态"""
        state_dict = self.state.model_dump()
        state_dict["current_rankings"] = [
            r.model_dump()
            for r in self.current_rankings[: self.config.ranking_display_count]
        ]
        state_dict["total_guesses"] = len(self.current_round_guesses)
        state_dict["config"] = self.config.model_dump()
        # 补充当前词的分类和难度
        current_word = self._get_current_word()
        state_dict["current_category"] = current_word.category if current_word else ""
        state_dict["current_difficulty"] = (
            current_word.difficulty if current_word else ""
        )
        return state_dict

    def get_config(self) -> GameConfigModel:
        """获取游戏配置"""
        return self.config

    def update_config(self, config_data: dict) -> GameConfigModel:
        """更新游戏配置"""
        for key, value in config_data.items():
            if hasattr(self.config, key) and value is not None:
                setattr(self.config, key, value)
        self._save_config()
        return self.config

    # ===== 广播 =====

    def _broadcast_game_update(self, update_type: str, data: dict):
        """广播游戏更新消息"""
        if self.message_callback:
            message = {
                "message_type": update_type,
                "data": data,
                "timestamp": datetime.now().isoformat(),
            }
            try:
                self.message_callback(message)
            except Exception as e:
                print(f"[GameManager] 广播消息失败: {e}")

    def set_broadcast_callback(self, callback: Callable):
        """设置广播回调"""
        self.message_callback = callback
