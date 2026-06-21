<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  getModelConfigs, createModelConfig, updateModelConfig,
  deleteModelConfig, setDefaultModel, listGroups, apiGet,
  getAppSettings, updateAppSetting,
  getStopwords, updateStopwords,
} from '../api/index.js'
import {
  Plus, Pencil, Trash2, Check, X, Loader2,
  Monitor, Cloud, Wifi, Star, Zap, Globe, Users, Sparkles,
  ChevronDown, ChevronRight, Filter, Shield, Thermometer, Clock, Radio, FileText, Settings2, ClipboardList,
  Fish,
} from 'lucide-vue-next'
import TaskHistory from './TaskHistory.vue'
import AiCallLogs from './AiCallLogs.vue'
import { getPrompts, createPrompt, updatePrompt, deletePrompt, setDefaultPrompt, getDefaultPrompt } from '../api/index.js'

const router = useRouter()

// ---- v1.5.4: Tab 切换 ----
const activeTab = ref('basic')  // 'basic' | 'advanced' | 'tasks' | 'pond' | 'aiLogs'

// v1.5.4: 折叠面板 (key → true=展开)
const collapsedSections = ref(loadCollapsed())
function loadCollapsed() {
  try { return JSON.parse(localStorage.getItem('settingsCollapsed') || '{}') } catch { return {} }
}
function saveCollapsed() {
  localStorage.setItem('settingsCollapsed', JSON.stringify(collapsedSections.value))
}
function toggleSection(key) {
  collapsedSections.value[key] = !collapsedSections.value[key]
  saveCollapsed()
}
function isExpanded(key) {
  return collapsedSections.value[key] !== false  // 默认展开
}

// v1.5.4: 提示词管理
const promptType = ref('daily')
const promptTypeLabel = { daily:'日报', portrait:'画像', weekly:'周报', monthly:'月报', annual:'年报', comprehensive:'全面画像', event_detection:'事件探测' }
const prompts = ref([])
const promptsLoading = ref(false)
const showPromptForm = ref(false)
const editingPromptId = ref(null)
const promptForm = ref({ name:'', system_prompt:'', is_default:false })
async function loadPrompts() {
  promptsLoading.value = true
  try { prompts.value = await getPrompts(promptType.value) } catch { prompts.value = [] }
  finally { promptsLoading.value = false }
}
async function openPromptCreate() {
  editingPromptId.value = null
  let defaultText = ''
  try { const r = await getDefaultPrompt(promptType.value); defaultText = r.system_prompt || '' } catch (e) { console.error('获取默认提示词失败:', e) }
  promptForm.value = { name:'', system_prompt: defaultText, is_default:false }
  showPromptForm.value = true
}
function openPromptEdit(p) {
  editingPromptId.value = p.id
  promptForm.value = { name:p.name, system_prompt:p.system_prompt, is_default:p.is_default }
  showPromptForm.value = true
}
async function savePrompt() {
  if (editingPromptId.value) {
    await updatePrompt(editingPromptId.value, { name:promptForm.value.name, system_prompt:promptForm.value.system_prompt, is_default:promptForm.value.is_default })
  } else {
    await createPrompt(promptForm.value.name, promptType.value, promptForm.value.system_prompt, promptForm.value.is_default)
  }
  showPromptForm.value = false
  await loadPrompts()
}
async function doDeletePrompt(id) { await deletePrompt(id); await loadPrompts() }
async function doSetDefaultPrompt(id) { try { await setDefaultPrompt(id); await loadPrompts() } catch (e) { alert('设置默认失败: ' + e.message) } }
watch(promptType, loadPrompts)
onMounted(() => { loadPrompts() })

// v1.5.4: 轮询间隔 (毫秒→显示用秒方便用户)
const pollDashboardS = ref(10)
const pollPortraitsS = ref(10)
const pollStatsS = ref(30)
async function loadPollSettings() {
  try {
    const settings = await getAppSettings()
    const map = {}
    for (const s of settings) map[s.key] = { value:s.value, value_type:s.value_type }
    if (map.poll_interval_dashboard_ms) pollDashboardS.value = Math.round(parseInt(map.poll_interval_dashboard_ms.value)/1000) || 10
    if (map.poll_interval_portraits_ms) pollPortraitsS.value = Math.round(parseInt(map.poll_interval_portraits_ms.value)/1000) || 10
    if (map.poll_interval_stats_s) pollStatsS.value = parseInt(map.poll_interval_stats_s.value) || 30
  } catch (e) { console.error('加载轮询设置失败:', e) }
}
async function savePollSetting(key, seconds) {
  // v1.5.5: 负值兜底 + 最小值限制
  const clamped = Math.max(key.endsWith('_ms') ? 5 : 10, seconds)
  const ms = key.endsWith('_ms') ? clamped * 1000 : clamped
  await updateAppSetting(key, String(ms))
  // 同步到 localStorage 供 Dashboard/Portraits 直接读取
  localStorage.setItem(key, String(ms))
}

// v1.16.1: 静默鱼塘设置
const pondExpanded = ref(false); const pondEnabled = ref(false)
const pondInterval = ref(30)
async function loadPondSettings() {
  try {
    const settings = await getAppSettings()
    const map = {}
    for (const s of settings) map[s.key] = { value:s.value, value_type:s.value_type }
    if (map.pond_auto_events_enabled) pondEnabled.value = map.pond_auto_events_enabled.value === 'true'
    if (map.pond_event_interval_minutes) pondInterval.value = parseInt(map.pond_event_interval_minutes.value) || 30
  } catch (e) { console.error('加载鱼塘设置失败:', e) }
}
async function togglePondEnabled() {
  pondEnabled.value = !pondEnabled.value
  await updateAppSetting('pond_auto_events_enabled', String(pondEnabled.value))
}
async function savePondSetting(key, val) {
  await updateAppSetting(key, String(val))
}
// v1.16.5: 作弊模式
const cheatMode = ref(false)
async function loadCheatMode() {
  try {
    const settings = await getAppSettings()
    if (!Array.isArray(settings)) return
    const s = settings.find(s => s.key === 'pond_cheat_mode')
    if (s) cheatMode.value = s.value === 'true'
  } catch {}
}
async function toggleCheatMode() {
  cheatMode.value = !cheatMode.value
  await updateAppSetting('pond_cheat_mode', String(cheatMode.value))
}
// v1.17.0: 本地大模型全局开关
const localLlmEnabled = ref(false)
const localLlmHost = ref('http://localhost:11434')
const localLlmFallbackModel = ref('qwen3.5:9b')
async function loadLocalLlmSettings() {
  try {
    const settings = await getAppSettings()
    if (!Array.isArray(settings)) return
    for (const s of settings) {
      if (s.key === 'local_llm_enabled') localLlmEnabled.value = s.value === 'true'
      if (s.key === 'local_llm_host') localLlmHost.value = s.value || 'http://localhost:11434'
      if (s.key === 'local_llm_fallback_model') localLlmFallbackModel.value = s.value || 'qwen3.5:9b'
    }
  } catch {}
}
async function toggleLocalLlm() {
  localLlmEnabled.value = !localLlmEnabled.value
  await updateAppSetting('local_llm_enabled', String(localLlmEnabled.value))
}

// v1.18.7: WeFlow 开关（乐观更新 + 失败回滚）
async function toggleWeFlowEnabled() {
  const prev = weflowSettings.value.weflow_enabled
  weflowSettings.value.weflow_enabled = !prev
  try {
    await updateAppSetting('weflow_enabled', String(weflowSettings.value.weflow_enabled))
    if (weflowSettings.value.weflow_enabled) {
      await loadAppSettings()
    }
  } catch (e) {
    weflowSettings.value.weflow_enabled = prev  // 回滚
    alert('保存失败: ' + (e.message || e))
  }
}

