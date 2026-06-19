<script setup>
import { ref, inject, watch, onMounted, onUnmounted, computed, nextTick } from 'vue'
import { Calendar, Search, Loader2, AlertCircle, Clock, Zap, ChevronDown, ChevronRight } from 'lucide-vue-next'
import { getEvents, getEventWindows, detectEvents, analyzeWindow, analyzeAllWindows, getDates } from '../api/index.js'
import EventWindowCard from '../components/EventWindowCard.vue'
import EventCard from '../components/EventCard.vue'

const currentGroup = inject('currentGroup', ref(null))
const activeTaskId = inject('activeTaskId', ref(''))
const triggerRefresh = inject('triggerRefresh', () => {})

const events = ref([])
const windows = ref([])
const totalEventsCount = ref(0) // 未筛选事件总数，用于区域可见性
const loading = ref(false)
const detecting = ref(false)
const batchAnalyzing = ref(false)
const error = ref('')
const dateRange = ref({ start: '', end: '' })
const fullRange = ref({ start: '', end: '' })
const activeFilter = ref('')
const batchProgress = ref({ current: 0, total: 0 })
const pollingTimer = ref(null)
const initialLoadDone = ref(false)

const eventTypes = [
  { value: '', label: '全部', icon: '📅' },
  { value: 'decision', label: '决策', icon: '🎯' },
  { value: 'discussion', label: '讨论', icon: '💬' },
  { value: 'social', label: '社交', icon: '🎉' },
  { value: 'announcement', label: '公告', icon: '📢' },
  { value: 'meme', label: '梗', icon: '🤣' },
]

const pendingCount = computed(() => windows.value.filter(w => w.status === 'pending').length)
const hasWindows = computed(() => windows.value.length > 0)

// 折叠状态
const windowsExpanded = ref(true)       // 候选事件区域
const eventsExpanded = ref(true)        // 已分析事件区域
const expandedMonths = ref(new Set())   // 展开的月份（窗口列表）
const expandedEventMonths = ref(new Set())  // 展开的月份（事件列表）

const groupedWindows = computed(() => {
  const groups = {}
  for (const w of windows.value) {
    const month = (w.start_time || '').slice(0, 7)
    if (!month) continue
    if (!groups[month]) groups[month] = []
    groups[month].push(w)
  }
  return Object.entries(groups).sort((a, b) => b[0].localeCompare(a[0]))
})

// 已分析事件按月分组
const groupedEvents = computed(() => {
  const groups = {}
  for (const e of events.value) {
    const month = (e.start_time || '').slice(0, 7)
    if (!month) continue
    if (!groups[month]) groups[month] = []
    groups[month].push(e)
  }
  return Object.entries(groups).sort((a, b) => b[0].localeCompare(a[0]))
})

function formatMonthLabel(month) {
  const [y, m] = month.split('-')
  return `${y}年${parseInt(m)}月`
}

function toggleMonth(month, isEvent = false) {
  const set = isEvent ? expandedEventMonths : expandedMonths
  const newSet = new Set(set.value)
  if (newSet.has(month)) {
    newSet.delete(month)
  } else {
    newSet.add(month)
  }
  if (isEvent) {
    expandedEventMonths.value = newSet
  } else {
    expandedMonths.value = newSet
  }
}

// 初始化：默认展开最新月份
function initExpandedMonths() {
  const winMonths = groupedWindows.value
  if (winMonths.length > 0) {
    expandedMonths.value = new Set([winMonths[0][0]])
  }
  const evtMonths = groupedEvents.value
  if (evtMonths.length > 0) {
    expandedEventMonths.value = new Set([evtMonths[0][0]])
  }
}

// 数据变化时重新初始化展开状态
watch([groupedWindows, groupedEvents], () => {
  if (groupedWindows.value.length > 0 && expandedMonths.value.size === 0) {
    expandedMonths.value = new Set([groupedWindows.value[0][0]])
  }
  if (groupedEvents.value.length > 0 && expandedEventMonths.value.size === 0) {
    expandedEventMonths.value = new Set([groupedEvents.value[0][0]])
  }
}, { deep: true })

async function loadEvents() {
  if (!currentGroup.value) return
  loading.value = true
  error.value = ''
  try {
    const params = {}
    if (activeFilter.value) params.type = activeFilter.value
    if (dateRange.value.start) params.date_from = dateRange.value.start
    if (dateRange.value.end) params.date_to = dateRange.value.end
    events.value = await getEvents(currentGroup.value.id, params)
  } catch (e) {
    error.value = e.message || '加载事件失败'
  } finally {
    loading.value = false
  }
}

