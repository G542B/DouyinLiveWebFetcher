<template>
  <div class="game-panel">
    <!-- 顶部标题栏：金橙渐变 -->
    <div class="game-header">
      <div class="header-left">
        <span class="game-title">猜词挑战</span>
        <span v-if="isRunning" class="auto-peek-hint">自动偷瞄中</span>
      </div>
      <div class="header-right">
        <el-tag
          :class="['countdown-tag', { 'countdown-warning': timeRemaining <= 10 && timeRemaining > 0 }]"
          effect="dark"
          size="small"
        >
          {{ isRunning ? formatCountdown(timeRemaining) : statusLabel }}
        </el-tag>
      </div>
    </div>

    <!-- 信息提示栏 -->
    <div class="info-bar">
      <div class="info-bar-left">
        <span class="participate-hint">参与方法：观众直接评论区发文字即可参与</span>
      </div>
    </div>

    <!-- 分类与操作栏 -->
    <div class="category-bar">
      <div class="category-info">
        <span class="category-label">本局类别：</span>
        <el-tag v-if="currentCategory" type="warning" effect="dark" size="default" class="category-tag">
          {{ currentCategory }}
        </el-tag>
        <span class="word-length-hint" v-if="gameState.current_answer">
          （字数：{{ gameState.current_answer.length }}个字）
        </span>
      </div>
      <div class="category-actions">
        <el-button size="small" type="danger" :disabled="!isRunning" @click="requestHint">
          偷瞄答案
        </el-button>
        <el-button size="small" :disabled="!isRunning" @click="skipRound">
          放弃本轮
        </el-button>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="game-content">
      <div class="content-left">
        <!-- 重复猜词通知区：紧贴 GuessTable 上方，固定位置 -->
        <transition-group name="notice-slide" tag="div" class="notice-stack">
          <div
            v-for="n in noticeList"
            :key="n.id"
            class="duplicate-notice"
            role="status"
          >
            <span class="notice-icon" aria-hidden="true">⚠</span>
            <span class="notice-text">
              <strong class="notice-user">{{ n.user_name }}</strong>
              <span class="notice-mid">猜过了，</span>
              <strong class="notice-prev">{{ n.previous_user }}</strong>
              <span class="notice-mid">已经猜过</span>
              <span class="notice-content">「{{ n.guess_content }}」</span>
            </span>
          </div>
        </transition-group>

        <GuessTable
          :guesses="currentGuesses"
          :category="currentCategory"
          :difficulty="currentDifficulty"
          :hints="currentHints"
          :answer-masked="answerMasked"
        />
      </div>
      <div class="content-right">
        <RankingBoard :rankings="currentRankings" />
      </div>
    </div>

    <!-- 底部区域：控制栏 + 观众问答 -->
    <div class="game-footer">
      <div class="footer-controls">
        <el-button type="success" size="small" :disabled="isRunning" @click="startGame">
          {{ gameState.status === 'paused' ? '恢复' : '开始游戏' }}
        </el-button>
        <el-button type="warning" size="small" :disabled="!isRunning" @click="pauseGame">
          暂停
        </el-button>
        <el-button type="danger" size="small" :disabled="gameState.status === 'idle'" @click="stopGame">
          结束
        </el-button>
        <el-button size="small" :disabled="!isRunning && gameState.status !== 'paused'" @click="nextRound">
          下一轮
        </el-button>
        <span class="round-info">
          轮次: {{ gameState.current_round || 0 }}/{{ gameState.config?.total_rounds || config.total_rounds }}
        </span>
        <el-button size="small" text @click="openSubWindow('history')">历史</el-button>
        <el-button size="small" text @click="openSubWindow('wordbank')">词库</el-button>
        <el-button size="small" text @click="openSubWindow('config')">设置</el-button>
      </div>
      <div class="qa-section">
        <span class="qa-label">观众问答</span>
        <div v-if="qaList.length > 0" class="qa-list">
          <div v-for="(qa, index) in qaList" :key="index" class="qa-item">
            <span class="qa-user">{{ qa.user_name }}</span>
            <span class="qa-question">{{ qa.question }}</span>
            <el-tag
              :type="qa.answer_text === '是' ? 'success' : qa.answer_text === '不是' ? 'danger' : 'info'"
              size="small"
              effect="dark"
              class="qa-answer-tag"
            >{{ qa.answer_text }}</el-tag>
          </div>
        </div>
        <span v-else class="qa-hint">可以问：是动物吗？能吃吗？是用品吗？</span>
      </div>
    </div>

    <!-- 猜中弹窗 -->
    <CongratsPopup
      :visible="congratsVisible"
      :winner-name="congratsData.winnerName"
      :answer="congratsData.answer"
      :guess-content="congratsData.guessContent"
      :duration="config.popup_duration"
      @close="congratsVisible = false"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import GuessTable from './GuessTable.vue'