// v1.17.0: Provider 预设
const PROVIDER_PRESETS = [
  { label: 'DeepSeek', endpoint: 'https://api.deepseek.com/v1/chat/completions', models: ['deepseek-v4-flash', 'deepseek-v4-pro'] },
  { label: 'SenseNova（商汤）', endpoint: 'https://token.sensenova.cn/v1/chat/completions', models: ['deepseek-v4-flash', 'sensenova-6.7-flash-lite'] },
  { label: '自定义', endpoint: '', models: [] },
]
const onlineProvider = ref('DeepSeek')
const onlineModelName = ref('deepseek-v4-flash')
const onlineApiKey = ref('')         // 用户新输入的 Key（已有 Key 时为空）
const onlineEndpoint = ref('https://api.deepseek.com/v1/chat/completions')
const onlineConfigId = ref(null)  // 当前编辑的在线模型 ID
const onlineTesting = ref(false)
const onlineTestResult = ref('')
const onlineSavedMsg = ref('')       // v1.18.0: 保存反馈
const hasExistingKey = ref(false)    // v1.18.0: 是否已有真实 Key
async function loadDefaultOnlineModel() {
  try {
    const configs = await getModelConfigs()
    // 同时更新模型列表，避免 loadConfigs 重复请求
    configs.value = configs  // 直接赋值，跳过 loading 状态
    const online = configs.find(c => c.model_type === 'online' && c.is_default)
    if (online) {
      onlineConfigId.value = online.id
      // v1.18.0: 不加载脱敏 Key，避免保存时覆盖真实 Key
      const key = online.api_key || ''
      if (key && key.includes('***')) {
        // 已脱敏 → 说明有真实 Key
        hasExistingKey.value = true
        onlineApiKey.value = ''
      } else if (key.trim()) {
        // 未脱敏的原始 Key
        hasExistingKey.value = false
        onlineApiKey.value = key
      } else {
        hasExistingKey.value = false
        onlineApiKey.value = ''
      }
      onlineEndpoint.value = online.endpoint || 'https://api.deepseek.com/v1/chat/completions'
      onlineModelName.value = online.model_name || 'deepseek-v4-flash'
      const preset = PROVIDER_PRESETS.find(p => p.endpoint === online.endpoint)
      if (preset) onlineProvider.value = preset.label
      else onlineProvider.value = '自定义'
      // 无有效 Key 时显示引导横幅
      if (!hasExistingKey.value && !key.trim()) {
        showFirstRunBanner.value = true
      }
    } else {
      // 无在线模型 → 显示引导
      showFirstRunBanner.value = true
    }
  } catch {}
}
function onProviderChange(label) {
  onlineProvider.value = label
  const preset = PROVIDER_PRESETS.find(p => p.label === label)
  if (preset) {
    onlineEndpoint.value = preset.endpoint
    onlineModelName.value = preset.models[0] || ''
  } else {
    onlineEndpoint.value = ''
    onlineModelName.value = ''
  }
}
async function saveOnlineModel() {
  onlineSavedMsg.value = ''
  const key = onlineApiKey.value.trim()
  // v1.18.0: 脱敏 Key 不发送 — 留空表示不修改已有 Key
  const isMasked = key.includes('***')
  const keyToSave = (isMasked || !key) ? '' : key
  const payload = {
    model_type: 'online',
    endpoint: onlineEndpoint.value,
    api_key: keyToSave,
    model_name: onlineModelName.value,
  }
  try {
    if (onlineConfigId.value) {
      // 更新已有模型：key 为空时不传 key（保留原值）
      if (!keyToSave) delete payload.api_key
      await updateModelConfig(onlineConfigId.value, payload)
    } else {
      if (!keyToSave) {
        onlineSavedMsg.value = '请先填写 API Key'
        setTimeout(() => { onlineSavedMsg.value = '' }, 3000)
        return
      }
      payload.name = onlineProvider.value === '自定义' ? '在线模型' : onlineProvider.value
      payload.is_default = true
      const created = await createModelConfig(payload)
      onlineConfigId.value = created?.id
      await loadConfigs()
    }
    hasExistingKey.value = !!keyToSave || hasExistingKey.value
    showFirstRunBanner.value = false  // 隐藏首次使用引导
    onlineApiKey.value = ''  // 清空输入框
    onlineSavedMsg.value = '已保存'
    setTimeout(() => { onlineSavedMsg.value = '' }, 3000)
  } catch (e) {
    onlineSavedMsg.value = '保存失败: ' + (e.message || '未知错误')
    setTimeout(() => { onlineSavedMsg.value = '' }, 5000)
  }
}
async function testOnlineConnection() {
  if (!onlineConfigId.value) { onlineTestResult.value = '请先保存模型'; return }
  onlineTesting.value = true; onlineTestResult.value = ''
  try {
    const res = await apiGet(`/settings/models/${onlineConfigId.value}/health`)
    onlineTestResult.value = res?.online ? '连接成功' : '连接失败'
  } catch {
    onlineTestResult.value = '连接失败'
  } finally {
    onlineTesting.value = false
    setTimeout(() => { onlineTestResult.value = '' }, 3000)
  }
}

// v1.17.0: 首次运行引导
const showFirstRunBanner = ref(false)

onMounted(() => { loadPollSettings(); loadPondSettings(); loadCreativeWorkshop(); loadCheatMode(); loadLocalLlmSettings(); loadDefaultOnlineModel() })

// ---- v1.16.4: 创意工坊 ----
const bulletinText = ref('')
const customFlavorText = ref('')
const customLastWords = ref('')
const customDailyStatus = ref('')

async function loadCreativeWorkshop() {
  try {
    const settings = await getAppSettings()
    if (!Array.isArray(settings)) return
    for (const s of settings) {
      if (s.key === 'pond_bulletin_board') bulletinText.value = s.value || ''
      if (s.key === 'custom_flavor_texts') {
        try { const arr = JSON.parse(s.value); customFlavorText.value = Array.isArray(arr) ? arr.join('\n') : '' } catch { customFlavorText.value = '' }
      }
      if (s.key === 'custom_last_words') {
        try { const arr = JSON.parse(s.value); customLastWords.value = Array.isArray(arr) ? arr.join('\n') : '' } catch { customLastWords.value = '' }
      }
      if (s.key === 'custom_daily_status') {
        try { const arr = JSON.parse(s.value); customDailyStatus.value = Array.isArray(arr) ? arr.join('\n') : '' } catch { customDailyStatus.value = '' }
      }
    }
  } catch (e) { /* ignore */ }
}

async function saveBulletin() {
  try {
    await updateAppSetting('pond_bulletin_board', bulletinText.value)
  } catch (e) { /* ignore */ }
}

function textareaToJsonArray(text) {
  return text.split('\n').map(l => l.trim()).filter(l => l)
}

async function saveCustom(key, text) {
  const arr = textareaToJsonArray(text)
  await updateAppSetting(key, JSON.stringify(arr))
}

// ---- State ----
const configs = ref([])
const loading = ref(true)
const error = ref('')
const showForm = ref(false)
const editingId = ref(null)
const healthChecking = ref({})
const healthResults = ref({})  // 存储健康检查结果消息
const deleteConfirm = ref(null)
const groups = ref([])
const defaultGroupId = ref(localStorage.getItem('defaultGroupId') || '')
const dailyModelId = ref(localStorage.getItem('dailyModelId') || '')
const portraitModelId = ref(localStorage.getItem('portraitModelId') || '')

// Form state
const form = ref({
  name: '',
  model_type: 'local',
  endpoint: '',
  api_key: '',
  model_name: '',
  is_default: false,
  extra_params: '',
})

// v1.0.2: 高级选项 & 停用词
const advancedOpen = ref(false)
const appSettings = ref({})
const stopwordsText = ref('')
const stopwordsLoading = ref(false)
const stopwordsSaved = ref(false)

// WeFlow 同步设置
const weflowSettings = ref({
  weflow_enabled: false,
  weflow_base_url: 'http://127.0.0.1:5031',
  weflow_access_token: '',
  weflow_sync_interval_hours: 24,
})

