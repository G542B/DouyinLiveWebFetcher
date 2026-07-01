<template>
  <el-card class="filter-config">
    <template #header>
      <div class="card-header">
        <span>🎯 弹幕过滤配置</span>
      </div>
    </template>
    
    <el-tabs v-model="activeTab" class="filter-tabs">
      <el-tab-pane label="消息类型" name="types">
        <el-checkbox-group v-model="config.enabled_types" @change="saveFilter">
          <el-checkbox
            v-for="(name, type) in messageTypes"
            :key="type"
            :value="type"
            :label="name"
            style="display: block; margin-bottom: 8px"
          />
        </el-checkbox-group>
        
        <div class="filter-actions" style="margin-top: 16px">
          <el-button size="small" @click="selectAll">全选</el-button>
          <el-button size="small" @click="selectNone">清空</el-button>
        </div>
      </el-tab-pane>
      
      <el-tab-pane label="关键词过滤" name="keywords">
        <el-form label-position="top" size="small">
          <el-form-item>
            <el-checkbox v-model="config.keyword_filter.enabled">启用关键词过滤</el-checkbox>
          </el-form-item>
          
          <el-form-item label="过滤模式" v-if="config.keyword_filter.enabled">
            <el-radio-group v-model="config.keyword_filter.mode" @change="saveFilter">
              <el-radio value="blacklist">黑名单模式</el-radio>
              <el-radio value="whitelist">白名单模式</el-radio>
            </el-radio-group>
          </el-form-item>
          
          <el-form-item label="关键词列表" v-if="config.keyword_filter.enabled">
            <el-input
              type="textarea"
              :rows="4"
              placeholder="每行一个关键词"
              v-model="keywordInput"
              @change="updateKeywords"
            />
          </el-form-item>
          
          <el-form-item v-if="config.keyword_filter.enabled">
            <el-checkbox v-model="config.keyword_filter.exact_match" @change="saveFilter">
              精确匹配
            </el-checkbox>
            <el-checkbox v-model="config.keyword_filter.case_sensitive" @change="saveFilter" style="margin-left: 16px">
              区分大小写
            </el-checkbox>
          </el-form-item>
        </el-form>
      </el-tab-pane>
      
      <el-tab-pane label="正则表达式" name="regex">
        <el-form label-position="top" size="small">
          <el-form-item>
            <el-checkbox v-model="config.regex_filter.enabled">启用正则过滤</el-checkbox>
          </el-form-item>
          
          <el-form-item label="正则表达式列表" v-if="config.regex_filter.enabled">
            <el-input
              type="textarea"
              :rows="4"
              placeholder="每行一个正则表达式"
              v-model="regexInput"
              @change="updateRegex"
            />
          </el-form-item>
        </el-form>
      </el-tab-pane>
      
      <el-tab-pane label="用户等级" name="userlevel">
        <el-form label-position="top" size="small">
          <el-form-item>
            <el-checkbox v-model="config.user_level_filter.enabled">启用用户等级过滤</el-checkbox>
          </el-form-item>

          <el-form-item label="最低等级" v-if="config.user_level_filter.enabled">
            <el-input-number
              v-model="config.user_level_filter.min_level"
              :min="0"
              :max="100"
              @change="saveFilter"
              style="width: 100%"
              placeholder="不限制留空"
            />
          </el-form-item>

          <el-form-item label="最高等级" v-if="config.user_level_filter.enabled">
            <el-input-number
              v-model="config.user_level_filter.max_level"
              :min="0"
              :max="100"
              @change="saveFilter"
              style="width: 100%"
              placeholder="不限制留空"
            />
          </el-form-item>

          <el-form-item label="白名单用户" v-if="config.user_level_filter.enabled">
            <el-input
              type="textarea"
              :rows="3"
              placeholder="每行一个用户名"
              v-model="allowedUsersInput"
              @change="updateAllowedUsers"
            />
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="表情包过滤" name="emoji">
        <el-form label-position="top" size="small">
          <el-form-item>
            <el-checkbox v-model="config.emoji_filter.enabled">启用药情包过滤</el-checkbox>
          </el-form-item>

          <el-form-item label="过滤策略" v-if="config.emoji_filter.enabled">
            <el-radio-group v-model="config.emoji_filter.strategy" @change="saveFilter">
              <el-radio value="full">完全过滤（整条消息过滤）</el-radio>
              <el-radio value="partial">部分过滤（仅过滤表情，保留文本）</el-radio>
            </el-radio-group>
          </el-form-item>

          <el-form-item label="过滤范围" v-if="config.emoji_filter.enabled">
            <el-checkbox v-model="config.emoji_filter.filter_image_emoji" @change="saveFilter">
              过滤图片表情
            </el-checkbox>
            <el-checkbox v-model="config.emoji_filter.filter_text_emoji" @change="saveFilter" style="margin-left: 16px">
              过滤字符表情
            </el-checkbox>
            <el-checkbox v-model="config.emoji_filter.filter_emoji_chat" @change="saveFilter" style="margin-left: 16px">
              过滤独立表情包消息
            </el-checkbox>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="方括号表情" name="emoticon">
        <el-form label-position="top" size="small">
          <el-form-item>
            <el-checkbox v-model="config.emoticon_filter.enabled">启用方括号表情过滤</el-checkbox>
          </el-form-item>

          <el-form-item v-if="config.emoticon_filter.enabled">
            <el-checkbox v-model="config.emoticon_filter.match_all" @change="saveFilter">
              匹配所有方括号表情（自动识别 [xxx] 格式）
            </el-checkbox>
          </el-form-item>

          <el-form-item label="表情模式列表" v-if="config.emoticon_filter.enabled && !config.emoticon_filter.match_all">
            <el-input
              type="textarea"
              :rows="4"
              placeholder="每行一个方括号表情，如 [捂脸]、[呲牙]"
              v-model="emoticonPatternsInput"
              @change="saveFilter"
            />
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="@提及过滤" name="mention">
        <el-form label-position="top" size="small">
          <el-form-item>
            <el-checkbox v-model="config.mention_filter.enabled">启用@提及过滤</el-checkbox>
          </el-form-item>

          <el-form-item label="过滤策略" v-if="config.mention_filter.enabled">
            <el-radio-group v-model="config.mention_filter.strategy" @change="saveFilter">
              <el-radio value="full">完全过滤（整条消息过滤）</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="特殊符号" name="special_symbol">
        <el-form label-position="top" size="small">
          <el-form-item>
            <el-checkbox v-model="config.special_symbol_filter.enabled">启用特殊符号过滤</el-checkbox>
          </el-form-item>
          
          <el-form-item label="匹配模式" v-if="config.special_symbol_filter.enabled">
            <el-radio-group v-model="config.special_symbol_filter.match_type" @change="saveFilter">
              <el-radio value="any">包含任意一个</el-radio>
              <el-radio value="all">包含全部</el-radio>
            </el-radio-group>
          </el-form-item>
          
          <el-form-item label="特殊符号列表" v-if="config.special_symbol_filter.enabled">
            <el-input
              type="textarea"
              :rows="4"
              placeholder="每行一个特殊符号，如 @、#、$"
              v-model="specialSymbolsInput"
              @change="saveFilter"
            />
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="提问类型" name="question">
        <el-form label-position="top" size="small">
          <el-form-item>
            <el-checkbox v-model="config.question_filter.enabled">启用提问类型过滤</el-checkbox>
          </el-form-item>
          
          <el-form-item label="匹配模式" v-if="config.question_filter.enabled">
            <el-radio-group v-model="config.question_filter.match_type" @change="saveFilter">
              <el-radio value="any">包含任意一个</el-radio>
              <el-radio value="all">包含全部</el-radio>
            </el-radio-group>
          </el-form-item>
          
          <el-form-item label="疑问标记列表" v-if="config.question_filter.enabled">
            <el-input
              type="textarea"
              :rows="4"
              placeholder="每行一个疑问标记，如 吗？、呢？、什么？"
              v-model="questionMarkersInput"
              @change="saveFilter"
            />
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="统计信息" name="stats">
        <el-descriptions :column="1" border v-if="stats">
          <el-descriptions-item label="总处理消息数">
            {{ stats.total_processed }}
          </el-descriptions-item>
          <el-descriptions-item label="已过滤消息数">
            {{ stats.total_filtered }}
          </el-descriptions-item>
          <el-descriptions-item label="过滤率">
            {{ stats.total_processed > 0 ? ((stats.total_filtered / stats.total_processed) * 100).toFixed(1) : 0 }}%
          </el-descriptions-item>
          
          <el-descriptions-item label="按类型过滤" v-if="Object.keys(stats.by_type).length > 0">
            <div v-for="(count, type) in stats.by_type" :key="type">
              {{ type }}: {{ count }}
            </div>
          </el-descriptions-item>
          
          <el-descriptions-item label="按关键词过滤" v-if="Object.keys(stats.by_keyword).length > 0">
            <div v-for="(count, keyword) in stats.by_keyword" :key="keyword">
              {{ keyword }}: {{ count }}
            </div>
          </el-descriptions-item>
          
          <el-descriptions-item label="按正则过滤" v-if="Object.keys(stats.by_regex).length > 0">
            <div v-for="(count, pattern) in stats.by_regex" :key="pattern">
              {{ pattern }}: {{ count }}
            </div>
          </el-descriptions-item>
          
          <el-descriptions-item label="按等级过滤" v-if="Object.keys(stats.by_level).length > 0">
            <div v-for="(count, reason) in stats.by_level" :key="reason">
              {{ reason }}: {{ count }}
            </div>
          </el-descriptions-item>

          <el-descriptions-item label="按表情包过滤" v-if="stats.by_emoji && Object.keys(stats.by_emoji).length > 0">
            <div v-for="(count, reason) in stats.by_emoji" :key="reason">
              {{ reason }}: {{ count }}
            </div>
          </el-descriptions-item>

          <el-descriptions-item label="按方括号表情过滤" v-if="stats.by_emoticon && Object.keys(stats.by_emoticon).length > 0">
            <div v-for="(count, reason) in stats.by_emoticon" :key="reason">
              {{ reason }}: {{ count }}
            </div>
          </el-descriptions-item>

          <el-descriptions-item label="按特殊符号过滤" v-if="stats.by_special_symbol && Object.keys(stats.by_special_symbol).length > 0">
            <div v-for="(count, reason) in stats.by_special_symbol" :key="reason">
              {{ reason }}: {{ count }}
            </div>
          </el-descriptions-item>

          <el-descriptions-item label="按@提及过滤" v-if="stats.by_mention && Object.keys(stats.by_mention).length > 0">
            <div v-for="(count, reason) in stats.by_mention" :key="reason">
              {{ reason }}: {{ count }}
            </div>
          </el-descriptions-item>

          <el-descriptions-item label="按提问类型过滤" v-if="stats.by_question && Object.keys(stats.by_question).length > 0">
            <div v-for="(count, reason) in stats.by_question" :key="reason">
              {{ reason }}: {{ count }}
            </div>
          </el-descriptions-item>
        </el-descriptions>
        
        <div style="margin-top: 16px">
          <el-button size="small" @click="resetStats">重置统计</el-button>
          <el-button size="small" @click="fetchStats">刷新</el-button>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const messageTypes = ref({})
