<template>
  <el-card class="output-config">
    <template #header>
      <div class="card-header">
        <span>📤 弹幕输出自动化</span>
        <div class="header-tags">
          <el-tag
            :type="status.running ? 'success' : 'info'"
            size="small"
            effect="dark"
          >
            {{ status.running ? '运行中' : '已停止' }}
          </el-tag>
        </div>
      </div>
    </template>

    <el-tabs v-model="activeTab" type="border-card">
      <el-tab-pane label="浏览器输出" name="browser">
        <div class="config-section">
          <div class="section-title">🌐 目标网站</div>
          <el-form label-position="top" size="small">
            <el-form-item label="网站 URL">
              <div class="url-row">
                <el-input
                  v-model="config.target_url"
                  placeholder="https://example.com/chat"
                  :disabled="status.running"
                />
                <el-button
                  v-if="!status.browser_connected"
                  type="primary"
                  @click="openWebsite"
                  :loading="openingWebsite"
                  :disabled="!config.target_url || status.running"
                >
                  {{ openingWebsite ? '正在打开...' : '打开网站' }}
                </el-button>
                <el-button
                  v-else
                  type="danger"
                  @click="closeBrowser"
                  :disabled="status.running"
                >
                  关闭浏览器
                </el-button>
              </div>
              <div v-if="openingWebsite && progressMessage" class="progress-hint">
                <el-icon class="rotating"><Loading /></el-icon>
                <span>{{ progressMessage }}</span>
              </div>
              <div v-if="status.status_message" class="status-message">
                {{ status.status_message }}
              </div>
            </el-form-item>
          </el-form>
        </div>

        <div class="config-section">
          <div class="section-title">🎯 页面元素配置</div>
          <ElementPicker
            ref="elementPickerRef"
            :browser-connected="status.browser_connected"
            :disabled="status.running"
            :initial-textarea-selector="config.textarea_selector"
            :initial-button-selector="config.button_selector"
            @update:textarea-selector="val => { config.textarea_selector = val; saveConfig() }"
            @update:button-selector="val => { config.button_selector = val; saveConfig() }"
            @update:textarea-selectors="val => { config.textarea_selectors = val; saveConfig() }"
            @update:button-selectors="val => { config.button_selectors = val; saveConfig() }"
          />
        </div>

        <div v-if="status.browser_connected" class="config-section">
          <div class="section-title">📐 窗口尺寸</div>
          <el-form label-position="top" size="small">
            <el-form-item>
              <div class="viewport-info-row">
                <span class="viewport-label">当前视口：</span>
                <el-tag size="small" type="info">{{ viewportInfo.width }} × {{ viewportInfo.height }}</el-tag>
                <el-tag v-if="viewportAutoResize" size="small" type="success" style="margin-left: 6px;">自适应</el-tag>
              </div>
            </el-form-item>
            <el-form-item label="自定义尺寸">
              <div class="viewport-row">
                <el-input-number v-model="customViewport.width" :min="320" :max="3840" :step="10" size="small" controls-position="right" />
                <span class="viewport-x">×</span>
                <el-input-number v-model="customViewport.height" :min="240" :max="2160" :step="10" size="small" controls-position="right" />
                <el-button size="small" type="primary" @click="applyViewport" :disabled="!status.browser_connected">应用</el-button>
              </div>
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="autoResizeSync" @change="handleAutoSyncChange">
                自适应同步（调整本窗口时自动同步 Playwright 视口）
              </el-checkbox>
            </el-form-item>
          </el-form>
        </div>

        <div class="config-section">
          <div class="section-title">⚙️ 发送参数</div>
          <el-form label-position="top" size="small">
            <el-form-item label="发送模式">
              <el-radio-group v-model="config.send_mode" @change="saveConfig">
                <el-radio value="sequential">逐条发送</el-radio>
                <el-radio value="batch">批量发送</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="发送间隔（秒）">
              <el-input-number
                v-model="config.send_interval"
                :min="0.1"
                :max="60"
                :step="0.1"
                :disabled="status.running"
                @change="saveConfig"
              />
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="config.include_username" @change="saveConfig">
                输出内容中包含用户名
              </el-checkbox>
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="config.include_timestamp" @change="saveConfig">
                输出内容中包含时间
              </el-checkbox>
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="config.auto_click_button" @change="saveConfig">
                自动点击发送按钮
              </el-checkbox>
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="config.auto_press_enter" @change="saveConfig">
                自动按回车键发送
              </el-checkbox>
            </el-form-item>
          </el-form>
        </div>

        <!-- 浏览器输出独立控制按钮和统计 -->
        <div class="control-section">
          <el-button
            type="success"
            size="large"
            :disabled="!canStartBrowser"
            :loading="browserStatus.running"
            @click="startBrowserOutput"
          >
            ▶ 开始浏览器输出
          </el-button>
          <el-button
            type="danger"
            size="large"
            :disabled="!browserStatus.running"
            @click="stopBrowserOutput"
          >
            ⏹ 停止浏览器输出
          </el-button>
        </div>

        <div class="stats-section">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="已发送数量">
              <strong>{{ browserStatus.total_sent }}</strong>
            </el-descriptions-item>
            <el-descriptions-item label="最后发送时间">
              {{ formatTime(browserStatus.last_execution_time) }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <div v-if="browserStatus.last_error" class="error-banner">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ browserStatus.last_error }}</span>
        </div>

        <div v-if="browserDisconnected" class="error-banner disconnect-banner">
          <el-icon><WarningFilled /></el-icon>
          <span>浏览器连接已断开，输出已自动停止。请重新打开网站。</span>
        </div>
      </el-tab-pane>

      <el-tab-pane label="文件输出" name="file">
        <div class="config-section">
          <div class="section-title">📄 文件配置</div>
          <el-form label-position="top" size="small">
            <el-form-item label="输出文件路径">
              <el-input
                v-model="config.file_output_path"
                placeholder="C:/output/danmaku.txt 或 /home/user/danmaku.txt"
                :disabled="status.running"
                @change="saveConfig"
              />
            </el-form-item>
            <el-form-item>
              <el-radio-group v-model="config.file_append_mode" @change="saveConfig">
                <el-radio :value="true">追加模式</el-radio>
                <el-radio :value="false">覆盖模式</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-form>
        </div>

        <div class="config-section">
          <div class="section-title">⚙️ 写入参数</div>
          <el-form label-position="top" size="small">
            <el-form-item label="写入模式">
              <el-radio-group v-model="config.send_mode" @change="saveConfig">
                <el-radio value="sequential">逐条写入</el-radio>
                <el-radio value="batch">批量写入</el-radio>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="写入间隔（秒）">
              <el-input-number
                v-model="config.send_interval"
                :min="0.1"
                :max="60"
                :step="0.1"
                :disabled="status.running"
                @change="saveConfig"
              />
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="config.include_username" @change="saveConfig">
                输出内容中包含用户名
              </el-checkbox>
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="config.include_timestamp" @change="saveConfig">
                输出内容中包含时间
              </el-checkbox>
            </el-form-item>
            <el-form-item>
              <el-checkbox v-model="config.add_newline" @change="saveConfig">
                每条消息后添加换行
              </el-checkbox>
            </el-form-item>
          </el-form>
        </div>

        <!-- 文件输出独立控制按钮和统计 -->
        <div class="control-section">
          <el-button
            type="success"
            size="large"
            :disabled="!canStartFile"
            :loading="fileStatus.running"
            @click="startFileOutput"
          >
            ▶ 开始文件输出
          </el-button>
          <el-button
            type="danger"
            size="large"
            :disabled="!fileStatus.running"
            @click="stopFileOutput"
          >
            ⏹ 停止文件输出
          </el-button>
        </div>

        <div class="stats-section">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item label="已写入数量">
              <strong>{{ fileStatus.total_sent }}</strong>
            </el-descriptions-item>
            <el-descriptions-item label="最后写入时间">
              {{ formatTime(fileStatus.last_execution_time) }}
            </el-descriptions-item>
          </el-descriptions>
        </div>

        <div v-if="fileStatus.last_error" class="error-banner">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ fileStatus.last_error }}</span>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- 浏览器输出独立控制按钮和统计（在浏览器Tab内） -->
    <!-- 注：控制按钮已移入各自 Tab 内，无全局控制按钮 -->

    <div class="logs-section">
      <div class="logs-title">📋 发送日志</div>
      <div class="logs-container">
        <div v-for="(log, index) in logs" :key="index" class="log-item" :class="{ error: !log.success }">
          <span class="log-time">{{ formatTime(log.timestamp) }}</span>
          <span class="log-content">{{ log.content }}</span>
          <span v-if="log.error" class="log-error">{{ log.error }}</span>
        </div>
        <div v-if="logs.length === 0" class="empty-logs">暂无日志</div>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { WarningFilled, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import ElementPicker from './ElementPicker.vue'

const browserStatus = ref({
  running: false,
  last_execution_time: null,
  total_sent: 0,
  last_error: null,
  status_message: '就绪'
})

const fileStatus = ref({
  running: false,
  last_execution_time: null,
  total_sent: 0,
  last_error: null,
  status_message: '就绪'
})

const config = ref({
  output_mode: 'browser',
  target_url: '',
  textarea_selector: '',
  button_selector: '',
  textarea_selectors: [],
  button_selectors: [],
  browser_headless: false,
  file_output_path: '',
  file_append_mode: true,
  send_mode: 'sequential',
  send_interval: 2.0,
  auto_click_button: true,
  auto_press_enter: false,
  add_newline: true,
  include_username: true,
  include_timestamp: false
})

const status = ref({
  running: false,
  last_execution_time: null,
  total_sent: 0,
  last_error: null,
  browser_connected: false,
  status_message: '就绪'
})

const activeTab = ref('browser')
const openingWebsite = ref(false)
const progressMessage = ref('')
const logs = ref([])
const elementPickerRef = ref(null)
const autoResizeSync = ref(false)
const browserDisconnected = ref(false)
const viewportInfo = ref({ width: 1280, height: 720 })
const viewportAutoResize = ref(false)
const customViewport = ref({ width: 1280, height: 720 })

let statusTimer = null
let browserStatusTimer = null
let fileStatusTimer = null
let logsTimer = null
let viewportInfoTimer = null
let resizeSyncTimer = null

// 订阅 window 自定义 ws-message 事件（修复打包版"命令执行超时"问题的关键体验改进）
const handleWebSocketMessage = (event) => {
  try {
    const data = event.detail
    if (data && data.message_type === 'playwright_progress') {
      const payload = data.data || {}
      progressMessage.value = payload.message || ''
      if (payload.phase === 'page_ready') {
        // 页面就绪后保留 2 秒提示再清空
        setTimeout(() => {
          if (progressMessage.value === payload.message) {
            progressMessage.value = ''
          }
        }, 2000)
      }
    }
    // 浏览器断开连接事件
    if (data && data.message_type === 'output_browser_disconnected') {
      browserDisconnected.value = true
      ElMessage.warning('浏览器连接已断开，输出已自动停止')
    }
  } catch (err) {
    // 忽略
  }
}

watch(activeTab, (newTab) => {
  config.value.output_mode = newTab
  saveConfig()
})

const canStartBrowser = computed(() => {
  return status.value.browser_connected && config.value.textarea_selector && !browserStatus.value.running
})

const canStartFile = computed(() => {
  return config.value.file_output_path && !fileStatus.value.running
})

const fetchConfig = async () => {
  try {
    const response = await axios.get('/api/output/config')
    Object.assign(config.value, response.data)
    activeTab.value = config.value.output_mode
  } catch (e) {
    console.error('获取输出配置失败:', e)
  }
}

const fetchStatus = async () => {
  try {
    const response = await axios.get('/api/output/status')
    Object.assign(status.value, response.data)
  } catch (e) {
    console.error('获取输出状态失败:', e)
  }
}

const fetchLogs = async () => {
  try {
    const response = await axios.get('/api/output/logs', { params: { count: 50 } })
    logs.value = response.data.reverse()
  } catch (e) {
    console.error('获取发送日志失败:', e)
  }
}

const saveConfig = async () => {
  try {
    await axios.put('/api/output/config', config.value)
  } catch (e) {
    console.error('配置保存失败:', e)
  }
}

const openWebsite = async () => {
  if (!config.value.target_url) {
    ElMessage.warning('请输入目标网站URL')
    return
  }

  openingWebsite.value = true
  progressMessage.value = '正在初始化浏览器，首次启动可能需要 30-60 秒，请稍候...'
  try {
    await saveConfig()
    const response = await axios.post('/api/output/open-website', null, {
      params: { url: config.value.target_url },
      timeout: 120000  // 前端也放宽到 120 秒，匹配后端 90 秒首次超时 + 网络缓冲
    })
    if (response.data.success) {
      ElMessage.success('网站已打开')
      progressMessage.value = ''
      browserDisconnected.value = false
      fetchStatus()
      fetchViewportInfo()
    } else {
      const err = response.data.error || '打开失败'
      if (err.includes('超时')) {
        ElMessage.error(
          `${err}。请检查：\n1) 网络是否可达\n2) Playwright 浏览器是否已安装（运行 scripts\\check_playwright.bat 检测）\n3) 目标网站是否可访问`,
          { duration: 8000 }
        )
      } else {
        ElMessage.error(err)
      }
      progressMessage.value = ''
    }
  } catch (e) {
    if (e && e.code === 'ECONNABORTED') {
      ElMessage.error('前端请求超时（120秒），请重试或检查网络', { duration: 6000 })
    } else {
      ElMessage.error('打开网站失败: ' + ((e && e.message) || '未知错误'))
    }
    progressMessage.value = ''
    console.error(e)
  } finally {
    openingWebsite.value = false
  }
}

const closeBrowser = async () => {
  try {
    await axios.post('/api/output/close-browser')
    ElMessage.success('浏览器已关闭')
    fetchStatus()
  } catch (e) {
    ElMessage.error('关闭浏览器失败')
    console.error(e)
  }
}

// ===== 浏览器输出控制 =====

const startBrowserOutput = async () => {
  try {
    await saveConfig()
    const response = await axios.post('/api/output/browser/start')
    if (response.data.success) {
      ElMessage.success('浏览器输出已开始')
      browserStatus.value = response.data.status
    } else {
      const err = response.data.status?.last_error || '未知错误'
      ElMessage.error(`启动失败: ${err}`)
    }
  } catch (e) {
    ElMessage.error('启动浏览器输出失败')
    console.error(e)
  }
}

const stopBrowserOutput = async () => {
  try {
    const response = await axios.post('/api/output/browser/stop')
    ElMessage.success('浏览器输出已停止')
    browserStatus.value = response.data.status
  } catch (e) {
    ElMessage.error('停止失败')
    console.error(e)
  }
}

const fetchBrowserStatus = async () => {
  try {
    const response = await axios.get('/api/output/browser/status')
    browserStatus.value = response.data
  } catch (e) {
    console.error('获取浏览器输出状态失败:', e)
  }
}

// ===== 文件输出控制 =====

const startFileOutput = async () => {
  try {
    await saveConfig()
    const response = await axios.post('/api/output/file/start')
    if (response.data.success) {
      ElMessage.success('文件输出已开始')
      fileStatus.value = response.data.status
    } else {
      const err = response.data.status?.last_error || '未知错误'
      ElMessage.error(`启动失败: ${err}`)
    }
  } catch (e) {
    ElMessage.error('启动文件输出失败')
    console.error(e)
  }
}

const stopFileOutput = async () => {
  try {
    const response = await axios.post('/api/output/file/stop')
    ElMessage.success('文件输出已停止')
    fileStatus.value = response.data.status
  } catch (e) {
    ElMessage.error('停止失败')
    console.error(e)
  }
}

const fetchFileStatus = async () => {
  try {
    const response = await axios.get('/api/output/file/status')
    fileStatus.value = response.data
  } catch (e) {
    console.error('获取文件输出状态失败:', e)
  }
}

// ===== Viewport 尺寸控制 =====

const fetchViewportInfo = async () => {
  if (!status.value.browser_connected) return
  try {
    const response = await axios.get('/api/output/viewport-info')
    if (response.data.success && response.data.data) {
      const vp = response.data.data.viewport
      if (vp) {
        viewportInfo.value = { width: vp.width, height: vp.height }
      }
      viewportAutoResize.value = response.data.data.auto_resize || false
    }
  } catch (e) {
    // 静默失败
  }
}

const applyViewport = async () => {
  try {
    const response = await axios.post('/api/output/resize-viewport', null, {
      params: { width: customViewport.value.width, height: customViewport.value.height }
    })
    if (response.data.success) {
      ElMessage.success(`视口已调整为 ${customViewport.value.width}×${customViewport.value.height}`)
      fetchViewportInfo()
    } else {
      ElMessage.error(response.data.error || '调整视口失败')
    }
  } catch (e) {
    ElMessage.error('调整视口失败')
    console.error(e)
  }
}

const handleAutoSyncChange = (val) => {
  if (val) {
    ElMessage.info('已开启自适应同步，调整本窗口大小时将自动同步 Playwright 视口')
  }
}

const handleWindowResize = () => {
  if (!autoResizeSync.value || !status.value.browser_connected) return
  // 防抖：300ms
  clearTimeout(resizeSyncTimer)
  resizeSyncTimer = setTimeout(async () => {
    const width = Math.max(320, Math.floor(window.innerWidth * 0.65))
    const height = Math.max(240, Math.floor(window.innerHeight * 0.75))
    try {
      await axios.post('/api/output/resize-viewport', null, {
        params: { width, height }
      })
      viewportInfo.value = { width, height }
    } catch (e) {
      console.error('同步 viewport 失败:', e)
    }
  }, 300)
}

// ===== 旧版全局控制（保留兼容） =====

const startOutput = async () => {
  try {
    await saveConfig()
    const response = await axios.post('/api/output/start')
    if (response.data.success) {
      ElMessage.success('输出已开始')
      fetchStatus()
    } else {
      const err = response.data.status?.last_error || '未知错误'
      ElMessage.error(`启动失败: ${err}`)
    }
  } catch (e) {
    ElMessage.error('启动失败')
    console.error(e)
  }
}

const stopOutput = async () => {
  try {
    await axios.post('/api/output/stop')
    ElMessage.success('输出已停止')
    fetchStatus()
  } catch (e) {
    ElMessage.error('停止失败')
    console.error(e)
  }
}

const formatTime = (timeStr) => {
  if (!timeStr) return '-'
  const date = new Date(timeStr)
  return date.toLocaleString('zh-CN')
}

onMounted(() => {
  fetchConfig()
  fetchStatus()
  fetchBrowserStatus()
  fetchFileStatus()
  fetchLogs()
  statusTimer = setInterval(fetchStatus, 2000)
  browserStatusTimer = setInterval(fetchBrowserStatus, 2000)
  fileStatusTimer = setInterval(fetchFileStatus, 2000)
  logsTimer = setInterval(fetchLogs, 3000)
  viewportInfoTimer = setInterval(fetchViewportInfo, 5000)

  // 订阅 window 自定义事件 ws-message 以接收 playwright_progress 等事件
  window.addEventListener('ws-message', handleWebSocketMessage)
  // 监听窗口 resize 事件，用于自适应同步 Playwright viewport
  window.addEventListener('resize', handleWindowResize)
})

onUnmounted(() => {
  if (statusTimer) clearInterval(statusTimer)
  if (browserStatusTimer) clearInterval(browserStatusTimer)
  if (fileStatusTimer) clearInterval(fileStatusTimer)
  if (logsTimer) clearInterval(logsTimer)
  if (viewportInfoTimer) clearInterval(viewportInfoTimer)
  if (resizeSyncTimer) clearTimeout(resizeSyncTimer)
  // 清理 ws-message 订阅
  window.removeEventListener('ws-message', handleWebSocketMessage)
  window.removeEventListener('resize', handleWindowResize)
})
</script>

<style scoped>
.output-config {
  flex-shrink: 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 700;
  font-size: 15px;
  color: var(--color-text-primary);
}

.header-tags {
  display: flex;
  gap: 6px;
}

.config-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 12px;
  padding-left: 8px;
  border-left: 3px solid var(--color-brand);
}

