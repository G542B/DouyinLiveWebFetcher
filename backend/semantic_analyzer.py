# -*- coding: utf-8 -*-
"""
语义关联度分析模块

提供词语与答案之间的语义关联系统性评估，包括：
1. 词义匹配度分析 - 基于Embedding向量的余弦相似度
2. 近义词语识别 - 基于同义词库和上下文感知
3. 语义相关性判断 - 基于语义类别和上下文理解
4. 规则匹配系统 - 多维度匹配规则库

输出关联度评分(0-100)及关键关联点说明，确保分析结果可解释
"""

import os
import sys
import threading
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

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


class MatchLevel(Enum):
    """匹配等级枚举"""
    EXACT = "exact"           # 完全匹配
    SYNONYM = "synonym"       # 同义匹配
    SEMANTIC = "semantic"     # 语义相关
    PARTIAL = "partial"       # 部分匹配
    WEAK = "weak"             # 弱关联
    NONE = "none"             # 无关联


@dataclass
class MatchEvidence:
    """匹配证据"""
    dimension: str           # 维度名称
    score: float             # 该维度得分 (0-100)
    level: MatchLevel        # 匹配等级
    description: str         # 说明描述
    details: Dict[str, Any] = field(default_factory=dict)  # 详细数据


@dataclass
class SemanticAnalysisResult:
    """语义分析结果"""
    guess: str               # 输入词语
    answer: str               # 目标答案
    total_score: float       # 总关联度评分 (0-100)

    # 各维度得分
    embedding_score: float = 0.0      # 词向量相似度得分
    synonym_score: float = 0.0       # 近义词匹配得分
    semantic_score: float = 0.0      # 语义相关性得分
    radical_score: float = 0.0       # 偏旁部首得分
    pinyin_score: float = 0.0        # 拼音相似度得分
    edit_score: float = 0.0          # 编辑距离得分
    context_score: float = 0.0       # 上下文相关性得分

    # 匹配证据
    match_evidence: List[MatchEvidence] = field(default_factory=list)

    # 关键关联点说明
    key_connections: List[str] = field(default_factory=list)

    # 匹配等级
    match_level: MatchLevel = MatchLevel.NONE

    # 维度权重配置
    weights: Dict[str, float] = field(default_factory=lambda: {
        "embedding": 0.25,
        "synonym": 0.20,
        "semantic": 0.20,
        "radical": 0.10,
        "pinyin": 0.10,
        "edit": 0.10,
        "context": 0.05,
    })

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "guess": self.guess,
            "answer": self.answer,
            "total_score": round(self.total_score, 1),
            "dimension_scores": {
                "embedding": round(self.embedding_score, 1),
                "synonym": round(self.synonym_score, 1),
                "semantic": round(self.semantic_score, 1),
                "radical": round(self.radical_score, 1),
                "pinyin": round(self.pinyin_score, 1),
                "edit": round(self.edit_score, 1),
                "context": round(self.context_score, 1),
            },
            "match_level": self.match_level.value,
            "key_connections": self.key_connections,
            "evidence": [
                {
                    "dimension": e.dimension,
                    "score": round(e.score, 1),
                    "level": e.level.value,
                    "description": e.description,
                    "details": e.details,
                }
                for e in self.match_evidence
            ],
        }