const activeTab = ref('types')
const stats = ref(null)
const statsTimer = ref(null)

const config = ref({
  enabled_types: [],
  keyword_filter: {
    enabled: false,
    mode: 'blacklist',
    keywords: [],
    exact_match: false,
    case_sensitive: false
  },
  regex_filter: {
    enabled: false,
    patterns: []
  },
  user_level_filter: {
    enabled: false,
    min_level: null,
    max_level: null,
    allowed_users: []
  },
  emoji_filter: {
    enabled: false,
    strategy: 'full',
    filter_image_emoji: true,
    filter_text_emoji: true,
    filter_emoji_chat: true
  },
  emoticon_filter: {
    enabled: false,
    match_all: false,
    patterns: []
  },
  special_symbol_filter: {
    enabled: false,
    symbols: [],
    match_type: 'any'
  },
  mention_filter: {
    enabled: false,
    strategy: 'full'
  },
  question_filter: {
    enabled: false,
    question_markers: [],
    match_type: 'any'
  }
})

const keywordInput = computed({
  get: () => config.value.keyword_filter.keywords.join('\n'),
  set: (val) => {
    config.value.keyword_filter.keywords = val.split('\n').map(k => k.trim()).filter(k => k)
  }
})

const regexInput = computed({
  get: () => config.value.regex_filter.patterns.join('\n'),
  set: (val) => {
    config.value.regex_filter.patterns = val.split('\n').map(p => p.trim()).filter(p => p)
  }
})

