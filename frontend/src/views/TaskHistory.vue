<template>
  <div class="p-6 max-w-6xl mx-auto">
    <!-- 页面标题 -->
    <div class="mb-6">
      <h1 class="text-xl font-bold text-slate-800">任务记录</h1>
      <p class="text-sm text-slate-500 mt-1">查看 JSON 导入、AI 分析、WeFlow 同步等所有任务的历史记录</p>
    </div>

    <!-- 筛选栏 -->
    <div class="flex flex-wrap gap-3 mb-5">
      <select v-model="filterType" @change="refresh" class="px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-300">
        <option value="">全部类型</option>
        <option value="analyze_day">日报分析</option>
        <option value="analyze_all">批量日报</option>
        <option value="portrait">画像生成</option>
        <option value="portrait_all">批量画像</option>
        <option value="analyze_all_portraits">批量画像（旧）</option>
        <option value="full_portrait">深度画像</option>
        <option value="import_json">JSON 导入</option>
        <option value="import_weflow">WeFlow 导入</option>
        <option value="weflow_sync">WeFlow 手动同步</option>
        <option value="weflow_auto_sync">WeFlow 定时同步</option>
        <option value="generate_weekly">周报生成</option>
        <option value="generate_all_weekly">批量周报</option>
        <option value="generate_monthly">月报生成</option>
        <option value="generate_all_monthly">批量月报</option>
        <option value="generate_annual">年报生成</option>
      </select>
      <select v-model="filterStatus" @change="refresh" class="px-3 py-1.5 text-sm border border-slate-200 rounded-lg bg-white text-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-300">
        <option value="">全部状态</option>
        <option value="done">成功</option>
        <option value="failed">失败</option>
        <option value="cancelled">已取消</option>
      </select>
      <button @click="refresh" class="px-4 py-1.5 text-sm bg-indigo-50 text-indigo-600 rounded-lg hover:bg-indigo-100 transition-colors">
        刷新
      </button>
      <span class="text-xs text-slate-400 self-center ml-auto">{{ records.length }} 条记录</span>
    </div>

    <!-- 任务列表 -->
    <div v-if="loading" class="text-center py-20 text-slate-400">
      <Loader2 class="w-6 h-6 mx-auto animate-spin mb-2" />
      加载中...
    </div>
    <div v-else-if="records.length === 0" class="text-center py-20 text-slate-400">
      <ClipboardList class="w-10 h-10 mx-auto mb-3 text-slate-300" />
      <p>暂无任务记录</p>
      <p class="text-xs mt-1">执行分析或导入后这里会显示记录</p>
    </div>
    <div v-else class="space-y-2">
      <div v-for="r in records" :key="r.id" class="bg-white rounded-lg border border-slate-200 hover:border-slate-300 transition-colors">
        <div class="flex items-center gap-3 px-4 py-3 cursor-pointer" @click="toggleExpand(r.id)">
          <!-- 类型图标 + 颜色 -->
          <div :class="['w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0', typeStyle(r.task_type).bg]">
            <component :is="typeStyle(r.task_type).icon" :class="['w-4 h-4', typeStyle(r.task_type).color]" />
          </div>
          <!-- 主信息 -->
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium text-slate-700 truncate">{{ typeStyle(r.task_type).label }} · {{ r.target || '-' }}</div>
            <div class="text-xs text-slate-400 mt-0.5">{{ formatTime(r.created_at) }}</div>
          </div>
          <!-- 状态标签 -->
          <span :class="['px-2 py-0.5 rounded-md text-xs font-medium flex-shrink-0', statusBadge(r.status)]">
            {{ statusLabel(r.status) }}
          </span>
          <!-- 耗时 -->
          <span v-if="r.total_duration_ms" class="text-xs text-slate-400 flex-shrink-0 w-16 text-right">
            {{ formatDuration(r.total_duration_ms) }}
          </span>
          <span v-else class="text-xs text-slate-400 flex-shrink-0 w-16 text-right">-</span>
          <!-- 展开箭头 -->
          <ChevronRight :class="['w-4 h-4 text-slate-300 flex-shrink-0 transition-transform', expanded === r.id && 'rotate-90']" />
        </div>
        <!-- 展开详情 -->
        <div v-if="expanded === r.id" class="px-4 pb-4 border-t border-slate-100">
          <div class="grid grid-cols-2 gap-2 mt-3 text-xs">
            <div><span class="text-slate-400">任务ID：</span><code class="text-slate-600">{{ r.task_id }}</code></div>
            <div><span class="text-slate-400">模型：</span><span class="text-slate-600">{{ r.model_used || '-' }}</span></div>
            <div v-if="r.error_summary" class="col-span-2 text-red-500">错误：{{ r.error_summary }}</div>
          </div>
          <!-- 子任务步骤 -->
          <div v-if="parseSteps(r.steps_json).length > 0" class="mt-3">
            <div class="text-xs text-slate-500 mb-2 font-medium">子任务步骤</div>
            <div class="space-y-1">
              <div v-for="(s, i) in parseSteps(r.steps_json)" :key="i" class="flex items-center gap-2 text-xs py-1 px-2 rounded bg-slate-50">
                <span :class="[s.status === 'done' ? 'text-green-500' : s.status === 'failed' ? 'text-red-500' : 'text-slate-400', 'text-sm']">
                  {{ s.status === 'done' ? '✓' : s.status === 'failed' ? '✗' : '○' }}
                </span>
                <span class="text-slate-600 flex-1">{{ s.name }}</span>
                <span class="text-slate-400">{{ s.duration_ms ? formatDuration(s.duration_ms) : '' }}</span>
                <span v-if="s.model" class="text-slate-400">{{ s.model }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载更多 -->
    <div v-if="records.length >= pageSize" class="text-center mt-4">
      <button @click="loadMore" class="px-6 py-2 text-sm text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors">
        加载更多
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { inject } from 'vue'
import { getTaskHistoryAll } from '../api/index.js'
import { Loader2, ClipboardList, Upload, FileText, RefreshCw, Users, MessageSquare, Fish, Settings, ChevronRight, Zap, Clock, Calendar } from 'lucide-vue-next'

const currentGroup = inject('currentGroup', ref(null))
const records = ref([])
const loading = ref(true)
const expanded = ref(null)
const filterType = ref('')
const filterStatus = ref('')
const pageSize = 50
const offset = ref(0)

const TYPE_MAP = {
  analyze_day:            { label: '日报分析', icon: Calendar,    bg: 'bg-blue-50',    color: 'text-blue-500' },
  analyze_all:            { label: '批量日报', icon: Calendar,    bg: 'bg-blue-50',    color: 'text-blue-500' },
  portrait:               { label: '画像生成', icon: Users,       bg: 'bg-violet-50',  color: 'text-violet-500' },
  portrait_all:           { label: '批量画像', icon: Users,       bg: 'bg-violet-50',  color: 'text-violet-500' },
  analyze_all_portraits:  { label: '批量画像', icon: Users,       bg: 'bg-violet-50',  color: 'text-violet-500' },
  full_portrait:          { label: '深度画像', icon: Users,       bg: 'bg-violet-50',  color: 'text-violet-500' },
  import_json:            { label: 'JSON 导入', icon: Upload,     bg: 'bg-emerald-50', color: 'text-emerald-500' },
  import_weflow:          { label: 'WeFlow 导入', icon: Upload,   bg: 'bg-emerald-50', color: 'text-emerald-500' },
  weflow_sync:            { label: 'WeFlow 同步', icon: RefreshCw,bg: 'bg-cyan-50',    color: 'text-cyan-500' },
  weflow_auto_sync:       { label: '定时同步', icon: Clock,        bg: 'bg-cyan-50',    color: 'text-cyan-500' },
  generate_weekly:        { label: '周报生成', icon: FileText,    bg: 'bg-amber-50',   color: 'text-amber-500' },
  generate_all_weekly:    { label: '批量周报', icon: FileText,    bg: 'bg-amber-50',   color: 'text-amber-500' },
  generate_monthly:       { label: '月报生成', icon: FileText,    bg: 'bg-orange-50',  color: 'text-orange-500' },
  generate_all_monthly:   { label: '批量月报', icon: FileText,    bg: 'bg-orange-50',  color: 'text-orange-500' },
  generate_annual:        { label: '年报生成', icon: FileText,    bg: 'bg-red-50',     color: 'text-red-500' },
}

function typeStyle(type) {
  return TYPE_MAP[type] || { label: type || '未知', icon: Zap, bg: 'bg-slate-50', color: 'text-slate-400' }
}

function statusBadge(status) {
  const m = {
    done: 'bg-emerald-50 text-emerald-600',
    failed: 'bg-red-50 text-red-500',
    cancelled: 'bg-amber-50 text-amber-600',
    pending: 'bg-blue-50 text-blue-500',
    inference: 'bg-indigo-50 text-indigo-500',
    parsing: 'bg-slate-100 text-slate-500',
  }
  return m[status] || 'bg-slate-50 text-slate-400'
}

function statusLabel(status) {
  const m = { done: '成功', failed: '失败', cancelled: '已取消', pending: '等待中', inference: '推理中', parsing: '解析中' }
  return m[status] || status || '未知'
}

function formatTime(ts) {
  if (!ts) return '-'
  const d = new Date(ts + 'Z')
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function formatDuration(ms) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m${Math.round((ms % 60000) / 1000)}s`
}

function parseSteps(raw) {
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(parsed) ? parsed : []
  } catch { return [] }
}

function toggleExpand(id) {
  expanded.value = expanded.value === id ? null : id
}

async function loadMore() {
  offset.value += pageSize
  await refresh()
}

async function refresh() {
  loading.value = true
  offset.value = 0
  try {
    const data = await getTaskHistoryAll({
      groupId: currentGroup.value?.id,
      taskType: filterType.value || undefined,
      status: filterStatus.value || undefined,
      limit: pageSize,
      offset: 0,
    })
    records.value = Array.isArray(data) ? data : []
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

onMounted(refresh)

// v1.3.0: 切换群聊时立即刷新
watch(() => currentGroup.value?.id, () => {
  if (currentGroup.value?.id) refresh()
})
</script>
