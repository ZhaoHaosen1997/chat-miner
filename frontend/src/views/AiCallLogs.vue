<script setup>
import { ref, onMounted, inject, watch } from 'vue'
import { getAiCallLogs, getAiCallLog } from '../api/index.js'
import { highlightContent } from '../utils/highlight.js'
import { Loader2, ChevronDown, ChevronRight, ChevronLeft, Copy, Check } from 'lucide-vue-next'

const currentGroup = inject('currentGroup', ref(null))

const logs = ref([])
const loading = ref(false)
const expandedId = ref(null)
const detailLoading = ref(false)
const detail = ref(null)

// 复制
const copied = ref('')
async function copyText(text, key) {
  try { await navigator.clipboard.writeText(text); copied.value = key; setTimeout(() => { copied.value = '' }, 1500) } catch { /* noop */ }
}

// 筛选
const filterTaskId = ref('')
const filterPipeline = ref('')
const filterGroupId = ref(0)
const pipelines = ['', 'daily', 'weekly', 'monthly', 'annual', 'event', 'meme', 'portrait']
const pipelineLabels = { daily: '日报', weekly: '周报', monthly: '月报', annual: '年报', event: '事件', meme: '梗百科', portrait: '画像' }
const statuses = ['', 'success', 'parse_error', 'error']
const statusLabels = { success: '成功', parse_error: '格式异常', error: '失败' }
const filterStatus = ref('')

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
      status: filterStatus.value || undefined,
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

function formatDuration(ms) { return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms` }
function formatChars(n) { return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}` }
function statusClass(s) {
  if (s === 'success') return 'bg-emerald-50 text-emerald-600'
  if (s === 'parse_error') return 'bg-amber-50 text-amber-600'
  return 'bg-red-50 text-red-600'
}
function statusLabel(s) { return statusLabels[s] || (s ? s : '失败') }

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <!-- 筛选栏 -->
    <div class="flex items-center gap-3">
      <input v-model="filterTaskId" @keyup.enter="(currentPage=1, load())" type="text" placeholder="任务 ID" class="w-28 px-3 py-1.5 text-sm border rounded-lg" />
      <select v-model="filterPipeline" @change="(currentPage=1, load())" class="px-3 py-1.5 text-sm border rounded-lg">
        <option v-for="p in pipelines" :key="p" :value="p">{{ p ? pipelineLabels[p] : '全部管线' }}</option>
      </select>
      <select v-model="filterStatus" @change="(currentPage=1, load())" class="px-3 py-1.5 text-sm border rounded-lg">
        <option v-for="s in statuses" :key="s" :value="s">{{ s ? statusLabels[s] : '全部状态' }}</option>
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
          <span class="text-xs font-medium px-2 py-0.5 rounded-full" :class="statusClass(log.status || (log.success ? 'success' : 'error'))">{{ statusLabel(log.status || (log.success ? 'success' : 'error')) }}</span>
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
              <summary class="text-xs font-semibold text-slate-500 cursor-pointer py-1">系统提示词（{{ detail.system_prompt?.length || 0 }} 字）</summary>
              <div class="relative mt-2 group/copy">
                <pre class="p-3 rounded-lg bg-white border text-xs text-slate-600 whitespace-pre-wrap max-h-48 overflow-y-auto font-sans" v-html="highlightContent(detail.system_prompt)"></pre>
                <button @click.stop="copyText(detail.system_prompt, 'system')" class="absolute top-2 right-2 p-1.5 rounded-md bg-white/80 hover:bg-white border border-slate-200 opacity-0 group-hover/copy:opacity-100 transition-opacity" title="复制">
                  <Check v-if="copied === 'system'" class="w-3.5 h-3.5 text-emerald-500" />
                  <Copy v-else class="w-3.5 h-3.5 text-slate-400" />
                </button>
              </div>
            </details>

            <details class="group" open>
              <summary class="text-xs font-semibold text-slate-500 cursor-pointer py-1">用户提示词（{{ detail.user_prompt?.length || 0 }} 字）</summary>
              <div class="relative mt-2 group/copy">
                <pre class="p-3 rounded-lg bg-white border text-xs text-slate-600 whitespace-pre-wrap max-h-80 overflow-y-auto font-sans" v-html="highlightContent(detail.user_prompt)"></pre>
                <button @click.stop="copyText(detail.user_prompt, 'user')" class="absolute top-2 right-2 p-1.5 rounded-md bg-white/80 hover:bg-white border border-slate-200 opacity-0 group-hover/copy:opacity-100 transition-opacity" title="复制">
                  <Check v-if="copied === 'user'" class="w-3.5 h-3.5 text-emerald-500" />
                  <Copy v-else class="w-3.5 h-3.5 text-slate-400" />
                </button>
              </div>
            </details>

            <details class="group" open>
              <summary class="text-xs font-semibold text-slate-500 cursor-pointer py-1">AI 响应（输入 {{ formatChars(detail.input_chars) }} 字 / 输出 {{ formatChars(detail.output_chars) }} 字）</summary>
              <div class="relative mt-2 group/copy">
                <pre class="p-3 rounded-lg bg-white border text-xs whitespace-pre-wrap max-h-80 overflow-y-auto font-mono" :class="detail.status === 'parse_error' ? 'text-amber-600' : (detail.success ? 'text-slate-600' : 'text-red-600')" v-html="highlightContent(detail.error || detail.response_raw)"></pre>
                <button @click.stop="copyText(detail.error || detail.response_raw, 'response')" class="absolute top-2 right-2 p-1.5 rounded-md bg-white/80 hover:bg-white border border-slate-200 opacity-0 group-hover/copy:opacity-100 transition-opacity" title="复制">
                  <Check v-if="copied === 'response'" class="w-3.5 h-3.5 text-emerald-500" />
                  <Copy v-else class="w-3.5 h-3.5 text-slate-400" />
                </button>
              </div>
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
