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
  ChevronDown, ChevronRight, Filter, Shield, Thermometer, Clock, Radio, FileText,
} from 'lucide-vue-next'

const router = useRouter()

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
  await setDefaultModel(id)
  await loadConfigs()
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
  <div class="max-w-4xl mx-auto space-y-8">
    <!-- 页头 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-gray-900">设置</h1>
        <p class="text-sm text-gray-500 mt-1">管理默认群组和 AI 模型配置</p>
      </div>
      <button
        @click="openCreateForm"
        class="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
      >
        <Plus :size="16" />
        添加模型
      </button>
    </div>

    <!-- 默认群选择 -->
    <section>
      <div class="flex items-center gap-2 mb-4">
        <Users :size="20" class="text-gray-600" />
        <h2 class="text-lg font-semibold text-gray-800">默认群组</h2>
      </div>
      <div class="card p-4">
        <p class="text-sm text-gray-500 mb-3">打开页面时自动进入该群，无需手动选择</p>
        <select
          :value="defaultGroupId"
          @change="defaultGroupId = $event.target.value; saveDefaultGroup()"
          class="w-full max-w-xs px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
        >
          <option value="">不自动选择</option>
          <option v-for="g in groups" :key="g.id" :value="g.id">
            {{ g.display_name || g.name }}
          </option>
        </select>
      </div>
    </section>

    <!-- 每日分析默认模型 -->
    <!-- AI 模型分配 v0.12.4 -->
    <section>
      <div class="flex items-center gap-2 mb-4">
        <Sparkles :size="20" class="text-gray-600" />
        <h2 class="text-lg font-semibold text-gray-800">AI 模型分配</h2>
      </div>
      <div class="card p-4 space-y-4">
        <div>
          <label class="text-sm font-medium text-gray-700">每日分析</label>
          <p class="text-xs text-gray-400 mb-2">在线模型单次调用更快，本地模型分步管线更稳定</p>
          <select
            :value="dailyModelId"
            @change="dailyModelId = $event.target.value; saveDailyModel()"
            class="w-full max-w-xs px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
          >
            <option value="">本地默认 (Ollama)</option>
            <optgroup label="本地模型">
              <option v-for="m in localConfigs" :key="'dl-'+m.id" :value="m.id">🖥️ {{ m.name }} ({{ m.model_name }})</option>
            </optgroup>
            <optgroup label="在线模型">
              <option v-for="m in onlineConfigs" :key="'do-'+m.id" :value="m.id">☁️ {{ m.name }} ({{ m.model_name }})</option>
            </optgroup>
          </select>
        </div>
        <div class="border-t border-gray-100 pt-4">
          <label class="text-sm font-medium text-gray-700">画像分析</label>
          <p class="text-xs text-gray-400 mb-2">在线模型一次生成完整画像（含深度洞察），质量更高</p>
          <select
            :value="portraitModelId"
            @change="portraitModelId = $event.target.value; savePortraitModel()"
            class="w-full max-w-xs px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
          >
            <option value="">本地默认 (Ollama)</option>
            <optgroup label="本地模型">
              <option v-for="m in localConfigs" :key="'pl-'+m.id" :value="m.id">🖥️ {{ m.name }} ({{ m.model_name }})</option>
            </optgroup>
            <optgroup label="在线模型">
              <option v-for="m in onlineConfigs" :key="'po-'+m.id" :value="m.id">☁️ {{ m.name }} ({{ m.model_name }})</option>
            </optgroup>
          </select>
        </div>
      </div>
    </section>

    <!-- 加载/错误状态 -->
    <div v-if="loading" class="flex items-center justify-center py-20 text-gray-400">
      <Loader2 :size="28" class="animate-spin mr-2" /> 加载中...
    </div>
    <div v-else-if="error" class="card text-center py-16 text-red-500">
      <X :size="32" class="mx-auto mb-2" />
      <p>{{ error }}</p>
      <button @click="loadConfigs" class="mt-3 text-indigo-600 text-sm hover:underline">重试</button>
    </div>

    <template v-else>
      <!-- 本地模型 -->
      <section>
        <div class="flex items-center gap-2 mb-4">
          <Monitor :size="20" class="text-gray-600" />
          <h2 class="text-lg font-semibold text-gray-800">本地模型 (Ollama)</h2>
          <span class="text-xs text-gray-400">({{ localConfigs.length }})</span>
        </div>
        <div v-if="localConfigs.length === 0" class="card-ghost text-center py-10 text-gray-400 text-sm">
          暂无本地模型配置，点击"添加模型"创建
        </div>
        <div v-else class="grid gap-3">
          <div v-for="cfg in localConfigs" :key="cfg.id"
               class="card flex items-center justify-between p-4 group">
            <div class="flex items-center gap-3 min-w-0">
              <div class="w-9 h-9 bg-indigo-50 rounded-lg flex items-center justify-center flex-shrink-0">
                <Monitor :size="18" class="text-indigo-600" />
              </div>
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-gray-800 text-sm truncate">{{ cfg.name }}</span>
                  <span v-if="cfg.is_default" class="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium flex-shrink-0">
                    <Star :size="10" class="inline mr-0.5" />默认
                  </span>
                </div>
                <div class="text-xs text-gray-400 truncate">{{ cfg.model_name }} · {{ cfg.endpoint }}</div>
              </div>
            </div>
            <div class="flex items-center gap-1 flex-shrink-0 ml-2">
              <button @click="doHealthCheck(cfg.id)" :disabled="healthChecking[cfg.id]"
                      class="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-md transition-colors"
                      title="测试连接">
                <Loader2 v-if="healthChecking[cfg.id]" :size="14" class="animate-spin" />
                <Wifi v-else :size="14" />
              </button>
              <span v-if="healthResults[cfg.id]" :class="['text-[11px] flex-shrink-0', healthResults[cfg.id].includes('成功') ? 'text-green-600' : 'text-red-500']">
                {{ healthResults[cfg.id] }}
              </span>
              <button v-if="!cfg.is_default" @click="doSetDefault(cfg.id)"
                      class="p-1.5 text-gray-400 hover:text-amber-600 hover:bg-amber-50 rounded-md transition-colors"
                      title="设为默认">
                <Star :size="14" />
              </button>
              <button @click="openEditForm(cfg)"
                      class="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors"
                      title="编辑">
                <Pencil :size="14" />
              </button>
              <button @click="deleteConfirm = cfg.id"
                      class="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                      title="删除">
                <Trash2 :size="14" />
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 在线模型 -->
      <section>
        <div class="flex items-center gap-2 mb-4">
          <Cloud :size="20" class="text-gray-600" />
          <h2 class="text-lg font-semibold text-gray-800">在线模型 (API)</h2>
          <span class="text-xs text-gray-400">({{ onlineConfigs.length }})</span>
        </div>
        <div v-if="onlineConfigs.length === 0" class="card-ghost text-center py-10 text-gray-400 text-sm">
          暂无在线模型配置，点击"添加模型"创建
        </div>
        <div v-else class="grid gap-3">
          <div v-for="cfg in onlineConfigs" :key="cfg.id"
               class="card flex items-center justify-between p-4 group">
            <div class="flex items-center gap-3 min-w-0">
              <div class="w-9 h-9 bg-emerald-50 rounded-lg flex items-center justify-center flex-shrink-0">
                <Globe :size="18" class="text-emerald-600" />
              </div>
              <div class="min-w-0">
                <div class="flex items-center gap-2">
                  <span class="font-medium text-gray-800 text-sm truncate">{{ cfg.name }}</span>
                  <span v-if="cfg.is_default" class="text-xs bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded font-medium flex-shrink-0">
                    <Star :size="10" class="inline mr-0.5" />默认
                  </span>
                </div>
                <div class="text-xs text-gray-400 truncate">{{ cfg.model_name }} · {{ maskKey(cfg.api_key) }}</div>
              </div>
            </div>
            <div class="flex items-center gap-1 flex-shrink-0 ml-2">
              <button @click="doHealthCheck(cfg.id)" :disabled="healthChecking[cfg.id]"
                      class="p-1.5 text-gray-400 hover:text-green-600 hover:bg-green-50 rounded-md transition-colors"
                      title="测试连接">
                <Loader2 v-if="healthChecking[cfg.id]" :size="14" class="animate-spin" />
                <Wifi v-else :size="14" />
              </button>
              <span v-if="healthResults[cfg.id]" :class="['text-[11px] flex-shrink-0', healthResults[cfg.id].includes('成功') ? 'text-green-600' : 'text-red-500']">
                {{ healthResults[cfg.id] }}
              </span>
              <button v-if="!cfg.is_default" @click="doSetDefault(cfg.id)"
                      class="p-1.5 text-gray-400 hover:text-amber-600 hover:bg-amber-50 rounded-md transition-colors"
                      title="设为默认">
                <Star :size="14" />
              </button>
              <button @click="openEditForm(cfg)"
                      class="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors"
                      title="编辑">
                <Pencil :size="14" />
              </button>
              <button @click="deleteConfirm = cfg.id"
                      class="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                      title="删除">
                <Trash2 :size="14" />
              </button>
            </div>
          </div>
        </div>
      </section>
    </template>

    <!-- 停用词编辑区 v1.0.2 -->
    <section>
      <div class="flex items-center gap-2 mb-4">
        <Filter :size="20" class="text-gray-600" />
        <h2 class="text-lg font-semibold text-gray-800">过滤词管理</h2>
      </div>
      <div class="card p-4">
        <p class="text-sm text-gray-500 mb-3">
          在此编辑停用词列表。以 <code class="text-xs bg-gray-100 px-1 rounded">#</code> 开头的行视为注释，不会被过滤。
          每行一个词，修改后下次分析时自动生效。
        </p>
        <textarea
          v-model="stopwordsText"
          rows="14"
          class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none resize-y"
          :disabled="stopwordsLoading"
          placeholder="# 每行一个过滤词&#10;# # 开头的行为注释&#10;示例词1&#10;示例词2"
        ></textarea>
        <div class="flex items-center justify-between mt-3">
          <span v-if="stopwordsSaved" class="text-xs text-green-600 flex items-center gap-1">
            <Check :size="14" /> 已保存
          </span>
          <span v-else class="text-xs text-gray-400">修改后即时生效（下次分析时加载），无需重启服务</span>
          <button
            @click="saveStopwords"
            :disabled="stopwordsLoading"
            class="px-4 py-1.5 bg-indigo-600 text-white text-sm rounded-lg hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            {{ stopwordsLoading ? '加载中...' : '保存' }}
          </button>
        </div>
      </div>
    </section>

    <!-- WeFlow 同步设置 -->
    <section>
      <div class="flex items-center gap-2 mb-4">
        <Radio :size="20" class="text-gray-600" />
        <h2 class="text-lg font-semibold text-gray-800">WeFlow 同步</h2>
        <span class="text-xs text-gray-400">(增量拉取新消息)</span>
      </div>
      <div class="card p-4 space-y-4">
        <p class="text-sm text-gray-500">
          配置 WeFlow 本地 API 连接，实现定时自动拉取微信新消息。首次导入请用 ArkMe JSON（首页"导入"按钮）。
        </p>
        <!-- 启用开关 -->
        <div class="flex items-center justify-between">
          <label class="text-sm font-medium text-gray-700">启用自动同步</label>
          <button
            @click="saveWeFlowSetting('weflow_enabled', (!weflowSettings.weflow_enabled).toString())"
            :class="['w-10 h-5 rounded-full transition-colors', weflowSettings.weflow_enabled ? 'bg-emerald-500' : 'bg-gray-300']"
          >
            <div :class="['w-4 h-4 rounded-full bg-white shadow transition-transform', weflowSettings.weflow_enabled ? 'translate-x-5' : 'translate-x-0.5']" />
          </button>
        </div>
        <!-- API 地址 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1.5">API 地址</label>
          <input
            :value="weflowSettings.weflow_base_url"
            @change="saveWeFlowSetting('weflow_base_url', $event.target.value)"
            class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-emerald-200 focus:border-emerald-400 outline-none"
            placeholder="http://127.0.0.1:5031"
          />
        </div>
        <!-- Access Token -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1.5">Access Token</label>
          <input
            :value="weflowSettings.weflow_access_token"
            @change="saveWeFlowSetting('weflow_access_token', $event.target.value)"
            type="password"
            class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono focus:ring-2 focus:ring-emerald-200 focus:border-emerald-400 outline-none"
            placeholder="WeFlow 设置页面中获取"
          />
          <p v-if="weflowSettings.weflow_access_token" class="text-[10px] text-gray-400 mt-1">
            已配置 ({{ weflowSettings.weflow_access_token.slice(-4).padStart(weflowSettings.weflow_access_token.length, '*') }})
          </p>
        </div>
        <!-- 同步间隔 -->
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1.5">自动同步间隔（小时）</label>
          <input
            :value="weflowSettings.weflow_sync_interval_hours"
            @change="saveWeFlowSetting('weflow_sync_interval_hours', $event.target.value)"
            type="number" min="1" max="168"
            class="w-28 px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-emerald-200 focus:border-emerald-400 outline-none"
          />
          <p class="text-[10px] text-gray-400 mt-0.5">只拉取新消息，不触发 AI 分析。默认 24 小时。</p>
        </div>
      </div>
    </section>

    <!-- 高级选项 v1.0.2 -->
    <section>
      <button
        @click="advancedOpen = !advancedOpen"
        class="flex items-center gap-2 w-full text-left mb-4 hover:bg-gray-50 rounded-lg p-1 -m-1 transition-colors"
      >
        <component :is="advancedOpen ? ChevronDown : ChevronRight" :size="20" class="text-gray-500" />
        <h2 class="text-lg font-semibold text-gray-800">高级选项</h2>
        <span class="text-xs text-gray-400">(Ollama 超时、GPU 锁、报告参数等)</span>
      </button>

      <div v-if="advancedOpen" class="space-y-6">
        <!-- Ollama 超时 -->
        <div class="card p-4">
          <div class="flex items-center gap-2 mb-3">
            <Clock :size="16" class="text-gray-500" />
            <h3 class="text-sm font-semibold text-gray-700">Ollama 超时设置</h3>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="text-xs text-gray-500">请求超时 (秒)</label>
              <input
                type="number"
                :value="appSettings.ollama_timeout?.value || 120"
                @change="saveAdvancedSetting('ollama_timeout', $event.target.value)"
                min="10" max="600"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
          </div>
        </div>

        <!-- GPU 分布式锁 -->
        <div class="card p-4">
          <div class="flex items-center gap-2 mb-3">
            <Shield :size="16" class="text-gray-500" />
            <h3 class="text-sm font-semibold text-gray-700">GPU 分布式锁</h3>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
            <div class="flex items-center gap-2">
              <label class="text-xs text-gray-500">启用</label>
              <input
                type="checkbox"
                :checked="appSettings.gpu_lock_enabled?.value === 'true'"
                @change="saveAdvancedSetting('gpu_lock_enabled', $event.target.checked)"
                class="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500">服务地址</label>
              <input
                type="text"
                :value="appSettings.gpu_lock_url?.value"
                @change="saveAdvancedSetting('gpu_lock_url', $event.target.value)"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500">标识名</label>
              <input
                type="text"
                :value="appSettings.gpu_lock_who?.value"
                @change="saveAdvancedSetting('gpu_lock_who', $event.target.value)"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="text-xs text-gray-500">重试间隔 (秒)</label>
              <input
                type="number"
                :value="appSettings.gpu_lock_retry_interval?.value || 5"
                @change="saveAdvancedSetting('gpu_lock_retry_interval', $event.target.value)"
                min="1" max="60"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500">最大重试次数</label>
              <input
                type="number"
                :value="appSettings.gpu_lock_max_retries?.value || 24"
                @change="saveAdvancedSetting('gpu_lock_max_retries', $event.target.value)"
                min="1" max="120"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
          </div>
        </div>

        <!-- 报告参数 -->
        <div class="card p-4">
          <div class="flex items-center gap-2 mb-3">
            <Thermometer :size="16" class="text-gray-500" />
            <h3 class="text-sm font-semibold text-gray-700">报告生成参数</h3>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="text-xs text-gray-500">周报 Temperature (0-2)</label>
              <input
                type="number"
                :value="appSettings.weekly_temperature?.value || 0.8"
                @change="saveAdvancedSetting('weekly_temperature', $event.target.value)"
                min="0" max="2" step="0.1"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500">月报 Temperature (0-2)</label>
              <input
                type="number"
                :value="appSettings.monthly_temperature?.value || 0.6"
                @change="saveAdvancedSetting('monthly_temperature', $event.target.value)"
                min="0" max="2" step="0.1"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500">周报最大 Tokens</label>
              <input
                type="number"
                :value="appSettings.deepseek_max_tokens_weekly?.value || 4096"
                @change="saveAdvancedSetting('deepseek_max_tokens_weekly', $event.target.value)"
                min="256" max="32768"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500">月报最大 Tokens</label>
              <input
                type="number"
                :value="appSettings.deepseek_max_tokens_monthly?.value || 8192"
                @change="saveAdvancedSetting('deepseek_max_tokens_monthly', $event.target.value)"
                min="256" max="32768"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500">DeepSeek 超时 (秒)</label>
              <input
                type="number"
                :value="appSettings.deepseek_timeout?.value || 120"
                @change="saveAdvancedSetting('deepseek_timeout', $event.target.value)"
                min="10" max="600"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500">在线模型重试次数</label>
              <input
                type="number"
                :value="appSettings.online_retry_count?.value || 2"
                @change="saveAdvancedSetting('online_retry_count', $event.target.value)"
                min="0" max="10"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
            <div>
              <label class="text-xs text-gray-500">画像刷新阈值 (天)</label>
              <input
                type="number"
                :value="appSettings.portrait_refresh_days?.value || 7"
                @change="saveAdvancedSetting('portrait_refresh_days', $event.target.value)"
                min="1" max="365"
                class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
              />
            </div>
          </div>
        </div>

        <!-- 周期报告可用性阈值 -->
        <div class="card p-4">
          <div class="flex items-center gap-2 mb-3">
            <FileText :size="16" class="text-gray-500" />
            <h3 class="text-sm font-semibold text-gray-700">周期报告可用性阈值</h3>
            <span class="text-xs text-gray-400">(不满足时前端标记为"数据不足")</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <!-- 周报 -->
            <div class="p-3 bg-indigo-50/50 rounded-xl space-y-2">
              <span class="text-xs font-semibold text-indigo-600">📰 周报</span>
              <div>
                <label class="text-[11px] text-gray-400">最低天数</label>
                <input type="number" :value="appSettings.weekly_min_days?.value || 3"
                  @change="saveAdvancedSetting('weekly_min_days', $event.target.value)"
                  min="1" max="7" class="w-full px-2.5 py-1 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" />
              </div>
              <div>
                <label class="text-[11px] text-gray-400">最低消息数</label>
                <input type="number" :value="appSettings.weekly_min_msgs?.value || 50"
                  @change="saveAdvancedSetting('weekly_min_msgs', $event.target.value)"
                  min="0" max="99999" class="w-full px-2.5 py-1 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" />
              </div>
            </div>
            <!-- 月报 -->
            <div class="p-3 bg-purple-50/50 rounded-xl space-y-2">
              <span class="text-xs font-semibold text-purple-600">📅 月报</span>
              <div>
                <label class="text-[11px] text-gray-400">最低天数</label>
                <input type="number" :value="appSettings.monthly_min_days?.value || 5"
                  @change="saveAdvancedSetting('monthly_min_days', $event.target.value)"
                  min="1" max="31" class="w-full px-2.5 py-1 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" />
              </div>
              <div>
                <label class="text-[11px] text-gray-400">最低消息数</label>
                <input type="number" :value="appSettings.monthly_min_msgs?.value || 100"
                  @change="saveAdvancedSetting('monthly_min_msgs', $event.target.value)"
                  min="0" max="99999" class="w-full px-2.5 py-1 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" />
              </div>
            </div>
            <!-- 年报 -->
            <div class="p-3 bg-amber-50/50 rounded-xl space-y-2">
              <span class="text-xs font-semibold text-amber-600">🏆 年报</span>
              <div>
                <label class="text-[11px] text-gray-400">最低天数</label>
                <input type="number" :value="appSettings.annual_min_days?.value || 30"
                  @change="saveAdvancedSetting('annual_min_days', $event.target.value)"
                  min="1" max="366" class="w-full px-2.5 py-1 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" />
              </div>
              <div>
                <label class="text-[11px] text-gray-400">最低消息数</label>
                <input type="number" :value="appSettings.annual_min_msgs?.value || 300"
                  @change="saveAdvancedSetting('annual_min_msgs', $event.target.value)"
                  min="0" max="99999" class="w-full px-2.5 py-1 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none" />
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 新增/编辑弹窗 -->
    <Teleport to="body">
      <div v-if="showForm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
           @click.self="closeForm">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 p-6 space-y-4">
          <h3 class="text-lg font-semibold text-gray-900">
            {{ editingId ? '编辑模型' : '添加模型' }}
          </h3>

          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">名称</label>
            <input v-model="form.name" class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
                   placeholder="如：我的 Qwen 14B" />
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">类型</label>
            <div class="flex gap-2">
              <button @click="form.model_type = 'local'; onTypeChange()"
                      :class="['flex-1 py-2 text-sm rounded-lg border transition-colors',
                               form.model_type === 'local' ? 'bg-indigo-50 border-indigo-300 text-indigo-700' : 'border-gray-200 text-gray-500 hover:bg-gray-50']">
                <Monitor :size="14" class="inline mr-1" />本地
              </button>
              <button @click="form.model_type = 'online'; onTypeChange()"
                      :class="['flex-1 py-2 text-sm rounded-lg border transition-colors',
                               form.model_type === 'online' ? 'bg-emerald-50 border-emerald-300 text-emerald-700' : 'border-gray-200 text-gray-500 hover:bg-gray-50']">
                <Globe :size="14" class="inline mr-1" />在线
              </button>
            </div>
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">端点 URL</label>
            <input v-model="form.endpoint" class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
                   :placeholder="form.model_type === 'local' ? 'http://localhost:11434' : 'https://api.openai.com/v1'" />
          </div>

          <div v-if="form.model_type === 'online'">
            <label class="block text-xs font-medium text-gray-600 mb-1">API Key</label>
            <input v-model="form.api_key" type="password" class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
                   placeholder="sk-..." />
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">模型名</label>
            <input v-model="form.model_name" class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
                   placeholder="如：qwen2.5:14b 或 gpt-4o" />
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">额外参数 (JSON, 可选)</label>
            <input v-model="form.extra_params" class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm font-mono focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
                   placeholder='{"temperature": 0.3}' />
          </div>

          <label class="flex items-center gap-2 cursor-pointer">
            <input v-model="form.is_default" type="checkbox" class="w-4 h-4 rounded border-gray-300 text-indigo-600 focus:ring-indigo-500" />
            <span class="text-sm text-gray-700">设为默认模型</span>
          </label>

          <div class="flex gap-2 pt-2">
            <button @click="closeForm"
                    class="flex-1 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
              取消
            </button>
            <button @click="saveForm"
                    :disabled="!form.name || !form.model_name"
                    class="flex-1 py-2 text-sm text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
              {{ editingId ? '保存' : '创建' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 删除确认弹窗 -->
    <Teleport to="body">
      <div v-if="deleteConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
           @click.self="deleteConfirm = null">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-sm mx-4 p-6 text-center space-y-4">
          <div class="w-12 h-12 bg-red-100 rounded-full flex items-center justify-center mx-auto">
            <Trash2 :size="22" class="text-red-600" />
          </div>
          <p class="text-gray-700">确定要删除此模型配置吗？</p>
          <p class="text-xs text-gray-400">如果删除的是默认模型，将自动提升同类型下一条配置为默认</p>
          <div class="flex gap-2">
            <button @click="deleteConfirm = null"
                    class="flex-1 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors">
              取消
            </button>
            <button @click="doDelete(deleteConfirm)"
                    class="flex-1 py-2 text-sm text-white bg-red-600 rounded-lg hover:bg-red-700 transition-colors">
              删除
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