const allowedUsersInput = computed({
  get: () => config.value.user_level_filter.allowed_users.join('\n'),
  set: (val) => {
    config.value.user_level_filter.allowed_users = val.split('\n').map(u => u.trim()).filter(u => u)
  }
})

const emoticonPatternsInput = computed({
  get: () => config.value.emoticon_filter.patterns.join('\n'),
  set: (val) => {
    config.value.emoticon_filter.patterns = val.split('\n').map(p => p.trim()).filter(p => p)
  }
})

const specialSymbolsInput = computed({
  get: () => config.value.special_symbol_filter.symbols.join('\n'),
  set: (val) => {
    config.value.special_symbol_filter.symbols = val.split('\n').map(s => s.trim()).filter(s => s)
  }
})

const questionMarkersInput = computed({
  get: () => config.value.question_filter.question_markers.join('\n'),
  set: (val) => {
    config.value.question_filter.question_markers = val.split('\n').map(q => q.trim()).filter(q => q)
  }
})

const fetchMessageTypes = async () => {
  try {
    const response = await axios.get('/api/message-types')
    messageTypes.value = response.data
  } catch (e) {
    console.error('获取消息类型失败:', e)
  }
}

const fetchFilters = async () => {
  try {
    const response = await axios.get('/api/filters/advanced')
    Object.assign(config.value, response.data)
  } catch (e) {
    console.error('获取过滤配置失败:', e)
  }
}

