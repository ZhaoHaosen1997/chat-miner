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
import { getPrompts, createPrompt, updatePrompt, deletePrompt, setDefaultPrompt, getDefaultPrompt } from '../api/index.js'

const router = useRouter()

// ---- v1.5.4: Tab 切换 ----
const activeTab = ref('basic')  // 'basic' | 'advanced' | 'tasks'

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
const promptTypeLabel = { daily:'日报', portrait:'画像', weekly:'周报', monthly:'月报', annual:'年报', comprehensive:'全面画像' }
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
const pondInterval = ref(30); const pondTaxRate = ref(5)
async function loadPondSettings() {
  try {
    const settings = await getAppSettings()
    const map = {}
    for (const s of settings) map[s.key] = { value:s.value, value_type:s.value_type }
    if (map.pond_auto_events_enabled) pondEnabled.value = map.pond_auto_events_enabled.value === 'true'
    if (map.pond_event_interval_minutes) pondInterval.value = parseInt(map.pond_event_interval_minutes.value) || 30
    if (map.pond_treasury_tax_rate) pondTaxRate.value = parseInt(map.pond_treasury_tax_rate.value) || 5
  } catch (e) { console.error('加载鱼塘设置失败:', e) }
}
async function togglePondEnabled() {
  pondEnabled.value = !pondEnabled.value
  await updateAppSetting('pond_auto_events_enabled', String(pondEnabled.value))
}
async function savePondSetting(key, val) {
  await updateAppSetting(key, String(val))
}
onMounted(() => { loadPollSettings(); loadPondSettings() })

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
    const [cfgs, grps] = await Promise.all([
      getModelConfigs(),
      listGroups().catch(() => []),
    ])
    configs.value = cfgs
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
    name: '', model_type: 'local', endpoint: '',
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
    </div>

    <!-- ====== 任务记录 ====== -->
    <div v-if="activeTab==='tasks'">
      <TaskHistory />
    </div>

    <!-- ====== 基础设置 ====== -->
    <div v-if="activeTab==='basic'" class="space-y-6">
      <div class="flex items-center justify-between">
        <p class="text-sm text-slate-500">管理 AI 模型配置和默认群组</p>
        <button @click="openCreateForm" class="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 transition-colors shadow-sm">
          <Plus :size="16" />添加模型
        </button>
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

      <!-- AI 模型分配 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-violet-400"></div>
          <Sparkles :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">AI 模型分配</span>
        </div>
        <div class="p-5 space-y-4">
          <div>
            <label class="text-sm font-medium text-slate-700">每日分析</label>
            <p class="text-xs text-slate-400 mb-2">在线模型单次调用更快，本地模型分步管线更稳定</p>
            <select :value="dailyModelId" @change="dailyModelId = $event.target.value; saveDailyModel()"
                    class="w-full max-w-xs px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none">
              <option value="">本地默认 (Ollama)</option>
              <optgroup label="本地模型">
                <option v-for="m in localConfigs" :key="'dl-'+m.id" :value="m.id">{{ m.name }} ({{ m.model_name }})</option>
              </optgroup>
              <optgroup label="在线模型">
                <option v-for="m in onlineConfigs" :key="'do-'+m.id" :value="m.id">{{ m.name }} ({{ m.model_name }})</option>
              </optgroup>
            </select>
          </div>
          <div class="border-t border-slate-100 pt-4">
            <label class="text-sm font-medium text-slate-700">画像分析</label>
            <p class="text-xs text-slate-400 mb-2">在线模型一次生成完整画像（含深度洞察），质量更高</p>
            <select :value="portraitModelId" @change="portraitModelId = $event.target.value; savePortraitModel()"
                    class="w-full max-w-xs px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none">
              <option value="">本地默认 (Ollama)</option>
              <optgroup label="本地模型">
                <option v-for="m in localConfigs" :key="'pl-'+m.id" :value="m.id">{{ m.name }} ({{ m.model_name }})</option>
              </optgroup>
              <optgroup label="在线模型">
                <option v-for="m in onlineConfigs" :key="'po-'+m.id" :value="m.id">{{ m.name }} ({{ m.model_name }})</option>
              </optgroup>
            </select>
          </div>
        </div>
      </div>

      <!-- 加载/错误 -->
      <div v-if="loading" class="flex items-center justify-center py-16 text-slate-400">
        <Loader2 :size="24" class="animate-spin mr-2" /> 加载中...
      </div>
      <div v-else-if="error" class="bg-white rounded-2xl border border-red-200 p-8 text-center">
        <X :size="32" class="mx-auto mb-2 text-red-400" />
        <p class="text-red-500">{{ error }}</p>
        <button @click="loadConfigs" class="mt-3 text-indigo-600 text-sm hover:underline">重试</button>
      </div>

      <!-- 模型列表 -->
      <template v-else>
        <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
          <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
            <div class="w-1 h-5 rounded-full bg-emerald-400"></div>
            <Monitor :size="16" class="text-slate-500" />
            <span class="text-sm font-semibold text-slate-700">本地模型</span>
            <span class="text-xs text-slate-400">{{ localConfigs.length }} 个</span>
          </div>
          <div class="p-5">
            <div v-if="localConfigs.length === 0" class="text-center py-8 text-sm text-slate-400">暂无本地模型</div>
            <div v-else class="space-y-2">
              <div v-for="cfg in localConfigs" :key="cfg.id" class="flex items-center justify-between p-3 rounded-xl bg-slate-50/80 hover:bg-slate-100/80 transition-colors group">
                <div class="flex items-center gap-3 min-w-0">
                  <div class="w-9 h-9 bg-emerald-50 rounded-lg flex items-center justify-center flex-shrink-0">
                    <Monitor :size="16" class="text-emerald-600" />
                  </div>
                  <div class="min-w-0">
                    <div class="flex items-center gap-2">
                      <span class="font-medium text-slate-800 text-sm truncate">{{ cfg.name }}</span>
                      <span v-if="cfg.is_default" class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium flex-shrink-0">默认</span>
                    </div>
                    <div class="text-xs text-slate-400 truncate">{{ cfg.model_name }} · {{ cfg.endpoint }}</div>
                  </div>
                </div>
                <div class="flex items-center gap-1 flex-shrink-0 ml-2">
                  <button @click="doHealthCheck(cfg.id)" :disabled="healthChecking[cfg.id]" class="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="测试连接">
                    <Loader2 v-if="healthChecking[cfg.id]" :size="14" class="animate-spin" />
                    <Wifi v-else :size="14" />
                  </button>
                  <span v-if="healthResults[cfg.id]" :class="['text-[11px] flex-shrink-0', healthResults[cfg.id].includes('成功') ? 'text-emerald-600' : 'text-red-500']">{{ healthResults[cfg.id] }}</span>
                  <button v-if="!cfg.is_default" @click="doSetDefault(cfg.id)" class="p-1.5 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition-colors" title="设为默认"><Star :size="14" /></button>
                  <button @click="openEditForm(cfg)" class="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="编辑"><Pencil :size="14" /></button>
                  <button @click="deleteConfirm = cfg.id" class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="删除"><Trash2 :size="14" /></button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
          <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
            <div class="w-1 h-5 rounded-full bg-sky-400"></div>
            <Cloud :size="16" class="text-slate-500" />
            <span class="text-sm font-semibold text-slate-700">在线模型</span>
            <span class="text-xs text-slate-400">{{ onlineConfigs.length }} 个</span>
          </div>
          <div class="p-5">
            <div v-if="onlineConfigs.length === 0" class="text-center py-8 text-sm text-slate-400">暂无在线模型</div>
            <div v-else class="space-y-2">
              <div v-for="cfg in onlineConfigs" :key="cfg.id" class="flex items-center justify-between p-3 rounded-xl bg-slate-50/80 hover:bg-slate-100/80 transition-colors group">
                <div class="flex items-center gap-3 min-w-0">
                  <div class="w-9 h-9 bg-sky-50 rounded-lg flex items-center justify-center flex-shrink-0">
                    <Globe :size="16" class="text-sky-600" />
                  </div>
                  <div class="min-w-0">
                    <div class="flex items-center gap-2">
                      <span class="font-medium text-slate-800 text-sm truncate">{{ cfg.name }}</span>
                      <span v-if="cfg.is_default" class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium flex-shrink-0">默认</span>
                    </div>
                    <div class="text-xs text-slate-400 truncate">{{ cfg.model_name }} · {{ maskKey(cfg.api_key) }}</div>
                  </div>
                </div>
                <div class="flex items-center gap-1 flex-shrink-0 ml-2">
                  <button @click="doHealthCheck(cfg.id)" :disabled="healthChecking[cfg.id]" class="p-1.5 text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors" title="测试连接">
                    <Loader2 v-if="healthChecking[cfg.id]" :size="14" class="animate-spin" /><Wifi v-else :size="14" />
                  </button>
                  <span v-if="healthResults[cfg.id]" :class="['text-[11px] flex-shrink-0', healthResults[cfg.id].includes('成功') ? 'text-emerald-600' : 'text-red-500']">{{ healthResults[cfg.id] }}</span>
                  <button v-if="!cfg.is_default" @click="doSetDefault(cfg.id)" class="p-1.5 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition-colors" title="设为默认"><Star :size="14" /></button>
                  <button @click="openEditForm(cfg)" class="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="编辑"><Pencil :size="14" /></button>
                  <button @click="deleteConfirm = cfg.id" class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="删除"><Trash2 :size="14" /></button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- ====== 高级选项 ====== -->
    <div v-if="activeTab==='advanced'" class="space-y-6">
      <!-- 停用词 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-rose-400"></div>
          <Filter :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">过滤词管理</span>
        </div>
        <div class="p-5">
          <p class="text-xs text-slate-400 mb-3">以 <code class="text-[11px] bg-slate-100 px-1 rounded">#</code> 开头的行视为注释。修改后下次分析时自动生效。</p>
          <textarea v-model="stopwordsText" rows="12"
                    class="w-full px-3 py-2.5 border border-slate-200 rounded-lg text-sm font-mono focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none resize-y"
                    :disabled="stopwordsLoading"></textarea>
          <div class="flex items-center justify-between mt-3">
            <span v-if="stopwordsSaved" class="text-xs text-emerald-600 flex items-center gap-1"><Check :size="14" /> 已保存</span>
            <span v-else class="text-xs text-slate-400">修改后即时生效，无需重启</span>
            <button @click="saveStopwords" :disabled="stopwordsLoading" class="px-4 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors">{{ stopwordsLoading ? '加载中...' : '保存' }}</button>
          </div>
        </div>
      </div>

      <!-- 超时 & 重试 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-indigo-400"></div>
          <Clock :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">模型超时 & 重试</span>
        </div>
        <div class="p-5 grid grid-cols-2 sm:grid-cols-3 gap-4">
          <div><label class="text-xs text-slate-500">Ollama 超时 (秒)</label>
            <input type="number" :value="appSettings.ollama_timeout?.value || 120" @change="saveAdvancedSetting('ollama_timeout', $event.target.value)" min="10" max="600"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">DeepSeek 超时 (秒)</label>
            <input type="number" :value="appSettings.deepseek_timeout?.value || 120" @change="saveAdvancedSetting('deepseek_timeout', $event.target.value)" min="10" max="600"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">在线模型重试次数</label>
            <input type="number" :value="appSettings.online_retry_count?.value || 2" @change="saveAdvancedSetting('online_retry_count', $event.target.value)" min="0" max="10"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
        </div>
      </div>

      <!-- GPU 锁 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div class="flex items-center gap-2">
            <div class="w-1 h-5 rounded-full bg-amber-400"></div>
            <Shield :size="16" class="text-slate-500" />
            <span class="text-sm font-semibold text-slate-700">GPU 分布式锁</span>
          </div>
          <button @click="saveAdvancedSetting('gpu_lock_enabled', appSettings.gpu_lock_enabled?.value === 'true' ? 'false' : 'true')"
                  :class="['w-10 h-5 rounded-full transition-colors', appSettings.gpu_lock_enabled?.value === 'true' ? 'bg-emerald-500' : 'bg-slate-300']">
            <div :class="['w-4 h-4 rounded-full bg-white shadow transition-transform', appSettings.gpu_lock_enabled?.value === 'true' ? 'translate-x-5' : 'translate-x-0.5']"></div>
          </button>
        </div>
        <div class="p-5 grid grid-cols-2 gap-4">
          <div><label class="text-xs text-slate-500">服务地址</label>
            <input type="text" :value="appSettings.gpu_lock_url?.value" @change="saveAdvancedSetting('gpu_lock_url', $event.target.value)"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">标识名</label>
            <input type="text" :value="appSettings.gpu_lock_who?.value" @change="saveAdvancedSetting('gpu_lock_who', $event.target.value)"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">重试间隔 (秒)</label>
            <input type="number" :value="appSettings.gpu_lock_retry_interval?.value || 5" @change="saveAdvancedSetting('gpu_lock_retry_interval', $event.target.value)" min="1" max="60"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">最大重试次数</label>
            <input type="number" :value="appSettings.gpu_lock_max_retries?.value || 24" @change="saveAdvancedSetting('gpu_lock_max_retries', $event.target.value)" min="1" max="120"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
        </div>
      </div>

      <!-- 报告参数 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-purple-400"></div>
          <Thermometer :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">报告生成参数</span>
        </div>
        <div class="p-5 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div><label class="text-xs text-slate-500">周报 Temp</label>
            <input type="number" :value="appSettings.weekly_temperature?.value || 0.8" @change="saveAdvancedSetting('weekly_temperature', $event.target.value)" min="0" max="2" step="0.1"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">月报 Temp</label>
            <input type="number" :value="appSettings.monthly_temperature?.value || 0.6" @change="saveAdvancedSetting('monthly_temperature', $event.target.value)" min="0" max="2" step="0.1"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">周报 Max Tokens</label>
            <input type="number" :value="appSettings.deepseek_max_tokens_weekly?.value || 4096" @change="saveAdvancedSetting('deepseek_max_tokens_weekly', $event.target.value)" min="256" max="32768"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">月报 Max Tokens</label>
            <input type="number" :value="appSettings.deepseek_max_tokens_monthly?.value || 8192" @change="saveAdvancedSetting('deepseek_max_tokens_monthly', $event.target.value)" min="256" max="32768"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
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
          <div class="p-3 bg-indigo-50/40 rounded-xl space-y-2">
            <span class="text-xs font-semibold text-indigo-600">周报</span>
            <div><label class="text-[11px] text-slate-400">最低天数</label>
              <input type="number" :value="appSettings.weekly_min_days?.value || 3" @change="saveAdvancedSetting('weekly_min_days', $event.target.value)" min="1" max="7"
                     class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-0.5" /></div>
            <div><label class="text-[11px] text-slate-400">最低消息</label>
              <input type="number" :value="appSettings.weekly_min_msgs?.value || 50" @change="saveAdvancedSetting('weekly_min_msgs', $event.target.value)" min="0" max="99999"
                     class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-0.5" /></div>
          </div>
          <div class="p-3 bg-purple-50/40 rounded-xl space-y-2">
            <span class="text-xs font-semibold text-purple-600">月报</span>
            <div><label class="text-[11px] text-slate-400">最低天数</label>
              <input type="number" :value="appSettings.monthly_min_days?.value || 5" @change="saveAdvancedSetting('monthly_min_days', $event.target.value)" min="1" max="31"
                     class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-0.5" /></div>
            <div><label class="text-[11px] text-slate-400">最低消息</label>
              <input type="number" :value="appSettings.monthly_min_msgs?.value || 100" @change="saveAdvancedSetting('monthly_min_msgs', $event.target.value)" min="0" max="99999"
                     class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-0.5" /></div>
          </div>
          <div class="p-3 bg-amber-50/40 rounded-xl space-y-2">
            <span class="text-xs font-semibold text-amber-600">年报</span>
            <div><label class="text-[11px] text-slate-400">最低天数</label>
              <input type="number" :value="appSettings.annual_min_days?.value || 30" @change="saveAdvancedSetting('annual_min_days', $event.target.value)" min="1" max="366"
                     class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-0.5" /></div>
            <div><label class="text-[11px] text-slate-400">最低消息</label>
              <input type="number" :value="appSettings.annual_min_msgs?.value || 300" @change="saveAdvancedSetting('annual_min_msgs', $event.target.value)" min="0" max="99999"
                     class="w-full px-2.5 py-1 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-0.5" /></div>
          </div>
        </div>
      </div>

      <!-- 画像刷新 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-pink-400"></div>
          <RefreshCw :size="16" class="text-slate-500" />
          <span class="text-sm font-semibold text-slate-700">画像刷新</span>
        </div>
        <div class="p-5">
          <div class="flex items-center gap-4">
            <label class="text-xs text-slate-500">刷新阈值 (天)</label>
            <input type="number" :value="appSettings.portrait_refresh_days?.value || 7" @change="saveAdvancedSetting('portrait_refresh_days', $event.target.value)" min="1" max="365"
                   class="w-28 px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" />
            <span class="text-xs text-slate-400">累积新消息超过该天数后触发刷新</span>
          </div>
        </div>
      </div>

      <!-- WeFlow 同步 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div class="flex items-center gap-2">
            <div class="w-1 h-5 rounded-full bg-emerald-400"></div>
            <Radio :size="16" class="text-slate-500" />
            <span class="text-sm font-semibold text-slate-700">WeFlow 同步</span>
          </div>
          <button @click="saveWeFlowSetting('weflow_enabled', (!weflowSettings.weflow_enabled).toString())"
                  :class="['w-10 h-5 rounded-full transition-colors', weflowSettings.weflow_enabled ? 'bg-emerald-500' : 'bg-slate-300']">
            <div :class="['w-4 h-4 rounded-full bg-white shadow transition-transform', weflowSettings.weflow_enabled ? 'translate-x-5' : 'translate-x-0.5']"></div>
          </button>
        </div>
        <div class="p-5 space-y-4">
          <p class="text-xs text-slate-400">配置 WeFlow 本地 API 连接，实现定时自动拉取微信新消息</p>
          <div><label class="text-xs text-slate-500">API 地址</label>
            <input :value="weflowSettings.weflow_base_url" @change="saveWeFlowSetting('weflow_base_url', $event.target.value)"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">Access Token</label>
            <input :value="weflowSettings.weflow_access_token" type="password" @change="saveWeFlowSetting('weflow_access_token', $event.target.value)"
                   class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm font-mono focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">同步间隔 (小时)</label>
            <input :value="weflowSettings.weflow_sync_interval_hours" type="number" min="1" max="168" @change="saveWeFlowSetting('weflow_sync_interval_hours', $event.target.value)"
                   class="w-28 px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
        </div>
      </div>

      <!-- v1.5.4: 提示词风格 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100">
          <div class="w-1 h-5 rounded-full bg-indigo-400"></div><Sparkles :size="16" class="text-slate-500" /><span class="text-sm font-semibold text-slate-700">提示词风格</span></div>
        <div class="p-5 space-y-4">
          <p class="text-xs text-slate-400">自定义 AI 的角色和语气，仅修改 system prompt（不影响 JSON 输出格式）</p>
          <div class="flex items-center gap-2">
            <select v-model="promptType" class="px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"><option v-for="(label, key) in promptTypeLabel" :key="key" :value="key">{{ label }}</option></select>
            <button @click="openPromptCreate" class="inline-flex items-center gap-1 px-3 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 transition-colors"><Plus :size="14" />添加</button></div>
          <div v-if="promptsLoading" class="text-center py-4 text-sm text-slate-400"><Loader2 :size="16" class="animate-spin inline mr-1" />加载中</div>
          <div v-else-if="!prompts.length" class="text-center py-4 text-sm text-slate-400">暂无自定义提示词，使用默认风格</div>
          <div v-else class="space-y-2">
            <div v-for="p in prompts" :key="p.id" class="flex items-center justify-between p-3 rounded-xl bg-slate-50/80 hover:bg-slate-100/80 transition-colors">
              <div class="min-w-0 flex-1"><div class="flex items-center gap-2"><span class="text-sm font-medium text-slate-700">{{ p.name }}</span><span v-if="p.is_default" class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">默认</span></div><div class="text-xs text-slate-400 truncate mt-0.5">{{ p.system_prompt?.slice(0, 80) }}{{ (p.system_prompt || '').length > 80 ? '...' : '' }}</div></div>
              <div class="flex items-center gap-1 flex-shrink-0 ml-2">
                <button v-if="!p.is_default" @click="doSetDefaultPrompt(p.id)" class="p-1.5 text-slate-400 hover:text-amber-600 hover:bg-amber-50 rounded-lg transition-colors" title="设为默认"><Star :size="14" /></button>
                <button @click="openPromptEdit(p)" class="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors" title="编辑"><Pencil :size="14" /></button>
                <button v-if="!p.is_default" @click="doDeletePrompt(p.id)" class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors" title="删除"><Trash2 :size="14" /></button></div></div></div></div></div>

      <!-- v1.5.4: 轮询间隔 -->
      <div class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100"><div class="w-1 h-5 rounded-full bg-slate-400"></div><Clock :size="16" class="text-slate-500" /><span class="text-sm font-semibold text-slate-700">轮询间隔</span></div>
        <div class="p-5 grid grid-cols-3 gap-4">
          <div><label class="text-xs text-slate-500">仪表盘 (秒)</label><input type="number" :value="pollDashboardS" @change="pollDashboardS = Math.max(5, Number($event.target.value)); savePollSetting('poll_interval_dashboard_ms', pollDashboardS)" min="5" max="120" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">画像页 (秒)</label><input type="number" :value="pollPortraitsS" @change="pollPortraitsS = Math.max(5, Number($event.target.value)); savePollSetting('poll_interval_portraits_ms', pollPortraitsS)" min="5" max="120" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div>
          <div><label class="text-xs text-slate-500">GUI窗口 (秒)</label><input type="number" :value="pollStatsS" @change="pollStatsS = Math.max(10, Number($event.target.value)); savePollSetting('poll_interval_stats_s', pollStatsS)" min="10" max="300" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none mt-1" /></div></div></div>
    </div>

    <!-- v1.16.1: 静默鱼塘 -->
    <div class="card mb-4 overflow-hidden">
      <div class="flex items-center gap-2 px-5 py-4 border-b border-slate-100 cursor-pointer"
        @click="pondExpanded = !pondExpanded">
        <div class="w-1 h-5 rounded-full bg-cyan-400"></div>
        <Fish :size="16" class="text-cyan-500" />
        <span class="text-sm font-semibold text-slate-700">静默鱼塘</span>
        <span class="text-xs text-slate-400 ml-auto">{{ pondExpanded ? '收起' : '展开' }}</span>
      </div>
      <div v-if="pondExpanded" class="p-5 space-y-4">
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
          <label class="text-xs text-slate-500">事件间隔 (分钟)</label>
          <input type="number" :value="pondInterval" @change="pondInterval = Math.max(5, Math.min(180, Number($event.target.value))); savePondSetting('pond_event_interval_minutes', pondInterval)" min="5" max="180" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" />
          <p class="text-[10px] text-slate-400 mt-1">建议 15-60 分钟。间隔越短事件越密集</p>
        </div>
        <div>
          <label class="text-xs text-slate-500">金库税率 (%)</label>
          <input type="number" :value="pondTaxRate" @change="pondTaxRate = Math.max(1, Math.min(20, Number($event.target.value))); savePondSetting('pond_treasury_tax_rate', pondTaxRate)" min="1" max="20" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm outline-none mt-1" />
          <p class="text-[10px] text-slate-400 mt-1">每次事件触发时，全群鳞币总和的百分比进入金库</p>
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
            <div class="flex gap-2">
              <button @click="form.model_type = 'local'; onTypeChange()" :class="['flex-1 py-2 text-sm rounded-lg border transition-colors', form.model_type === 'local' ? 'bg-emerald-50 border-emerald-300 text-emerald-700' : 'border-slate-200 text-slate-500 hover:bg-slate-50']"><Monitor :size="14" class="inline mr-1" />本地</button>
              <button @click="form.model_type = 'online'; onTypeChange()" :class="['flex-1 py-2 text-sm rounded-lg border transition-colors', form.model_type === 'online' ? 'bg-sky-50 border-sky-300 text-sky-700' : 'border-slate-200 text-slate-500 hover:bg-slate-50']"><Globe :size="14" class="inline mr-1" />在线</button>
            </div>
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
