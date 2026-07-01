<template>
  <div class="guess-table">
    <!-- 顶部提示与分类标签区域 -->
    <div class="guess-header" v-if="category || difficulty || hints.length">
      <div class="header-tags">
        <el-tag v-if="category" effect="dark" size="default" class="category-tag">
          {{ category }}
        </el-tag>
        <el-tag :type="difficultyType" effect="plain" size="default" class="difficulty-tag">
          {{ difficultyLabel }}
        </el-tag>
      </div>
      <div class="header-hints" v-if="hints.length">
        <span class="hint-label">提示</span>
        <span class="hint-item" v-for="(hint, i) in hints" :key="i">{{ hint }}</span>
      </div>
    </div>

    <!-- 答案遮罩区 -->
    <div class="answer-display" v-if="answerMasked && answerMasked !== '***'">
      <span class="answer-masked-text">{{ answerMasked }}</span>
      <span class="answer-label">题</span>
    </div>

    <!-- 列表表头 -->
    <div class="guess-list-header">
      <span class="col-rank">#</span>
      <span class="col-user">用户名</span>
      <span class="col-content">猜词</span>
      <span class="col-score">关联度</span>
      <span class="col-time">时间</span>
    </div>

    <!-- 消息列表（带动画） -->
    <TransitionGroup name="guess-slide" tag="div" class="guess-list" ref="guessListRef">
      <div
        v-for="item in displayGuesses"
        :key="item.id"
        class="guess-item"
        :class="[rowClass(item), rankBorderClass(item.rank)]"
      >
        <span class="guess-rank" :class="rankBadgeClass(item.rank)">
          {{ item.rank }}
        </span>
        <span class="guess-user" :class="{ 'top-guess': item.rank <= 3 }">
          {{ item.user_name }}
        </span>
        <span class="guess-content">{{ item.guess_content }}</span>
        <span class="guess-score" :style="{ color: getScoreColor(item.similarity_score) }">
          {{ displayScore(item) }}%
        </span>
        <span class="guess-time">{{ formatTime(item.timestamp) }}</span>
      </div>
    </TransitionGroup>

    <div v-if="guesses.length === 0" class="empty-guesses">
      等待观众猜词...
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch, nextTick } from 'vue'

const props = defineProps({
  guesses: { type: Array, default: () => [] },
  category: { type: String, default: '' },
  difficulty: { type: String, default: '' },
  hints: { type: Array, default: () => [] },
  answerMasked: { type: String, default: '' }
})

const guessListRef = ref(null)

const displayGuesses = computed(() => {
  return [...props.guesses]
    .sort((a, b) => b.similarity_score - a.similarity_score)
    .slice(0, 100)
    .map((g, idx) => ({ ...g, rank: idx + 1 }))
})

const difficultyType = computed(() => {
  const map = { easy: 'success', medium: 'warning', hard: 'danger' }
  return map[props.difficulty] || 'info'
})

const difficultyLabel = computed(() => {
  const map = { easy: '简单', medium: '中等', hard: '困难' }
  return map[props.difficulty] || '中等'
})

const getScoreColor = (score) => {
  if (score >= 90) return '#67c23a'
  if (score >= 70) return '#e6a23c'
  if (score >= 50) return '#f56c6c'
  return '#909399'
}

const rowClass = (item) => {
  if (item.is_correct) return 'correct-row'
  if (item.similarity_score >= 70) return 'high-score-row'
  return ''
}

const rankBadgeClass = (rank) => {
  if (rank === 1) return 'rank-gold-badge'
  if (rank === 2) return 'rank-silver-badge'
  if (rank === 3) return 'rank-bronze-badge'
  return ''
}

const rankBorderClass = (rank) => {
  if (rank === 1) return 'border-gold'
  if (rank === 2) return 'border-silver'
  if (rank === 3) return 'border-bronze'
  return ''
}

// 显示分数（1位小数）
const displayScore = (item) => {
  return item.similarity_score.toFixed(1)
}

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

// 自动滚动到顶部（新弹幕优先展示）
watch(() => props.guesses.length, () => {
  nextTick(() => {
    if (guessListRef.value) {
      guessListRef.value.scrollTop = 0
    }
  })
})
</script>

