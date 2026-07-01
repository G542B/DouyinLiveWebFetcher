<template>
  <el-card class="danmaku-viewer">
    <template #header>
      <div class="card-header">
        <span>💬 弹幕消息</span>
        <div class="header-right">
          <span class="message-count">{{ messages.length }} 条</span>
          <el-button size="small" @click="clearMessages">清空</el-button>
        </div>
      </div>
    </template>
    
    <div 
      class="messages-container" 
      ref="messagesContainer"
      @scroll="handleScroll"
    >
      <div 
        class="messages-phantom"
        :style="{ height: totalHeight + 'px' }"
      >
        <div 
          class="messages-content"
          :style="{ transform: `translateY(${offset}px)` }"
        >
          <div
            v-for="msg in visibleMessages"
            :key="msg._uid || msg.timestamp"
            class="message-item"
            :class="getMessageClass(msg)"
            :style="{ height: itemHeight + 'px' }"
          >
            <div class="message-header">
              <span class="message-type">{{ getMessageTypeName(msg.message_type) }}</span>
              <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
            </div>
            <div class="message-content">
              <div v-if="msg.data.user_name" class="user-name">
                {{ msg.data.user_name }}
              </div>
              <div class="content-text">
                {{ getMessageText(msg) }}
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div v-if="messages.length === 0" class="empty-state">
        等待弹幕消息...
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  messages: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['clear'])

const messagesContainer = ref(null)
const scrollTop = ref(0)
const itemHeight = ref(100)
const isUserScrolling = ref(false)
const lastScrollTop = ref(0)

const containerHeight = ref(600)

const startIndex = computed(() => {
  return Math.floor(scrollTop.value / itemHeight.value)
})

const endIndex = computed(() => {
  const visibleCount = Math.ceil(containerHeight.value / itemHeight.value) + 2
  return Math.min(startIndex.value + visibleCount, props.messages.length)
})

const visibleMessages = computed(() => {
  return props.messages.slice(startIndex.value, endIndex.value)
})

const offset = computed(() => {
  return startIndex.value * itemHeight.value
})

const totalHeight = computed(() => {
  return props.messages.length * itemHeight.value
})

const messageTypeNames = {
  'WebcastChatMessage': '聊天',
  'WebcastMemberMessage': '进场',
  'WebcastGiftMessage': '礼物',
  'WebcastControlMessage': '管理',
  'WebcastRoomUserSeqMessage': '统计',
  'WebcastLikeMessage': '点赞',
  'WebcastSocialMessage': '关注',
  'WebcastFansclubMessage': '粉丝团',
  'WebcastEmojiChatMessage': '表情',
  'WebcastRoomStatsMessage': '房间统计',
  'WebcastRoomMessage': '房间信息',
  'WebcastRoomRankMessage': '排行榜',
  'WebcastRoomStreamAdaptationMessage': '流配置'
}

const getMessageTypeName = (type) => {
  return messageTypeNames[type] || type
}

const getMessageClass = (msg) => {
  return {
    'type-chat': msg.message_type === 'WebcastChatMessage' || msg.message_type === 'WebcastEmojiChatMessage',
    'type-gift': msg.message_type === 'WebcastGiftMessage',
    'type-like': msg.message_type === 'WebcastLikeMessage',
    'type-member': msg.message_type === 'WebcastMemberMessage',
    'type-social': msg.message_type === 'WebcastSocialMessage',
    'type-stats': msg.message_type === 'WebcastRoomUserSeqMessage' || msg.message_type === 'WebcastRoomStatsMessage',
    'type-room': msg.message_type === 'WebcastRoomMessage' || msg.message_type === 'WebcastRoomRankMessage' || msg.message_type === 'WebcastRoomStreamAdaptationMessage',
    'type-fansclub': msg.message_type === 'WebcastFansclubMessage'
  }
}

