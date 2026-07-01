<template>
  <el-card class="performance-monitor">
    <template #header>
      <div class="card-header">
        <span>📊 性能监控</span>
        <el-tag size="small" :type="fps >= 50 ? 'success' : fps >= 30 ? 'warning' : 'danger'">
          {{ fps }} FPS
        </el-tag>
      </div>
    </template>
    
    <div class="monitor-content">
      <div class="stat-item">
        <span class="stat-label">前端帧率</span>
        <span class="stat-value" :class="{ 'good': fps >= 50, 'warning': fps >= 30 && fps < 50, 'bad': fps < 30 }">
          {{ fps }} FPS
        </span>
      </div>
      
      <div class="stat-item">
        <span class="stat-label">内存使用</span>
        <span class="stat-value">{{ memoryUsed }} MB</span>
      </div>
      
      <div class="stat-item">
        <span class="stat-label">后端消息数</span>
        <span class="stat-value">{{ backendStats.total_messages || 0 }}</span>
      </div>
      
      <div class="stat-item">
        <span class="stat-label">消息/秒</span>
        <span class="stat-value">{{ backendStats.messages_per_second_recent || 0 }}</span>
      </div>
      
      <div class="stat-item">
        <span class="stat-label">后端内存</span>
        <span class="stat-value">{{ backendStats.memory_rss_mb || 0 }} MB</span>
      </div>
      
      <div class="stat-item">
        <span class="stat-label">缓冲区大小</span>
        <span class="stat-value">{{ bufferStats.current_size || 0 }} / {{ bufferStats.max_size || 0 }}</span>
      </div>
      
      <div class="stat-item">
        <span class="stat-label">已清理</span>
        <span class="stat-value">{{ bufferStats.cleanup_count || 0 }}</span>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const fps = ref(60)
const memoryUsed = ref(0)
const backendStats = ref({})
const bufferStats = ref({})

let lastTime = performance.now()
let frameCount = 0
let fpsInterval = null
let statsInterval = null

const measureFPS = () => {
  const now = performance.now()
  frameCount++
  
  if (now - lastTime >= 1000) {
    fps.value = frameCount
    frameCount = 0
    lastTime = now
  }
  
  requestAnimationFrame(measureFPS)
}

const getMemoryUsed = () => {
  if (performance.memory) {
    memoryUsed.value = Math.round(performance.memory.usedJSHeapSize / 1024 / 1024)
  }
}

const fetchBackendStats = async () => {
  try {
    const response = await fetch('/api/performance/stats')
    const data = await response.json()
    backendStats.value = data.backend || {}
    bufferStats.value = data.buffer || {}
  } catch (e) {
    console.error('[PerformanceMonitor] 获取后端统计失败:', e)
  }
}

onMounted(() => {
  requestAnimationFrame(measureFPS)
  
  fpsInterval = setInterval(() => {
    getMemoryUsed()
  }, 1000)
  
  statsInterval = setInterval(() => {
    fetchBackendStats()
  }, 3000)
  
  fetchBackendStats()
})

onUnmounted(() => {
  if (fpsInterval) {
    clearInterval(fpsInterval)
  }
  if (statsInterval) {
    clearInterval(statsInterval)
  }
})
</script>

<style scoped>
.performance-monitor {
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
}

.monitor-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stat-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

.stat-label {
  color: #606266;
  font-size: 14px;
}

.stat-value {
  font-weight: bold;
  font-size: 14px;
  color: #303133;
}

.stat-value.good {
  color: #67c23a;
}

.stat-value.warning {
  color: #e6a23c;
}

.stat-value.bad {
  color: #f56c6c;
}
</style>
