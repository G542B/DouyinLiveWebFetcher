<template>
  <div class="ranking-board">
    <div class="ranking-header">
      <div class="ranking-header-left">
        <span class="ranking-title">今日答题排行榜</span>
        <el-tooltip placement="bottom" effect="light">
          <template #content>
            <div class="ranking-rule-tip">
              <div class="rule-title">排序规则</div>
              <div>1. 猜中次数（主指标）</div>
              <div>2. 综合关联度（次指标）</div>
              <div class="rule-sub">综合关联度 = 平均关联度×40% + 速度分×30% + 稳定性×30%</div>
            </div>
          </template>
          <span class="rule-icon">?</span>
        </el-tooltip>
      </div>
      <span class="ranking-count">{{ rankings.length }} 人</span>
    </div>
    <div class="ranking-list" ref="rankingList">
      <transition-group name="rank-move" tag="div">
        <div
          v-for="entry in rankings"
          :key="entry.user_name"
          class="ranking-item"
          :class="[getRankClass(entry.rank), { 'rank-expanded': expandedUser === entry.user_name }]"
          @click="toggleExpand(entry.user_name)"
        >
          <div class="ranking-main">
            <span class="rank-number-badge">{{ entry.rank }}</span>
            <span class="rank-user">{{ entry.user_name }}</span>
            <span class="rank-score" :style="compositeStyle(entry.composite_score)">
              {{ formatScore(entry.composite_score) }}
            </span>
            <span class="rank-times-badge" :class="{ 'has-correct': entry.correct_count > 0 }">
              {{ entry.correct_count }}次
            </span>
          </div>
          <div v-if="expandedUser === entry.user_name" class="ranking-detail">
            <div class="detail-row">
              <span class="detail-label">平均关联度</span>
              <span class="detail-value">{{ formatScore(entry.avg_similarity) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">答题速度</span>
              <span class="detail-value">{{ formatScore(entry.speed_score) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">稳定性</span>
              <span class="detail-value">{{ formatScore(entry.stability_score) }}</span>
            </div>
            <div class="detail-row">
              <span class="detail-label">最高关联度</span>
              <span class="detail-value">{{ formatScore(entry.best_similarity) }}</span>
            </div>
          </div>
        </div>
      </transition-group>
      <div v-if="rankings.length === 0" class="empty-ranking">
        暂无猜词记录
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  rankings: { type: Array, default: () => [] }
})

const expandedUser = ref('')

const toggleExpand = (user_name) => {
  expandedUser.value = expandedUser.value === user_name ? '' : user_name
}

const getRankClass = (rank) => {
  if (rank === 1) return 'rank-gold'
  if (rank === 2) return 'rank-silver'
  if (rank === 3) return 'rank-bronze'
  return ''
}

const compositeStyle = (score) => {
  if (score >= 80) return { color: '#34c759', fontWeight: 'bold' }
  if (score >= 60) return { color: '#ff9500' }
  if (score >= 40) return { color: '#ff3b30' }
  return { color: '#8e8e93' }
}

const formatScore = (score) => {
  if (score === undefined || score === null) return '0.0'
  return Number(score).toFixed(1)
}
</script>

<style scoped>
.ranking-board {
  height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0; /* 允许 flex 子项收缩，防止内容溢出产生滚动条 */
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
}

.ranking-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 14px;
  background: var(--color-bg-primary);
  border-bottom: 2px solid var(--color-brand-light);
}

.ranking-header-left {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ranking-title {
  font-weight: 800;
  font-size: 14px;
  color: var(--color-text-primary);
}

.rule-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--color-brand-light);
  color: var(--color-brand);
  font-size: 11px;
  font-weight: 700;
  cursor: help;
}

.ranking-count {
  font-size: 12px;
  color: var(--color-brand);
  background: var(--color-brand-light);
  padding: 2px 8px;
  border-radius: 20px;
  font-weight: 600;
}

.ranking-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
  min-height: 0; /* 允许 flex 收缩 */
}

.ranking-item {
  display: flex;
  flex-direction: column;
  padding: 8px 12px;
  transition: all var(--transition-fast);
  border-bottom: 1px solid var(--color-border-light);
  font-size: 13px;
  line-height: 1.6;
  cursor: pointer;
}

.ranking-item:hover {
  background: var(--color-bg-tertiary);
}

.ranking-main {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 排名序号 */
.rank-number-badge {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 800;
  flex-shrink: 0;
  background: var(--color-bg-tertiary);
  color: var(--color-text-tertiary);
}

/* 用户名 */
.rank-user {
  flex: 1;
  font-size: 13px;
  color: var(--color-text-primary);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}

/* 综合关联度 */
.rank-score {
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  min-width: 42px;
  text-align: right;
}

/* 次数徽章 */
.rank-times-badge {
  font-size: 11px;
  color: var(--color-text-tertiary);
  background: var(--color-bg-tertiary);
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 700;
  white-space: nowrap;
  flex-shrink: 0;
}

.rank-times-badge.has-correct {
  color: #fff;
  background: linear-gradient(135deg, #ffd700, #ffec8b);
  box-shadow: 0 1px 3px rgba(255, 215, 0, 0.25);
}

/* 详情展开区 */
.ranking-detail {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 12px;
  padding: 6px 30px 2px;
  animation: detail-expand 0.2s ease-out;
}

.detail-row {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  min-width: 45%;
}

.detail-label {
  color: var(--color-text-tertiary);
}

.detail-value {
  color: var(--color-text-secondary);
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

@keyframes detail-expand {
  from {
    opacity: 0;
    max-height: 0;
  }
  to {
    opacity: 1;
    max-height: 60px;
  }
}

/* ===== 前三名特殊样式 ===== */
.rank-gold {
  background: linear-gradient(90deg, #fffdf0 0%, var(--color-bg-primary) 100%);
  border-left: 3px solid #ffd700;
}
.rank-gold .rank-number-badge {
  background: linear-gradient(135deg, #ffd700 0%, #ffec8b 100%);
  color: #8b6914;
}
.rank-gold .rank-user {
  color: #8b6914;
  font-weight: 700;
}

.rank-silver {
  background: linear-gradient(90deg, #fafafa 0%, var(--color-bg-primary) 100%);
  border-left: 3px solid #c0c0c0;
}
.rank-silver .rank-number-badge {
  background: linear-gradient(135deg, #c0c0c0 0%, #e8e8e8 100%);
  color: #555;
}
.rank-silver .rank-user {
  font-weight: 600;
}

.rank-bronze {
  background: linear-gradient(90deg, #fff8f0 0%, var(--color-bg-primary) 100%);
  border-left: 3px solid #cd7f32;
}
.rank-bronze .rank-number-badge {
  background: linear-gradient(135deg, #cd7f32 0%, #e8a861 100%);
  color: #6b4423;
}
.rank-bronze .rank-user {
  font-weight: 600;
}

.empty-ranking {
  text-align: center;
  color: var(--color-text-tertiary);
  padding: 40px 16px;
  font-size: 13px;
}

/* 位移动画 */
.rank-move-enter-active {
  animation: rank-fade-in 0.35s ease-out;
}
.rank-move-leave-active {
  position: absolute;
  width: calc(100% - 0px);
  animation: rank-fade-out 0.2s ease-in;
}
.rank-move-move {
  transition: transform 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}

@keyframes rank-fade-in {
  from {
    opacity: 0;
    transform: translateY(-10px) scale(0.97);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes rank-fade-out {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
    transform: translateX(20px);
  }
}
</style>
