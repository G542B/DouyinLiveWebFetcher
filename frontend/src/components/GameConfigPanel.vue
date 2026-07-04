<template>
  <el-card class="game-config-panel" shadow="never">
    <template #header>
      <div class="card-header">
        <span>游戏配置</span>
      </div>
    </template>

    <el-form :model="config" label-width="100px" size="small" label-position="left">
      <el-form-item label="总轮次数">
        <el-input-number v-model="config.total_rounds" :min="1" :max="50" />
      </el-form-item>
      <el-form-item label="每轮时间(秒)">
        <el-input-number v-model="config.round_time_limit" :min="30" :max="14400" :step="60" />
        <span class="form-hint">
          {{ formatTimeHint(config.round_time_limit) }}
        </span>
      </el-form-item>
      <el-form-item label="关联度算法">
        <el-select v-model="config.similarity_algorithm">
          <el-option label="Embedding 语义（推荐高精度）" value="embedding" />
          <el-option label="语义算法" value="semantic" />
          <el-option label="混合算法" value="hybrid" />
          <el-option label="编辑距离" value="edit_distance" />
          <el-option label="拼音匹配" value="pinyin" />
        </el-select>
        <span class="form-hint">
          Embedding 模型自动下载本地模型（约 95MB）
        </span>
      </el-form-item>

      <el-card
        v-if="config.similarity_algorithm === 'embedding'"
        shadow="never"
        class="embedding-status-card"
      >
        <template #header>
          <div class="card-header">
            <span>Embedding 模型状态</span>
            <el-button
              size="small"
              text
              :icon="Refresh"
              @click="loadEmbeddingStatus"
              :loading="loadingStatus"
            />
          </div>
        </template>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="状态">
            <el-tag :type="embeddingStatusType" size="small">
              {{ embeddingStatusText }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="模型">
            {{ embeddingStatus.model_name || '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="已编码词库">
            {{ embeddingStatus.word_bank_vector_count ?? 0 }} 个
          </el-descriptions-item>
          <el-descriptions-item label="平均编码耗时">
            {{ embeddingStatus.encode_avg_ms ?? 0 }} ms
          </el-descriptions-item>
          <el-descriptions-item label="缓存命中率">
            {{ embeddingStatus.cache_hit_rate ?? 0 }}%
          </el-descriptions-item>
          <el-descriptions-item label="单次匹配耗时">
            <span :class="perfWarningClass">
              {{ similarityPerf.avg_ms ?? 0 }} ms (max: {{ similarityPerf.max_ms ?? 0 }})
            </span>
            <span
              v-if="(similarityPerf.avg_ms ?? 0) > 100"
              class="perf-warn-inline"
            >
              超过 100ms 目标
            </span>
          </el-descriptions-item>
          <el-descriptions-item
            v-if="embeddingStatus.error_message"
            label="错误信息"
          >
            <span class="perf-error">{{ embeddingStatus.error_message }}</span>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <el-form-item label="排行榜显示数">
        <el-input-number v-model="config.ranking_display_count" :min="5" :max="100" />
      </el-form-item>
      <el-form-item label="自动下一轮">
        <el-switch v-model="config.auto_next_round" />
      </el-form-item>
      <el-form-item label="观众问答">
        <el-switch v-model="config.qa_enabled" />
      </el-form-item>
      <el-form-item label="弹窗时长(秒)">
        <el-input-number v-model="config.popup_duration" :min="3" :max="30" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="saveConfig">保存配置</el-button>
        <el-button
          v-if="config.similarity_algorithm === 'embedding'"
          @click="loadEmbeddingStatus"
        >
          刷新状态
        </el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

const config = ref({
  total_rounds: 5,
  round_time_limit: 7200,
  similarity_algorithm: 'hybrid',
  ranking_display_count: 20,
  auto_next_round: true,
  popup_duration: 10,
  hint_penalty: 0.05,
  qa_enabled: true,
  embedding_model_name: 'BAAI/bge-small-zh-v1.5',
  embedding_enabled: true
})

const embeddingStatus = ref({})
const similarityPerf = ref({ avg_ms: 0, max_ms: 0 })
const loadingStatus = ref(false)
let statusTimer = null

const embeddingStatusText = computed(() => {
  const map = {
    ready: '已就绪',
    downloading: '下载中',
    loading: '加载中',
    failed: '加载失败',
    unloaded: '未加载',
    unavailable: '不可用'
  }
  return map[embeddingStatus.value.status] || embeddingStatus.value.status || '未知'
})

const embeddingStatusType = computed(() => {
  const map = {
    ready: 'success',
    downloading: 'warning',
    loading: 'warning',
    failed: 'danger',
    unloaded: 'info',
    unavailable: 'info'
  }
  return map[embeddingStatus.value.status] || 'info'
})

const perfWarningClass = computed(() => {
  const avg = similarityPerf.value.avg_ms ?? 0
  if (avg > 100) return 'perf-warn'
  if (avg > 50) return 'perf-ok'
  return 'perf-good'
})

const formatTimeHint = (seconds) => {
  if (!seconds) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `约 ${h} 小时 ${m > 0 ? m + ' 分钟' : ''}`
  return `${m} 分钟`
}

const loadConfig = async () => {
  try {
    const res = await axios.get('/api/game/config')
    config.value = { ...config.value, ...res.data }
  } catch (e) {
    console.error('加载配置失败:', e)
  }
}

const loadEmbeddingStatus = async () => {
  if (config.value.similarity_algorithm !== 'embedding') return
  loadingStatus.value = true
  try {
    const res = await axios.get('/api/game/embedding/status')
    embeddingStatus.value = res.data.embedding || {}
    similarityPerf.value = res.data.similarity_perf || { avg_ms: 0, max_ms: 0 }
  } catch (e) {
    console.error('加载 Embedding 状态失败:', e)
  } finally {
    loadingStatus.value = false
  }
}

const saveConfig = async () => {
  try {
    await axios.put('/api/game/config', config.value)
    ElMessage.success('配置已保存')
    // 通知游戏窗体配置已变更
    if (window.electronAPI) {
      window.electronAPI.notifyConfigChanged()
    }
    // 切到 embedding 后立即拉一次状态
    if (config.value.similarity_algorithm === 'embedding') {
      loadEmbeddingStatus()
    }
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

onMounted(() => {
  loadConfig()
  // embedding 模式下定时轮询状态（启动阶段模型可能仍在下载/加载）
  statusTimer = setInterval(() => {
    if (config.value.similarity_algorithm === 'embedding') {
      loadEmbeddingStatus()
    }
  }, 5000)
  loadEmbeddingStatus()
})

onUnmounted(() => {
  if (statusTimer) {
    clearInterval(statusTimer)
    statusTimer = null
  }
})
</script>

<style scoped>
.game-config-panel {
  height: 100%;
}

.card-header {
  font-weight: bold;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  color: var(--color-text-primary);
}

.embedding-status-card {
  margin: 8px 0 16px 100px;
  width: calc(100% - 100px);
}

.form-hint {
  margin-left: 8px;
  color: var(--color-text-secondary);
  font-size: 12px;
}

.perf-good {
  color: var(--color-success);
  font-weight: bold;
}

.perf-ok {
  color: var(--color-brand);
  font-weight: bold;
}

.perf-warn {
  color: var(--color-warning);
  font-weight: bold;
}

.perf-warn-inline {
  color: var(--color-warning);
  margin-left: 8px;
  font-size: 12px;
}

.perf-error {
  color: var(--color-danger);
}

@media (max-width: 768px) {
  .embedding-status-card {
    margin: 8px 0;
    width: 100%;
  }
}
</style>