const fetchStats = async () => {
  try {
    const response = await axios.get('/api/filters/stats')
    stats.value = response.data
  } catch (e) {
    console.error('获取统计信息失败:', e)
  }
}

const saveFilter = async () => {
  try {
    // 构造要发送的数据，确保只发送需要的字段
    const payload = {
      enabled_types: config.value.enabled_types || [],
      keyword_filter: {
        enabled: config.value.keyword_filter?.enabled || false,
        mode: config.value.keyword_filter?.mode || 'blacklist',
        keywords: config.value.keyword_filter?.keywords || [],
        exact_match: config.value.keyword_filter?.exact_match || false,
        case_sensitive: config.value.keyword_filter?.case_sensitive || false
      },
      regex_filter: {
        enabled: config.value.regex_filter?.enabled || false,
        patterns: config.value.regex_filter?.patterns || []
      },
      user_level_filter: {
        enabled: config.value.user_level_filter?.enabled || false,
        min_level: config.value.user_level_filter?.min_level,
        max_level: config.value.user_level_filter?.max_level,
        allowed_users: config.value.user_level_filter?.allowed_users || []
      },
      emoji_filter: {
        enabled: config.value.emoji_filter?.enabled || false,
        strategy: config.value.emoji_filter?.strategy || 'full',
        filter_image_emoji: config.value.emoji_filter?.filter_image_emoji ?? true,
        filter_text_emoji: config.value.emoji_filter?.filter_text_emoji ?? true,
        filter_emoji_chat: config.value.emoji_filter?.filter_emoji_chat ?? true
      },
      emoticon_filter: {
        enabled: config.value.emoticon_filter?.enabled || false,
        match_all: config.value.emoticon_filter?.match_all || false,
        patterns: config.value.emoticon_filter?.patterns || []
      },
      special_symbol_filter: {
        enabled: config.value.special_symbol_filter?.enabled || false,
        symbols: config.value.special_symbol_filter?.symbols || [],
        match_type: config.value.special_symbol_filter?.match_type || 'any'
      },
      mention_filter: {
        enabled: config.value.mention_filter?.enabled || false,
        strategy: config.value.mention_filter?.strategy || 'full'
      },
      question_filter: {
        enabled: config.value.question_filter?.enabled || false,
        question_markers: config.value.question_filter?.question_markers || [],
        match_type: config.value.question_filter?.match_type || 'any'
      }
    }
    await axios.put('/api/filters/advanced', payload)
    ElMessage.success('配置已保存')
  } catch (e) {
    const errorMsg = e.response?.data?.detail || '保存失败'
    ElMessage.error(errorMsg)
    console.error(e)
  }
}

const updateKeywords = () => {
  saveFilter()
}

const updateRegex = () => {
  saveFilter()
}

const updateAllowedUsers = () => {
  saveFilter()
}

const selectAll = () => {
  config.value.enabled_types = Object.keys(messageTypes.value)
  saveFilter()
}

const selectNone = () => {
  config.value.enabled_types = []
  saveFilter()
}

const resetStats = async () => {
  try {
    await axios.post('/api/filters/stats/reset')
    ElMessage.success('统计已重置')
    fetchStats()
  } catch (e) {
    ElMessage.error('重置失败')
    console.error(e)
  }
}

onMounted(() => {
  fetchMessageTypes()
  fetchFilters()
  
  statsTimer.value = setInterval(fetchStats, 3000)
})

onUnmounted(() => {
  if (statsTimer.value) {
    clearInterval(statsTimer.value)
  }
})
</script>

<style scoped>
.filter-config {
  flex-shrink: 0;
}

.filter-config :deep(.el-card__body) {
  padding: 16px;
}

.filter-tabs :deep(.el-tabs__content) {
  max-height: 350px;
  overflow-y: auto;
  padding-top: 16px;
}

.card-header {
  font-weight: bold;
  font-size: 16px;
}

.filter-actions {
  display: flex;
  gap: 8px;
}
</style>
