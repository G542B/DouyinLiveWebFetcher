<template>
  <div class="game-launcher">
    <!-- 横幅标题 -->
    <div class="launcher-banner">
      <div class="banner-content">
        <h2>🎮 游戏大厅</h2>
        <p class="banner-sub">选择游戏，开始弹幕互动之旅</p>
      </div>
    </div>

    <!-- 游戏卡片网格 -->
    <div class="game-grid">
      <div
        v-for="game in availableGames"
        :key="game.id"
        class="game-card"
        :class="{ 'game-card-disabled': game.status === 'coming_soon' }"
        @click="openGame(game)"
      >
        <!-- 卡片头部：图标 + 状态标签 -->
        <div class="card-header" :style="{ background: game.gradient, borderBottomColor: game.accent }">
          <span class="card-icon" :style="{ background: game.accent }">{{ game.icon }}</span>
          <el-tag
            v-if="game.status === 'new'"
            size="small"
            class="status-tag status-new"
            effect="dark"
          >NEW</el-tag>
          <el-tag
            v-else-if="game.status === 'hot'"
            size="small"
            class="status-tag status-hot"
            effect="dark"
          >HOT</el-tag>
          <el-tag
            v-else-if="game.status === 'coming_soon'"
            size="small"
            class="status-tag status-soon"
            effect="dark"
          >即将上线</el-tag>
        </div>

        <!-- 卡片体 -->
        <div class="card-body">
          <h3 class="card-title">{{ game.name }}</h3>
          <p class="card-desc">{{ game.description }}</p>
        </div>

        <!-- 卡片底部 -->
        <div class="card-footer">
          <el-button
            :type="game.status === 'coming_soon' ? 'info' : 'primary'"
            size="default"
            round
            :disabled="game.status === 'coming_soon'"
            class="play-btn"
          >
            {{ game.status === 'coming_soon' ? '敬请期待' : '▶ 开始游戏' }}
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'

// ===== 游戏注册表 =====
const availableGames = ref([
  {
    id: 'word-guessing',
    name: '猜词挑战',
    icon: '🎯',
    description: '观众通过弹幕发送文字猜词，智能算法评估相似度，快来比比谁猜得最准！',
    gradient: 'linear-gradient(135deg, var(--color-brand-light) 0%, var(--color-bg-primary) 100%)',
    accent: 'var(--color-brand)',
    status: 'hot',
  },
  {
    id: 'future-1',
    name: '更多模式',
    icon: '🎮',
    description: '更多精彩游戏模式即将上线，敬请期待...',
    gradient: 'linear-gradient(135deg, var(--color-bg-tertiary) 0%, var(--color-bg-primary) 100%)',
    accent: 'var(--color-info)',
    status: 'coming_soon',
  }
])

const openGame = (game) => {
  if (game.status === 'coming_soon') {
    ElMessage.info('该游戏正在开发中，敬请期待！')
    return
  }
  // Electron 环境通过 IPC 打开独立窗体，浏览器环境用新标签页
  if (window.electronAPI) {
    window.electronAPI.openGameWindow()
  } else {
    window.open(`${window.location.origin}${window.location.pathname}?window=game`, '_blank')
  }
}

// 监听游戏窗体关闭事件
const onGameWindowClosed = () => {
  // 可在此处做状态重置
}

onMounted(() => {
  if (window.electronAPI) {
    window.electronAPI.onGameWindowClosed(onGameWindowClosed)
  }
})

onUnmounted(() => {
  // IPC 监听器随窗口销毁自动清理
})
</script>

<style scoped>
.game-launcher {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  background: var(--color-bg-secondary);
}

/* ===== 横幅：白色 + 品牌色底线 ===== */
.launcher-banner {
  background: var(--color-bg-primary);
  padding: 32px 40px;
  color: var(--color-text-primary);
  flex-shrink: 0;
  border-bottom: 3px solid var(--color-brand);
  animation: banner-fade-in 0.4s ease-out;
}

@keyframes banner-fade-in {
  from { opacity: 0; transform: translateY(-8px); }
  to { opacity: 1; transform: translateY(0); }
}

.banner-content h2 {
  font-size: 24px;
  margin: 0 0 6px 0;
  font-weight: 800;
  color: var(--color-text-primary);
}

.banner-sub {
  font-size: 14px;
  color: var(--color-text-secondary);
  margin: 0;
}

/* ===== 卡片网格 ===== */
.game-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 24px;
  padding: 28px 32px;
  flex: 1;
  align-content: start;
}

/* ===== 单张卡片 ===== */
.game-card {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  overflow: hidden;
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--color-border-light);
  animation: card-enter 0.4s ease-out backwards;
}

.game-card:nth-child(1) { animation-delay: 0.05s; }
.game-card:nth-child(2) { animation-delay: 0.1s; }
.game-card:nth-child(3) { animation-delay: 0.15s; }
.game-card:nth-child(4) { animation-delay: 0.2s; }
.game-card:nth-child(5) { animation-delay: 0.25s; }
.game-card:nth-child(6) { animation-delay: 0.3s; }

@keyframes card-enter {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}

.game-card:hover {
  transform: translateY(-6px);
  box-shadow: var(--shadow-lg);
  border-color: var(--color-brand-light);
}

.game-card:active {
  transform: translateY(-2px);
}

.game-card-disabled {
  opacity: 0.6;
  cursor: default;
}

.game-card-disabled:hover {
  transform: none;
  box-shadow: var(--shadow-sm);
  border-color: var(--color-border-light);
}

/* 卡片头部 */
.card-header {
  height: 110px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  flex-shrink: 0;
  border-bottom: 3px solid var(--color-brand);
}

.card-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  font-size: 32px;
  color: #fff;
  filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.15));
}

.status-tag {
  position: absolute;
  top: 12px;
  right: 12px;
  font-weight: 700 !important;
  border: none !important;
  border-radius: 20px !important;
}

.status-new {
  background: var(--color-success) !important;
}

.status-hot {
  background: var(--color-warning) !important;
}

.status-soon {
  background: var(--color-info) !important;
}

/* 卡片体 */
.card-body {
  padding: 18px 20px 12px;
  flex: 1;
}

.card-title {
  font-size: 17px;
  font-weight: 700;
  margin: 0 0 8px 0;
  color: var(--color-text-primary);
}

.card-desc {
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.6;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 卡片底部 */
.card-footer {
  padding: 8px 20px 18px;
  flex-shrink: 0;
}

.play-btn {
  width: 100%;
  font-weight: 600;
  letter-spacing: 0.5px;
}

/* ===== 响应式 ===== */
@media (max-width: 1024px) {
  .game-grid {
    padding: 20px 24px;
    gap: 20px;
  }
}

@media (max-width: 768px) {
  .launcher-banner {
    padding: 24px 20px;
  }
  .banner-content h2 {
    font-size: 20px;
  }
  .game-grid {
    grid-template-columns: 1fr;
    padding: 16px;
    gap: 16px;
  }
}
</style>
