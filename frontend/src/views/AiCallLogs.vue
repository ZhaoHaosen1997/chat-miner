<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getAiCallLogs, getAiCallLog } from '../api/index.js'
import { Loader2, ChevronDown, ChevronRight, ExternalLink, CheckCircle2, XCircle, Clock, Zap, ArrowLeft } from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const logs = ref([])
const loading = ref(false)
const expandedId = ref(null)
const detailLoading = ref(false)
const detail = ref(null)

// 筛选
const filterTaskId = ref(route.query.task_id ? Number(route.query.task_id) : 0)
const filterPipeline = ref(route.query.pipeline || '')

const pipelines = ['', 'daily', 'weekly', 'monthly', 'annual', 'event', 'meme', 'portrait']
const pipelineLabels = { daily: '日报', weekly: '周报', monthly: '月报', annual: '年报', event: '事件', meme: '梗百科', portrait: '画像' }

async function load() {
  loading.value = true
  try {
    logs.value = await getAiCallLogs({
      task_id: filterTaskId.value || undefined,
      pipeline: filterPipeline.value || undefined,
      limit: 50,
    })
  } catch { logs.value = [] }
  finally { loading.value = false }
}

async function toggleDetail(logId) {
  if (expandedId.value === logId) { expandedId.value = null; detail.value = null; return }
  expandedId.value = logId
  detailLoading.value = true
  try { detail.value = await getAiCallLog(logId) }
  catch { detail.value = null }
  finally { detailLoading.value = false }
}

function formatJSON(text) {
  try { return JSON.stringify(JSON.parse(text), null, 2) }
  catch { return text }
}

function formatDuration(ms) { return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms` }

watch(() => route.query, (q) => {
  filterTaskId.value = q.task_id ? Number(q.task_id) : 0
  filterPipeline.value = q.pipeline || ''
  load()
})

onMounted(load)
</script>

<template>
  <div class="max-w-4xl mx-auto px-4 py-6 space-y-5">
    <!-- 头部 -->
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-xl font-bold text-slate-800">AI 调用日志</h2>
        <p class="text-sm text-slate-400 mt-0.5">每次 AI 调用的输入输出记录</p>
      </div>
      <button @click="router.push('/')" class="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600">
        <ArrowLeft class="w-4 h-4" />返回仪表盘
      </button>
    </div>

    <!-- 筛选栏 -->
    <div class="flex items-center gap-3">
      <input v-model.number="filterTaskId" @keyup.enter="load" type="number" placeholder="任务 ID" class="w-28 px-3 py-1.5 text-sm border rounded-lg" />
      <select v-model="filterPipeline" @change="load" class="px-3 py-1.5 text-sm border rounded-lg">
        <option v-for="p in pipelines" :key="p" :value="p">{{ p ? pipelineLabels[p] : '全部管线' }}</option>
      </select>
      <button @click="load" class="px-3 py-1.5 text-sm bg-indigo-500 text-white rounded-lg hover:bg-indigo-600">筛选</button>
    </div>

    <!-- 日志列表 -->
    <div v-if="loading" class="flex justify-center py-12"><Loader2 class="w-5 h-5 animate-spin text-slate-300" /></div>

    <div v-else-if="!logs.length" class="py-12 text-center text-sm text-slate-400">
      暂无日志记录
    </div>

    <div v-else class="space-y-1.5">
      <div v-for="log in logs" :key="log.id" class="border rounded-xl overflow-hidden">
        <!-- 摘要行 -->
        <div @click="toggleDetail(log.id)" class="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-slate-50 transition-colors">
          <component :is="expandedId === log.id ? ChevronDown : ChevronRight" class="w-4 h-4 text-slate-300 shrink-0" />
          <span class="text-xs font-medium px-2 py-0.5 rounded-full" :class="log.success ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600'">{{ log.success ? '成功' : '失败' }}</span>
          <span class="text-xs font-medium text-slate-500">{{ pipelineLabels[log.pipeline] || log.pipeline }}</span>
          <span class="text-xs text-slate-400">{{ log.model_name }}</span>
          <span v-if="log.task_id" class="text-xs text-indigo-400 cursor-pointer hover:underline" @click.stop="router.push(`/ai-logs?task_id=${log.task_id}`)">#{{ log.task_id }}</span>
          <span class="text-xs text-slate-300 ml-auto">{{ formatDuration(log.duration_ms) }}</span>
          <span class="text-[10px] text-slate-300">{{ log.created_at?.slice(5, 16) }}</span>
        </div>

        <!-- 展开详情 -->
        <div v-if="expandedId === log.id" class="border-t bg-slate-50/50">
          <div v-if="detailLoading" class="flex justify-center py-6"><Loader2 class="w-4 h-4 animate-spin text-slate-300" /></div>
          <div v-else-if="detail" class="p-4 space-y-4">
            <div v-if="detail.error" class="p-3 rounded-lg bg-red-50 text-red-600 text-sm">{{ detail.error }}</div>

            <!-- System Prompt -->
            <details class="group" open>
              <summary class="text-xs font-semibold text-slate-500 cursor-pointer py-1">System Prompt（{{ detail.system_prompt?.length || 0 }} 字）</summary>
              <pre class="mt-2 p-3 rounded-lg bg-white border text-xs text-slate-600 whitespace-pre-wrap max-h-48 overflow-y-auto font-sans">{{ detail.system_prompt }}</pre>
            </details>

            <!-- User Prompt -->
            <details class="group">
              <summary class="text-xs font-semibold text-slate-500 cursor-pointer py-1">User Prompt（{{ detail.user_prompt?.length || 0 }} 字）</summary>
              <pre class="mt-2 p-3 rounded-lg bg-white border text-xs text-slate-600 whitespace-pre-wrap max-h-80 overflow-y-auto font-sans">{{ detail.user_prompt }}</pre>
            </details>

            <!-- Response -->
            <details class="group" open>
              <summary class="text-xs font-semibold text-slate-500 cursor-pointer py-1">AI 响应（{{ detail.token_estimate || 0 }} 估字）</summary>
              <pre class="mt-2 p-3 rounded-lg bg-white border text-xs whitespace-pre-wrap max-h-80 overflow-y-auto font-mono" :class="detail.success ? 'text-slate-600' : 'text-red-600'">{{ detail.success ? formatJSON(detail.response_raw) : (detail.error || detail.response_raw) }}</pre>
            </details>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
