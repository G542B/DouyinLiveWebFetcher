import re
import threading
from typing import Dict, Optional, Tuple
from datetime import datetime
from .models import (
    AdvancedFilterConfig,
    KeywordFilterConfig,
    RegexFilterConfig,
    UserLevelFilterConfig,
    EmojiFilterConfig,
    EmoticonFilterConfig,
    SpecialSymbolFilterConfig,
    MentionFilterConfig,
    QuestionFilterConfig,
    FilterStats,
)


class DanmakuFilterEngine:
    def __init__(self):
        self.config = AdvancedFilterConfig()
        self.stats = FilterStats()
        self._compiled_patterns: Dict[str, re.Pattern] = {}
        self._emoticon_pattern: Optional[re.Pattern] = None
        self._mention_pattern: Optional[re.Pattern] = None
        self._lock = threading.Lock()

    def update_config(self, config: AdvancedFilterConfig):
        with self._lock:
            self.config = config
            self._compile_patterns()

    def _compile_patterns(self):
        if self.config.regex_filter.enabled:
            self._compiled_patterns = {}
            for pattern in self.config.regex_filter.patterns:
                try:
                    self._compiled_patterns[pattern] = re.compile(pattern)
                except re.error:
                    pass

        # 预编译方括号表情正则（匹配所有 [xxx] 格式）
        if (
            self.config.emoticon_filter.enabled
            and self.config.emoticon_filter.match_all
        ):
            self._emoticon_pattern = re.compile(r"\[[^\]]+\]")
        else:
            self._emoticon_pattern = None

        # 预编译@提及正则（匹配 @后接空格和用户名 或 @直接接用户名）
        if self.config.mention_filter.enabled:
            try:
                self._mention_pattern = re.compile(r"@\s*\S+")
            except re.error:
                self._mention_pattern = None
        else:
            self._mention_pattern = None

    def _update_stats(self, filtered: bool, filter_type: str, detail: str = None):
        self.stats.total_processed += 1
        if filtered:
            self.stats.total_filtered += 1
            stats_dict = getattr(self.stats, f"by_{filter_type}")
            if detail:
                stats_dict[detail] = stats_dict.get(detail, 0) + 1
        self.stats.last_updated = datetime.now()

    def should_allow(self, message: dict) -> Tuple[bool, Optional[str]]:
        msg_type = message.get("message_type", "")
        data = message.get("data", {})
        content = data.get("content", "")
        user_name = data.get("user_name", "")
        user_level = data.get("user_level", 0)

        with self._lock:
            if self.config.enabled_types and msg_type not in self.config.enabled_types:
                self._update_stats(True, "type", msg_type)
                return False, f"消息类型 {msg_type} 被过滤"

            # 表情包过滤
            emoji_result = self._check_emoji_filter(msg_type, data)
            if emoji_result is not None:
                allowed, reason = emoji_result
                if not allowed:
                    self._update_stats(True, "emoji", reason)
                    return False, reason
                self._update_stats(False, "emoji")

            if self.config.keyword_filter.enabled:
                keyword_result = self._check_keyword_filter(content)
                if keyword_result is not None:
                    allowed, keyword = keyword_result
                    if not allowed:
                        self._update_stats(True, "keyword", keyword)
                        return False, f'关键词 "{keyword}" 被过滤'
                    self._update_stats(False, "keyword")
                    return True, None

            if self.config.regex_filter.enabled:
                regex_result = self._check_regex_filter(content)
                if regex_result is not None:
                    allowed, pattern = regex_result
                    if not allowed:
                        self._update_stats(True, "regex", pattern)
                        return False, f'正则 "{pattern}" 匹配被过滤'
                    self._update_stats(False, "regex")
                    return True, None

            if self.config.user_level_filter.enabled:
                level_result = self._check_user_level_filter(user_name, user_level)
                if level_result is not None:
                    allowed, reason = level_result
                    if not allowed:
                        self._update_stats(True, "level", reason)
                        return False, reason
                    self._update_stats(False, "level")
                    return True, None

            # 方括号表情过滤
            emoticon_result = self._check_emoticon_filter(content)
            if emoticon_result is not None:
                allowed, reason = emoticon_result
                if not allowed:
                    self._update_stats(True, "emoticon", reason)
                    return False, reason

            # @提及过滤
            mention_result = self._check_mention_filter(content)
            if mention_result is not None:
                allowed, reason = mention_result
                if not allowed:
                    self._update_stats(True, "mention", reason)
                    return False, reason

            # 特殊符号过滤
            symbol_result = self._check_special_symbol_filter(content)
            if symbol_result is not None:
                allowed, reason = symbol_result
                if not allowed:
                    self._update_stats(True, "special_symbol", reason)
                    return False, reason

            # 提问类型过滤
            question_result = self._check_question_filter(content)
            if question_result is not None:
                allowed, reason = question_result
                if not allowed:
                    self._update_stats(True, "question", reason)
                    return False, reason

            self._update_stats(False, "type")
            return True, None

    def _check_emoji_filter(
        self, msg_type: str, data: dict
    ) -> Optional[Tuple[bool, str]]:
        ef = self.config.emoji_filter
        if not ef.enabled:
            return None

        # 处理独立表情包消息
        if msg_type == "WebcastEmojiChatMessage":
            if ef.filter_emoji_chat:
                sub_type = data.get("emoji_sub_type", "image_emoji")
                if sub_type == "image_emoji" and ef.filter_image_emoji:
                    return (False, "图片表情包消息")
                if sub_type == "text_emoji" and ef.filter_text_emoji:
                    return (False, "字符表情包消息")
            return (True, None)

        # 处理普通聊天中的嵌入表情
        if msg_type == "WebcastChatMessage":
            has_image = data.get("has_image_emoji", False)
            has_text = data.get("has_text_emoji", False)

            if ef.strategy == "full":
                # 完全过滤：包含表情的消息整体过滤
                if has_image and ef.filter_image_emoji:
                    return (False, "含图片表情的聊天消息")
                if has_text and ef.filter_text_emoji:
                    return (False, "含字符表情的聊天消息")

        return None

    def _check_keyword_filter(self, content: str) -> Optional[Tuple[bool, str]]:
        kf = self.config.keyword_filter
        if not kf.keywords:
            return None

        content_to_check = content if kf.case_sensitive else content.lower()

        for keyword in kf.keywords:
            keyword_to_check = keyword if kf.case_sensitive else keyword.lower()

            if kf.exact_match:
                match = content_to_check == keyword_to_check
            else:
                match = keyword_to_check in content_to_check

            if match:
                if kf.mode == "blacklist":
                    return (False, keyword)
                else:
                    return (True, keyword)

        if kf.mode == "whitelist":
            return (False, "无白名单关键词匹配")
        return None

    def _check_regex_filter(self, content: str) -> Optional[Tuple[bool, str]]:
        if not self._compiled_patterns:
            return None

        for pattern, compiled in self._compiled_patterns.items():
            if compiled.search(content):
                return (False, pattern)

        return None

    def _check_user_level_filter(
        self, user_name: str, user_level: int
    ) -> Optional[Tuple[bool, str]]:
        ul = self.config.user_level_filter

        if user_name in ul.allowed_users:
            return (True, "白名单用户")

        if ul.min_level is not None and user_level < ul.min_level:
            return (False, f"等级 {user_level} 低于最低要求 {ul.min_level}")

        if ul.max_level is not None and user_level > ul.max_level:
            return (False, f"等级 {user_level} 高于最高限制 {ul.max_level}")

        return None

    def _check_emoticon_filter(self, content: str) -> Optional[Tuple[bool, str]]:
        ef = self.config.emoticon_filter
        if not ef.enabled:
            return None

        # match_all 模式：正则匹配所有 [xxx] 格式
        if ef.match_all and self._emoticon_pattern:
            match = self._emoticon_pattern.search(content)
            if match:
                return (False, f'包含方括号表情 "{match.group()}"')

        # 逐个模式匹配（兼容旧逻辑）
        if ef.patterns:
            for pattern in ef.patterns:
                if pattern in content:
                    return (False, f'包含方括号表情 "{pattern}"')

        return None

    def _check_mention_filter(self, content: str) -> Optional[Tuple[bool, str]]:
        mf = self.config.mention_filter
        if not mf.enabled:
            return None

        if mf.strategy == "full":
            # 正则匹配 @后接用户名（支持 @用户 或 @ 用户 格式）
            if self._mention_pattern and self._mention_pattern.search(content):
                return (False, "包含@提及")
            # 兜底：只要内容含 @ 符号即过滤
            if "@" in content:
                return (False, "包含@符号")

        return None

    def _check_special_symbol_filter(self, content: str) -> Optional[Tuple[bool, str]]:
        sf = self.config.special_symbol_filter
        if not sf.enabled or not sf.symbols:
            return None

        matched_symbols = [symbol for symbol in sf.symbols if symbol in content]

        if sf.match_type == "any" and matched_symbols:
            return (False, f'包含特殊符号 "{matched_symbols[0]}"')

        if sf.match_type == "all" and len(matched_symbols) == len(sf.symbols):
            return (False, f'包含所有特殊符号 "{", ".join(sf.symbols)}"')

        return None

    def _check_question_filter(self, content: str) -> Optional[Tuple[bool, str]]:
        qf = self.config.question_filter
        if not qf.enabled or not qf.question_markers:
            return None

        matched_markers = [
            marker for marker in qf.question_markers if marker in content
        ]

        if qf.match_type == "any" and matched_markers:
            return (False, f'包含疑问句式 "{matched_markers[0]}"')

        if qf.match_type == "all" and len(matched_markers) == len(qf.question_markers):
            return (False, f'包含所有疑问标记 "{", ".join(qf.question_markers)}"')

        return None

    def get_stats(self) -> FilterStats:
        with self._lock:
            return FilterStats(**self.stats.model_dump())

    def reset_stats(self):
        with self._lock:
            self.stats = FilterStats()


filter_engine = DanmakuFilterEngine()
