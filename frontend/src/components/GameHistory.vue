<template>
  <el-card class="game-history" shadow="never">
    <template #header>
      <div class="card-header">
        <span>游戏历史</span>
        <el-button size="small" type="danger" @click="clearHistory">清空</el-button>
      </div>
    </template>

    <el-table :data="historyRecords" stripe size="small" max-height="400" style="width: 100%">
      <el-table-column type="expand">
        <template #default="{ row }">
          <div class="expand-content">
            <p v-if="row.guesses && row.guesses.length > 0">
              <strong>猜词记录 ({{ row.guesses.length }}条)：</strong>
            </p>
            <el-table v-if="row.guesses && row.guesses.length > 0" :data="row.guesses" size="small" border>
              <el-table-column prop="user_name" label="用户名" width="120" />
              <el-table-column prop="guess_content" label="猜词" width="120" />
              <el-table-column prop="similarity_score" label="关联度" width="100">
                <template #default="{ row: guess }">
                  {{ guess.similarity_score.toFixed(2) }}%
                </template>
              </el-table-column>
              <el-table-column prop="timestamp" label="时间" width="100">
                <template #default="{ row: guess }">
                  {{ formatTime(guess.timestamp) }}
                </template>
              </el-table-column>
            </el-table>
            <p v-else class="empty-record">暂无猜词记录</p>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="round_number" label="轮次" width="60" />
      <el-table-column prop="answer" label="答案" min-width="80" />
      <el-table-column prop="winner" label="赢家" min-width="80">
        <template #default="{ row }">
          <span v-if="row.winner" class="winner-text">{{ row.winner }}</span>
          <span v-else class="no-winner-text">无人猜中</span>
        </template>
      </el-table-column>
      <el-table-column prop="total_guesses" label="猜词数" width="70" />
      <el-table-column prop="start_time" label="开始时间" width="100">
        <template #default="{ row }">
          {{ formatTime(row.start_time) }}
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-bar">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        small
        @current-change="loadHistory"
      />
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'

const historyRecords = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

const loadHistory = async () => {
  try {
    const res = await axios.get('/api/game/history', {
      params: { page: currentPage.value, page_size: pageSize.value }
    })
    historyRecords.value = res.data.records || []
    total.value = res.data.total || 0
  } catch (e) {
    console.error('加载历史失败:', e)
  }
}

const clearHistory = async () => {
  try {
    await ElMessageBox.confirm('确定清空所有游戏历史记录？', '确认', { type: 'warning' })
    await axios.post('/api/game/history/clear')
    ElMessage.success('已清空')
    loadHistory()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('清空失败')
    }
  }
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

onMounted(() => {
  loadHistory()
})
</script>

<style scoped>
.game-history {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
  font-size: 14px;
  color: var(--color-text-primary);
}

.expand-content {
  padding: 12px 20px;
}

.empty-record {
  color: var(--color-text-tertiary);
}

.winner-text {
  color: var(--color-success);
  font-weight: bold;
}

.no-winner-text {
  color: var(--color-text-tertiary);
}

.pagination-bar {
  margin-top: 12px;
  display: flex;
  justify-content: center;
}

:deep(.el-table) {
  --el-table-row-hover-bg-color: var(--color-bg-tertiary);
}

:deep(.el-table__row:hover) {
  transition: background var(--transition-fast);
}
</style>