// ---- Computed ----
const localConfigs = computed(() => configs.value.filter(c => c.model_type === 'local'))
const onlineConfigs = computed(() => configs.value.filter(c => c.model_type === 'online'))

// ---- Methods ----
async function loadConfigs() {
  loading.value = true
  error.value = ''
  try {
    // v1.17.1: 如果 loadDefaultOnlineModel 已加载，跳过重复请求
    const [cfgs, grps] = await Promise.all([
      configs.value.length ? Promise.resolve(configs.value) : getModelConfigs(),
      listGroups().catch(() => []),
    ])
    if (cfgs !== configs.value) configs.value = cfgs
    groups.value = grps
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function saveDefaultGroup() {
  if (defaultGroupId.value) {
    localStorage.setItem('defaultGroupId', defaultGroupId.value)
  } else {
    localStorage.removeItem('defaultGroupId')
  }
}

function saveDailyModel() {
  if (dailyModelId.value) {
    localStorage.setItem('dailyModelId', dailyModelId.value)
  } else {
    localStorage.removeItem('dailyModelId')
  }
}

function savePortraitModel() {
  if (portraitModelId.value) {
    localStorage.setItem('portraitModelId', portraitModelId.value)
  } else {
    localStorage.removeItem('portraitModelId')
  }
}

function openCreateForm() {
  editingId.value = null
  form.value = {
    name: '', model_type: 'online', endpoint: 'https://api.deepseek.com/v1/chat/completions',
    api_key: '', model_name: 'deepseek-v4-flash', is_default: false, extra_params: '',
  }
  showForm.value = true
}
// v1.17.0: 高级选项中按类型创建模型
function openCreateOnlineForm() {
  editingId.value = null
  form.value = {
    name: '', model_type: 'online', endpoint: 'https://api.deepseek.com/v1/chat/completions',
    api_key: '', model_name: 'deepseek-v4-flash', is_default: false, extra_params: '',
  }
  showForm.value = true
}
function openCreateLocalForm() {
  editingId.value = null
  form.value = {
    name: '', model_type: 'local', endpoint: localLlmHost.value,
    api_key: '', model_name: '', is_default: false, extra_params: '',
  }
  showForm.value = true
}

function openEditForm(cfg) {
  editingId.value = cfg.id
  form.value = {
    name: cfg.name,
    model_type: cfg.model_type,
    endpoint: cfg.endpoint || '',
    api_key: cfg.api_key ? '••••••••' : '',
    model_name: cfg.model_name,
    is_default: cfg.is_default || false,
    extra_params: cfg.extra_params ? JSON.stringify(cfg.extra_params) : '',
  }
  showForm.value = true
}

function closeForm() {
  showForm.value = false
  editingId.value = null
}

async function saveForm() {
  // v0.13.2: 解析 extra_params 确保是对象，避免 JSON.stringify 双重编码
  let extraParams = ''
  if (form.value.extra_params && form.value.extra_params.trim()) {
    try {
      const parsed = JSON.parse(form.value.extra_params)
      extraParams = typeof parsed === 'object' ? JSON.stringify(parsed) : form.value.extra_params
    } catch {
      extraParams = form.value.extra_params  // 解析失败，原样发送
    }
  }
  const payload = {
    name: form.value.name,
    model_type: form.value.model_type,
    endpoint: form.value.endpoint,
    api_key: form.value.api_key === '••••••••' ? '' : form.value.api_key,
    model_name: form.value.model_name,
    is_default: form.value.is_default,
    extra_params: extraParams,
  }

  if (editingId.value) {
    // Update: only send changed fields
    const updates = {}
    for (const [k, v] of Object.entries(payload)) {
      if (k === 'api_key' && v === '') continue
      updates[k] = v
    }
    await updateModelConfig(editingId.value, updates)
  } else {
    await createModelConfig(payload)
  }
  closeForm()
  await loadConfigs()
}

async function doDelete(id) {
  await deleteModelConfig(id)
  deleteConfirm.value = null
  await loadConfigs()
}

async function doSetDefault(id) {
  try {
    await setDefaultModel(id)
    await loadConfigs()
  } catch (e) {
    alert('设置默认失败: ' + e.message)
  }
}

async function doHealthCheck(id) {
  healthChecking.value[id] = true
  healthResults.value[id] = ''
  try {
    const res = await apiGet(`/settings/models/${id}/health`)
    healthResults.value[id] = res.online ? '连通成功' : '连通失败'
  } catch (e) {
    healthResults.value[id] = '检查失败: ' + e.message
  } finally {
    healthChecking.value[id] = false
    // 3s 后清除结果消息
    setTimeout(() => { healthResults.value[id] = '' }, 3000)
  }
}

function maskKey(key) {
  if (!key) return '(未设置)'
  if (key.length <= 8) return '••••'
  return key.slice(0, 4) + '•••' + key.slice(-4)
}

function onTypeChange() {
  if (form.value.model_type === 'local') {
    if (!form.value.endpoint) form.value.endpoint = 'http://localhost:11434'
    form.value.api_key = ''
  } else {
    if (!form.value.endpoint) form.value.endpoint = 'https://api.openai.com'
  }
}

// ---- Lifecycle ----
async function loadAppSettings() {
  try {
    const settings = await getAppSettings()
    const map = {}
    for (const s of settings) {
      map[s.key] = { value: s.value, value_type: s.value_type, description: s.description }
      // 同步 WeFlow 设置
      if (s.key in weflowSettings.value) {
        if (s.value_type === 'bool') {
          weflowSettings.value[s.key] = s.value === 'true'
        } else if (s.value_type === 'int') {
          weflowSettings.value[s.key] = parseInt(s.value) || 0
        } else {
          weflowSettings.value[s.key] = s.value
        }
      }
    }
    appSettings.value = map
  } catch (e) { /* ignore */ }
}

async function saveWeFlowSetting(key, value) {
  try {
    await updateAppSetting(key, String(value))
    // 更新本地状态
    const setting = appSettings.value[key]
    if (setting) {
      if (setting.value_type === 'bool') {
        weflowSettings.value[key] = value === 'true'
        setting.value = String(value)
      } else if (setting.value_type === 'int') {
        weflowSettings.value[key] = parseInt(value) || 0
        setting.value = String(value)
      } else {
        weflowSettings.value[key] = value
        setting.value = value
      }
    }
  } catch (e) {
    alert('保存失败: ' + e.message)
  }
}

async function loadStopwords() {
  stopwordsLoading.value = true
  try {
    const result = await getStopwords()
    stopwordsText.value = result.text || ''
  } catch (e) { /* ignore */ }
  finally { stopwordsLoading.value = false }
}

async function saveAdvancedSetting(key, value) {
  try {
    await updateAppSetting(key, String(value))
    if (appSettings.value[key]) {
      appSettings.value[key].value = String(value)
    }
  } catch (e) {
    alert('保存失败: ' + e.message)
  }
}

async function saveStopwords() {
  try {
    await updateStopwords(stopwordsText.value)
    stopwordsSaved.value = true
    setTimeout(() => { stopwordsSaved.value = false }, 2000)
  } catch (e) {
    alert('保存失败: ' + e.message)
  }
}

onMounted(async () => {
  await loadConfigs()
  loadAppSettings()
  loadStopwords()
})
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6">
    <!-- Tabs -->
    <div class="flex items-center gap-1 bg-slate-100 rounded-lg p-1 w-fit">
      <button @click="activeTab='basic'"
        :class="['flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all',
          activeTab==='basic' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400 hover:text-slate-600']">
        <Settings2 class="w-4 h-4" />基础设置
      </button>
      <button @click="activeTab='advanced'"
        :class="['flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all',
          activeTab==='advanced' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400 hover:text-slate-600']">
        <Zap class="w-4 h-4" />高级选项
      </button>
      <button @click="activeTab='tasks'"
        :class="['flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all',
          activeTab==='tasks' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400 hover:text-slate-600']">
        <ClipboardList class="w-4 h-4" />任务记录
      </button>
      <button @click="activeTab='pond'"
        :class="['flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all',
          activeTab==='pond' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400 hover:text-slate-600']">
        🐟 鱼塘设置
      </button>
      <button @click="activeTab='aiLogs'"
        :class="['flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all',
          activeTab==='aiLogs' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400 hover:text-slate-600']">
        <Zap class="w-4 h-4" />AI日志
      </button>
    </div>

    <!-- ====== AI 调用日志 ====== -->
    <div v-if="activeTab==='aiLogs'">
      <AiCallLogs />
    </div>

    <!-- ====== 群梗百科（已迁移至独立页面 /memes）====== -->

    <!-- ====== 任务记录 ====== -->
    <div v-if="activeTab==='tasks'">
      <TaskHistory />
    </div>

    <!-- ====== 鱼塘设置 ====== -->
    <div v-if="activeTab==='pond'" class="space-y-6">
      <!-- v1.16.1: 鱼塘自动化 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-cyan-400"></div>
          <span class="text-sm font-semibold text-slate-700">⚙️ 鱼塘自动化</span>
        </div>
        <div class="p-5 space-y-4">
          <div class="flex items-center justify-between">
            <div>
              <label class="text-sm font-medium text-slate-700">全局开关</label>
              <p class="text-xs text-slate-400">开启后鱼塘自动运转，不再依赖指令</p>
            </div>
            <button @click="togglePondEnabled"
              :class="['w-11 h-6 rounded-full relative transition', pondEnabled ? 'bg-cyan-500' : 'bg-slate-200']">
              <div :class="['w-5 h-5 rounded-full bg-white shadow absolute top-0.5 transition', pondEnabled ? 'right-0.5' : 'left-0.5']"></div>
            </button>
          </div>
          <div>
            <label class="text-sm font-medium text-slate-700">事件间隔 (分钟)</label>
            <input type="number" :value="pondInterval" @change="pondInterval = Math.max(5, Math.min(180, Number($event.target.value))); savePondSetting('pond_event_interval_minutes', pondInterval)" min="5" max="180" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" />
          </div>
        </div>
      </div>

      <!-- v1.16.5: 允许作弊 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-amber-400"></div>
          <span class="text-sm font-semibold text-slate-700">🎮 允许作弊</span>
        </div>
        <div class="p-5">
          <div class="flex items-center justify-between">
            <div>
              <label class="text-sm font-medium text-slate-700">作弊模式</label>
              <p class="text-xs text-slate-400">开启后禁用成就系统，鱼塘页面显示指令模拟器和调试面板</p>
            </div>
            <button @click="toggleCheatMode"
              :class="['w-11 h-6 rounded-full relative transition', cheatMode ? 'bg-amber-500' : 'bg-slate-200']">
              <div :class="['w-5 h-5 rounded-full bg-white shadow absolute top-0.5 transition', cheatMode ? 'right-0.5' : 'left-0.5']"></div>
            </button>
          </div>
        </div>
      </div>

      <!-- 公告牌 -->
      <div class="card p-5">
        <h3 class="text-sm font-semibold text-slate-600 mb-1">📢 鱼塘公告牌</h3>
        <p class="text-xs text-slate-400 mb-3">显示在鱼塘管理面板顶部，最多 200 字</p>
        <div class="flex gap-2">
          <input v-model="bulletinText" maxlength="200"
            class="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm outline-none focus:border-indigo-400"
            placeholder="写一句塘主宣言..." />
          <button @click="saveBulletin"
            class="px-4 py-2 bg-indigo-500 text-white text-sm rounded-lg hover:bg-indigo-600 transition">
            保存
          </button>
        </div>
        <div class="text-xs text-slate-400 mt-1">{{ bulletinText.length }}/200</div>
      </div>

      <!-- 自定义风味文本 -->
      <div class="card p-5">
        <h3 class="text-sm font-semibold text-slate-600 mb-1">📝 自定义风味文本</h3>
        <p class="text-xs text-slate-400 mb-3">每行一条，与内置风味文本合并使用。最多 5000 字符</p>
        <textarea v-model="customFlavorText" maxlength="5000" rows="6"
          class="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs outline-none focus:border-indigo-400 resize-y"
          placeholder="一只海龟慢悠悠地游过鱼塘上空...&#10;每条风味文本一行..."></textarea>
        <div class="flex items-center gap-2 mt-2">
          <button @click="saveCustom('custom_flavor_texts', customFlavorText)"
            class="px-4 py-1.5 bg-indigo-500 text-white text-xs rounded-lg hover:bg-indigo-600 transition">保存</button>
          <button @click="customFlavorText = ''"
            class="px-3 py-1.5 text-xs text-slate-400 hover:text-red-500 transition">恢复默认</button>
          <span class="text-xs text-slate-400 ml-auto">{{ customFlavorText.length }}/5000</span>
        </div>
      </div>

      <!-- 自定义遗言 -->
      <div class="card p-5">
        <h3 class="text-sm font-semibold text-slate-600 mb-1">🪦 自定义鱼遗言</h3>
        <p class="text-xs text-slate-400 mb-3">每行一条遗言，鱼死亡时随机使用。最多 5000 字符</p>
        <textarea v-model="customLastWords" maxlength="5000" rows="4"
          class="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs outline-none focus:border-indigo-400 resize-y"
          placeholder="告诉塘主...我柜子里还有三颗鱼食没吃...&#10;每条遗言一行..."></textarea>
        <div class="flex items-center gap-2 mt-2">
          <button @click="saveCustom('custom_last_words', customLastWords)"
            class="px-4 py-1.5 bg-indigo-500 text-white text-xs rounded-lg hover:bg-indigo-600 transition">保存</button>
          <button @click="customLastWords = ''"
            class="px-3 py-1.5 text-xs text-slate-400 hover:text-red-500 transition">恢复默认</button>
          <span class="text-xs text-slate-400 ml-auto">{{ customLastWords.length }}/5000</span>
        </div>
      </div>

      <!-- 自定义状态语 -->
      <div class="card p-5">
        <h3 class="text-sm font-semibold text-slate-600 mb-1">💬 自定义状态语</h3>
        <p class="text-xs text-slate-400 mb-3">鱼无特别事件时随机使用。每行一条，最多 5000 字符</p>
        <textarea v-model="customDailyStatus" maxlength="5000" rows="4"
          class="w-full px-3 py-2 border border-slate-200 rounded-lg text-xs outline-none focus:border-indigo-400 resize-y"
          placeholder="又是和平的一天。水很清，心情还行。&#10;每条状态语一行..."></textarea>
        <div class="flex items-center gap-2 mt-2">
          <button @click="saveCustom('custom_daily_status', customDailyStatus)"
            class="px-4 py-1.5 bg-indigo-500 text-white text-xs rounded-lg hover:bg-indigo-600 transition">保存</button>
          <button @click="customDailyStatus = ''"
            class="px-3 py-1.5 text-xs text-slate-400 hover:text-red-500 transition">恢复默认</button>
          <span class="text-xs text-slate-400 ml-auto">{{ customDailyStatus.length }}/5000</span>
        </div>
      </div>
    </div>

    <!-- ====== 基础设置 ====== -->
    <div v-if="activeTab==='basic'" class="space-y-6">
      <!-- v1.17.0: 首次运行引导 -->
      <div v-if="showFirstRunBanner" class="bg-indigo-50 border border-indigo-200 rounded-xl px-4 py-3 flex items-center gap-2">
        <span class="text-indigo-500 text-lg">💡</span>
        <span class="text-sm text-indigo-700">欢迎使用 Chat-Miner！请先配置在线 AI 模型，选择服务商并填入 API Key 即可开始分析群聊。</span>
      </div>

      <!-- 默认群组 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-indigo-400"></div>
          <Users :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">默认群组</span>
        </div>
        <div class="p-5">
          <p class="text-xs text-slate-400 mb-3">打开页面时自动进入该群</p>
          <select :value="defaultGroupId" @change="defaultGroupId = $event.target.value; saveDefaultGroup()"
                  class="w-full max-w-xs px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none">
            <option value="">不自动选择</option>
            <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.display_name || g.name }}</option>
          </select>
        </div>
      </div>

      <!-- 在线模型（默认，直接编辑 is_default=1 的 online 模型） -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-sky-400"></div>
          <Globe :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">在线模型</span>
          <span class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">默认</span>
        </div>
        <div class="p-5 space-y-4">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="text-xs text-slate-500">服务商</label>
              <select :value="onlineProvider" @change="onProviderChange($event.target.value)"
                class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1">
                <option v-for="p in PROVIDER_PRESETS" :key="p.label" :value="p.label">{{ p.label }}</option>
              </select>
            </div>
            <div>
              <label class="text-xs text-slate-500">模型名</label>
              <template v-if="onlineProvider !== '自定义'">
                <select :value="onlineModelName" @change="onlineModelName = $event.target.value"
                  class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1">
                  <option v-for="m in (PROVIDER_PRESETS.find(p=>p.label===onlineProvider)?.models||[])" :key="m" :value="m">{{ m }}</option>
                </select>
              </template>
              <input v-else :value="onlineModelName" @change="onlineModelName = $event.target.value"
                class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" placeholder="输入模型名" />
            </div>
          </div>
          <div>
            <label class="text-xs text-slate-500">端点 URL</label>
            <input :value="onlineEndpoint" @change="onlineEndpoint = $event.target.value"
              class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1 font-mono"
              :disabled="onlineProvider !== '自定义'" />
          </div>
          <div>
            <label class="text-xs text-slate-500">API Key</label>
            <div class="flex gap-2 mt-1">
              <input
                v-model="onlineApiKey"
                type="password"
                class="flex-1 px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none focus:border-indigo-400 font-mono"
                :placeholder="hasExistingKey ? '已有 Key，留空则不修改' : 'sk-...'" />
              <button @click="saveOnlineModel" class="px-4 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition">保存</button>
              <button @click="testOnlineConnection" :disabled="onlineTesting" class="px-4 py-1.5 border border-slate-200 text-slate-600 text-sm rounded-lg hover:bg-slate-50 transition disabled:opacity-50">
                <Loader2 v-if="onlineTesting" :size="14" class="animate-spin inline" />
                <span v-else>测试</span>
              </button>
            </div>
            <span v-if="onlineSavedMsg" :class="['text-xs mt-1', onlineSavedMsg.startsWith('已保存') ? 'text-emerald-600' : 'text-red-500']">{{ onlineSavedMsg }}</span>
            <span v-else-if="onlineTestResult" :class="['text-xs mt-1', onlineTestResult.includes('成功') ? 'text-emerald-600' : 'text-red-500']">{{ onlineTestResult }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ====== 高级选项 ====== -->
    <div v-if="activeTab==='advanced'" class="space-y-6">
      <!-- v1.17.0: 谨慎修改警告 -->
      <div class="bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 flex items-center gap-2">
        <span class="text-amber-500 text-lg">⚠️</span>
        <span class="text-sm text-amber-700">以下为高级配置，请谨慎修改。不正确的设置可能导致分析失败。</span>
      </div>

      <!-- 在线模型配置 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-sky-400"></div>
          <Globe :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">在线模型配置</span>
          <span class="text-xs text-slate-400">{{ onlineConfigs.length }} 个</span>
          <div class="flex-1"></div>
          <button @click="openCreateOnlineForm()" class="inline-flex items-center gap-1 px-3 py-1.5 bg-sky-600 text-white text-xs font-medium rounded-lg hover:bg-sky-700 transition-colors"><Plus :size="14" />添加</button>
        </div>
        <div class="p-5">
          <div v-if="onlineConfigs.length === 0" class="text-center py-8 text-sm text-slate-400">暂无在线模型</div>
          <div v-else class="space-y-2">
            <div v-for="cfg in onlineConfigs" :key="cfg.id" class="flex items-center justify-between p-3 rounded-xl bg-slate-50/80 hover:bg-slate-100/80 transition-colors group">
              <div class="flex items-center gap-3 min-w-0">
                <div class="w-9 h-9 bg-sky-50 rounded-lg flex items-center justify-center flex-shrink-0"><Globe :size="16" class="text-sky-600" /></div>
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-medium text-slate-800 text-sm truncate">{{ cfg.name }}</span>
                    <span v-if="cfg.is_default" class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium flex-shrink-0">默认</span>
                  </div>
                  <div class="text-xs text-slate-400 truncate">{{ cfg.model_name }} · {{ maskKey(cfg.api_key) }}</div>
                </div>
              </div>
              <div class="flex items-center gap-1 flex-shrink-0 ml-2">
                <button @click="doHealthCheck(cfg.id)" :disabled="healthChecking[cfg.id]" class="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="测试连接"><Loader2 v-if="healthChecking[cfg.id]" :size="14" class="animate-spin" /><Wifi v-else :size="14" /></button>
                <span v-if="healthResults[cfg.id]" :class="['text-[11px] flex-shrink-0', healthResults[cfg.id].includes('成功') ? 'text-emerald-600' : 'text-red-500']">{{ healthResults[cfg.id] }}</span>
                <button v-if="!cfg.is_default" @click="doSetDefault(cfg.id)" class="p-1.5 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition-colors" title="设为默认"><Star :size="14" /></button>
                <button @click="openEditForm(cfg)" class="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="编辑"><Pencil :size="14" /></button>
                <button @click="deleteConfirm = cfg.id" class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="删除"><Trash2 :size="14" /></button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 本地模型配置 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-emerald-400"></div>
          <Monitor :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">本地模型配置</span>
          <span class="text-xs text-slate-400">{{ localConfigs.length }} 个</span>
          <div class="flex-1"></div>
          <button @click="openCreateLocalForm()" class="inline-flex items-center gap-1 px-3 py-1.5 bg-emerald-600 text-white text-xs font-medium rounded-lg hover:bg-emerald-700 transition-colors"><Plus :size="14" />添加</button>
        </div>
        <div class="px-5 pb-3 grid grid-cols-2 gap-3">
          <div><label class="text-[11px] text-slate-400">Ollama 服务地址（添加模型时默认使用）</label>
            <input :value="localLlmHost" @change="localLlmHost = $event.target.value; updateAppSetting('local_llm_host', $event.target.value)"
              class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-xs font-mono outline-none mt-0.5" /></div>
          <div><label class="text-[11px] text-slate-400">降级模型名（子任务重试用）</label>
            <input :value="localLlmFallbackModel" @change="localLlmFallbackModel = $event.target.value; updateAppSetting('local_llm_fallback_model', $event.target.value)"
              class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-xs outline-none mt-0.5" /></div>
        </div>
        <div class="p-5 pt-0">
          <div v-if="localConfigs.length === 0" class="text-center py-8 text-sm text-slate-400">暂无本地模型</div>
          <div v-else class="space-y-2">
            <div v-for="cfg in localConfigs" :key="cfg.id" class="flex items-center justify-between p-3 rounded-xl bg-slate-50/80 hover:bg-slate-100/80 transition-colors group">
              <div class="flex items-center gap-3 min-w-0">
                <div class="w-9 h-9 bg-emerald-50 rounded-lg flex items-center justify-center flex-shrink-0"><Monitor :size="16" class="text-emerald-600" /></div>
                <div class="min-w-0">
                  <div class="flex items-center gap-2">
                    <span class="font-medium text-slate-800 text-sm truncate">{{ cfg.name }}</span>
                    <span v-if="cfg.is_default" class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium flex-shrink-0">默认</span>
                  </div>
                  <div class="text-xs text-slate-400 truncate">{{ cfg.model_name }} · {{ cfg.endpoint }}</div>
                </div>
              </div>
              <div class="flex items-center gap-1 flex-shrink-0 ml-2">
                <button @click="doHealthCheck(cfg.id)" :disabled="healthChecking[cfg.id]" class="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="测试连接"><Loader2 v-if="healthChecking[cfg.id]" :size="14" class="animate-spin" /><Wifi v-else :size="14" /></button>
                <span v-if="healthResults[cfg.id]" :class="['text-[11px] flex-shrink-0', healthResults[cfg.id].includes('成功') ? 'text-emerald-600' : 'text-red-500']">{{ healthResults[cfg.id] }}</span>
                <button v-if="!cfg.is_default" @click="doSetDefault(cfg.id)" class="p-1.5 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition-colors" title="设为默认"><Star :size="14" /></button>
                <button @click="openEditForm(cfg)" class="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="编辑"><Pencil :size="14" /></button>
                <button @click="deleteConfirm = cfg.id" class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="删除"><Trash2 :size="14" /></button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- AI 模型分配 & 降级 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div class="flex items-center gap-2">
            <div class="w-1 h-5 rounded-full bg-violet-400"></div>
            <Sparkles :size="16" class="text-slate-500" />
            <span class="text-sm font-semibold text-slate-700">AI 模型分配 & 降级</span>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-slate-400">在线模型不可用时自动降级到本地默认</span>
            <button @click="toggleLocalLlm()"
              :class="['w-11 h-6 rounded-full relative transition flex-shrink-0', localLlmEnabled ? 'bg-emerald-500' : 'bg-slate-300']">
              <div :class="['w-5 h-5 rounded-full bg-white shadow absolute top-0.5 transition', localLlmEnabled ? 'right-0.5' : 'left-0.5']"></div>
            </button>
          </div>
        </div>
        <div class="p-5 space-y-4">
          <div>
            <label class="text-sm font-medium text-slate-700">每日分析</label>
            <p class="text-xs text-slate-400 mb-2">未选择时使用在线默认模型</p>
            <select :value="dailyModelId" @change="dailyModelId = $event.target.value; saveDailyModel()"
              class="w-full max-w-xs px-3 py-2 border border-slate-200 rounded-lg text-sm outline-none">
              <option value="">在线默认</option>
              <optgroup label="在线模型"><option v-for="m in onlineConfigs" :key="'do-'+m.id" :value="m.id">{{ m.name }} ({{ m.model_name }}){{ m.is_default ? ' [默认]' : '' }}</option></optgroup>
              <optgroup label="本地模型"><option v-for="m in localConfigs" :key="'dl-'+m.id" :value="m.id">{{ m.name }} ({{ m.model_name }}){{ m.is_default ? ' [默认]' : '' }}</option></optgroup>
            </select>
          </div>
          <div class="border-t border-slate-100 pt-4">
            <label class="text-sm font-medium text-slate-700">画像分析</label>
            <p class="text-xs text-slate-400 mb-2">未选择时使用在线默认模型</p>
            <select :value="portraitModelId" @change="portraitModelId = $event.target.value; savePortraitModel()"
              class="w-full max-w-xs px-3 py-2 border border-slate-200 rounded-lg text-sm outline-none">
              <option value="">在线默认</option>
              <optgroup label="在线模型"><option v-for="m in onlineConfigs" :key="'po-'+m.id" :value="m.id">{{ m.name }} ({{ m.model_name }}){{ m.is_default ? ' [默认]' : '' }}</option></optgroup>
              <optgroup label="本地模型"><option v-for="m in localConfigs" :key="'pl-'+m.id" :value="m.id">{{ m.name }} ({{ m.model_name }}){{ m.is_default ? ' [默认]' : '' }}</option></optgroup>
            </select>
          </div>
        </div>
      </div>

      <!-- 管道执行参数 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-teal-400"></div>
          <Zap :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">管道执行参数</span>
        </div>
        <div class="p-5 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div><label class="text-xs text-slate-500">重试次数</label>
            <input type="number" :value="appSettings.pipeline_max_retries?.value || 3" @change="saveAdvancedSetting('pipeline_max_retries', Math.max(1, Number($event.target.value)))" min="1" max="20" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">单步超时 (秒)</label>
            <input type="number" :value="appSettings.pipeline_step_timeout?.value || 90" @change="saveAdvancedSetting('pipeline_step_timeout', Math.max(10, Number($event.target.value)))" min="10" max="600" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">熔断阈值 (次)</label>
            <input type="number" :value="appSettings.pipeline_circuit_breaker_threshold?.value || 5" @change="saveAdvancedSetting('pipeline_circuit_breaker_threshold', Math.max(1, Number($event.target.value)))" min="1" max="50" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">熔断冷却 (秒)</label>
            <input type="number" :value="appSettings.pipeline_circuit_breaker_cooldown?.value || 30" @change="saveAdvancedSetting('pipeline_circuit_breaker_cooldown', Math.max(5, Number($event.target.value)))" min="5" max="600" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
        </div>
      </div>

      <!-- 在线模型超时 & 重试 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-indigo-400"></div>
          <Clock :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">在线模型超时 & 重试</span>
        </div>
        <div class="p-5 grid grid-cols-2 sm:grid-cols-3 gap-4">
          <div><label class="text-xs text-slate-500">Ollama 超时 (秒)</label>
            <input type="number" :value="appSettings.ollama_timeout?.value || 120" @change="saveAdvancedSetting('ollama_timeout', $event.target.value)" min="10" max="600" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">DeepSeek 超时 (秒)</label>
            <input type="number" :value="appSettings.deepseek_timeout?.value || 120" @change="saveAdvancedSetting('deepseek_timeout', $event.target.value)" min="10" max="600" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">在线模型重试次数</label>
            <input type="number" :value="appSettings.online_retry_count?.value || 2" @change="saveAdvancedSetting('online_retry_count', $event.target.value)" min="0" max="10" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
        </div>
      </div>

      <!-- 报告生成参数 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-purple-400"></div>
          <Thermometer :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">报告生成参数</span>
        </div>
        <div class="p-5 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div><label class="text-xs text-slate-500">周报 Temp</label><input type="number" :value="appSettings.weekly_temperature?.value || 0.8" @change="saveAdvancedSetting('weekly_temperature', $event.target.value)" min="0" max="2" step="0.1" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">月报 Temp</label><input type="number" :value="appSettings.monthly_temperature?.value || 0.6" @change="saveAdvancedSetting('monthly_temperature', $event.target.value)" min="0" max="2" step="0.1" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">周报 Max Tokens</label><input type="number" :value="appSettings.deepseek_max_tokens_weekly?.value || 4096" @change="saveAdvancedSetting('deepseek_max_tokens_weekly', $event.target.value)" min="256" max="32768" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">月报 Max Tokens</label><input type="number" :value="appSettings.deepseek_max_tokens_monthly?.value || 8192" @change="saveAdvancedSetting('deepseek_max_tokens_monthly', $event.target.value)" min="256" max="32768" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
        </div>
      </div>

      <!-- 周期报告阈值 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-teal-400"></div>
          <FileText :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">周期报告可用性阈值</span>
        </div>
        <div class="p-5 grid grid-cols-3 gap-4">
          <div class="p-3 bg-indigo-50/40 rounded-xl space-y-2"><span class="text-xs font-semibold text-indigo-600">周报</span>
            <div><label class="text-[11px] text-slate-400">最低天数</label><input type="number" :value="appSettings.weekly_min_days?.value || 3" @change="saveAdvancedSetting('weekly_min_days', $event.target.value)" min="1" max="7" class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm outline-none mt-0.5" /></div>
            <div><label class="text-[11px] text-slate-400">最低消息</label><input type="number" :value="appSettings.weekly_min_msgs?.value || 50" @change="saveAdvancedSetting('weekly_min_msgs', $event.target.value)" min="0" max="99999" class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm outline-none mt-0.5" /></div></div>
          <div class="p-3 bg-purple-50/40 rounded-xl space-y-2"><span class="text-xs font-semibold text-purple-600">月报</span>
            <div><label class="text-[11px] text-slate-400">最低天数</label><input type="number" :value="appSettings.monthly_min_days?.value || 5" @change="saveAdvancedSetting('monthly_min_days', $event.target.value)" min="1" max="31" class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm outline-none mt-0.5" /></div>
            <div><label class="text-[11px] text-slate-400">最低消息</label><input type="number" :value="appSettings.monthly_min_msgs?.value || 100" @change="saveAdvancedSetting('monthly_min_msgs', $event.target.value)" min="0" max="99999" class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm outline-none mt-0.5" /></div></div>
          <div class="p-3 bg-amber-50/40 rounded-xl space-y-2"><span class="text-xs font-semibold text-amber-600">年报</span>
            <div><label class="text-[11px] text-slate-400">最低天数</label><input type="number" :value="appSettings.annual_min_days?.value || 30" @change="saveAdvancedSetting('annual_min_days', $event.target.value)" min="1" max="366" class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm outline-none mt-0.5" /></div>
            <div><label class="text-[11px] text-slate-400">最低消息</label><input type="number" :value="appSettings.annual_min_msgs?.value || 300" @change="saveAdvancedSetting('annual_min_msgs', $event.target.value)" min="0" max="99999" class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm outline-none mt-0.5" /></div></div>
        </div>
      </div>

      <!-- GPU 分布式锁 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div class="flex items-center gap-2"><div class="w-1 h-5 rounded-full bg-amber-400"></div><Shield :size="16" class="text-slate-500" /><span class="text-sm font-semibold text-slate-700">GPU 分布式锁</span></div>
          <button @click="saveAdvancedSetting('gpu_lock_enabled', appSettings.gpu_lock_enabled?.value === 'true' ? 'false' : 'true')" :class="['w-10 h-5 rounded-full transition-colors', appSettings.gpu_lock_enabled?.value === 'true' ? 'bg-emerald-500' : 'bg-slate-300']"><div :class="['w-4 h-4 rounded-full bg-white shadow transition-transform', appSettings.gpu_lock_enabled?.value === 'true' ? 'translate-x-5' : 'translate-x-0.5']"></div></button>
        </div>
        <div class="p-5 grid grid-cols-2 gap-4">
          <div><label class="text-xs text-slate-500">服务地址</label><input type="text" :value="appSettings.gpu_lock_url?.value" @change="saveAdvancedSetting('gpu_lock_url', $event.target.value)" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">标识名</label><input type="text" :value="appSettings.gpu_lock_who?.value" @change="saveAdvancedSetting('gpu_lock_who', $event.target.value)" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">重试间隔 (秒)</label><input type="number" :value="appSettings.gpu_lock_retry_interval?.value || 5" @change="saveAdvancedSetting('gpu_lock_retry_interval', $event.target.value)" min="1" max="60" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">最大重试次数</label><input type="number" :value="appSettings.gpu_lock_max_retries?.value || 24" @change="saveAdvancedSetting('gpu_lock_max_retries', $event.target.value)" min="1" max="120" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
        </div>
      </div>

      <!-- 过滤词管理 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100"><div class="w-1 h-5 rounded-full bg-rose-400"></div><Filter :size="16" class="text-slate-500" /><span class="text-sm font-semibold text-slate-700">过滤词管理</span></div>
        <div class="p-5"><p class="text-xs text-slate-400 mb-3">以 <code class="text-[11px] bg-slate-100 px-1 rounded">#</code> 开头的行视为注释。修改后下次分析时自动生效。</p>
          <textarea v-model="stopwordsText" rows="12" class="w-full px-3 py-2.5 border border-slate-200 rounded-lg text-sm font-mono outline-none resize-y" :disabled="stopwordsLoading"></textarea>
          <div class="flex items-center justify-between mt-3"><span v-if="stopwordsSaved" class="text-xs text-emerald-600 flex items-center gap-1"><Check :size="14" />已保存</span><span v-else class="text-xs text-slate-400">修改后即时生效，无需重启</span>
            <button @click="saveStopwords" :disabled="stopwordsLoading" class="px-4 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition">{{ stopwordsLoading ? '加载中...' : '保存' }}</button></div></div></div>

      <!-- 其他设置 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100"><div class="w-1 h-5 rounded-full bg-slate-400"></div><Settings2 :size="16" class="text-slate-500" /><span class="text-sm font-semibold text-slate-700">其他设置</span></div>
        <div class="p-5 grid grid-cols-2 md:grid-cols-4 gap-4">
          <div><label class="text-xs text-slate-500">画像刷新 (天)</label><input type="number" :value="appSettings.portrait_refresh_days?.value || 7" @change="saveAdvancedSetting('portrait_refresh_days', $event.target.value)" min="1" max="365" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">日志保留 (天)</label><input type="number" :value="appSettings.log_retention_days?.value || 90" @change="saveAdvancedSetting('log_retention_days', $event.target.value)" min="1" max="365" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">任务记录上限</label><input type="number" :value="appSettings.log_max_records?.value || 500" @change="saveAdvancedSetting('log_max_records', $event.target.value)" min="10" max="99999" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">AI 日志保留 (天)</label><input type="number" :value="appSettings.ai_log_retention_days?.value || 7" @change="saveAdvancedSetting('ai_log_retention_days', $event.target.value)" min="1" max="365" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
        </div>
      </div>

      <!-- WeFlow 同步 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100"><div class="w-1 h-5 rounded-full bg-sky-400"></div><RefreshCw :size="16" class="text-slate-500" /><span class="text-sm font-semibold text-slate-700">WeFlow 同步</span></div>
        <div class="p-5 space-y-4">
          <div class="flex items-center justify-between">
            <label class="text-sm text-slate-700 font-medium">启用自动同步</label>
            <button @click="toggleWeFlowEnabled"
              :class="['w-10 h-5 rounded-full transition-colors', weflowSettings.weflow_enabled ? 'bg-sky-500' : 'bg-slate-200']">
              <div :class="['w-4 h-4 rounded-full bg-white shadow-sm transition-transform', weflowSettings.weflow_enabled ? 'translate-x-5' : 'translate-x-0.5']" />
            </button>
          </div>
          <template v-if="weflowSettings.weflow_enabled">
            <div><label class="text-xs text-slate-500">WeFlow 地址</label>
              <input :value="weflowSettings.weflow_base_url" @change="saveWeFlowSetting('weflow_base_url', $event.target.value)" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" placeholder="http://127.0.0.1:5031" /></div>
            <div><label class="text-xs text-slate-500">Access Token</label>
              <input :value="weflowSettings.weflow_access_token" @change="saveWeFlowSetting('weflow_access_token', $event.target.value)" type="password" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" placeholder="粘贴 WeFlow Token" /></div>
            <div><label class="text-xs text-slate-500">同步间隔 (小时)</label>
              <input type="number" :value="weflowSettings.weflow_sync_interval_hours" @change="saveWeFlowSetting('weflow_sync_interval_hours', $event.target.value)" min="1" max="168" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          </template>
        </div>
      </div>

      <!-- 提示词风格 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100"><div class="w-1 h-5 rounded-full bg-indigo-400"></div><Sparkles :size="16" class="text-slate-500" /><span class="text-sm font-semibold text-slate-700">提示词风格</span></div>
        <div class="p-5 space-y-4"><p class="text-xs text-slate-400">自定义 AI 的角色和语气</p>
          <div class="flex items-center gap-2"><select v-model="promptType" class="px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none"><option v-for="(label, key) in promptTypeLabel" :key="key" :value="key">{{ label }}</option></select>
            <button @click="openPromptCreate" class="inline-flex items-center gap-1 px-3 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition"><Plus :size="14" />添加</button></div>
          <div v-if="promptsLoading" class="text-center py-4 text-sm text-slate-400"><Loader2 :size="16" class="animate-spin inline mr-1" />加载中</div>
          <div v-else-if="!prompts.length" class="text-center py-4 text-sm text-slate-400">暂无自定义提示词</div>
          <div v-else class="space-y-2"><div v-for="p in prompts" :key="p.id" class="flex items-center justify-between p-3 rounded-xl bg-slate-50/80"><div class="min-w-0 flex-1"><div class="flex items-center gap-2"><span class="text-sm font-medium text-slate-700">{{ p.name }}</span><span v-if="p.is_default" class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">默认</span></div><div class="text-xs text-slate-400 truncate mt-0.5">{{ (p.system_prompt||'').slice(0,80) }}{{ (p.system_prompt||'').length>80?'...':'' }}</div></div>
            <div class="flex items-center gap-1 flex-shrink-0 ml-2"><button v-if="!p.is_default" @click="doSetDefaultPrompt(p.id)" class="p-1.5 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition" title="设为默认"><Star :size="14" /></button><button @click="openPromptEdit(p)" class="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition" title="编辑"><Pencil :size="14" /></button><button v-if="!p.is_default" @click="doDeletePrompt(p.id)" class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition" title="删除"><Trash2 :size="14" /></button></div></div></div></div></div>

      <!-- 轮询间隔 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100"><div class="w-1 h-5 rounded-full bg-slate-400"></div><Clock :size="16" class="text-slate-500" /><span class="text-sm font-semibold text-slate-700">轮询间隔</span></div>
        <div class="p-5 grid grid-cols-3 gap-4">
          <div><label class="text-xs text-slate-500">仪表盘 (秒)</label><input type="number" :value="pollDashboardS" @change="pollDashboardS=Math.max(5,Number($event.target.value));savePollSetting('poll_interval_dashboard_ms',pollDashboardS)" min="5" max="120" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">画像页 (秒)</label><input type="number" :value="pollPortraitsS" @change="pollPortraitsS=Math.max(5,Number($event.target.value));savePollSetting('poll_interval_portraits_ms',pollPortraitsS)" min="5" max="120" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">GUI窗口 (秒)</label><input type="number" :value="pollStatsS" @change="pollStatsS=Math.max(10,Number($event.target.value));savePollSetting('poll_interval_stats_s',pollStatsS)" min="10" max="300" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div></div></div>

      <!-- 事件探测 v1.18.0 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100"><div class="w-1 h-5 rounded-full bg-orange-400"></div><Clock :size="16" class="text-slate-500" /><span class="text-sm font-semibold text-slate-700">事件探测</span></div>
        <div class="p-5 grid grid-cols-3 gap-4">
          <div><label class="text-xs text-slate-500">AI 并发数</label><input type="number" :value="appSettings.event_ai_concurrency?.value || 3" @change="saveAdvancedSetting('event_ai_concurrency', $event.target.value)" min="1" max="10" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">窗口消息数</label><input type="number" :value="appSettings.event_window_size?.value || 200" @change="saveAdvancedSetting('event_window_size', $event.target.value)" min="50" max="500" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">窗口重叠数</label><input type="number" :value="appSettings.event_window_overlap?.value || 20" @change="saveAdvancedSetting('event_window_overlap', $event.target.value)" min="0" max="100" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">活跃群阈值 (条/小时)</label><input type="number" :value="appSettings.event_active_group_threshold?.value || 30" @change="saveAdvancedSetting('event_active_group_threshold', $event.target.value)" min="5" max="100" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">活跃群尖峰阈值 (条/30分)</label><input type="number" :value="appSettings.event_active_peak_absolute?.value || 80" @change="saveAdvancedSetting('event_active_peak_absolute', $event.target.value)" min="20" max="500" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">安静群相对倍数</label><input type="number" :value="appSettings.event_quiet_peak_multiplier?.value || 3" @change="saveAdvancedSetting('event_quiet_peak_multiplier', $event.target.value)" min="1.5" max="10" step="0.5" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" /></div>
        </div>
      </div>
    </div>


    <!-- ====== 弹窗 ====== -->
    <Teleport to="body">
      <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" @click.self="closeForm">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6 space-y-4">
          <h3 class="text-lg font-semibold text-slate-800">{{ editingId ? '编辑模型' : '添加模型' }}</h3>
          <div><label class="block text-xs font-medium text-slate-600 mb-1">名称</label>
            <input v-model="form.name" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" placeholder="如：我的 Qwen 14B" /></div>
          <div><label class="block text-xs font-medium text-slate-600 mb-1">类型</label>
            <span :class="['inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm font-medium',
              form.model_type === 'local' ? 'bg-emerald-50 text-emerald-700' : 'bg-sky-50 text-sky-700']">
              <template v-if="form.model_type === 'local'"><Monitor :size="14" />本地</template>
              <template v-else><Globe :size="14" />在线</template>
            </span>
          </div>
          <div><label class="block text-xs font-medium text-slate-600 mb-1">端点 URL</label>
            <input v-model="form.endpoint" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" :placeholder="form.model_type === 'local' ? 'http://localhost:11434' : 'https://api.openai.com/v1'" /></div>
          <div v-if="form.model_type === 'online'"><label class="block text-xs font-medium text-slate-600 mb-1">API Key</label>
            <input v-model="form.api_key" type="password" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" placeholder="sk-..." /></div>
          <div><label class="block text-xs font-medium text-slate-600 mb-1">模型名</label>
            <input v-model="form.model_name" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" placeholder="如：qwen2.5:14b 或 gpt-4o" /></div>
          <div><label class="block text-xs font-medium text-slate-600 mb-1">额外参数 (JSON, 可选)</label>
            <input v-model="form.extra_params" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm font-mono focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" placeholder='{"temperature": 0.3}' /></div>
          <label class="flex items-center gap-2 cursor-pointer">
            <input v-model="form.is_default" type="checkbox" class="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500" />
            <span class="text-sm text-slate-700">设为默认模型</span>
          </label>
          <div class="flex gap-2 pt-2">
            <button @click="closeForm" class="flex-1 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors">取消</button>
            <button @click="saveForm" :disabled="!form.name || !form.model_name" class="flex-1 py-2 text-sm text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">{{ editingId ? '保存' : '创建' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div v-if="deleteConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" @click.self="deleteConfirm = null">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6 text-center space-y-4">
          <div class="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto"><Trash2 :size="22" class="text-red-600" /></div>
          <p class="text-slate-700">确定要删除此模型配置吗？</p>
          <p class="text-xs text-slate-400">如果删除的是默认模型，将自动提升同类型下一条配置为默认</p>
          <div class="flex gap-2">
            <button @click="deleteConfirm = null" class="flex-1 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors">取消</button>
            <button @click="doDelete(deleteConfirm)" class="flex-1 py-2 text-sm text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors">删除</button>
          </div>
        </div>
      </div>
    </Teleport>

  <!-- v1.5.4: 提示词编辑弹窗 -->
  <Teleport to="body">
    <div v-if="showPromptForm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" @click.self="showPromptForm = false">
      <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6 space-y-4">
        <h3 class="text-lg font-semibold text-slate-800">{{ editingPromptId ? '编辑提示词' : '添加提示词' }}</h3>
        <div><label class="block text-xs font-medium text-slate-600 mb-1">名称</label>
          <input v-model="promptForm.name" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" placeholder="如：吐槽风" /></div>
        <div><label class="block text-xs font-medium text-slate-600 mb-1">System Prompt <span class="text-slate-400 font-normal">（角色/风格描述，不含 JSON 格式指令）</span></label>
          <textarea v-model="promptForm.system_prompt" rows="5" class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none resize-y" placeholder="如：你是一位毒舌的群聊观察者..."></textarea></div>
        <label class="flex items-center gap-2 cursor-pointer">
          <input v-model="promptForm.is_default" type="checkbox" class="w-4 h-4 rounded border-slate-300 text-indigo-600" /><span class="text-sm text-slate-700">设为默认</span></label>
        <div class="flex gap-2 pt-2">
          <button @click="showPromptForm = false" class="flex-1 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors">取消</button>
          <button @click="savePrompt" :disabled="!promptForm.name" class="flex-1 py-2 text-sm text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">{{ editingPromptId ? '保存' : '创建' }}</button>
        </div>
      </div>
    </div>
  </Teleport>

  </div>
</template>
