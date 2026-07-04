<template>
  <!-- 子窗口模式：独立渲染对应组件 -->
  <div v-if="windowMode" class="sub-window-container">
    <GamePanel v-if="windowMode === 'game'" />
    <GameConfigPanel v-else-if="windowMode === 'config'" />
    <WordBankManager v-else-if="windowMode === 'wordbank'" />
    <GameHistory v-else-if="windowMode === 'history'" />
  </div>

  <!-- 主窗口模式 -->
  <div v-else-if="checkingLicense" class="loading-wrapper">
    <div class="loading-container">
      <el-icon class="loading-icon" :size="48"><Loading /></el-icon>
      <p>正在验证许可证...</p>
    </div>
  </div>
  <LicenseVerify v-else-if="!licenseVerified" />
  <el-container v-else class="app-container">
    <el-header class="app-header">
      <button class="sidebar-toggle" @click="sidebarOpen = !sidebarOpen" aria-label="菜单">
        <el-icon><Menu /></el-icon>
      </button>
      <h1>🎬 抖音直播弹幕抓取器</h1>
      <div class="header-right">
        <el-tag
          :type="wsConnected ? 'success' : 'danger'"
          size="small"
          effect="dark"
        >
          {{ wsConnected ? 'WebSocket 已连接' : 'WebSocket 未连接' }}
        </el-tag>
      </div>
    </el-header>

    <el-container class="main-container">
      <div v-if="sidebarOpen" class="sidebar-mask" @click="sidebarOpen = false"></div>
      <el-aside class="sidebar" :class="{ open: sidebarOpen }" width="360px">
        <div class="sidebar-content">
          <RoomManager @rooms-updated="handleRoomsUpdated" />
          <FilterConfig />
          <OutputConfig />
          <PerformanceMonitor />
        </div>
      </el-aside>

      <el-main class="main-content">
        <el-tabs v-model="activeTab" class="main-tabs">
          <el-tab-pane label="弹幕消息" name="danmaku">
            <DanmakuViewer :messages="messages" @clear="clearMessages" />
          </el-tab-pane>
          <el-tab-pane label="游戏大厅" name="game">
            <GameLauncher />
          </el-tab-pane>
        </el-tabs>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { Loading, Menu } from '@element-plus/icons-vue'
import LicenseVerify from './components/LicenseVerify.vue'
import RoomManager from './components/RoomManager.vue'
import FilterConfig from './components/FilterConfig.vue'
import DanmakuViewer from './components/DanmakuViewer.vue'
import OutputConfig from './components/OutputConfig.vue'
import PerformanceMonitor from './components/PerformanceMonitor.vue'
import GameLauncher from './components/GameLauncher.vue'
import GamePanel from './components/GamePanel.vue'
import GameConfigPanel from './components/GameConfigPanel.vue'
import WordBankManager from './components/WordBankManager.vue'
import GameHistory from './components/GameHistory.vue'

// 检测子窗口模式
const urlParams = new URLSearchParams(window.location.search)
const windowMode = urlParams.get('window') || null

const messages = ref([])
const wsConnected = ref(false)
const licenseVerified = ref(false)
const maxMessageAge = 10 * 60 * 1000
const checkingLicense = ref(true)
const activeTab = ref('danmaku')
const sidebarOpen = ref(false)
let ws = null
let cleanupInterval = null

// [TEMP-DISABLE-LICENSE] 临时禁用许可证验证标志，设为 true 跳过验证，设为 false 恢复验证
const LICENSE_BYPASS = true

const checkLicense = async () => {
  // [TEMP-DISABLE-LICENSE] 当 LICENSE_BYPASS 为 true 时直接跳过验证
  if (LICENSE_BYPASS) {
    licenseVerified.value = true
    checkingLicense.value = false
    console.warn('[License] 许可证验证已临时禁用（LICENSE_BYPASS=true）')
    return
  }
  try {
    const response = await axios.get('/api/license/status')
    licenseVerified.value = response.data.verified === true
  } catch (e) {
    console.error('许可证检查失败:', e)
    licenseVerified.value = false
  } finally {
    checkingLicense.value = false
  }
}

onMounted(async () => {
  // 子窗口模式：游戏窗体需要 WebSocket，其他子窗体不需要
  if (windowMode === 'game') {
    connectWebSocket()
    return
  }
  if (windowMode) {
    return
  }

  await checkLicense()
  if (licenseVerified.value) {
    connectWebSocket()
    startCleanup()
  }
})

const startCleanup = () => {
  cleanupInterval = setInterval(() => {
    const now = Date.now()
    messages.value = messages.value.filter(msg => {
      const msgTime = new Date(msg.timestamp).getTime()
      return now - msgTime < maxMessageAge
    })
  }, 30000)
}