import RankingBoard from './RankingBoard.vue'
import CongratsPopup from './CongratsPopup.vue'

// 游戏状态
const gameState = ref({
  status: 'idle',
  current_round: 0,
  current_answer: null,
  current_hints: [],
  current_hints_shown: 0,
  time_remaining: 0,
  used_word_ids: [],
  config: null,
  current_rankings: [],
  total_guesses: 0
})

const config = ref({
  total_rounds: 5,
  round_time_limit: 7200,
  similarity_algorithm: 'hybrid',
  ranking_display_count: 20,
  auto_next_round: true,
  popup_duration: 10,
  hint_penalty: 0.05,
  qa_enabled: true
})

const currentGuesses = ref([])
const currentRankings = ref([])
const timeRemaining = ref(0)
const currentCategory = ref('')
const currentDifficulty = ref('')
const currentHints = ref([])
const qaList = ref([]) // 观众问答记录

// 重复猜词本地通知队列
const noticeList = ref([])      // 当前展示中的通知
const noticeQueue = ref([])     // 等待展示的队列
const NOTICE_DURATION = 2500    // 单条显示时长（毫秒）
const NOTICE_MAX_VISIBLE = 1    // 同时最多展示条数

const pushDuplicateNotice = (payload) => {
  // 去重：相同 (user_name, previous_user, guess_content) 的未过期提示不重复入队
  const dupKey = `${payload.user_name}|${payload.previous_user}|${payload.guess_content}`
  const isDuplicate = [...noticeList.value, ...noticeQueue.value]
    .some(n => n.key === dupKey)
  if (isDuplicate) return

  const item = {
    key: dupKey,
    user_name: payload.user_name,
    previous_user: payload.previous_user,
    guess_content: payload.guess_content,
    id: Date.now() + Math.random()
  }
  noticeQueue.value.push(item)
  flushNoticeQueue()
}

const flushNoticeQueue = () => {
  while (noticeList.value.length < NOTICE_MAX_VISIBLE && noticeQueue.value.length > 0) {
    const item = noticeQueue.value.shift()
    noticeList.value.push(item)
    // 单条定时移除
    setTimeout(() => {
      const idx = noticeList.value.findIndex(n => n.id === item.id)
      if (idx > -1) {
        noticeList.value.splice(idx, 1)
        flushNoticeQueue()
      }
    }, NOTICE_DURATION)
  }
}

// 子窗体管理：Electron 用 IPC，浏览器用新标签页
const openSubWindow = (type) => {
  if (window.electronAPI) {
    window.electronAPI.openSubWindow(type)
  } else {
    window.open(`${window.location.origin}${window.location.pathname}?window=${type}`, '_blank')
  }
}

// 词库变更：刷新当前题面与排行榜（下一轮自动用新词）
const onWordsChanged = async () => {
  await Promise.all([loadState(), loadRankings(), loadGuesses()])
  ElMessage.success('词库已更新，下一轮将使用新词库')
}

// 猜中弹窗
const congratsVisible = ref(false)
const congratsData = ref({
  winnerName: '',
  answer: '',
  guessContent: ''
})

// 计算属性
const isRunning = computed(() => gameState.value.status === 'running')

const answerMasked = computed(() => {
  const answer = gameState.value.current_answer
  if (!answer) return '***'
  return '*'.repeat(answer.length)
})

const statusLabel = computed(() => {
  if (gameState.value.status === 'paused') return '已暂停'
  if (gameState.value.status === 'finished') return '已结束'
  return '未开始'
})

// API调用
const loadState = async () => {
  try {
    const res = await axios.get('/api/game/state')
    gameState.value = res.data
    if (res.data.config) {
      config.value = { ...config.value, ...res.data.config }
    }
    timeRemaining.value = res.data.time_remaining || 0
    currentCategory.value = res.data.current_category || ''
    currentDifficulty.value = res.data.current_difficulty || ''
    currentHints.value = res.data.current_hints || []
  } catch (e) {
    console.error('加载游戏状态失败:', e)
  }
}

const loadRankings = async () => {
  try {
    const res = await axios.get('/api/game/rankings')
    currentRankings.value = res.data
  } catch (e) {
    console.error('加载排行榜失败:', e)
  }
}

const loadGuesses = async () => {
  try {
    const res = await axios.get('/api/game/guesses')
    currentGuesses.value = res.data
  } catch (e) {
    console.error('加载猜词记录失败:', e)
  }
}

