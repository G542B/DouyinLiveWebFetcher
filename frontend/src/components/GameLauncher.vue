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
        <div class="card-header" :style="{ background: game.gradient }">
          <span class="card-icon">{{ game.icon }}</span>
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
    gradient: 'linear-gradient(135deg, #f5a623 0%, #f7b733 40%, #fcdbb6 100%)',
    status: 'hot',
  },
  {
    id: 'future-1',
    name: '更多模式',
    icon: '🎮',
    description: '更多精彩游戏模式即将上线，敬请期待...',
    gradient: 'linear-gradient(135deg, #a8c0ff 0%, #3f2b96 100%)',
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
  background: linear-gradient(180deg, #f0f2f5 0%, #e8ecf1 100%);
}

/* ===== 横幅 ===== */
.launcher-banner {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 36px 40px;
  color: white;
  flex-shrink: 0;
}

.banner-content h2 {
  font-size: 28px;
  margin: 0 0 8px 0;
  font-weight: 700;
}

.banner-sub {
  font-size: 15px;
  opacity: 0.85;
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
  background: #fff;
  border-radius: 16px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  transition: all 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94);
  cursor: pointer;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(0, 0, 0, 0.04);
}

.game-card:hover {
  transform: translateY(-6px);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
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
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

/* 卡片头部 */
.card-header {
  height: 110px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  flex-shrink: 0;
}

.card-icon {
  font-size: 48px;
  filter: drop-shadow(0 2px 8px rgba(0, 0, 0, 0.15));
}

.status-tag {
  position: absolute;
  top: 12px;
  right: 12px;
  font-weight: 700 !important;
  border: none !important;
}

.status-new {
  background: #67c23a !important;
}

.status-hot {
  background: #e6a23c !important;
}

.status-soon {
  background: #909399 !important;
}

/* 卡片体 */
.card-body {
  padding: 18px 20px 12px;
  flex: 1;
}

.card-title {
  font-size: 18px;
  font-weight: 700;
  margin: 0 0 8px 0;
  color: #303133;
}

.card-desc {
  font-size: 13px;
  color: #909399;
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

@media (max-width: 640px) {
  .launcher-banner {
    padding: 24px 20px;
  }
  .banner-content h2 {
    font-size: 22px;
  }
  .game-grid {
    grid-template-columns: 1fr;
    padding: 16px;
    gap: 16px;
  }
}
</style>