const connectWebSocket = () => {
  const wsUrl = location.protocol === 'https:' 
    ? `wss://${location.host}/ws/danmaku`
    : `ws://${location.host}/ws/danmaku`
  
  ws = new WebSocket(wsUrl)

  ws.onopen = () => {
    wsConnected.value = true
    console.log('[WebSocket] 连接成功')
  }

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      const msgType = data.message_type

      // 触发 window 自定义事件，让其他组件（如 OutputConfig）能订阅特定事件类型
      try {
        window.dispatchEvent(new CustomEvent('ws-message', { detail: data }))
      } catch (evtErr) {
        // 忽略 CustomEvent 不支持的旧浏览器
      }

      if (msgType === 'output_sent' || msgType === 'output_error' || msgType === 'output_progress' || msgType === 'output_status' || msgType === 'playwright_progress') {
        return
      }

      // 游戏消息不显示在弹幕列表中，由GamePanel组件通过ws-message事件处理
      if (msgType && msgType.startsWith('game_')) {
        return
      }

      data._uid = Date.now() + Math.random()
      messages.value.unshift(data)

      const now = Date.now()
      messages.value = messages.value.filter(msg => {
        const msgTime = new Date(msg.timestamp).getTime()
        return now - msgTime < maxMessageAge
      })
    } catch (e) {
      console.error('[WebSocket] 解析消息失败:', e, event.data)
    }
  }

  ws.onerror = (error) => {
    console.error('[WebSocket] 连接错误:', error)
  }

  ws.onclose = (event) => {
    wsConnected.value = false
    console.log(`[WebSocket] 连接关闭: code=${event.code}, reason=${event.reason}`)
    setTimeout(connectWebSocket, 3000)
  }
}

const handleRoomsUpdated = () => {
}

const clearMessages = () => {
  messages.value = []
}
</script>

<style>
/* ===== 全局设计系统 ===== */
:root {
  /* 主色调 - 白色系 */
  --color-bg-primary: #ffffff;
  --color-bg-secondary: #f8f9fb;
  --color-bg-tertiary: #f1f3f7;

  /* 品牌色 */
  --color-brand: #4f6df5;
  --color-brand-light: #e8edfe;
  --color-brand-dark: #3b54d4;

  /* 功能色 - 柔和系 */
  --color-success: #34c759;
  --color-warning: #ff9500;
  --color-danger: #ff3b30;
  --color-info: #8e8e93;

  /* 文字色 */
  --color-text-primary: #1d1d1f;
  --color-text-secondary: #6e6e73;
  --color-text-tertiary: #aeaeb2;

  /* 边框与分割 */
  --color-border: #e5e5ea;
  --color-border-light: #f0f0f5;

  /* 阴影 - 柔和层次 */
  --shadow-sm: 0 1px 3px rgba(0,0,0,0.04);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.06);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.08);
  --shadow-brand: 0 4px 14px rgba(79,109,245,0.15);

  /* 圆角 */
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;

  /* 过渡 */
  --transition-fast: 0.15s ease;
  --transition-base: 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  --transition-spring: 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);

  /* 奖牌色 */
  --medal-gold: #ffd700;
  --medal-gold-light: #ffec8b;
  --medal-silver: #c0c0c0;
  --medal-silver-light: #e8e8e8;
  --medal-bronze: #cd7f32;
  --medal-bronze-light: #e8a861;

  /* 响应式断点 */
  --bp-tablet: 1024px;
  --bp-mobile: 768px;
  --bp-small: 480px;
}

html, body {
  margin: 0;
  padding: 0;
  height: 100%;
  overflow: hidden;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif;
  color: var(--color-text-primary);
  background: var(--color-bg-primary);
}

/* ===== 滚动条美化 ===== */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-thumb {
  background: var(--color-text-tertiary);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--color-text-secondary);
}
::-webkit-scrollbar-track {
  background: transparent;
}

/* ===== Element Plus 全局覆盖 ===== */

/* 按钮统一交互 */
.el-button {
  transition: all var(--transition-base) !important;
  border-radius: var(--radius-sm) !important;
}
.el-button:not(.is-disabled):hover {
  transform: translateY(-1px);
}
.el-button:not(.is-disabled):active {
  transform: translateY(0);
}
.el-button--primary {
  box-shadow: var(--shadow-brand) !important;
}

/* 输入框聚焦反馈 */
.el-input__wrapper {
  transition: box-shadow var(--transition-fast) !important;
  border-radius: var(--radius-sm) !important;
}
.el-input__wrapper.is-focus {
  box-shadow: 0 0 0 3px var(--color-brand-light) !important;
}

/* 卡片统一 */
.el-card {
  border-radius: var(--radius-md) !important;
  box-shadow: var(--shadow-sm) !important;
  border: none !important;
  transition: box-shadow var(--transition-base) !important;
}
.el-card:hover {
  box-shadow: var(--shadow-md) !important;
}

/* Tab 样式 */
.el-tabs__header {
  margin: 0 !important;
}