.url-row {
  display: flex;
  gap: 8px;
}

.url-row .el-input {
  flex: 1;
}

.status-message {
  font-size: 12px;
  color: var(--color-success);
  margin-top: 4px;
}

.progress-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--color-brand);
  margin-top: 6px;
  padding: 6px 10px;
  background: var(--color-brand-light);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--color-brand);
}

.progress-hint .rotating {
  animation: rotating 1.4s linear infinite;
}

@keyframes rotating {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.control-section {
  display: flex;
  gap: 12px;
  margin: 20px 0;
  justify-content: center;
}

.stats-section {
  margin: 16px 0;
}

.error-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px;
  background: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  color: var(--color-danger);
  font-size: 13px;
  margin: 16px 0;
}

.logs-section {
  margin-top: 20px;
}

.logs-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}

.logs-container {
  max-height: 200px;
  overflow-y: auto;
  background: var(--color-bg-secondary);
  border-radius: var(--radius-sm);
  padding: 12px;
}

.log-item {
  padding: 6px 10px;
  margin-bottom: 4px;
  background: var(--color-bg-primary);
  border-radius: var(--radius-sm);
  font-size: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  transition: background var(--transition-fast);
}

.log-item:hover {
  background: var(--color-bg-tertiary);
}

.log-item.error {
  background: var(--color-bg-tertiary);
  border-left: 2px solid var(--color-danger);
}

.log-time {
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}

.log-content {
  color: var(--color-text-primary);
  flex: 1;
}

.log-error {
  color: var(--color-danger);
}

.empty-logs {
  text-align: center;
  color: var(--color-text-tertiary);
  padding: 48px 20px;
  font-size: 12px;
}

.viewport-info-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.viewport-label {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.viewport-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.viewport-x {
  color: var(--color-text-tertiary);
  font-size: 14px;
}

.disconnect-banner {
  background: var(--color-bg-tertiary);
  color: var(--color-warning);
  border-left: 3px solid var(--color-warning);
}
</style>
