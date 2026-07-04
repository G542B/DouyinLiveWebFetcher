<template>
  <div class="element-picker">
    <div class="picker-section">
      <div class="picker-label">
        <el-icon><Edit /></el-icon>
        <span>输入区域选择器</span>
      </div>
      <div class="picker-row">
        <el-input
          v-model="textareaSelector"
          placeholder="textarea, #chat-input, .message-box"
          size="small"
          :disabled="disabled"
          @change="emitSelectors"
        />
        <el-button
          :type="pickingTarget === 'textarea' ? 'warning' : 'primary'"
          size="small"
          :disabled="!browserConnected || disabled"
          @click="startPick('textarea')"
        >
          {{ pickingTarget === 'textarea' ? '拾取中...' : '拾取' }}
        </el-button>
      </div>
      <div v-if="textareaInfo" class="picked-info">
        <el-tag size="small" type="info">{{ textareaInfo.tag_name }}</el-tag>
        <el-tag size="small" :type="textareaInfo.element_type === 'input' ? 'success' : textareaInfo.element_type === 'button' ? 'warning' : 'info'">
          {{ textareaInfo.element_type === 'input' ? '输入框' : textareaInfo.element_type === 'button' ? '按钮' : '其他' }}
        </el-tag>
        <span v-if="textareaInfo.important_attrs && textareaInfo.important_attrs.placeholder" class="picked-attr" title="placeholder">{{ textareaInfo.important_attrs.placeholder }}</span>
        <span v-else-if="textareaInfo.important_attrs && textareaInfo.important_attrs['aria-label']" class="picked-attr" title="aria-label">{{ textareaInfo.important_attrs['aria-label'] }}</span>
        <span v-else class="picked-text">{{ textareaInfo.text_preview }}</span>
      </div>
    </div>

    <div class="picker-section">
      <div class="picker-label">
        <el-icon><Pointer /></el-icon>
        <span>发送按钮选择器</span>
      </div>
      <div class="picker-row">
        <el-input
          v-model="buttonSelector"
          placeholder="button.send, .submit-btn, #send"
          size="small"
          :disabled="disabled"
          @change="emitSelectors"
        />
        <el-button
          :type="pickingTarget === 'button' ? 'warning' : 'primary'"
          size="small"
          :disabled="!browserConnected || disabled"
          @click="startPick('button')"
        >
          {{ pickingTarget === 'button' ? '拾取中...' : '拾取' }}
        </el-button>
      </div>
      <div v-if="buttonInfo" class="picked-info">
        <el-tag size="small" type="info">{{ buttonInfo.tag_name }}</el-tag>
        <el-tag size="small" :type="buttonInfo.element_type === 'button' ? 'success' : buttonInfo.element_type === 'input' ? 'warning' : 'info'">
          {{ buttonInfo.element_type === 'button' ? '按钮' : buttonInfo.element_type === 'input' ? '输入框' : '其他' }}
        </el-tag>
        <span v-if="buttonInfo.important_attrs && buttonInfo.important_attrs['aria-label']" class="picked-attr" title="aria-label">{{ buttonInfo.important_attrs['aria-label'] }}</span>
        <span v-else class="picked-text">{{ buttonInfo.text_preview }}</span>
      </div>
    </div>

    <div class="picker-status">
      <el-tag
        :type="pickingTarget ? 'warning' : 'info'"
        size="small"
        effect="dark"
      >
        {{ pickingTarget ? `拾取模式运行中 - 目标: ${pickingTarget === 'textarea' ? '输入区域' : '发送按钮'}` : '拾取模式未启动' }}
      </el-tag>
      <el-button
        v-if="pickingTarget"
        type="danger"
        size="small"
        link
        @click="stopPick"
      >
        停止拾取
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import { Edit, Pointer } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const props = defineProps({
  browserConnected: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  initialTextareaSelector: { type: String, default: '' },
  initialButtonSelector: { type: String, default: '' }
})

const emit = defineEmits(['update:textareaSelector', 'update:buttonSelector', 'update:textareaSelectors', 'update:buttonSelectors'])

const textareaSelector = ref(props.initialTextareaSelector)
const buttonSelector = ref(props.initialButtonSelector)
const pickingTarget = ref('')
const textareaInfo = ref(null)
const buttonInfo = ref(null)
let pickerTimer = null

const startPick = async (target) => {
  if (pickingTarget.value) {
    await stopPick()
  }

  try {
    const response = await axios.post('/api/output/picker/start')
    if (response.data.success) {
      pickingTarget.value = target
      ElMessage.info('请在目标页面中点击要选择的元素')
      startPickerPolling()
    } else {
      ElMessage.error(response.data.error || '启动拾取失败')
    }
  } catch (e) {
    ElMessage.error('启动拾取失败')
    console.error(e)
  }
}

const stopPick = async () => {
  try {
    await axios.post('/api/output/picker/stop')
  } catch (e) {
    console.error(e)
  }
  pickingTarget.value = ''
  if (pickerTimer) {
    clearInterval(pickerTimer)
    pickerTimer = null
  }
}

const startPickerPolling = () => {
  if (pickerTimer) clearInterval(pickerTimer)
  pickerTimer = setInterval(async () => {
    if (!pickingTarget.value) {
      clearInterval(pickerTimer)
      pickerTimer = null
      return
    }

    try {
      const response = await axios.get('/api/output/picker/result')
      if (response.data.success && response.data.result) {
        const result = response.data.result
        if (pickingTarget.value === 'textarea') {
          textareaSelector.value = result.selector
          textareaInfo.value = result
          emit('update:textareaSelector', result.selector)
          if (result.selectors && result.selectors.length > 1) {
            emit('update:textareaSelectors', result.selectors)
          }
        } else if (pickingTarget.value === 'button') {
          buttonSelector.value = result.selector
          buttonInfo.value = result
          emit('update:buttonSelector', result.selector)
          if (result.selectors && result.selectors.length > 1) {
            emit('update:buttonSelectors', result.selectors)
          }
        }
        ElMessage.success(`已选择: ${result.selector}`)
        await stopPick()
      }
    } catch (e) {
      console.error('轮询拾取结果失败:', e)
    }
  }, 1000)
}

const emitSelectors = () => {
  emit('update:textareaSelector', textareaSelector.value)
  emit('update:buttonSelector', buttonSelector.value)
}

onUnmounted(() => {
  if (pickerTimer) {
    clearInterval(pickerTimer)
    pickerTimer = null
  }
})

defineExpose({
  textareaSelector,
  buttonSelector,
  setSelectors: (textarea, button) => {
    textareaSelector.value = textarea
    buttonSelector.value = button
  }
})
</script>

<style scoped>
.element-picker {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.picker-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.picker-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.picker-row {
  display: flex;
  gap: 8px;
}

.picker-row .el-input {
  flex: 1;
}

.picked-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.picked-text {
  color: var(--color-text-tertiary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 150px;
}

.picked-attr {
  color: var(--color-brand);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 150px;
}

.picker-status {
  display: flex;
  align-items: center;
  gap: 8px;
}

.picker-section {
  transition: opacity var(--transition-fast);
}

.picker-section:hover {
  opacity: 0.85;
}
</style>
