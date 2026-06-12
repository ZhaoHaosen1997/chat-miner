<script setup>
import { ref, watch, onUnmounted } from 'vue'
import { Loader2, CheckCircle2, XCircle, X, Clock, AlertTriangle } from 'lucide-vue-next'

const props = defineProps({
  taskId: { type: String, required: true },
})
const emit = defineEmits(['done', 'close'])

const status = ref('pending')
const step = ref('')
const progress = ref({ current: 0, total: 0 })
const steps = ref([])
const error = ref(null)
const duration = ref(0)
const modelUsed = ref('')
const fallback = ref(false)
const expanded = ref(true)
let eventSource = null

function connect() {
  const url = `/api/tasks/${props.taskId}/stream`
  eventSource = new EventSource(url)

  eventSource.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data)
      status.value = data.status
      step.value = data.step
      if (data.progress) progress.value = data.progress
      if (data.steps) steps.value = data.steps
      if (data.error) error.value = data.error
      if (data.model_used) modelUsed.value = data.model_used
      if (data.fallback) fallback.value = true
      duration.value = data.duration_ms || 0

      if (data.status === 'done' || data.status === 'failed' || data.status === 'cancelled') {
        emit('done', data)
        eventSource?.close()
      }
    } catch (e) { /* ignore parse errors */ }
  }

  eventSource.onerror = () => {
    // SSE 会定期重连，但任务完成后我们主动关闭
    if (status.value === 'done' || status.value === 'failed') {
      eventSource?.close()
    }
  }
}

function closePanel() {
  eventSource?.close()
  emit('close')
}

function cancelTask() {
  fetch(`/api/tasks/${props.taskId}`, { method: 'DELETE' })
  eventSource?.close()
}

const stepLabels = {
  'pending':    { text: '准备中', icon: Clock },
  'waiting_gpu':{ text: '等待 GPU', icon: Clock },
  'inference':  { text: 'AI 推理中', icon: Loader2 },
  'parsing':    { text: '解析结果', icon: Loader2 },
  'done':       { text: '完成', icon: CheckCircle2 },
}

const errorLabels = {
  'ollama_down': 'Ollama 服务离线',
  'gpu_busy': 'GPU 被占用超时',
  'json_parse': 'AI 返回解析失败',
  'timeout': '请求超时',
  'too_few': '文本消息过少',
  'unknown': '未知错误',
}

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

watch(() => props.taskId, (id) => {
  if (id) connect()
}, { immediate: true })

onUnmounted(() => eventSource?.close())
</script>

<template>
  <div class="fixed bottom-4 right-4 z-50">
    <!-- v0.13.1: 折叠时显示小按钮可重新展开 -->
    <button v-if="!expanded" @click="expanded = true"
            :class="[
              'w-10 h-10 rounded-full shadow-lg border flex items-center justify-center transition-colors',
              status === 'done' ? 'bg-emerald-50 border-emerald-200 text-emerald-600' :
              status === 'failed' ? 'bg-red-50 border-red-200 text-red-600' :
              'bg-indigo-50 border-indigo-200 text-indigo-600',
            ]"
            title="展开进度面板">
      <Loader2 v-if="status !== 'done' && status !== 'failed'" class="w-4 h-4 animate-spin" />
      <CheckCircle2 v-else-if="status === 'done'" class="w-4 h-4" />
      <XCircle v-else class="w-4 h-4" />
    </button>
    <div v-if="expanded" class="w-80 bg-white rounded-xl shadow-2xl border border-slate-200 overflow-hidden transition-all">
    <!-- Header -->
    <div :class="[
      'flex items-center justify-between px-4 py-2.5',
      status === 'done' ? 'bg-emerald-50' :
      status === 'failed' ? 'bg-red-50' :
      'bg-indigo-50',
    ]">
      <div class="flex items-center gap-2 text-sm font-medium"
           :class="status === 'done' ? 'text-emerald-700' : status === 'failed' ? 'text-red-700' : 'text-indigo-700'">
        <CheckCircle2 v-if="status === 'done'" class="w-4 h-4" />
        <XCircle v-else-if="status === 'failed'" class="w-4 h-4" />
        <Loader2 v-else class="w-4 h-4 animate-spin" />
        {{ status === 'done' ? '分析完成' : status === 'failed' ? '分析失败' : step }}
      </div>
      <div class="flex items-center gap-1">
        <span v-if="duration > 0" class="text-xs text-slate-400">{{ formatDuration(duration) }}</span>
        <button v-if="status !== 'done' && status !== 'failed'" @click="cancelTask"
                class="text-xs text-slate-400 hover:text-red-500 px-1">取消</button>
        <button @click="status === 'done' ? closePanel() : expanded = !expanded"
                class="p-0.5 rounded hover:bg-black/5 text-slate-400">
          <X v-if="status === 'done'" class="w-3.5 h-3.5" />
          <span v-else class="text-xs">−</span>
        </button>
      </div>
    </div>

    <!-- Body -->
    <div class="p-3 space-y-2 text-sm">
      <!-- v0.12.4: 模型信息 + 降级警告 -->
      <div v-if="modelUsed" class="text-xs text-slate-400 flex items-center gap-1">
        <span>模型：{{ modelUsed }}</span>
      </div>
      <div v-if="fallback" class="flex items-center gap-1.5 px-2 py-1.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">
        <AlertTriangle :size="12" class="flex-shrink-0" />
        <span>在线模型未能响应，已自动切换本地模型</span>
      </div>
      <!-- 批量进度条 -->
      <div v-if="progress.total > 0" class="mb-2">
        <div class="flex justify-between text-xs text-slate-500 mb-1">
          <span>{{ progress.total > 10 ? `已分析 ${progress.current}/${progress.total} 天` : `步骤 ${progress.current}/${progress.total}` }}</span>
          <span>{{ Math.round(progress.current / progress.total * 100) }}%</span>
        </div>
        <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
          <div :class="['h-full rounded-full transition-all', status === 'failed' ? 'bg-red-400' : 'bg-indigo-400']"
               :style="{ width: Math.round(progress.current / progress.total * 100) + '%' }" />
        </div>
      </div>

      <!-- 子步骤列表 -->
      <div v-if="steps.length > 0" class="space-y-1">
        <div
          v-for="(s, i) in steps"
          :key="i"
          class="flex items-center justify-between text-xs"
        >
          <div class="flex items-center gap-1.5">
            <CheckCircle2 v-if="s.status === 'done'" class="w-3 h-3 text-emerald-500" />
            <XCircle v-else-if="s.status === 'failed'" class="w-3 h-3 text-red-400" />
            <Loader2 v-else class="w-3 h-3 animate-spin text-indigo-400" />
            <span :class="s.status === 'failed' ? 'text-red-500' : 'text-slate-600'">{{ s.name }}</span>
          </div>
          <span class="text-slate-400 font-mono">{{ s.duration_ms > 0 ? (s.duration_ms / 1000).toFixed(1) + 's' : '' }}</span>
        </div>
      </div>

      <!-- 步骤 -->
      <div v-if="steps.length === 0" class="text-xs text-slate-500">{{ step }}</div>

      <!-- 错误详情 -->
      <div v-if="error" class="p-2 bg-red-50 rounded-lg text-xs text-red-600">
        <div class="font-medium">{{ errorLabels[error.type] || error.type }}</div>
        <div class="mt-0.5 text-red-400">{{ error.detail }}</div>
      </div>
    </div>
  </div>
  </div>
</template>