class SemanticAnalyzer:
    """
    语义关联度分析器

    提供多维度语义关联分析，系统性评估词语与答案之间的语义关系
    """

    # 语义类别词典：类别名 → 代表词集合
    _SEMANTIC_CATEGORIES: Dict[str, Set[str]] = {
        "家具": {"椅", "桌", "凳", "柜", "床", "沙发", "书架", "茶几", "衣柜", "鞋柜", "梳妆", "屏风", "架", "案", "榻", "垫", "席", "枕", "被", "毯"},
        "食物": {"饭", "面", "米", "肉", "鱼", "鸡", "鸭", "菜", "汤", "饼", "饺", "包", "糕", "糖", "果", "蛋", "奶", "茶", "粥", "粉", "虾", "蟹", "牛", "羊", "猪", "豆腐", "肠", "翅", "腿", "排", "苹果", "橘子", "橙子", "梨子", "香蕉", "葡萄", "西瓜", "草莓", "桃子", "李子", "杏子", "樱桃", "芒果", "菠萝", "柚子", "柿子", "柠檬", "荔枝", "龙眼", "榴莲", "猕猴桃", "枣"},
        "饮品": {"水", "酒", "茶", "汁", "奶", "咖啡", "啤", "饮料", "汤", "浆", "醋", "油", "酱"},
        "颜色": {"红", "绿", "蓝", "黄", "白", "黑", "紫", "灰", "粉", "橙", "棕", "青", "金", "银", "彩", "色"},
        "动物": {"狗", "猫", "鸟", "鱼", "马", "牛", "羊", "猪", "鸡", "鸭", "虎", "龙", "蛇", "兔", "鼠", "猴", "象", "狮", "豹", "鹿", "熊", "狼", "狐", "鹰", "鹤", "蝶", "蜂", "蚁", "蚊", "蛙"},
        "交通": {"车", "船", "飞机", "火车", "地铁", "公交", "自行车", "摩托", "出租", "桥", "路", "站", "港", "轨", "轮", "驾"},
        "服装": {"衣", "裤", "裙", "帽", "鞋", "袜", "衫", "袍", "领", "袖", "带", "巾", "围", "手套", "背心", "外套", "大衣", "西装"},
        "天气": {"晴", "阴", "雨", "雪", "风", "云", "雷", "雾", "霜", "露", "冰", "虹", "霞", "暴", "旱", "涝"},
        "建筑": {"房", "楼", "塔", "桥", "墙", "门", "窗", "院", "亭", "阁", "殿", "庙", "寺", "宫", "堡", "坝", "堤", "井"},
        "工具": {"刀", "锤", "钳", "锯", "钉", "针", "线", "绳", "尺", "秤", "锁", "钥匙", "铲", "斧", "扳手", "刷", "胶", "漆"},
        "身体": {"头", "手", "脚", "眼", "耳", "鼻", "口", "心", "腿", "臂", "肩", "背", "腰", "肚", "脸", "发", "指", "掌", "拳", "骨"},
        "自然": {"山", "水", "河", "湖", "海", "树", "花", "草", "石", "土", "沙", "冰", "火", "风", "云", "雨", "雪", "日", "月", "星", "天", "地", "泉", "瀑", "岛", "谷", "洞", "林", "森"},
        "电器": {"灯", "电视", "冰箱", "空调", "电脑", "手机", "风扇", "洗衣机", "微波", "烤箱", "热水", "音响", "相机", "钟", "表"},
        "乐器": {"琴", "鼓", "笛", "箫", "筝", "琵琶", "吉他", "号", "铃", "锣", "钹", "笙", "埙", "二胡", "提琴"},
        "职业": {"医生", "老师", "警察", "工人", "农民", "司机", "厨师", "律师", "记者", "演员", "歌手", "画家", "作家", "工程师", "护士"},
    }

    # 同义词/近义词组
    _SYNONYM_GROUPS: List[Set[str]] = [
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

    # 偏旁部首映射表
    _RADICAL_MAP: Dict[str, str] = {
        "椅": "木", "桌": "木", "凳": "木", "柜": "木", "床": "木",
        "板": "木", "树": "木", "林": "木", "森": "木", "桥": "木",
        "楼": "木", "梯": "木", "栏": "木", "杆": "木", "枝": "木",
        "根": "木", "桶": "木", "棒": "木", "框": "木", "梁": "木",
        "棚": "木", "棠": "木", "梨": "木", "柿": "木", "樱": "木",
        "榕": "木", "樟": "木", "梳": "木", "核": "木", "格": "木",
        "酒": "水", "汁": "水", "汤": "水", "河": "水", "湖": "水",
        "海": "水", "洋": "水", "江": "水", "溪": "水", "池": "水",
        "波": "水", "浪": "水", "潮": "水", "洗": "水", "清": "水",
        "泪": "水", "滴": "水", "油": "水", "漆": "水", "浮": "水",
        "深": "水", "浅": "水", "温": "水", "凉": "水", "冷": "水",
        "冰": "水", "冻": "水", "泡": "水", "泥": "水", "沙": "水",
        "滩": "水", "港": "水", "湾": "水", "洒": "水", "泼": "水",
        "浇": "水", "洪": "水",
        "火": "火", "灯": "火", "炉": "火", "烟": "火", "烧": "火",
        "烤": "火", "炒": "火", "炸": "火", "燃": "火", "焰": "火",
        "烛": "火", "烘": "火", "热": "火", "暖": "火", "照": "火",
        "耀": "火", "辉": "火", "煌": "火", "煤": "火", "炭": "火",
        "灯": "火", "炉": "火",
        "铁": "金", "钢": "金", "铜": "金", "银": "金", "钱": "金",
        "针": "金", "钉": "金", "锅": "金", "刀": "金", "剑": "金",
        "锁": "金", "链": "金", "钟": "金", "铃": "金", "镜": "金",
        "钻": "金", "锤": "金", "铲": "金", "钩": "金", "锋": "金",
        "红": "丝", "绿": "丝", "蓝": "丝", "紫": "丝", "白": "丝",
        "黑": "丝", "黄": "丝", "灰": "丝", "粉": "丝", "线": "丝",
        "绳": "丝", "织": "丝", "绣": "丝", "绸": "丝", "缎": "丝",
        "纱": "丝", "绢": "丝", "编": "丝", "维": "丝",
        "吃": "口", "喝": "口", "唱": "口", "叫": "口", "喊": "口",
        "吹": "口", "咬": "口", "味": "口", "吐": "口", "吸": "口",
        "呼": "口", "叹": "口", "吵": "口", "告": "口", "听": "口",
        "问": "口", "答": "口", "嘴": "口", "唇": "口", "喉": "口",
        "咖": "口", "啡": "口", "啤": "口",
        "打": "手", "抓": "手", "拿": "手", "推": "手", "拉": "手",
        "提": "手", "按": "手", "拍": "手", "摸": "手", "抱": "手",
        "摔": "手", "拔": "手", "挑": "手", "指": "手", "掌": "手",
        "拳": "手", "握": "手", "托": "手", "扶": "手", "搓": "手",
        "跑": "足", "走": "足", "跳": "足", "踢": "足", "踩": "足",
        "踏": "足", "跨": "足", "跃": "足", "跌": "足", "跪": "足",
        "蹲": "足", "路": "足", "跟": "足", "蹄": "足",
        "明": "日", "暗": "日", "晴": "日", "晨": "日", "晚": "日",
        "昨": "日", "今": "日", "时": "日", "间": "日", "期": "日",
        "星": "日", "春": "日", "夏": "日", "秋": "日", "冬": "日",
        "月": "月", "脑": "月", "腿": "月", "脚": "月", "脸": "月",
        "背": "月", "肚": "月", "臂": "月", "肩": "月", "肝": "月",
        "胆": "月", "肠": "月", "胃": "月", "肾": "月", "胖": "月",
        "花": "草", "草": "草", "茶": "草", "药": "草", "菜": "草",
        "果": "草", "苗": "草", "莲": "草", "荷": "草", "菊": "草",
        "兰": "草", "芦": "草", "蕉": "草", "葱": "草", "蒜": "草",
        "苦": "草", "甜": "草", "芽": "草", "茂": "草", "茎": "草",
        "藤": "草", "萝": "草", "葡": "草",
        "石": "石", "岩": "石", "矿": "石", "砖": "石", "碑": "石",
        "碗": "石", "碟": "石", "砚": "石", "砂": "石", "碎": "石",
        "硬": "石", "破": "石", "砸": "石",
        "虫": "虫", "蝶": "虫", "蜂": "虫", "蚁": "虫", "蚊": "虫",
        "蝇": "虫", "蛇": "虫", "蛙": "虫", "虾": "虫", "蟹": "虫",
        "蛛": "虫", "蝉": "虫", "蚕": "虫", "蛾": "虫",
        "鸡": "鸟", "鸭": "鸟", "鹅": "鸟", "鸽": "鸟", "鹰": "鸟",
        "燕": "鸟", "鹤": "鸟", "雀": "鸟", "鸦": "鸟", "鸥": "鸟",
        "鱼": "鱼", "鲤": "鱼", "鲨": "鱼", "鲸": "鱼", "鲜": "鱼",
        "鲍": "鱼", "鳗": "鱼", "鳞": "鱼", "鳍": "鱼", "鳃": "鱼",
        "车": "车", "轮": "车", "轨": "车", "转": "车", "载": "车",
        "轿": "车", "辙": "车",
        "门": "门", "窗": "门", "闭": "门", "开": "门", "关": "门",
        "闪": "门", "闯": "门", "阔": "门", "闸": "门", "阅": "门",
        "心": "心", "情": "心", "爱": "心", "恨": "心", "想": "心",
        "念": "心", "思": "心", "意": "心", "愿": "心", "愁": "心",
        "怒": "心", "惊": "心", "怕": "心", "忆": "心", "懂": "心",
        "饭": "食", "饼": "食", "饺": "食", "馒": "食", "馆": "食",
        "餐": "食",
        "衣": "衣", "裤": "衣", "裙": "衣", "衫": "衣", "袍": "衣",
        "被": "衣", "衬": "衣", "袜": "衣", "袖": "衣", "领": "衣",
        "袋": "衣", "装": "衣", "裹": "衣",
        "竹": "竹", "笔": "竹", "筒": "竹", "篮": "竹", "筐": "竹",
        "笛": "竹", "竿": "竹", "笋": "竹", "筷": "竹", "简": "竹",
        "狗": "犬", "猫": "犬", "猪": "犬", "狼": "犬", "狐": "犬",
        "狮": "犬", "猎": "犬", "猛": "犬", "兽": "犬",
        "女": "女", "妈": "女", "姐": "女", "妹": "女", "奶": "女",
        "姑": "女", "娘": "女", "姨": "女", "嫂": "女", "妇": "女",
        "雨": "雨", "雪": "雨", "雷": "雨", "雾": "雨", "露": "雨",
        "霜": "雨", "霞": "雨", "霸": "雨", "零": "雨", "震": "雨",
        "财": "贝", "贵": "贝", "贪": "贝", "贫": "贝", "货": "贝",
        "购": "贝", "贩": "贝", "赚": "贝", "赔": "贝", "赠": "贝",
        "稻": "禾", "穗": "禾", "秧": "禾", "稼": "禾", "秋": "禾",
        "种": "禾", "积": "禾", "程": "禾", "秀": "禾", "秘": "禾",
        "马": "马", "骑": "马", "驾": "马", "驰": "马", "骏": "马",
        "腾": "马",
    }

    # 互斥类别组（用于跨类别惩罚）
    _MUTUALLY_EXCLUSIVE_GROUPS: List[Set[str]] = [
        {"家具", "食物", "饮品", "服装"},
        {"动物", "电器", "交通工具", "工具"},
        {"自然", "建筑", "职业"},
        {"颜色", "身体", "乐器", "天气"},
    ]

    def __init__(self, embedding_engine=None):
        """
        初始化语义分析器

        Args:
            embedding_engine: Embedding引擎实例（可选，用于词向量分析）
        """
        self._embedding_engine = embedding_engine
        self._embedding_lock = threading.Lock()
        self._pypinyin_available = self._check_pypinyin()

    def _check_pypinyin(self) -> bool:
        """检查pypinyin是否可用"""
        try:
            from pypinyin import lazy_pinyin
            return True
        except ImportError:
            return False

    def set_embedding_engine(self, engine):
        """设置Embedding引擎"""
        with self._embedding_lock:
            self._embedding_engine = engine

    def analyze(
        self,
        guess: str,
        answer: str,
        category: str = "",
        hints: Optional[List[str]] = None,
        weights: Optional[Dict[str, float]] = None,
    ) -> SemanticAnalysisResult:
        """
        综合语义关联度分析

        Args:
            guess: 待分析词语
            answer: 目标答案
            category: 当前分类提示（可选）
            hints: 提示词列表（可选）
            weights: 维度权重配置（可选）

        Returns:
            SemanticAnalysisResult: 包含各维度评分和关键关联点的分析结果
        """
        guess_norm = self._normalize(guess)
        answer_norm = self._normalize(answer)

        result = SemanticAnalysisResult(
            guess=guess,
            answer=answer,
            total_score=0.0,
        )

        if not guess_norm or not answer_norm:
            result.match_level = MatchLevel.NONE
            return result

        # 完全匹配
        if guess_norm == answer_norm:
            result.total_score = 100.0
            result.match_level = MatchLevel.EXACT
            result.key_connections.append("词语完全相同")
            return result

        # 设置权重
        if weights:
            result.weights = weights

        # 1. 词向量相似度分析
        result.embedding_score = self._calc_embedding_score(guess_norm, answer_norm)
        self._add_embedding_evidence(result, guess_norm, answer_norm)

        # 2. 近义词语识别
        result.synonym_score = self._calc_synonym_score(guess_norm, answer_norm)
        self._add_synonym_evidence(result, guess_norm, answer_norm)

        # 3. 语义类别相关性分析
        result.semantic_score = self._calc_semantic_score(guess_norm, answer_norm)
        self._add_semantic_evidence(result, guess_norm, answer_norm)

        # 4. 偏旁部首分析
        result.radical_score = self._calc_radical_score(guess_norm, answer_norm)
        self._add_radical_evidence(result, guess_norm, answer_norm)

        # 5. 拼音相似度分析
        result.pinyin_score = self._calc_pinyin_score(guess_norm, answer_norm)
        self._add_pinyin_evidence(result, guess_norm, answer_norm)

        # 6. 编辑距离分析
        result.edit_score = self._calc_edit_score(guess_norm, answer_norm)
        self._add_edit_evidence(result, guess_norm, answer_norm)

        # 7. 上下文相关性分析
        result.context_score = self._calc_context_score(guess_norm, answer_norm, category, hints)
        self._add_context_evidence(result, guess_norm, answer_norm, category, hints)

        # 计算加权总分
        w = result.weights
        result.total_score = (
            result.embedding_score * w.get("embedding", 0.25) +
            result.synonym_score * w.get("synonym", 0.20) +
            result.semantic_score * w.get("semantic", 0.20) +
            result.radical_score * w.get("radical", 0.10) +
            result.pinyin_score * w.get("pinyin", 0.10) +
            result.edit_score * w.get("edit", 0.10) +
            result.context_score * w.get("context", 0.05)
        )

        # 应用跨类别惩罚
        penalty = self._calc_cross_category_penalty(guess_norm, answer_norm)
        if penalty < 1.0:
            result.total_score *= penalty
            result.key_connections.append(f"跨类别惩罚: {penalty:.2f}")

        # 确保最高99.9
        result.total_score = min(99.9, result.total_score)

        # 确定匹配等级
        result.match_level = self._determine_match_level(result)

        # 生成关键关联点说明
        self._generate_key_connections(result)

        # 按得分降序排列证据
        result.match_evidence.sort(key=lambda x: x.score, reverse=True)

        return result

    def _normalize(self, text: str) -> str:
        """文本标准化"""
        return text.strip().lower().replace(" ", "").replace("\t", "")

    # ===== 1. 词向量相似度分析 =====

    def _calc_embedding_score(self, guess: str, answer: str) -> float:
        """基于Embedding向量的余弦相似度计算"""
        if not self._embedding_engine or not self._embedding_engine.is_ready:
            return 0.0

        try:
            guess_vec = self._embedding_engine.encode(guess, use_instruction=True)
            answer_vec = self._embedding_engine.encode(answer, use_instruction=False)

            if guess_vec is None or answer_vec is None:
                return 0.0

            # 余弦相似度（已归一化向量点积）
            similarity = self._embedding_engine.cosine_similarity(guess_vec, answer_vec)

            # 映射到 0-100
            # BGE余弦相似度通常在 [0.3, 0.95]
            sim_low = 0.30
            sim_high = 0.95
            score = (similarity - sim_low) / (sim_high - sim_low) * 100
            return max(0.0, min(100.0, score))
        except Exception:
            return 0.0

    def _add_embedding_evidence(self, result: SemanticAnalysisResult, guess: str, answer: str):
        """添加词向量分析证据"""
        score = result.embedding_score
        if score > 80:
            level = MatchLevel.SYNONYM
            desc = "词向量高度相似，语义接近"
        elif score > 50:
            level = MatchLevel.SEMANTIC
            desc = "词向量中度相似，存在语义关联"
        elif score > 20:
            level = MatchLevel.PARTIAL
            desc = "词向量弱相似"
        elif score > 0:
            level = MatchLevel.WEAK
            desc = "词向量相似度极低"
        else:
            level = MatchLevel.NONE
            desc = "无词向量相似度数据"

        result.match_evidence.append(MatchEvidence(
            dimension="embedding",
            score=score,
            level=level,
            description=desc,
            details={"method": "BGE-small-zh cosine similarity"},
        ))

    # ===== 2. 近义词语识别 =====

    def _calc_synonym_score(self, guess: str, answer: str) -> float:
        """基于同义词库的近义匹配得分"""
        score = 0.0

        for group in self._SYNONYM_GROUPS:
            guess_in = any(w in guess or guess in w for w in group)
            answer_in = any(w in answer or answer in w for w in group)

            if guess_in and answer_in:
                # 两个词都在同一同义词组中
                # 检查是否完全相同
                if guess == answer:
                    return 100.0
                # 部分匹配
                score = max(score, 75.0)
                break

        return score

    def _get_synonym_group(self, word: str) -> Optional[Set[str]]:
        """获取词语所属的同义词组"""
        for group in self._SYNONYM_GROUPS:
            if word in group or any(w in word for w in group):
                return group
        return None

    def _add_synonym_evidence(self, result: SemanticAnalysisResult, guess: str, answer: str):
        """添加近义词分析证据"""
        score = result.synonym_score

        if score >= 75:
            level = MatchLevel.SYNONYM
            group = self._get_synonym_group(guess)
            desc = f"近义词匹配: '{guess}' 与 '{answer}' 属于同一语义组"
            if group:
                desc += f" ({', '.join(group)})"
        elif score > 0:
            level = MatchLevel.PARTIAL
            desc = "存在部分同义关系"
        else:
            level = MatchLevel.NONE
            desc = "非近义词关系"

        result.match_evidence.append(MatchEvidence(
            dimension="synonym",
            score=score,
            level=level,
            description=desc,
        ))

    # ===== 3. 语义类别相关性分析 =====

    def _calc_semantic_score(self, guess: str, answer: str) -> float:
        """基于语义类别的相关性得分"""
        guess_cats = self._get_categories(guess)
        answer_cats = self._get_categories(answer)

        if not guess_cats or not answer_cats:
            return 0.0

        common = guess_cats & answer_cats
        if not common:
            return 0.0

        # 共同类别占比
        overlap_ratio = len(common) / min(len(guess_cats), len(answer_cats))
        return overlap_ratio * 70

    def _get_categories(self, text: str) -> Set[str]:
        """获取文本所属的语义类别"""
        categories = set()
        for cat_name, words in self._SEMANTIC_CATEGORIES.items():
            for word in words:
                if word in text or text in word:
                    categories.add(cat_name)
                    break
            for char in text:
                if char in words:
                    categories.add(cat_name)
                    break
        return categories

    def _add_semantic_evidence(self, result: SemanticAnalysisResult, guess: str, answer: str):
        """添加语义类别分析证据"""
        score = result.semantic_score
        guess_cats = self._get_categories(guess)
        answer_cats = self._get_categories(answer)
        common = guess_cats & answer_cats

        if score >= 60:
            level = MatchLevel.SEMANTIC
            desc = f"同属语义类别: {', '.join(common)}"
        elif score > 0:
            level = MatchLevel.PARTIAL
            desc = f"部分语义相关: 猜词属于{guess_cats}, 答案属于{answer_cats}"
        else:
            level = MatchLevel.NONE
            desc = "无共同语义类别"

        result.match_evidence.append(MatchEvidence(
            dimension="semantic",
            score=score,
            level=level,
            description=desc,
            details={"guess_categories": list(guess_cats), "answer_categories": list(answer_cats)},
        ))

    # ===== 4. 偏旁部首分析 =====

    def _calc_radical_score(self, guess: str, answer: str) -> float:
        """基于偏旁部首的相似度"""
        radicals1 = {self._RADICAL_MAP.get(c) for c in guess if c in self._RADICAL_MAP}
        radicals2 = {self._RADICAL_MAP.get(c) for c in answer if c in self._RADICAL_MAP}

        if not radicals1 or not radicals2:
            return 0.0

        common = radicals1 & radicals2
        if not common:
            return 0.0

        # 共同偏旁占比
        overlap_ratio = len(common) / min(len(radicals1), len(radicals2))

        # 类别校验：偏旁相同但语义类别不同则惩罚
        guess_cats = self._get_categories(guess)
        answer_cats = self._get_categories(answer)

        if guess_cats and answer_cats and not (guess_cats & answer_cats):
            overlap_ratio *= 0.3

        return overlap_ratio * 80

    def _add_radical_evidence(self, result: SemanticAnalysisResult, guess: str, answer: str):
        """添加偏旁部首分析证据"""
        score = result.radical_score
        radicals1 = {self._RADICAL_MAP.get(c) for c in guess if c in self._RADICAL_MAP}
        radicals2 = {self._RADICAL_MAP.get(c) for c in answer if c in self._RADICAL_MAP}
        common = radicals1 & radicals2

        if score >= 60:
            level = MatchLevel.SEMANTIC
            desc = f"共享偏旁部首: {', '.join(common) if common else '无'}"
        elif score > 0:
            level = MatchLevel.PARTIAL
            desc = f"偏旁部首部分相关"
        else:
            level = MatchLevel.NONE
            desc = "无共同偏旁部首"

        result.match_evidence.append(MatchEvidence(
            dimension="radical",
            score=score,
            level=level,
            description=desc,
            details={"guess_radicals": list(radicals1), "answer_radicals": list(radicals2)},
        ))

    # ===== 5. 拼音相似度分析 =====

    def _calc_pinyin_score(self, guess: str, answer: str) -> float:
        """基于拼音的相似度"""
        if not self._pypinyin_available:
            return self._calc_char_pinyin_score(guess, answer)

        try:
            from pypinyin import lazy_pinyin

            pinyin1 = "".join(lazy_pinyin(guess))
            pinyin2 = "".join(lazy_pinyin(answer))

            if not pinyin1 or not pinyin2:
                return 0.0

            # 完全匹配
            if pinyin1 == pinyin2:
                return 95.0

            # 首字母匹配
            initial1 = "".join([p[0] for p in lazy_pinyin(guess) if p])
            initial2 = "".join([p[0] for p in lazy_pinyin(answer) if p])

            if initial1 == initial2:
                return 80.0

            # 拼音编辑距离
            full_sim = self._edit_distance_ratio(pinyin1, pinyin2) * 0.6
            initial_sim = self._edit_distance_ratio(initial1, initial2) * 0.4

            return max(full_sim, initial_sim) * 100
        except Exception:
            return self._calc_char_pinyin_score(guess, answer)

    def _calc_char_pinyin_score(self, guess: str, answer: str) -> float:
        """无pypinyin时的字符级拼音相似度（简单版）"""
        set1 = set(guess)
        set2 = set(answer)
        overlap = len(set1 & set2)
        total = len(set1 | set2)
        if total == 0:
            return 0.0
        return (overlap / total) * 50

    def _add_pinyin_evidence(self, result: SemanticAnalysisResult, guess: str, answer: str):
        """添加拼音分析证据"""
        score = result.pinyin_score

        if score >= 90:
            level = MatchLevel.EXACT
            desc = "拼音完全相同"
        elif score >= 70:
            level = MatchLevel.SYNONYM
            desc = "拼音高度相似"
        elif score >= 40:
            level = MatchLevel.PARTIAL
            desc = "拼音部分相似"
        elif score > 0:
            level = MatchLevel.WEAK
            desc = "拼音微弱相似"
        else:
            level = MatchLevel.NONE
            desc = "拼音不相似"

        result.match_evidence.append(MatchEvidence(
            dimension="pinyin",
            score=score,
            level=level,
            description=desc,
        ))

    # ===== 6. 编辑距离分析 =====

    def _calc_edit_score(self, guess: str, answer: str) -> float:
        """基于编辑距离的相似度"""
        if not guess or not answer:
            return 0.0

        max_len = max(len(guess), len(answer))
        if max_len == 0:
            return 100.0

        distance = self._levenshtein_distance(guess, answer)
        similarity = (1 - distance / max_len) * 100
        return max(0.0, similarity)

    def _edit_distance_ratio(self, s1: str, s2: str) -> float:
        """编辑距离比率"""
        if not s1 and not s2:
            return 1.0
        max_len = max(len(s1), len(s2))
        if max_len == 0:
            return 1.0
        return 1 - self._levenshtein_distance(s1, s2) / max_len

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """计算Levenshtein编辑距离"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        if len(s2) == 0:
            return len(s1)

        prev = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            curr = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = prev[j + 1] + 1
                deletions = curr[j] + 1
                substitutions = prev[j] + (c1 != c2)
                curr.append(min(insertions, deletions, substitutions))
            prev = curr
        return prev[-1]

    def _add_edit_evidence(self, result: SemanticAnalysisResult, guess: str, answer: str):
        """添加编辑距离分析证据"""
        score = result.edit_score

        if score >= 90:
            level = MatchLevel.EXACT
            desc = "字符高度一致"
        elif score >= 70:
            level = MatchLevel.PARTIAL
            desc = "字符较为接近"
        elif score >= 40:
            level = MatchLevel.WEAK
            desc = "字符部分相似"
        else:
            level = MatchLevel.NONE
            desc = "字符差异较大"

        distance = self._levenshtein_distance(guess, answer)
        result.match_evidence.append(MatchEvidence(
            dimension="edit",
            score=score,
            level=level,
            description=desc,
            details={"edit_distance": distance, "guess_len": len(guess), "answer_len": len(answer)},
        ))

    # ===== 7. 上下文相关性分析 =====

    def _calc_context_score(
        self,
        guess: str,
        answer: str,
        category: str = "",
        hints: Optional[List[str]] = None,
    ) -> float:
        """基于上下文的语义相关性得分"""
        score = 0.0

        # 分类匹配
        if category:
            guess_cats = self._get_categories(guess)
            if category in guess_cats:
                score += 60.0

        # 提示词匹配
        if hints:
            for hint in hints:
                hint_norm = self._normalize(hint)
                if hint_norm and hint_norm in guess:
                    score += 30.0
                    break

        return min(score, 90.0)

    def _add_context_evidence(
        self,
        result: SemanticAnalysisResult,
        guess: str,
        answer: str,
        category: str,
        hints: Optional[List[str]],
    ):
        """添加上下文分析证据"""
        score = result.context_score

        if score >= 80:
            level = MatchLevel.SEMANTIC
            desc = "与上下文高度相关"
        elif score >= 40:
            level = MatchLevel.PARTIAL
            desc = "与上下文部分相关"
        elif score > 0:
            level = MatchLevel.WEAK
            desc = "与上下文微弱相关"
        else:
            level = MatchLevel.NONE
            desc = "与上下文无关"

        result.match_evidence.append(MatchEvidence(
            dimension="context",
            score=score,
            level=level,
            description=desc,
            details={"category": category, "hints": hints or []},
        ))

    # ===== 辅助方法 =====

    def _calc_cross_category_penalty(self, guess: str, answer: str) -> float:
        """计算跨类别惩罚系数"""
        guess_cats = self._get_categories(guess)
        answer_cats = self._get_categories(answer)

        if not guess_cats or not answer_cats:
            return 1.0

        if guess_cats & answer_cats:
            return 1.0

        for group in self._MUTUALLY_EXCLUSIVE_GROUPS:
            c1_in_group = bool(guess_cats & group)
            c2_in_group = bool(answer_cats & group)
            if c1_in_group and c2_in_group:
                return 0.15

        return 0.30

    def _determine_match_level(self, result: SemanticAnalysisResult) -> MatchLevel:
        """根据总分和证据确定匹配等级"""
        score = result.total_score

        if score >= 95:
            return MatchLevel.EXACT
        if score >= 70:
            return MatchLevel.SYNONYM
        if score >= 40:
            return MatchLevel.SEMANTIC
        if score >= 20:
            return MatchLevel.PARTIAL
        if score > 0:
            return MatchLevel.WEAK
        return MatchLevel.NONE

    def _generate_key_connections(self, result: SemanticAnalysisResult):
        """生成关键关联点说明"""
        connections = []

        # 基于各维度证据生成说明
        for evidence in result.match_evidence:
            if evidence.score >= 60:
                if evidence.dimension == "embedding":
                    connections.append("语义向量层面高度相似")
                elif evidence.dimension == "synonym":
                    connections.append("属于近义语义群")
                elif evidence.dimension == "semantic":
                    connections.append(f"同属语义类别: {evidence.description.split(': ')[-1] if ': ' in evidence.description else ''}")
                elif evidence.dimension == "radical":
                    connections.append("共享偏旁部首特征")
                elif evidence.dimension == "pinyin":
                    connections.append("拼音高度匹配")
                elif evidence.dimension == "edit":
                    connections.append("字符序列高度相似")
                elif evidence.dimension == "context":
                    connections.append("与给定上下文相关")

        # 基于总分生成总体说明
        if result.total_score >= 80:
            connections.insert(0, "整体关联度很高，词语与答案语义紧密相关")
        elif result.total_score >= 50:
            connections.insert(0, "整体关联度中等，存在一定语义关联")
        elif result.total_score >= 20:
            connections.insert(0, "整体关联度较低，词语与答案语义关系较弱")

        result.key_connections = connections[:5]  # 最多5个关键点

    def get_dimension_weights(self) -> Dict[str, float]:
        """获取当前维度权重配置"""
        return {
            "embedding": 0.25,
            "synonym": 0.20,
            "semantic": 0.20,
            "radical": 0.10,
            "pinyin": 0.10,
            "edit": 0.10,
            "context": 0.05,
        }

    def set_dimension_weights(self, weights: Dict[str, float]):
        """设置维度权重配置"""
        self._default_weights = weights.copy()