<style scoped>
.guess-table {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0; /* 允许 flex 子项收缩，防止内容撑出弹窗产生滚动条 */
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  background: #fff;
}

/* 答案遮罩 */
.answer-display {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 16px;
  background: linear-gradient(135deg, #fef9e7 0%, #fdf0d5 100%);
  border-bottom: 2px dashed #f0dca0;
}

.answer-masked-text {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: 8px;
  color: #5d4037;
}

.answer-label {
  font-size: 12px;
  color: #8d6e63;
  background: #f0dca0;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}

/* 顶部提示区域 */
.guess-header {
  padding: 12px 16px;
  background: linear-gradient(135deg, #f0f5ff 0%, #e8f0fe 100%);
  border-bottom: 2px solid #d0e2ff;
}

.header-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.category-tag {
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.5px;
  padding: 4px 14px;
  height: 30px;
  border-radius: 6px;
}

.difficulty-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 4px 14px;
  height: 30px;
  border-radius: 6px;
}

.header-hints {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.hint-label {
  font-size: 13px;
  font-weight: 600;
  color: #667eea;
  flex-shrink: 0;
}

.hint-item {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  background: #fff;
  border: 1px solid #d0e2ff;
  border-radius: 6px;
  padding: 3px 10px;
  line-height: 1.5;
}

/* 列表表头 */
.guess-list-header {
  display: grid;
  /* 排名 / 用户名 / 猜词 / 关联度 / 时间：minmax 控制最小/最大，fr 分配剩余 */
  grid-template-columns:
    minmax(32px, 0.4fr)   /* 排名：硬性窄列 */
    minmax(120px, 2.5fr)  /* 用户名：弹性扩展，占据主要宽度 */
    minmax(80px, 1fr)     /* 猜词：弹性扩展 */
    minmax(70px, 0.9fr)   /* 关联度 */
    minmax(70px, 0.8fr);  /* 时间 */
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #faf8f0;
  border-bottom: 1px solid #eee4d0;
  font-size: 13px;
  font-weight: 600;
  color: #8d6e63;
  flex-shrink: 0;
}

.col-rank { text-align: center; }
.col-user { /* 由 grid 分配 */ }
.col-content { /* 由 grid 分配 */ }
.col-score { text-align: right; }
.col-time { text-align: right; }

/* 消息列表 */
.guess-list {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  /* 依赖 flex 布局自动约束高度，不再使用固定 max-height 避免弹窗内出现多余滚动条 */
  /* 自定义滚动条 */
  scrollbar-width: thin;
  scrollbar-color: #c0c4cc transparent;
}

.guess-list::-webkit-scrollbar {
  width: 6px;
}

.guess-list::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 3px;
}

.guess-list::-webkit-scrollbar-thumb:hover {
  background: #909399;
}

.guess-list::-webkit-scrollbar-track {
  background: transparent;
}

/* ===== 入场动画 ===== */
.guess-slide-enter-active {
  animation: slideInLeft 0.35s ease-out;
}
.guess-slide-leave-active {
  animation: slideOutRight 0.25s ease-in;
  position: absolute;
  width: 100%;
}

@keyframes slideInLeft {
  from {
    opacity: 0;
    transform: translateX(-30px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes slideOutRight {
  from {
    opacity: 1;
    transform: translateX(0);
  }
  to {
    opacity: 0;
    transform: translateX(30px);
  }
}

/* 列表行 */
.guess-item {
  display: grid;
  /* 与表头列定义完全一致，保证对齐 */
  grid-template-columns:
    minmax(32px, 0.4fr)
    minmax(120px, 2.5fr)
    minmax(80px, 1fr)
    minmax(70px, 0.9fr)
    minmax(70px, 0.8fr);
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  font-size: 14px;
  line-height: 1.6;
  border-bottom: 1px solid #f5f2ec;
  transition: all 0.25s ease;
  position: relative;
}

.guess-item:hover {
  background: #fdfcf8;
}

.guess-item.correct-row {
  background: linear-gradient(90deg, #f0f9eb 0%, #ffffff 100%) !important;
  animation: correct-flash 0.6s ease;
}

.guess-item.high-score-row {
  background: linear-gradient(90deg, #fdf6ec 0%, #ffffff 100%) !important;
}

@keyframes correct-flash {
  0% { background: #d4edda; }
  50% { background: #f0f9eb; }
  100% { background: linear-gradient(90deg, #f0f9eb 0%, #ffffff 100%); }
}

/* 排名徽章（圆形） */
.guess-rank {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 800;
  flex-shrink: 0;
  margin-right: 8px;
  background: #f0f0f0;
  color: #999;
  justify-self: center;  /* grid 单元格内水平居中，与表头 # 对齐 */
}

.rank-gold-badge {
  background: linear-gradient(135deg, #ffd700 0%, #ffec8b 100%);
  color: #8b6914;
  box-shadow: 0 2px 6px rgba(255, 215, 0, 0.35);
  animation: medal-bounce 2s ease-in-out infinite;
}

.rank-silver-badge {
  background: linear-gradient(135deg, #c0c0c0 0%, #e8e8e8 100%);
  color: #666;
  box-shadow: 0 2px 4px rgba(192, 192, 192, 0.3);
}

.rank-bronze-badge {
  background: linear-gradient(135deg, #cd7f32 0%, #e8a861 100%);
  color: #6b4423;
  box-shadow: 0 2px 4px rgba(205, 127, 50, 0.3);
}

@keyframes medal-bounce {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.08); }
}

/* 左侧彩色边框 */
.border-gold { border-left: 3px solid #ffd700; }
.border-silver { border-left: 3px solid #c0c0c0; }
.border-bronze { border-left: 3px solid #cd7f32; }

/* Top3脉冲效果 */
.guess-item.border-gold,
.guess-item.border-silver,
.guess-item.border-bronze {
  position: relative;
}

.guess-item.border-gold::after {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: linear-gradient(180deg, #ffd700, #ffec8b, #ffd700);
  animation: shimmer 2s ease-in-out infinite;
}

@keyframes shimmer {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.guess-user {
  font-weight: 500;
  color: #303133;
  min-width: 0;            /* 关键：允许 grid 子项收缩到 0 */
  max-width: 240px;        /* 防止超长用户名撑爆列 */
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;  /* 中文/混合文本友好换行 */
  overflow-wrap: anywhere;
  line-height: 1.3;
}

.guess-user.top-guess {
  color: #e6a23c;
  font-weight: 700;
}

.guess-content {
  color: #303133;
  min-width: 0;            /* 关键 */
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.3;
}

.guess-score {
  text-align: right;
  font-weight: 800;
  font-size: 15px;
  font-variant-numeric: tabular-nums;
  transition: color 0.3s ease;
  white-space: nowrap;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.guess-time {
  text-align: right;
  font-size: 12px;
  color: #b0a898;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.empty-guesses {
  text-align: center;
  color: #c0b8a8;
  padding: 40px;
  font-size: 14px;
}

/* 响应式：中屏（500-700px）— 时间列缩短，用户名列获更多份额 */
@media (max-width: 700px) {
  .guess-list-header,
  .guess-item {
    grid-template-columns:
      minmax(30px, 0.35fr)
      minmax(100px, 3fr)    /* 用户名份额提高 */
      minmax(70px, 0.9fr)
      minmax(60px, 0.8fr)
      minmax(60px, 0.7fr);
    gap: 6px;
    padding-left: 12px;
    padding-right: 12px;
  }
  .guess-user { max-width: 200px; }
  .guess-time { font-size: 11px; }
}

/* 响应式：窄屏（<500px）— 隐藏时间列，4 列布局 */
@media (max-width: 500px) {
  .guess-list-header,
  .guess-item {
    grid-template-columns:
      minmax(28px, 0.3fr)
      minmax(100px, 3.5fr)   /* 用户名获得更多空间 */
      minmax(60px, 0.8fr)
      minmax(60px, 0.7fr);
    gap: 4px;
    padding-left: 10px;
    padding-right: 10px;
  }
  /* 隐藏时间列（表头与行内均隐藏） */
  .col-time,
  .guess-time {
    display: none;
  }
  .guess-user { max-width: 160px; font-size: 13px; }
  .guess-content { font-size: 13px; }
  .guess-score { font-size: 13px; }
}
</style>
