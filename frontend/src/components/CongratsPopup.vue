<template>
  <transition name="popup-fade">
    <div v-if="visible" class="congrats-overlay" @click.self="close">
      <div class="congrats-popup">
        <button class="close-btn" @click="close">&times;</button>
        <div class="congrats-content">
          <div class="celebration-icon">&#127881;</div>
          <h2 class="congrats-title">猜中啦！</h2>
          <p class="congrats-message">
            恭喜 <span class="winner-name">{{ winnerName }}</span> 猜中答案！
          </p>
          <p class="congrats-answer">
            正确答案是：<span class="answer-text">{{ answer }}</span>
          </p>
          <div class="congrats-meta">
            <span v-if="guessContent" class="guess-info">猜词：{{ guessContent }}</span>
          </div>
          <div class="countdown-bar">
            <div class="countdown-progress" :style="{ width: progressPercent + '%' }"></div>
          </div>
          <p class="countdown-text">{{ remainingSeconds }}秒后自动关闭</p>
        </div>
        <div class="particles">
          <span v-for="i in 12" :key="i" class="particle" :style="particleStyle(i)"></span>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  winnerName: { type: String, default: '' },
  answer: { type: String, default: '' },
  guessContent: { type: String, default: '' },
  duration: { type: Number, default: 10 }
})

const emit = defineEmits(['close'])

const remainingSeconds = ref(props.duration)
let timer = null

const progressPercent = computed(() => {
  return (remainingSeconds.value / props.duration) * 100
})

const close = () => {
  emit('close')
}

const startCountdown = () => {
  remainingSeconds.value = props.duration
  if (timer) clearInterval(timer)
  timer = setInterval(() => {
    remainingSeconds.value--
    if (remainingSeconds.value <= 0) {
      clearInterval(timer)
      timer = null
      close()
    }
  }, 1000)
}

const particleStyle = (i) => {
  const angle = (i / 12) * 360
  const distance = 80 + Math.random() * 60
  const x = Math.cos(angle * Math.PI / 180) * distance
  const y = Math.sin(angle * Math.PI / 180) * distance
  const colors = ['#4f6df5', '#34c759', '#ff9500', '#ff3b30', '#b37feb', '#ff85c0']
  const color = colors[i % colors.length]
  return {
    '--tx': x + 'px',
    '--ty': y + 'px',
    'background-color': color,
    'animation-delay': (i * 0.05) + 's'
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    startCountdown()
  } else {
    if (timer) {
      clearInterval(timer)
      timer = null
    }
  }
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
})
</script>

<style scoped>
.congrats-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.congrats-popup {
  position: relative;
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  padding: 40px 48px;
  min-width: 400px;
  max-width: 500px;
  text-align: center;
  box-shadow: var(--shadow-lg), 0 0 40px rgba(79, 109, 245, 0.15);
  overflow: hidden;
}

.close-btn {
  position: absolute;
  top: 12px;
  right: 16px;
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  font-size: 24px;
  cursor: pointer;
  line-height: 1;
  transition: color var(--transition-fast);
}

.close-btn:hover {
  color: var(--color-danger);
}

.congrats-content {
  position: relative;
  z-index: 1;
}

.celebration-icon {
  font-size: 48px;
  margin-bottom: 12px;
  animation: bounce 0.6s ease infinite alternate;
}

.congrats-title {
  color: var(--color-brand);
  font-size: 28px;
  margin: 0 0 16px;
  font-weight: 800;
}

.congrats-message {
  color: var(--color-text-primary);
  font-size: 16px;
  margin: 0 0 8px;
}

.winner-name {
  color: var(--color-warning);
  font-weight: bold;
  font-size: 18px;
}

.congrats-answer {
  color: var(--color-text-secondary);
  font-size: 14px;
  margin: 0 0 12px;
}

.answer-text {
  color: var(--color-brand);
  font-size: 22px;
  font-weight: bold;
}

.congrats-meta {
  margin-bottom: 16px;
}

.guess-info {
  color: var(--color-text-tertiary);
  font-size: 13px;
}

.countdown-bar {
  height: 4px;
  background: var(--color-bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 8px;
}

.countdown-progress {
  height: 100%;
  background: linear-gradient(90deg, var(--color-brand), var(--color-success));
  border-radius: 2px;
  transition: width 1s linear;
}

.countdown-text {
  color: var(--color-text-tertiary);
  font-size: 12px;
  margin: 0;
}

.particles {
  position: absolute;
  top: 50%;
  left: 50%;
  pointer-events: none;
}

.particle {
  position: absolute;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  animation: particle-burst 1.2s ease-out forwards;
  transform: translate(-50%, -50%);
}

@keyframes bounce {
  from { transform: translateY(0); }
  to { transform: translateY(-8px); }
}

@keyframes particle-burst {
  0% {
    transform: translate(-50%, -50%) scale(1);
    opacity: 1;
  }
  100% {
    transform: translate(calc(-50% + var(--tx)), calc(-50% + var(--ty))) scale(0);
    opacity: 0;
  }
}

.popup-fade-enter-active {
  animation: popup-in 0.4s ease;
}

.popup-fade-leave-active {
  animation: popup-out 0.3s ease;
}

@keyframes popup-in {
  from {
    opacity: 0;
    transform: scale(0.8);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

@keyframes popup-out {
  from {
    opacity: 1;
    transform: scale(1);
  }
  to {
    opacity: 0;
    transform: scale(0.8);
  }
}
</style>
