<template>
  <el-card class="word-bank-manager" shadow="never">
    <template #header>
      <div class="card-header">
        <span>词库管理</span>
        <div class="header-actions">
          <el-button size="small" type="primary" @click="showAddDialog">添加</el-button>
          <el-button size="small" @click="showBatchDialog">批量导入</el-button>
          <el-button size="small" @click="exportWords">导出</el-button>
        </div>
      </div>
    </template>

    <div class="search-bar">
      <el-input v-model="searchKeyword" placeholder="搜索答案或分类..." size="small" clearable prefix-icon="Search" />
    </div>

    <el-table :data="filteredWords" stripe size="small" max-height="360" style="width: 100%">
      <el-table-column prop="answer" label="答案" min-width="80" />
      <el-table-column prop="hints" label="提示" min-width="120">
        <template #default="{ row }">
          <el-tag v-for="(hint, i) in row.hints" :key="i" size="small" type="info" style="margin-right: 4px;">
            {{ hint }}
          </el-tag>
          <span v-if="!row.hints || row.hints.length === 0" style="color: #c0c4cc;">无</span>
        </template>
      </el-table-column>
      <el-table-column prop="category" label="分类" width="80">
        <template #default="{ row }">
          <el-tag v-if="row.category" size="small">{{ row.category }}</el-tag>
          <span v-else style="color: #c0c4cc;">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="difficulty" label="难度" width="70">
        <template #default="{ row }">
          <el-tag :type="difficultyType(row.difficulty)" size="small">{{ difficultyLabel(row.difficulty) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_active" label="状态" width="60">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '启用' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="120" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="editWord(row)">编辑</el-button>
          <el-button link type="danger" size="small" @click="deleteWord(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 添加/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑词库' : '添加词库'" width="480px" destroy-on-close append-to-body>
      <el-form :model="formData" label-width="70px" size="default">
        <el-form-item label="答案" required>
          <el-input v-model="formData.answer" placeholder="请输入答案词" />
        </el-form-item>
        <el-form-item label="提示">
          <div class="hints-editor">
            <div v-for="(hint, i) in formData.hints" :key="i" class="hint-item">
              <el-input v-model="formData.hints[i]" :placeholder="`提示${i + 1}`" />
              <el-button link type="danger" @click="formData.hints.splice(i, 1)">删除</el-button>
            </div>
            <el-button size="small" @click="formData.hints.push('')">+ 添加提示</el-button>
          </div>
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="formData.category" placeholder="可选分类标签" />
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="formData.difficulty">
            <el-option label="简单" value="easy" />
            <el-option label="中等" value="medium" />
            <el-option label="困难" value="hard" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveWord">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量导入对话框 -->
    <el-dialog v-model="batchDialogVisible" title="批量导入词库" width="560px" destroy-on-close append-to-body>
      <p style="color: #909399; font-size: 13px; margin-bottom: 12px;">
        请输入JSON格式数据，示例：[{"answer":"北京","hints":["中国首都","北方城市"],"category":"城市","difficulty":"easy"}]
      </p>
      <el-input v-model="batchData" type="textarea" :rows="10" placeholder="粘贴JSON数据..." />
      <template #footer>
        <el-button @click="batchDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="importBatch">导入</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'

// 词库变更事件：用于父组件（GamePanel）同步状态
const emit = defineEmits(['words-changed'])

// 通知游戏窗体词库已变更（独立窗体模式下通过 IPC）
const notifyWordsChanged = () => {
  if (window.electronAPI) {
    window.electronAPI.notifyWordsChanged()
  }
}

const words = ref([])
const searchKeyword = ref('')
const dialogVisible = ref(false)
const batchDialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const batchData = ref('')

const formData = ref({
  answer: '',
  hints: [],
  category: '',
  difficulty: 'medium'
})

const filteredWords = computed(() => {
  if (!searchKeyword.value) return words.value
  const kw = searchKeyword.value.toLowerCase()
  return words.value.filter(w =>
    w.answer.toLowerCase().includes(kw) ||
    w.category.toLowerCase().includes(kw)
  )
})

const difficultyType = (d) => {
  if (d === 'easy') return 'success'
  if (d === 'hard') return 'danger'
  return 'warning'
}

const difficultyLabel = (d) => {
  if (d === 'easy') return '简单'
  if (d === 'hard') return '困难'
  return '中等'
}

const loadWords = async () => {
  try {
    const res = await axios.get('/api/game/words')
    words.value = res.data
  } catch (e) {
    console.error('加载词库失败:', e)
  }
}

const showAddDialog = () => {
  isEditing.value = false
  editingId.value = null
  formData.value = { answer: '', hints: [], category: '', difficulty: 'medium' }
  dialogVisible.value = true
}

const editWord = (row) => {
  isEditing.value = true
  editingId.value = row.id
  formData.value = {
    answer: row.answer,
    hints: [...(row.hints || [])],
    category: row.category || '',
    difficulty: row.difficulty || 'medium'
  }
  dialogVisible.value = true
}

const saveWord = async () => {
  if (!formData.value.answer.trim()) {
    ElMessage.warning('请输入答案词')
    return
  }
  try {
    if (isEditing.value) {
      await axios.put(`/api/game/words/${editingId.value}`, formData.value)
      ElMessage.success('更新成功')
    } else {
      await axios.post('/api/game/words', formData.value)
      ElMessage.success('添加成功')
    }
    dialogVisible.value = false
    await loadWords()
    emit('words-changed', { type: isEditing.value ? 'update' : 'add' })
    notifyWordsChanged()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

const deleteWord = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除答案"${row.answer}"？`, '确认删除', { type: 'warning' })
    await axios.delete(`/api/game/words/${row.id}`)
    ElMessage.success('删除成功')
    await loadWords()
    emit('words-changed', { type: 'delete' })
    notifyWordsChanged()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败')
    }
  }
}

const showBatchDialog = () => {
  batchData.value = ''
  batchDialogVisible.value = true
}

const importBatch = async () => {
  try {
    const data = JSON.parse(batchData.value)
    if (!Array.isArray(data)) {
      ElMessage.error('数据格式错误，需要JSON数组')
      return
    }
    const res = await axios.post('/api/game/words/batch', { words: data })
    ElMessage.success(`成功导入 ${res.data.imported_count} 个词`)
    batchDialogVisible.value = false
    await loadWords()
    emit('words-changed', { type: 'batch' })
    notifyWordsChanged()
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || 'JSON格式错误'))
  }
}

const exportWords = async () => {
  try {
    const res = await axios.get('/api/game/words/export')
    const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'word_bank.json'
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e) {
    ElMessage.error('导出失败')
  }
}

onMounted(() => {
  loadWords()
})
</script>

<style scoped>
.word-bank-manager {
  height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 4px;
}

.search-bar {
  margin-bottom: 12px;
}

.hints-editor {
  width: 100%;
}

.hint-item {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.hint-item .el-input {
  flex: 1;
}
</style>