/* 表格统一 */
.el-table {
  --el-table-border-color: var(--color-border-light);
  --el-table-header-bg-color: var(--color-bg-secondary);
  --el-table-row-hover-bg-color: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.el-table th.el-table__cell {
  background: var(--color-bg-secondary) !important;
  color: var(--color-text-secondary);
  font-weight: 600;
}

/* 标签统一 */
.el-tag {
  border-radius: var(--radius-sm);
  font-weight: 500;
}

/* 对话框统一 */
.el-dialog {
  border-radius: var(--radius-lg);
  overflow: hidden;
}
.el-dialog__header {
  border-bottom: 1px solid var(--color-border-light);
  margin-right: 0 !important;
}
.el-dialog__title {
  font-weight: 600;
  color: var(--color-text-primary);
}

/* 表单项统一 */
.el-form-item__label {
  color: var(--color-text-secondary);
  font-weight: 500;
}

/* 空状态统一 */
.empty-state,
.empty-guesses,
.empty-ranking,
.empty-logs {
  text-align: center;
  color: var(--color-text-tertiary);
  padding: 48px 20px;
  font-size: 14px;
}

/* Emoji 标准化 */
.emoji-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--color-brand-light);
  font-size: 16px;
  flex-shrink: 0;
}

/* 页面淡入动画 */
@keyframes app-fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

/* 卡片入场动画 */
.el-card {
  animation: app-fade-in 0.4s ease-out;
}
</style>

<style scoped>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

/* 子窗口容器：撑满整个窗口 */
.sub-window-container {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  animation: app-fade-in 0.4s ease-out;
}

.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
  animation: app-fade-in 0.4s ease-out;
}

/* ===== Header：白色毛玻璃 ===== */
.app-header {
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--color-border-light);
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  padding: 0 24px;
  height: 56px;
  flex-shrink: 0;
  z-index: 100;
  gap: 12px;
}

.app-header h1 {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

/* 汉堡菜单按钮（移动端显示） */
.sidebar-toggle {
  display: none;
  background: none;
  border: none;
  font-size: 20px;
  color: var(--color-text-primary);
  cursor: pointer;
  padding: 6px;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
  align-items: center;
  justify-content: center;
}
.sidebar-toggle:hover {
  background: var(--color-bg-tertiary);
}

.header-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

/* WebSocket 状态指示器 */
.header-right :deep(.el-tag) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none !important;
  font-weight: 600;
  border-radius: 20px !important;
  padding: 0 12px !important;
}

.main-container {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* ===== 侧边栏 ===== */
.sidebar {
  background: var(--color-bg-secondary);
  border-right: 1px solid var(--color-border-light);
  overflow-y: auto;
  padding: 20px 16px;
  min-width: 280px;
  max-width: 480px;
  flex-shrink: 0;
}

.sidebar-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ===== 主内容区 ===== */
.main-content {
  flex: 1;
  padding: 0;
  overflow: hidden;
  background: var(--color-bg-primary);
  display: flex;
  flex-direction: column;
}

.main-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.main-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: hidden;
}

.main-tabs :deep(.el-tab-pane) {
  height: 100%;
}

.main-tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 20px;
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-light);
}

.main-tabs :deep(.el-tabs__item) {
  font-weight: 600;
  font-size: 15px;
  height: 48px;
}

/* ===== 加载页 ===== */
.loading-wrapper {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-secondary);
}

.loading-container {
  text-align: center;
  color: var(--color-text-secondary);
}

.loading-icon {
  animation: rotating 1.4s linear infinite;
  margin-bottom: 16px;
  color: var(--color-brand);
}

.loading-container p {
  font-size: 15px;
  opacity: 0.8;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ===== 响应式布局 ===== */
@media (max-width: 1024px) {
  .sidebar {
    width: 300px !important;
    min-width: 260px !important;
  }
}

@media (max-width: 768px) {
  .sidebar-toggle {
    display: inline-flex;
  }
  .main-container {
    flex-direction: column !important;
    position: relative;
  }
  .sidebar {
    position: fixed !important;
    left: 0;
    top: 56px;
    bottom: 0;
    width: 320px !important;
    max-width: 85vw !important;
    min-width: 0 !important;
    max-height: none !important;
    transform: translateX(-100%);
    transition: transform var(--transition-base);
    z-index: 1000;
    box-shadow: var(--shadow-lg);
  }
  .sidebar.open {
    transform: translateX(0);
  }
  .sidebar-mask {
    position: fixed;
    inset: 56px 0 0 0;
    background: rgba(0, 0, 0, 0.4);
    z-index: 999;
    backdrop-filter: blur(2px);
  }
  .main-content {
    min-height: 0;
    width: 100%;
  }
  .app-header {
    padding: 0 12px;
  }
  .app-header h1 {
    font-size: 15px;
  }
}
</style>