// 加载未筛选事件总数（用于区域可见性）
async function loadTotalEventsCount() {
  if (!currentGroup.value) return
  try {
    const all = await getEvents(currentGroup.value.id, {})
    totalEventsCount.value = Array.isArray(all) ? all.length : 0
  } catch (e) {
    // 静默
  }
}

async function loadWindows() {
  if (!currentGroup.value) return
  try {
    const data = await getEventWindows(currentGroup.value.id)
    if (Array.isArray(data)) {
      windows.value = data
    } else {
      console.warn('getEventWindows 返回非数组:', data)
      windows.value = []
    }
  } catch (e) {
    console.error('加载候选事件列表失败:', e)
    windows.value = []
  }
}

async function initDateRange() {
  if (!currentGroup.value) return
  try {
    const dates = await getDates(currentGroup.value.id)
    if (dates && dates.length > 0) {
      const startDate = typeof dates[dates.length - 1] === 'string' ? dates[dates.length - 1] : dates[dates.length - 1]?.date
      const endDate = typeof dates[0] === 'string' ? dates[0] : dates[0]?.date
      fullRange.value = { start: startDate || '', end: endDate || '' }
      if (!dateRange.value.start) {
        dateRange.value = { start: startDate || '', end: endDate || '' }
      }
    }
  } catch (e) { /* ignore */ }
}

// Phase 1: 检测
async function startDetection() {
  if (!currentGroup.value) return
  detecting.value = true
  error.value = ''
  windows.value = []
  try {
    const result = await detectEvents(
      currentGroup.value.id,
      dateRange.value.start,
      dateRange.value.end
    )
    windows.value = result.windows || []
    if (result.count === 0) {
      error.value = '该时间段内未发现候选事件时段'
    }
    await loadEvents()
  } catch (e) {
    error.value = e.message || '检测失败'
  } finally {
    detecting.value = false
  }
}

// Phase 2: 单条分析
async function analyzeSingle(windowId) {
  if (!currentGroup.value) return
  error.value = ''

  // 立即更新 UI 状态
  const idx = windows.value.findIndex(w => w.id === windowId)
  if (idx >= 0) {
    windows.value[idx] = { ...windows.value[idx], status: 'analyzing' }
  }

  try {
    const result = await analyzeWindow(currentGroup.value.id, windowId)
    // 用 splice 触发更强的响应式更新
    const wi = windows.value.findIndex(w => w.id === windowId)
    if (wi >= 0) {
      const updated = {
        ...windows.value[wi],
        status: result.status,
        event_count: result.status === 'analyzed' ? 1 : 0,
        event: result.event || null,
      }
      windows.value.splice(wi, 1, updated)
    }
    await loadEvents()
    await nextTick()
  } catch (e) {
    const wi2 = windows.value.findIndex(w => w.id === windowId)
    if (wi2 >= 0) {
      windows.value[wi2] = { ...windows.value[wi2], status: 'pending' }
    }
    error.value = `分析失败: ${e.message}`
  }
}

// Phase 2: 一键分析
async function analyzeAll() {
  if (!currentGroup.value || pendingCount.value === 0) return
  batchAnalyzing.value = true
  error.value = ''
  batchProgress.value = { current: 0, total: pendingCount.value }

  try {
    const result = await analyzeAllWindows(currentGroup.value.id)
    batchProgress.value.total = result.total || pendingCount.value
    // 触发右下角全局进度面板（SSE）
    if (result.task_id) {
      activeTaskId.value = result.task_id
    }
    // 立即开始轮询刷新
    startPolling()
  } catch (e) {
    error.value = e.message || '批量分析启动失败'
    batchAnalyzing.value = false
  }
}

function startPolling() {
  stopPolling()
  refreshBatchStatus()
  pollingTimer.value = setInterval(refreshBatchStatus, 2000)
}

async function refreshBatchStatus() {
  if (!currentGroup.value) return

  // 检测全局任务是否被取消/完成
  if (!activeTaskId.value) {
    stopPolling()
    batchAnalyzing.value = false
    await loadWindows()
    await loadEvents()
    return
  }

  await loadWindows()
  await loadEvents()
  await loadTotalEventsCount()

  const done = windows.value.filter(
    w => w.status === 'analyzed' || w.status === 'empty'
  ).length
  batchProgress.value.current = done

  const stillPending = windows.value.filter(
    w => w.status === 'pending' || w.status === 'analyzing'
  )
  if (stillPending.length === 0) {
    stopPolling()
    batchAnalyzing.value = false
    activeTaskId.value = ''
  }
}

function stopPolling() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

function setFilter(type) {
  activeFilter.value = type
  loadEvents()
}

