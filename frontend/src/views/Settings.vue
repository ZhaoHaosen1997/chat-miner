<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  getModelConfigs, createModelConfig, updateModelConfig,
  deleteModelConfig, setDefaultModel, listGroups, apiGet
} from '../api/index.js'
import {
  Plus, Pencil, Trash2, Check, X, Loader2,
  Monitor, Cloud, Wifi, Star, Zap, Globe, Users
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
  const payload = {
    name: form.value.name,
    model_type: form.value.model_type,
    endpoint: form.value.endpoint,
    api_key: form.value.api_key === '••••••••' ? '' : form.value.api_key,
    model_name: form.value.model_name,
    is_default: form.value.is_default,
    extra_params: form.value.extra_params,
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
    // 用 apiGet 获取完整响应（含 message），而不是 request 只返回 data
    const res = await apiGet(`/settings/models/${id}/health`)
    healthResults.value[id] = res.message || (res.data?.online ? '连通成功' : '连通失败')
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
    if (!form.value.endpoint) form.value.endpoint = 'https://api.deepseek.com'
  }
}

// ---- Lifecycle ----
onMounted(loadConfigs)
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
    <section>
      <div class="flex items-center gap-2 mb-4">
        <Zap :size="20" class="text-gray-600" />
        <h2 class="text-lg font-semibold text-gray-800">每日分析默认模型</h2>
      </div>
      <div class="card p-4">
        <p class="text-sm text-gray-500 mb-3">
          生成日报时使用的默认模型。在线模型使用单次调用模式（更快），本地模型使用分步管线模式。
        </p>
        <select
          :value="dailyModelId"
          @change="dailyModelId = $event.target.value; saveDailyModel()"
          class="w-full max-w-xs px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
        >
          <option value="">本地默认 (Ollama)</option>
          <optgroup label="本地模型">
            <option v-for="m in localConfigs" :key="'daily-local-'+m.id" :value="m.id">
              🖥️ {{ m.name }} ({{ m.model_name }})
            </option>
          </optgroup>
          <optgroup label="在线模型">
            <option v-for="m in onlineConfigs" :key="'daily-online-'+m.id" :value="m.id">
              ☁️ {{ m.name }} ({{ m.model_name }})
            </option>
          </optgroup>
        </select>
      </div>
    </section>

    <!-- 画像分析默认模型 v0.12.2 -->
    <section>
      <div class="flex items-center gap-2 mb-4">
        <Users :size="20" class="text-gray-600" />
        <h2 class="text-lg font-semibold text-gray-800">画像分析默认模型</h2>
      </div>
      <div class="card p-4">
        <p class="text-sm text-gray-500 mb-3">
          生成群友画像时使用的默认模型。在线模型将一次生成完整画像（含深度分析），更快更深入。
        </p>
        <select
          :value="portraitModelId"
          @change="portraitModelId = $event.target.value; savePortraitModel()"
          class="w-full max-w-xs px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
        >
          <option value="">本地默认 (Ollama)</option>
          <optgroup label="本地模型">
            <option v-for="m in localConfigs" :key="'pt-local-'+m.id" :value="m.id">
              🖥️ {{ m.name }} ({{ m.model_name }})
            </option>
          </optgroup>
          <optgroup label="在线模型">
            <option v-for="m in onlineConfigs" :key="'pt-online-'+m.id" :value="m.id">
              ☁️ {{ m.name }} ({{ m.model_name }})
            </option>
          </optgroup>
        </select>
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
                   :placeholder="form.model_type === 'local' ? 'http://localhost:11434' : 'https://api.deepseek.com'" />
          </div>

          <div v-if="form.model_type === 'online'">
            <label class="block text-xs font-medium text-gray-600 mb-1">API Key</label>
            <input v-model="form.api_key" type="password" class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
                   placeholder="sk-..." />
          </div>

          <div>
            <label class="block text-xs font-medium text-gray-600 mb-1">模型名</label>
            <input v-model="form.model_name" class="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none"
                   placeholder="如：qwen2.5:14b 或 deepseek-v4-flash" />
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