const getMessageText = (msg) => {
  const data = msg.data
  if (!data) return ''

  switch (msg.message_type) {
    case 'WebcastChatMessage':
      return data.content || ''
    case 'WebcastEmojiChatMessage':
      return data.default_content || data.content || ''
    case 'WebcastGiftMessage':
      return data.gift_name ? `送出 ${data.gift_name} x${data.gift_count || 1}` : ''
    case 'WebcastLikeMessage':
      return data.count ? `点赞 x${data.count}` : '点赞'
    case 'WebcastMemberMessage':
      return '进入直播间'
    case 'WebcastSocialMessage':
      return data.action === 'follow' ? '关注了主播' : ''
    case 'WebcastRoomUserSeqMessage':
      return data.current_viewers !== undefined ? `当前 ${data.current_viewers} 人观看, 累计 ${data.total_viewers || 0}` : ''
    case 'WebcastRoomStatsMessage':
      return data.display_long || ''
    case 'WebcastRoomRankMessage':
      return '排行榜更新'
    case 'WebcastRoomMessage':
      return data.room_id ? `直播间 ID: ${data.room_id}` : ''
    case 'WebcastRoomStreamAdaptationMessage':
      return data.adaptation_type !== undefined ? `流配置: ${data.adaptation_type}` : ''
    case 'WebcastFansclubMessage':
      return data.content || ''
    case 'WebcastControlMessage':
      return data.status !== undefined ? `直播间状态: ${data.status}` : ''
    default:
      return data.content || JSON.stringify(data)
  }
}

const formatTime = (timestamp) => {
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const clearMessages = () => {
  emit('clear')
}

const handleScroll = () => {
  if (messagesContainer.value) {
    const currentScrollTop = messagesContainer.value.scrollTop
    // 用户主动向下滚动（远离顶部），标记为手动滚动
    if (currentScrollTop > lastScrollTop.value + 10 && currentScrollTop > itemHeight.value) {
      isUserScrolling.value = true
    }
    // 用户滚动回顶部附近，恢复自动滚动
    if (currentScrollTop < itemHeight.value) {
      isUserScrolling.value = false
    }
    lastScrollTop.value = currentScrollTop
    scrollTop.value = currentScrollTop
  }
}

const updateContainerHeight = () => {
  if (messagesContainer.value) {
    containerHeight.value = messagesContainer.value.clientHeight
  }
}

let resizeObserver = null

onMounted(() => {
  updateContainerHeight()
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(updateContainerHeight)
    resizeObserver.observe(messagesContainer.value)
  }
})

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
  }
})

watch(() => props.messages.length, () => {
  nextTick(() => {
    if (messagesContainer.value && !isUserScrolling.value) {
      messagesContainer.value.scrollTop = 0
      scrollTop.value = 0
    }
  })
})
</script>

<style scoped>
.danmaku-viewer {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.danmaku-viewer :deep(.el-card__body) {
  flex: 1;
  padding: 0;
  overflow: hidden;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: bold;
  font-size: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.message-count {
  font-size: 14px;
  color: #909399;
}

.messages-container {
  height: 100%;
  overflow-y: auto;
  position: relative;
  padding: 12px;
}

.messages-phantom {
  position: absolute;
  left: 12px;
  right: 12px;
  top: 12px;
}

.messages-content {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
}

.message-item {
  box-sizing: border-box;
  padding: 12px;
  background: white;
  border-radius: 8px;
  margin-bottom: 8px;
  border-left: 4px solid #dcdfe6;
  overflow: hidden;
}

.message-item.type-chat {
  border-left-color: #409eff;
}

.message-item.type-gift {
  border-left-color: #e6a23c;
  background: linear-gradient(90deg, #fdf6ec 0%, white 100%);
}

.message-item.type-like {
  border-left-color: #f56c6c;
}

.message-item.type-member {
  border-left-color: #67c23a;
}

.message-item.type-social {
  border-left-color: #909399;
}

.message-item.type-stats {
  border-left-color: #e6a23c;
  background: linear-gradient(90deg, #faf3e0 0%, white 100%);
}

.message-item.type-room {
  border-left-color: #b37feb;
}

.message-item.type-fansclub {
  border-left-color: #ff85c0;
}

.message-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.message-type {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
  background: #f5f7fa;
  color: #909399;
}

.message-time {
  font-size: 12px;
  color: #c0c4cc;
}

.message-content {
  line-height: 1.5;
}

.user-name {
  font-weight: bold;
  color: #409eff;
  margin-bottom: 4px;
}

.content-text {
  color: #303133;
  word-break: break-all;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}

.empty-state {
  text-align: center;
  color: #909399;
  padding: 40px;
}
</style>
