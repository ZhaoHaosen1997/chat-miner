<script setup>
import { ref, onMounted, inject, watch } from 'vue'
import { getAiCallLogs, getAiCallLog } from '../api/index.js'
import { Loader2, ChevronDown, ChevronRight, ChevronLeft } from 'lucide-vue-next'

const currentGroup = inject('currentGroup', ref(null))

const logs = ref([])
const loading = ref(false)
const expandedId = ref(null)
const detailLoading = ref(false)
const detail = ref(null)

// 筛选
const filterTaskId = ref(0)
const filterPipeline = ref('')
const filterGroupId = ref(0)
const pipelines = ['', 'daily', 'weekly', 'monthly', 'annual', 'event', 'meme', 'portrait']
const pipelineLabels = { daily: '日报', weekly: '周报', monthly: '月报', annual: '年报', event: '事件', meme: '梗百科', portrait: '画像' }

// 分页
const pageSize = 50
const currentPage = ref(1)
const total = ref(0)
const totalPages = ref(0)

async function load() {
  loading.value = true
  try {
    const offset = (currentPage.value - 1) * pageSize
    const gid = filterGroupId.value || (currentGroup.value?.id) || 0
    const res = await getAiCallLogs({
      task_id: filterTaskId.value || undefined,
      pipeline: filterPipeline.value || undefined,
      group_id: gid || undefined,
      limit: pageSize,
      offset,
    })
    logs.value = res.logs || []
    total.value = res.total || 0
    totalPages.value = Math.ceil(total.value / pageSize)
  } catch { logs.value = []; total.value = 0; totalPages.value = 0 }
  finally { loading.value = false }
}

// 切换群时自动刷新
watch(() => currentGroup.value?.id, () => { currentPage.value = 1; load() })

function goPage(n) {
  currentPage.value = n
  load()
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
function formatChars(n) { return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}` }

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <!-- 筛选栏 -->
    <div class="flex items-center gap-3">
      <input v-model.number="filterTaskId" @keyup.enter="(currentPage=1, load())" type="number" placeholder="任务 ID" class="w-28 px-3 py-1.5 text-sm border rounded-lg" />
      <select v-model="filterPipeline" @change="(currentPage=1, load())" class="px-3 py-1.5 text-sm border rounded-lg">
        <option v-for="p in pipelines" :key="p" :value="p">{{ p ? pipelineLabels[p] : '全部管线' }}</option>
      </select>
      <button @click="(currentPage=1, load())" class="px-3 py-1.5 text-sm bg-indigo-500 text-white rounded-lg hover:bg-indigo-600">筛选</button>
      <span class="text-xs text-slate-400 ml-auto">{{ total }} 条记录</span>
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
          <span class="text-xs text-slate-300">入{{ formatChars(log.input_chars) }} / 出{{ formatChars(log.output_chars) }}</span>
          <span class="text-xs text-slate-300 ml-auto">{{ formatDuration(log.duration_ms) }}</span>
          <span class="text-[10px] text-slate-300">{{ log.created_at?.slice(5, 16) }}</span>
        </div>

        <!-- 展开详情 -->
        <div v-if="expandedId === log.id" class="border-t bg-slate-50/50">
          <div v-if="detailLoading" class="flex justify-center py-6"><Loader2 class="w-4 h-4 animate-spin text-slate-300" /></div>
          <div v-else-if="detail" class="p-4 space-y-4">
            <div v-if="detail.error" class="p-3 rounded-lg bg-red-50 text-red-600 text-sm">{{ detail.error }}</div>

            <details class="group" open>
              <summary class="text-xs font-semibold text-slate-500 cursor-pointer py-1">System Prompt（{{ detail.system_prompt?.length || 0 }} 字）</summary>
              <pre class="mt-2 p-3 rounded-lg bg-white border text-xs text-slate-600 whitespace-pre-wrap max-h-48 overflow-y-auto font-sans">{{ detail.system_prompt }}</pre>
            </details>

            <details class="group">
              <summary class="text-xs font-semibold text-slate-500 cursor-pointer py-1">User Prompt（{{ detail.user_prompt?.length || 0 }} 字）</summary>
              <pre class="mt-2 p-3 rounded-lg bg-white border text-xs text-slate-600 whitespace-pre-wrap max-h-80 overflow-y-auto font-sans">{{ detail.user_prompt }}</pre>
            </details>

            <details class="group" open>
              <summary class="text-xs font-semibold text-slate-500 cursor-pointer py-1">AI 响应（输入 {{ formatChars(detail.input_chars) }} 字 / 输出 {{ formatChars(detail.output_chars) }} 字）</summary>
              <pre class="mt-2 p-3 rounded-lg bg-white border text-xs whitespace-pre-wrap max-h-80 overflow-y-auto font-mono" :class="detail.success ? 'text-slate-600' : 'text-red-600'">{{ detail.success ? formatJSON(detail.response_raw) : (detail.error || detail.response_raw) }}</pre>
            </details>
          </div>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="totalPages > 1" class="flex items-center justify-center gap-2 pt-2">
      <button @click="goPage(currentPage-1)" :disabled="currentPage<=1" class="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border disabled:opacity-30 hover:bg-slate-50"><ChevronLeft class="w-4 h-4" />上一页</button>
      <span class="text-sm text-slate-400">{{ currentPage }} / {{ totalPages }}</span>
      <button @click="goPage(currentPage+1)" :disabled="currentPage>=totalPages" class="flex items-center gap-1 px-3 py-1.5 text-sm rounded-lg border disabled:opacity-30 hover:bg-slate-50">下一页<ChevronRight class="w-4 h-4" /></button>
    </div>
  </div>
</template>