const startGame = async () => {
  try {
    if (gameState.value.status === 'paused') {
      await axios.post('/api/game/resume')
    } else {
      await axios.post('/api/game/start')
    }
    ElMessage.success('游戏已开始')
    loadState()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const pauseGame = async () => {
  try {
    await axios.post('/api/game/pause')
    ElMessage.info('游戏已暂停')
    loadState()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const stopGame = async () => {
  try {
    await axios.post('/api/game/stop')
    ElMessage.info('游戏已结束')
    loadState()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const nextRound = async () => {
  try {
    await axios.post('/api/game/next-round')
    loadState()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

const requestHint = async () => {
  try {
    const res = await axios.post('/api/game/hint')
    if (res.data.hint) {
      ElMessage.info(`提示：${res.data.hint}`)
    }
    loadState()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '没有更多提示')
  }
}

const skipRound = async () => {
  try {
    await axios.post('/api/game/next-round')
    ElMessage.info('已跳过本轮')
    loadState()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

// WebSocket消息处理
const handleWsMessage = (data) => {
  const msgType = data.message_type

  if (msgType === 'game_new_round') {
    currentGuesses.value = []
    qaList.value = []
    gameState.value.status = 'running'
    gameState.value.current_round = data.data.current_round
    timeRemaining.value = data.data.time_remaining
    currentCategory.value = data.data.category || ''
    currentDifficulty.value = data.data.difficulty || ''
    currentHints.value = data.data.hints || []
    loadState()
  }

  if (msgType === 'game_state_update') {
    gameState.value.status = data.data.status
    if (data.data.time_remaining !== undefined) {
      timeRemaining.value = data.data.time_remaining
    }
    if (data.data.current_round !== undefined) {
      gameState.value.current_round = data.data.current_round
    }
    if (data.data.hints_shown !== undefined) {
      currentHints.value = data.data.hints_shown || []
    }
  }

  if (msgType === 'game_new_guess') {
    currentGuesses.value = [...currentGuesses.value, data.data]
  }

  if (msgType === 'game_ranking_update') {
    currentRankings.value = data.data.rankings || []
  }

  if (msgType === 'game_correct_answer') {
    congratsData.value = {
      winnerName: data.data.user_name,
      answer: data.data.answer,
      guessContent: data.data.guess_content
    }
    congratsVisible.value = true
  }

  if (msgType === 'game_round_timeout') {
    ElMessage.warning(`本轮时间到！答案是：${data.data.answer}`)
    loadState()
  }

  if (msgType === 'game_duplicate_guess') {
    pushDuplicateNotice({
      user_name: data.data.user_name,
      previous_user: data.data.previous_user,
      guess_content: data.data.guess_content
    })
  }

  if (msgType === 'game_new_question') {
    qaList.value.push(data.data)
    // 最多保留10条问答记录
    if (qaList.value.length > 10) {
      qaList.value = qaList.value.slice(-10)
    }
  }
}

// 格式化倒计时（支持 HH:MM:SS 格式）
const formatCountdown = (seconds) => {
  if (!seconds || seconds <= 0) return '00:00'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) {
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  }
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

// 注册WebSocket消息监听
const onWsMessage = (event) => {
  try {
    const data = event.detail
    handleWsMessage(data)
  } catch (e) {
    console.error('处理游戏消息失败:', e)
  }
}

onMounted(() => {
  loadState()
  loadRankings()
  loadGuesses()
  window.addEventListener('ws-message', onWsMessage)

  // 监听子窗体的数据变更通知
  if (window.electronAPI) {
    window.electronAPI.onWordsChanged(() => onWordsChanged())
    window.electronAPI.onConfigChanged(() => loadState())
  }
})

onUnmounted(() => {
  window.removeEventListener('ws-message', onWsMessage)
})
</script>

<style scoped>
.game-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg-primary);
  border-radius: var(--radius-md);
  overflow: hidden;
  min-height: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', 'Helvetica Neue', Helvetica, Arial, sans-serif;
  animation: app-fade-in 0.4s ease-out;
}

/* ===== 顶部标题栏：白色 + 品牌色底线 ===== */
.game-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 24px;
  background: var(--color-bg-primary);
  border-bottom: 2px solid var(--color-brand);
  color: var(--color-text-primary);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.game-title {
  font-size: 20px;
  font-weight: 800;
  letter-spacing: 1px;
  color: var(--color-text-primary);
}

.auto-peek-hint {
  font-size: 11px;
  color: var(--color-brand);
  background: var(--color-brand-light);
  padding: 2px 10px;
  border-radius: 20px;
  font-weight: 600;
}

.header-right {
  display: flex;
  align-items: center;
}

.countdown-tag {
  background: var(--color-bg-tertiary) !important;
  border-color: transparent !important;
  color: var(--color-text-primary) !important;
  font-weight: 700;
  font-size: 14px;
  letter-spacing: 1px;
  min-width: 60px;
  text-align: center;
  border-radius: var(--radius-sm) !important;
}

.countdown-warning {
  animation: countdown-pulse 0.8s ease-in-out infinite alternate;
  background: var(--color-danger) !important;
  color: #fff !important;
}

@keyframes countdown-pulse {
  from { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 59, 48, 0.3); }
  to { transform: scale(1.05); box-shadow: 0 0 8px 2px rgba(255, 59, 48, 0.15); }
}

/* ===== 信息提示栏 ===== */
.info-bar {
  display: flex;
  align-items: center;
  padding: 8px 24px;
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.participate-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

/* ===== 分类与操作栏 ===== */
.category-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 24px;
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.category-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.category-label {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.category-tag {
  font-size: 13px !important;
  font-weight: 700 !important;
  border-radius: var(--radius-sm) !important;
}

.word-length-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.category-actions {
  display: flex;
  gap: 6px;
}

/* ===== 主内容区 ===== */
.game-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
  max-height: 100%;
}

.content-left {
  flex: 1;
  overflow: hidden;
  border-right: 1px solid var(--color-border-light);
  max-height: 100%;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.content-right {
  width: 260px;
  min-width: 200px;
  max-width: 320px;
  flex-shrink: 0;
  overflow: hidden;
  min-height: 0;
  background: var(--color-bg-primary);
}

/* ===== 底部区域 ===== */
.game-footer {
  flex-shrink: 0;
  border-top: 1px solid var(--color-border-light);
}

.footer-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: var(--color-bg-secondary);
  gap: 6px;
  flex-wrap: wrap;
}

.round-info {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin-right: 4px;
  font-weight: 600;
}

/* 观众问答区 */
.qa-section {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 8px 20px;
  background: var(--color-bg-secondary);
  border-top: 1px solid var(--color-border-light);
}

.qa-label {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-primary);
  white-space: nowrap;
  flex-shrink: 0;
  line-height: 24px;
}

.qa-list {
  flex: 1;
  max-height: 72px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.qa-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  line-height: 20px;
}

.qa-user {
  color: var(--color-text-secondary);
  font-weight: 600;
  flex-shrink: 0;
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.qa-question {
  color: var(--color-text-primary);
  flex-shrink: 0;
}

.qa-answer-tag {
  flex-shrink: 0;
}

.qa-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 24px;
}

/* ===== 重复猜词提示横幅 ===== */
.notice-stack {
  position: relative;
  flex-shrink: 0;
  z-index: 5;
  /* 固定高度槽位：有/无通知都恒为 36px，不挤压下方 GuessTable */
  height: 36px;
  /* 通知条 absolute 浮于槽位内，但保留 overflow:hidden 防止动画超出 */
  overflow: hidden;
  background: transparent;
}

.duplicate-notice {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 36px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  margin: 0;
  background: linear-gradient(90deg, #fff9f0 0%, #fff5e6 100%);
  border-bottom: 1px solid var(--color-border);
  border-left: 3px solid var(--color-warning);
  font-size: 13px;
  line-height: 1.5;
  color: var(--color-text-primary);
  box-shadow: var(--shadow-sm);
  box-sizing: border-box;
}

.notice-icon {
  font-size: 16px;
  color: var(--color-warning);
  flex-shrink: 0;
  line-height: 1;
}

.notice-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notice-user,
.notice-prev {
  color: var(--color-brand);
  font-weight: 700;
}

.notice-mid {
  color: var(--color-text-secondary);
  margin: 0 2px;
}

.notice-content {
  color: var(--color-warning);
  font-weight: 600;
}

/* 滑入/滑出动画 */
.notice-slide-enter-active {
  transition: opacity 0.3s ease-out, transform 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94);
}
.notice-slide-leave-active {
  transition: opacity 0.25s ease-in, transform 0.25s ease-in;
}
.notice-slide-enter-from {
  opacity: 0;
  transform: translateY(-100%);
}
.notice-slide-enter-to {
  opacity: 1;
  transform: translateY(0);
}
.notice-slide-leave-from {
  opacity: 1;
  transform: translateY(0);
}
.notice-slide-leave-to {
  opacity: 0;
  transform: translateY(-100%);
}

/* 响应式布局：小窗口时主内容区改为纵向排列 */
@media (max-width: 768px) {
  .game-content {
    flex-direction: column;
  }
  .content-left {
    border-right: none;
    border-bottom: 1px solid var(--color-border-light);
    min-height: 200px;
  }
  .content-right {
    width: 100% !important;
    min-width: 0 !important;
    max-width: 100% !important;
    max-height: 200px;
  }
  .category-bar {
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
  }
  .footer-controls {
    justify-content: center;
  }
  .duplicate-notice {
    font-size: 12px;
    padding: 6px 12px;
    height: 32px;
  }
  .notice-stack { height: 32px; }
  .notice-icon { font-size: 14px; }
}
</style>
