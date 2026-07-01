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
      <el-aside class="sidebar" width="360px">
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
import { Loading } from '@element-plus/icons-vue'
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

<style scoped>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

/* 子窗口容器：撑满整个窗口 */
.sub-window-container {
  width: 100vw;
  height: 100vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.app-container {
  height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  padding: 0 20px;
  height: 60px;
}

.app-header h1 {
  font-size: 24px;
}

.header-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.main-container {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.sidebar {
  background: #f5f7fa;
  border-right: 1px solid #e4e7ed;
  overflow-y: auto;
  padding: 16px;
  min-width: 280px;
  max-width: 480px;
  flex-shrink: 0;
}

.sidebar-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.main-content {
  flex: 1;
  padding: 0;
  overflow: hidden;
  background: #fafafa;
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
  padding: 0 16px;
  background: #fff;
}

.loading-wrapper {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.loading-container {
  text-align: center;
  color: white;
}

.loading-icon {
  animation: rotating 1.4s linear infinite;
  margin-bottom: 16px;
}

.loading-container p {
  font-size: 16px;
  opacity: 0.9;
}

@keyframes rotating {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 响应式布局：小窗口时侧边栏切换为上下布局 */
@media (max-width: 900px) {
  .main-container {
    flex-direction: column !important;
  }
  .sidebar {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    max-height: 40vh;
    border-right: none !important;
    border-bottom: 1px solid #e4e7ed;
  }
  .main-content {
    min-height: 0;
  }
}
</style>
