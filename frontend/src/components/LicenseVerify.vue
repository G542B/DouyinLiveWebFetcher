<template>
  <div class="license-wrapper">
    <div class="license-container">
      <div class="license-header">
        <div class="logo-icon">
          <svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5">
            <rect x="3" y="11" width="18" height="11" rx="2" stroke-linecap="round"/>
            <path d="M7 11V7a5 5 0 0110 0v4" stroke-linecap="round"/>
            <circle cx="12" cy="16" r="1.5" fill="currentColor"/>
          </svg>
        </div>
        <h1>许可证验证</h1>
        <p class="subtitle">请验证您的许可证以继续使用</p>
      </div>

      <el-alert
        v-if="errorMessage"
        :title="errorMessage"
        type="error"
        show-icon
        :closable="true"
        @close="errorMessage = ''"
        class="status-alert"
      />

      <el-alert
        v-if="successMessage"
        :title="successMessage"
        type="success"
        show-icon
        class="status-alert"
      />

      <div class="section">
        <div class="section-title">
          <el-icon><Monitor /></el-icon>
          <span>本机机器码</span>
        </div>
        <div class="machine-code-box">
          <code class="machine-code">{{ machineCode }}</code>
          <el-button
            type="primary"
            size="small"
            plain
            @click="copyMachineCode"
            :icon="copied ? 'Check' : 'CopyDocument'"
          >
            {{ copied ? '已复制' : '复制' }}
          </el-button>
        </div>
        <p class="hint">
          请将此机器码发送给管理员获取许可证密钥
        </p>
      </div>

      <div class="section">
        <div class="section-title">
          <el-icon><Key /></el-icon>
          <span>输入许可证密钥</span>
        </div>
        <el-input
          v-model="licenseKey"
          type="textarea"
          :rows="3"
          placeholder="请粘贴管理员提供的许可证密钥"
          class="key-input"
        />
        <el-button
          type="primary"
          size="large"
          class="verify-btn"
          :loading="verifying"
          :disabled="!licenseKey.trim()"
          @click="verifyLicense"
        >
          {{ verifying ? '验证中...' : '验证许可证' }}
        </el-button>
      </div>

      <div class="footer-info">
        <p>首次使用？请将上方机器码提供给管理员以获取许可证密钥</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Monitor, Key } from '@element-plus/icons-vue'
import axios from 'axios'

const machineCode = ref('')
const licenseKey = ref('')
const verifying = ref(false)
const copied = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const fetchMachineCode = async () => {
  try {
    const response = await axios.get('/api/license/machine-code')
    machineCode.value = response.data.machine_code
  } catch (e) {
    errorMessage.value = '无法获取机器码，请检查后端服务是否正常运行'
  }
}

const copyMachineCode = async () => {
  try {
    await navigator.clipboard.writeText(machineCode.value)
    copied.value = true
    ElMessage.success('机器码已复制到剪贴板')
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}

const verifyLicense = async () => {
  if (!licenseKey.value.trim()) {
    ElMessage.warning('请输入许可证密钥')
    return
  }

  verifying.value = true
  errorMessage.value = ''
  successMessage.value = ''

  try {
    const response = await axios.post('/api/license/verify', {
      license_key: licenseKey.value.trim()
    })

    if (response.data.success) {
      successMessage.value = response.data.message || '许可证验证通过！即将进入应用...'
      ElMessage.success('验证通过！')
      setTimeout(() => {
        window.location.reload()
      }, 1500)
    } else {
      errorMessage.value = response.data.message || '许可证密钥无效'
    }
  } catch (e) {
    if (e.response && e.response.data && e.response.data.detail) {
      errorMessage.value = e.response.data.detail
    } else {
      errorMessage.value = '验证失败，请检查网络连接后重试'
    }
  } finally {
    verifying.value = false
  }
}

onMounted(() => {
  fetchMachineCode()
})
</script>

<style scoped>
.license-wrapper {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.license-container {
  background: white;
  border-radius: 16px;
  padding: 48px;
  max-width: 560px;
  width: 100%;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
}

.license-header {
  text-align: center;
  margin-bottom: 32px;
}

.logo-icon {
  color: #667eea;
  margin-bottom: 16px;
}

.license-header h1 {
  font-size: 28px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0 0 8px 0;
}

.subtitle {
  color: #909399;
  font-size: 14px;
  margin: 0;
}

.status-alert {
  margin-bottom: 24px;
}

.section {
  margin-bottom: 28px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
}

.section-title .el-icon {
  color: #667eea;
  font-size: 18px;
}

.machine-code-box {
  display: flex;
  gap: 8px;
  align-items: center;
}

.machine-code {
  flex: 1;
  padding: 12px 16px;
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  color: #303133;
  word-break: break-all;
  user-select: all;
}

.hint {
  font-size: 12px;
  color: #909399;
  margin: 8px 0 0 0;
}

.key-input {
  margin-bottom: 16px;
}

.key-input :deep(.el-textarea__inner) {
  font-family: 'Courier New', monospace;
  font-size: 13px;
}

.verify-btn {
  width: 100%;
  height: 44px;
  font-size: 16px;
}

.footer-info {
  text-align: center;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}

.footer-info p {
  font-size: 12px;
  color: #c0c4cc;
  margin: 0;
}
</style>
