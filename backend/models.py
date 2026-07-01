from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class RoomCreate(BaseModel):
    live_id: str
    name: Optional[str] = None


class Room(BaseModel):
    id: str
    live_id: str
    name: str
    status: str
    created_at: datetime


class KeywordFilterConfig(BaseModel):
    enabled: bool = False
    mode: str = "blacklist"  # 'blacklist' | 'whitelist'
    keywords: List[str] = Field(default_factory=list)
    exact_match: bool = False
    case_sensitive: bool = False


class RegexFilterConfig(BaseModel):
    enabled: bool = False
    patterns: List[str] = Field(default_factory=list)


class EmojiFilterConfig(BaseModel):
    enabled: bool = False
    # 过滤策略: 'full'=完全过滤, 'partial'=仅过滤表情部分保留文本
    strategy: str = "full"
    # 过滤范围
    filter_image_emoji: bool = True  # 过滤图片表情
    filter_text_emoji: bool = True  # 过滤字符表情
    filter_emoji_chat: bool = True  # 过滤独立表情包消息(EmojiChatMessage)


class EmoticonFilterConfig(BaseModel):
    enabled: bool = False
    match_all: bool = True  # 匹配所有 [xxx] 格式的方括号表情
    patterns: List[str] = Field(
        default_factory=list
    )  # 方括号表情模式列表，如 ['[捂脸]', '[呲牙]']


class SpecialSymbolFilterConfig(BaseModel):
    enabled: bool = False
    symbols: List[str] = Field(default_factory=list)  # 特殊符号列表，如 ['@', '#', '$']
    match_type: str = "any"  # 'any'=包含任意一个, 'all'=包含全部


class MentionFilterConfig(BaseModel):
    enabled: bool = False
    strategy: str = "full"  # 'full'=过滤整条消息, 'remove'=仅移除@提及部分保留其余文本


class QuestionFilterConfig(BaseModel):
    enabled: bool = False
    question_markers: List[str] = Field(
        default_factory=list
    )  # 疑问标记列表，如 ['吗？', '呢？', '什么？']
    match_type: str = "any"  # 'any'=包含任意一个, 'all'=包含全部


class UserLevelFilterConfig(BaseModel):
    enabled: bool = False
    min_level: Optional[int] = None
    max_level: Optional[int] = None
    allowed_users: List[str] = Field(default_factory=list)


class FilterStats(BaseModel):
    total_processed: int = 0
    total_filtered: int = 0
    by_type: dict = Field(default_factory=dict)
    by_keyword: dict = Field(default_factory=dict)
    by_regex: dict = Field(default_factory=dict)
    by_level: dict = Field(default_factory=dict)
    by_emoji: dict = Field(default_factory=dict)
    by_emoticon: dict = Field(default_factory=dict)
    by_special_symbol: dict = Field(default_factory=dict)
    by_mention: dict = Field(default_factory=dict)
    by_question: dict = Field(default_factory=dict)
    last_updated: Optional[datetime] = None


class AdvancedFilterConfig(BaseModel):
    enabled_types: List[str] = Field(default_factory=list)
    keyword_filter: KeywordFilterConfig = Field(default_factory=KeywordFilterConfig)
    regex_filter: RegexFilterConfig = Field(default_factory=RegexFilterConfig)
    user_level_filter: UserLevelFilterConfig = Field(
        default_factory=UserLevelFilterConfig
    )
    emoji_filter: EmojiFilterConfig = Field(default_factory=EmojiFilterConfig)
    emoticon_filter: EmoticonFilterConfig = Field(default_factory=EmoticonFilterConfig)
    special_symbol_filter: SpecialSymbolFilterConfig = Field(
        default_factory=SpecialSymbolFilterConfig
    )
    mention_filter: MentionFilterConfig = Field(default_factory=MentionFilterConfig)
    question_filter: QuestionFilterConfig = Field(default_factory=QuestionFilterConfig)


class FilterConfig(BaseModel):
    enabled_types: List[str]


class OutputConfig(BaseModel):
    output_mode: str = "browser"  # 'browser' or 'file'
    # 浏览器输出配置
    target_url: str = ""
    textarea_selector: str = ""
    button_selector: str = ""
    textarea_selectors: List[str] = Field(default_factory=list)  # 备选选择器（新增）
    button_selectors: List[str] = Field(default_factory=list)  # 备选选择器（新增）
    browser_headless: bool = False
    # 文件输出配置
    file_output_path: str = ""
    file_append_mode: bool = True
    # 通用发送配置
    send_mode: str = "sequential"  # 'sequential' or 'batch'
    send_interval: float = 2.0
    auto_click_button: bool = True
    auto_press_enter: bool = False
    add_newline: bool = True
    include_username: bool = True  # 是否在输出中包含用户名
    include_timestamp: bool = False  # 是否在输出中包含时间


class OutputStatus(BaseModel):
    running: bool = False
    last_execution_time: Optional[str] = None
    total_sent: int = 0
    last_error: Optional[str] = None
    browser_connected: bool = False
    current_index: int = 0
    total_lines: int = 0
    paused: bool = False


class PickerResult(BaseModel):
    selector: str = ""
    tag_name: str = ""
    text_preview: str = ""
    element_type: str = "other"


class TextFileConfig(BaseModel):
    file_path: str = ""
    file_format: str = "txt"
    remove_duplicates: bool = True
    remove_empty: bool = True
    filter_keywords: List[str] = []
    separator: str = "\n"


class TextPreview(BaseModel):
    total_lines: int = 0
    preview_lines: List[str] = []
    file_path: str = ""
    file_format: str = "txt"


class SendLogEntry(BaseModel):
    timestamp: str
    content: str
    success: bool
    error: Optional[str] = None


