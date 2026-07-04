<template>
  <el-card class="room-manager">
    <template #header>
      <div class="card-header">
        <span>📺 直播间管理</span>
      </div>
    </template>
    
    <el-form :model="newRoom" @submit.prevent="addRoom" class="add-room-form">
      <el-input
        v-model="newRoom.live_id"
        placeholder="输入直播间 ID"
        clearable
        style="margin-bottom: 8px"
      />
      <el-input
        v-model="newRoom.name"
        placeholder="直播间名称（可选）"
        clearable
        style="margin-bottom: 8px"
      />
      <el-button type="primary" @click="addRoom" style="width: 100%">
        添加直播间
      </el-button>
    </el-form>
    
    <div class="room-list">
      <div
        v-for="room in rooms"
        :key="room.id"
        class="room-item"
      >
        <div class="room-info">
          <div class="room-name">{{ room.name }}</div>
          <div class="room-id">ID: {{ room.live_id }}</div>
        </div>
        <div class="room-actions">
          <el-button
            v-if="room.status === 'stopped'"
            type="success"
            size="small"
            @click="startRoom(room.id)"
          >
            启动
          </el-button>
          <el-button
            v-else
            type="warning"
            size="small"
            @click="stopRoom(room.id)"
          >
            停止
          </el-button>
          <el-button
            type="danger"
            size="small"
            @click="deleteRoom(room.id)"
          >
            删除
          </el-button>
        </div>
        <el-tag
          :type="room.status === 'running' ? 'success' : 'info'"
          size="small"
          class="status-tag"
        >
          {{ room.status === 'running' ? '运行中' : '已停止' }}
        </el-tag>
      </div>
      
      <div v-if="rooms.length === 0" class="empty-state">
        暂无直播间
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const emit = defineEmits(['rooms-updated'])

const newRoom = ref({
  live_id: '',
  name: ''
})

const rooms = ref([])

const fetchRooms = async () => {
  try {
    const response = await axios.get('/api/rooms')
    rooms.value = response.data
  } catch (e) {
    console.error('获取直播间列表失败:', e)
  }
}

const addRoom = async () => {
  if (!newRoom.value.live_id.trim()) {
    ElMessage.warning('请输入直播间 ID')
    return
  }
  
  try {
    await axios.post('/api/rooms', newRoom.value)
    newRoom.value = { live_id: '', name: '' }
    ElMessage.success('添加成功')
    fetchRooms()
    emit('rooms-updated')
  } catch (e) {
    ElMessage.error('添加失败')
    console.error(e)
  }
}

const deleteRoom = async (roomId) => {
  try {
    await axios.delete(`/api/rooms/${roomId}`)
    ElMessage.success('删除成功')
    fetchRooms()
    emit('rooms-updated')
  } catch (e) {
    ElMessage.error('删除失败')
    console.error(e)
  }
}

const startRoom = async (roomId) => {
  try {
    await axios.post(`/api/rooms/${roomId}/start`)
    ElMessage.success('已启动')
    fetchRooms()
    emit('rooms-updated')
  } catch (e) {
    ElMessage.error('启动失败')
    console.error(e)
  }
}

const stopRoom = async (roomId) => {
  try {
    await axios.post(`/api/rooms/${roomId}/stop`)
    ElMessage.success('已停止')
    fetchRooms()
    emit('rooms-updated')
  } catch (e) {
    ElMessage.error('停止失败')
    console.error(e)
  }
}

onMounted(() => {
  fetchRooms()
})
</script>

<style scoped>
.room-manager {
  flex-shrink: 0;
}

.card-header {
  font-weight: 700;
  font-size: 15px;
  color: var(--color-text-primary);
}

.add-room-form {
  margin-bottom: 16px;
}

.room-list {
  max-height: 400px;
  overflow-y: auto;
}

.room-item {
  padding: 12px;
  background: var(--color-bg-primary);
  border-radius: var(--radius-md);
  margin-bottom: 8px;
  border: 1px solid var(--color-border-light);
  position: relative;
  transition: border-color var(--transition-fast);
}

.room-item:hover {
  border-color: var(--color-brand-light);
}

.room-info {
  margin-bottom: 8px;
}

.room-name {
  font-weight: 700;
  font-size: 14px;
  margin-bottom: 4px;
  color: var(--color-text-primary);
}

.room-id {
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.room-actions {
  display: flex;
  gap: 8px;
}

.status-tag {
  position: absolute;
  right: 12px;
  top: 12px;
}

.empty-state {
  text-align: center;
  color: var(--color-text-tertiary);
  padding: 30px 20px;
  font-size: 13px;
}
</style>