// 群切换时清理
watch(() => currentGroup.value?.id, (newId, oldId) => {
  if (newId && newId !== oldId) {
    stopPolling()
    detecting.value = false
    batchAnalyzing.value = false
    events.value = []
    windows.value = []
    initialLoadDone.value = false
    dateRange.value = { start: '', end: '' }
    initDateRange().then(() => {
      loadEvents()
      loadWindows()
      initialLoadDone.value = true
    })
  }
})

onMounted(async () => {
  await initDateRange()
  if (currentGroup.value) {
    await Promise.all([loadEvents(), loadWindows(), loadTotalEventsCount()])
    initialLoadDone.value = true
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="max-w-3xl mx-auto">
    <!-- 页头 -->
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-bold text-slate-800 flex items-center gap-2">
        <Zap class="w-6 h-6 text-indigo-500" />
        事件时间轴
      </h1>
    </div>

    <!-- 时间范围选择 + 检测按钮 -->
    <div v-if="currentGroup" class="bg-white rounded-xl border border-slate-200 p-4 mb-6">
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-2">
          <Calendar class="w-4 h-4 text-slate-400" />
          <input
            v-model="dateRange.start"
            type="date"
            class="text-sm border border-slate-300 rounded-lg px-3 py-1.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
          <span class="text-slate-400 text-sm">~</span>
          <input
            v-model="dateRange.end"
            type="date"
            class="text-sm border border-slate-300 rounded-lg px-3 py-1.5 text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
          />
        </div>
        <button
          @click="startDetection"
          :disabled="detecting"
          class="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          <Loader2 v-if="detecting" class="w-4 h-4 animate-spin" />
          <Search v-else class="w-4 h-4" />
          {{ detecting ? '检测中...' : hasWindows ? '重新检测' : '扫描候选事件' }}
        </button>
        <span v-if="hasWindows && !detecting" class="text-xs text-slate-400">
          共 {{ windows.length }} 个时段，{{ pendingCount }} 个待分析
        </span>
      </div>
    </div>

    <!-- 错误 -->
    <div v-if="error && !detecting" class="flex flex-col items-center justify-center py-8 mb-4">
      <AlertCircle class="w-8 h-8 text-red-400 mb-2" />
      <p class="text-slate-600 mb-3">{{ error }}</p>
      <button @click="startDetection" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">重试</button>
    </div>

    <!-- 检测中 -->
    <div v-if="detecting" class="flex flex-col items-center justify-center py-16 text-slate-500">
      <Loader2 class="w-10 h-10 animate-spin text-indigo-400 mb-4" />
      <p>正在扫描消息量尖峰，识别候选事件时段...</p>
      <p class="text-sm text-slate-400 mt-1">纯 Python 处理，通常只需几秒</p>
    </div>

    <!-- ====== 候选事件区域 ====== -->
    <div v-if="hasWindows && !detecting" class="mb-6">
      <!-- 分区标题（可折叠） -->
      <button
        @click="windowsExpanded = !windowsExpanded"
        class="flex items-center gap-2 w-full text-left mb-3 group"
      >
        <component :is="windowsExpanded ? ChevronDown : ChevronRight"
          class="w-5 h-5 text-slate-400 group-hover:text-slate-600 transition-colors" />
        <span class="text-base font-semibold text-slate-700">
          候选事件
        </span>
        <span class="text-xs text-slate-400">
          ({{ windows.length }} 个时段，{{ pendingCount }} 个待分析)
        </span>
      </button>

      <template v-if="windowsExpanded">
        <!-- 一键分析栏 -->
        <div v-if="pendingCount > 0" class="flex items-center justify-between mb-4 p-3 bg-indigo-50 rounded-lg">
          <div class="text-sm text-indigo-700">
            <span class="font-medium">{{ pendingCount }}</span> 个候选事件待分析
            <span v-if="batchAnalyzing" class="ml-2 text-indigo-500">
              ({{ batchProgress.current }}/{{ batchProgress.total }})
            </span>
          </div>
          <button
            @click="analyzeAll"
            :disabled="batchAnalyzing"
            class="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
          >
            <Loader2 v-if="batchAnalyzing" class="w-3.5 h-3.5 animate-spin" />
            <Zap v-else class="w-3.5 h-3.5" />
            一键分析
          </button>
        </div>
        <div v-else class="mb-4 p-3 bg-green-50 rounded-lg text-sm text-green-700">
          ✅ 所有候选事件已分析完毕
        </div>

        <!-- 按月分组（可折叠） -->
        <div class="relative">
          <div class="absolute left-4 top-0 bottom-0 w-px bg-slate-200" />
          <div v-for="[month, monthWindows] in groupedWindows" :key="month" class="mb-6">
            <!-- 月份标题（可折叠） -->
            <button
              @click="toggleMonth(month)"
              class="flex items-center gap-2 mb-3 relative group w-full text-left"
            >
              <div
                :class="[
                  'w-3 h-3 rounded-full border-2 border-white shadow-sm z-10 flex-shrink-0 transition-colors',
                  expandedMonths.has(month) ? 'bg-indigo-500' : 'bg-slate-300',
                ]"
              />
              <component
                :is="expandedMonths.has(month) ? ChevronDown : ChevronRight"
                class="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-600 transition-colors"
              />
              <span class="text-sm font-semibold text-slate-500">
                {{ formatMonthLabel(month) }}
              </span>
              <span class="text-xs text-slate-400">({{ monthWindows.length }})</span>
            </button>

            <!-- 月份下的卡片列表 -->
            <div v-if="expandedMonths.has(month)" class="ml-7 space-y-3">
              <EventWindowCard
                v-for="w in monthWindows"
                :key="w.id"
                :window="w"
                :group-id="currentGroup?.id"
                @analyze="analyzeSingle"
              />
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- ====== 已分析事件区域 ====== -->
    <div v-if="totalEventsCount > 0 && !detecting" class="mb-6">
      <!-- 分区标题（可折叠） -->
      <button
        @click="eventsExpanded = !eventsExpanded"
        class="flex items-center gap-2 w-full text-left mb-3 group"
      >
        <component :is="eventsExpanded ? ChevronDown : ChevronRight"
          class="w-5 h-5 text-slate-400 group-hover:text-slate-600 transition-colors" />
        <span class="text-base font-semibold text-slate-700">
          已分析事件
        </span>
        <span class="text-xs text-slate-400">
          ({{ totalEventsCount }} 个)
          <span v-if="activeFilter" class="text-amber-500">· 筛选: {{ activeFilter }}</span>
        </span>
      </button>

      <template v-if="eventsExpanded">
        <!-- 类型筛选 -->
        <div class="flex flex-wrap gap-2 mb-4">
          <button
            v-for="t in eventTypes"
            :key="t.value"
            @click="setFilter(t.value)"
            :class="[
              'px-3 py-1.5 rounded-full text-sm font-medium transition-colors',
              activeFilter === t.value
                ? 'bg-indigo-100 text-indigo-700'
                : 'bg-slate-100 text-slate-500 hover:bg-slate-200',
            ]"
          >
            {{ t.icon }} {{ t.label }}
          </button>
        </div>

        <!-- 筛选结果为空 -->
        <div v-if="events.length === 0 && activeFilter"
             class="text-center py-8 text-sm text-slate-400">
          该类型暂无事件
          <button @click="setFilter('')" class="text-indigo-500 hover:underline ml-1">查看全部</button>
        </div>

        <!-- 按月分组（可折叠） -->
        <div v-if="events.length > 0" class="relative">
          <div class="absolute left-4 top-0 bottom-0 w-px bg-slate-200" />
          <div v-for="[month, monthEvents] in groupedEvents" :key="month" class="mb-6">
            <button
              @click="toggleMonth(month, true)"
              class="flex items-center gap-2 mb-3 relative group w-full text-left"
            >
              <div
                :class="[
                  'w-3 h-3 rounded-full border-2 border-white shadow-sm z-10 flex-shrink-0 transition-colors',
                  expandedEventMonths.has(month) ? 'bg-green-500' : 'bg-slate-300',
                ]"
              />
              <component
                :is="expandedEventMonths.has(month) ? ChevronDown : ChevronRight"
                class="w-3.5 h-3.5 text-slate-400 group-hover:text-slate-600 transition-colors"
              />
              <span class="text-sm font-semibold text-slate-500">
                {{ formatMonthLabel(month) }}
              </span>
              <span class="text-xs text-slate-400">({{ monthEvents.length }})</span>
            </button>

            <div v-if="expandedEventMonths.has(month)" class="ml-7 space-y-3">
              <EventCard
                v-for="event in monthEvents"
                :key="event.id"
                :event="event"
                :group-id="currentGroup?.id"
              />
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- 加载中 -->
    <div v-if="loading && !detecting" class="flex items-center justify-center py-16">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <!-- 空状态 -->
    <div v-if="!detecting && initialLoadDone && !loading && events.length === 0 && !hasWindows && !error"
         class="flex flex-col items-center justify-center py-16 text-slate-400">
      <Zap class="w-12 h-12 mb-4" />
      <p class="text-lg font-medium text-slate-500 mb-1">尚无事件数据</p>
      <p class="text-sm mb-4">选择时间范围，点击"扫描候选事件"让 AI 从群聊中发现事件</p>
    </div>
  </div>
</template>