MESSAGE_TYPES = {
    "WebcastChatMessage": "互动消息（聊天）",
    "WebcastMemberMessage": "进入直播间",
    "WebcastGiftMessage": "礼物消息",
    "WebcastControlMessage": "管理员消息",
    "WebcastRoomUserSeqMessage": "在线观众消息",
    "WebcastLikeMessage": "点赞消息",
    "WebcastSocialMessage": "关注消息",
    "WebcastFansclubMessage": "粉丝团消息",
    "WebcastEmojiChatMessage": "表情包消息",
    "WebcastRoomStatsMessage": "直播间统计",
    "WebcastRoomMessage": "直播间信息",
    "WebcastRoomRankMessage": "排行榜信息",
    "WebcastRoomStreamAdaptationMessage": "流配置信息",
}


# ===== 猜词游戏模型 =====


class WordBankEntry(BaseModel):
    """词库条目"""

    id: str
    answer: str
    hints: List[str] = Field(default_factory=list)
    category: str = ""
    difficulty: str = "medium"  # easy/medium/hard
    sort_order: int = 0  # 排序序号，用于按顺序取词
    created_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = True


class WordBankCreate(BaseModel):
    """创建词库条目请求"""

    answer: str
    hints: List[str] = Field(default_factory=list)
    category: str = ""
    difficulty: str = "medium"


class WordBankUpdate(BaseModel):
    """更新词库条目请求"""

    answer: Optional[str] = None
    hints: Optional[List[str]] = None
    category: Optional[str] = None
    difficulty: Optional[str] = None
    is_active: Optional[bool] = None


class GameConfigModel(BaseModel):
    """游戏配置"""

    total_rounds: int = 5
    round_time_limit: int = 7200  # 默认2小时
    similarity_algorithm: str = "hybrid"  # edit_distance/pinyin/hybrid/semantic/embedding
    ranking_display_count: int = 20
    auto_next_round: bool = True
    popup_duration: int = 10
    hint_penalty: float = 0.05
    qa_enabled: bool = True  # 观众问答功能开关
    # Embedding 模型配置
    embedding_model_name: str = "BAAI/bge-small-zh-v1.5"
    embedding_enabled: bool = True  # 是否启用 Embedding 算法（关闭则不下载模型）


class GameStateModel(BaseModel):
    """游戏状态"""

    status: str = "idle"  # idle/running/paused/finished
    current_round: int = 0
    current_word_id: Optional[str] = None
    current_answer: Optional[str] = None
    current_hints: List[str] = Field(default_factory=list)
    current_hints_shown: int = 0
    round_start_time: Optional[str] = None
    round_end_time: Optional[str] = None
    time_remaining: int = 0
    used_word_ids: List[str] = Field(default_factory=list)


class GuessRecord(BaseModel):
    """用户猜词记录"""

    id: str
    round_id: str
    user_name: str
    guess_content: str
    similarity_score: float
    is_correct: bool = False
    timestamp: str


class UserGameStats(BaseModel):
    """用户游戏统计（跨轮次累积）"""

    user_name: str
    correct_count: int = 0  # 猜中次数（主要指标）
    total_guesses: int = 0  # 总猜词次数
    avg_similarity: float = 0.0  # 平均关联度（0-100）
    speed_score: float = 0.0  # 答题速度分（0-100）
    stability_score: float = 0.0  # 稳定性分（0-100）
    composite_score: float = 0.0  # 综合关联度（次要指标，0-100）
    best_similarity: float = 0.0  # 最高关联度
    best_guess: str = ""  # 最高关联度对应的猜词内容
    correct_round_ids: List[str] = Field(default_factory=list)  # 猜中的轮次ID列表
    speed_records: List[float] = Field(
        default_factory=list
    )  # 每次猜中的速度记录（0-1比例）
    similarity_records: List[float] = Field(
        default_factory=list
    )  # 每次猜词的关联度记录


class RankingEntry(BaseModel):
    """排行条目"""

    rank: int
    user_name: str
    correct_count: int = 0  # 猜中次数
    composite_score: float = 0.0  # 综合关联度
    avg_similarity: float = 0.0  # 平均关联度
    speed_score: float = 0.0  # 答题速度分
    stability_score: float = 0.0  # 稳定性分
    best_similarity: float = 0.0  # 最高关联度
    guess_content: str = ""  # 最佳猜词内容
    similarity_score: float = 0.0  # 兼容旧字段，指向 best_similarity
    timestamp: str = ""


class GameRoundRecord(BaseModel):
    """游戏轮次记录"""

    round_id: str
    round_number: int
    answer: str
    winner: Optional[str] = None
    winner_guess: Optional[str] = None
    total_guesses: int = 0
    start_time: str
    end_time: Optional[str] = None
    guesses: List[GuessRecord] = Field(default_factory=list)


class GameHistoryResponse(BaseModel):
    """游戏历史记录响应"""

    total: int
    page: int
    page_size: int
    records: List[GameRoundRecord]


class WordBankBatchImport(BaseModel):
    """批量导入词库请求"""

    words: List[WordBankCreate]


class EmbeddingStatus(BaseModel):
    """Embedding 模型状态（供前端/性能监控查询）"""

    status: str = "unloaded"  # unloaded/downloading/loading/ready/failed
    model_name: str = "BAAI/bge-small-zh-v1.5"
    local_path: str = ""
    embedding_dim: int = 512
    error_message: Optional[str] = None
    dependencies_available: bool = False
    encode_count: int = 0
    encode_avg_ms: float = 0.0
    cache_size: int = 0
    cache_hit_rate: float = 0.0
    fallback_count: int = 0
    word_bank_vector_count: int = 0
    last_precompute_ms: float = 0.0
