<script setup>
import { ref, inject, watch, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { Calendar, Search, Loader2, AlertCircle, Clock, ChevronRight } from 'lucide-vue-next'
import { getEvents, detectEvents, getDates } from '../api/index.js'
import EventTimeline from '../components/EventTimeline.vue'

const route = useRoute()
const currentGroup = inject('currentGroup', ref(null))
const activeTaskId = inject('activeTaskId', ref(''))
const triggerRefresh = inject('triggerRefresh', () => {})

const events = ref([])
const loading = ref(false)
const analyzing = ref(false)
const error = ref('')
const dateRange = ref({ start: '', end: '' })
const fullRange = ref({ start: '', end: '' })  // 群数据全量范围
const activeFilter = ref('')  // '' = 全部
const currentTaskId = ref('')   // 当前分析任务 ID
const pollingTimer = ref(null)  // 轮询定时器

const eventTypes = [
  { value: '', label: '全部', icon: '📅' },
  { value: 'decision', label: '决策', icon: '🎯' },
  { value: 'discussion', label: '讨论', icon: '💬' },
  { value: 'social', label: '社交', icon: '🎉' },
  { value: 'announcement', label: '公告', icon: '📢' },
  { value: 'meme', label: '梗', icon: '🤣' },
]

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

async function startDetection() {
  if (!currentGroup.value) return
  analyzing.value = true
  error.value = ''
  try {
    const result = await detectEvents(
      currentGroup.value.id,
      dateRange.value.start,
      dateRange.value.end
    )
    currentTaskId.value = result.task_id
    activeTaskId.value = result.task_id  // 同步全局 ProgressPanel
    startPolling()
  } catch (e) {
    error.value = e.message || '启动分析失败'
    analyzing.value = false
  }
}

function startPolling() {
  stopPolling()
  pollingTimer.value = setInterval(async () => {
    await loadEvents()
  }, 5000)
}

function stopPolling() {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
}

// Watch: 全局任务完成后停止轮询
watch(activeTaskId, (val, oldVal) => {
  if (oldVal && !val) {
    stopPolling()
    analyzing.value = false
    currentTaskId.value = ''
    loadEvents()
  }
})

function setFilter(type) {
  activeFilter.value = type
  loadEvents()
}

// Watch: 群切换时清理
watch(() => currentGroup.value?.id, (newId, oldId) => {
  if (newId && newId !== oldId) {
    stopPolling()
    analyzing.value = false
    currentTaskId.value = ''
    events.value = []
    dateRange.value = { start: '', end: '' }
    initDateRange().then(() => loadEvents())
  }
})

// Watch: 群切换
watch(() => currentGroup.value?.id, (newId, oldId) => {
  if (newId && newId !== oldId) {
    events.value = []
    dateRange.value = { start: '', end: '' }
    initDateRange().then(() => loadEvents())
  }
})

onMounted(async () => {
  await initDateRange()
  if (currentGroup.value) {
    await loadEvents()
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
        <Clock class="w-6 h-6 text-indigo-500" />
        事件时间轴
      </h1>
    </div>

    <!-- 时间范围选择 + 分析按钮 -->
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
          :disabled="analyzing"
          class="flex items-center gap-1.5 px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-colors"
        >
          <Loader2 v-if="analyzing" class="w-4 h-4 animate-spin" />
          <Search v-else class="w-4 h-4" />
          {{ analyzing ? '分析中...' : '开始分析事件' }}
        </button>
        <button
          v-if="events.length > 0 && !analyzing"
          @click="startDetection"
          class="text-sm text-slate-500 hover:text-indigo-600 transition-colors"
        >
          重新分析
        </button>
      </div>
    </div>

    <!-- 类型筛选 -->
    <div v-if="events.length > 0 || activeFilter" class="flex flex-wrap gap-2 mb-6">
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

    <!-- 加载状态 -->
    <div v-if="loading && !analyzing" class="flex items-center justify-center py-16">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <!-- 非分析中：错误/空状态 -->
    <template v-if="!analyzing">
      <div v-if="error" class="flex flex-col items-center justify-center py-16">
        <AlertCircle class="w-10 h-10 text-red-400 mb-4" />
        <p class="text-slate-600 mb-4">{{ error }}</p>
        <button @click="startDetection" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm hover:bg-indigo-700">重试</button>
      </div>

      <div v-else-if="!loading && events.length === 0 && !activeFilter"
           class="flex flex-col items-center justify-center py-16 text-slate-400">
        <Clock class="w-12 h-12 mb-4" />
        <p class="text-lg font-medium text-slate-500 mb-1">尚无事件数据</p>
        <p class="text-sm mb-4">选择时间范围，点击"开始分析事件"让 AI 从群聊中发现事件</p>
      </div>

      <div v-else-if="!loading && events.length === 0 && activeFilter"
           class="flex flex-col items-center justify-center py-16 text-slate-400">
        <p class="text-lg font-medium text-slate-500">该类型暂无事件</p>
        <button @click="setFilter('')" class="text-sm text-indigo-500 hover:underline mt-2">查看全部事件</button>
      </div>
    </template>

    <!-- 分析中：无事件 -->
    <div v-if="analyzing && events.length === 0" class="flex flex-col items-center justify-center py-16 text-slate-500">
      <Loader2 class="w-10 h-10 animate-spin text-indigo-400 mb-4" />
      <p>AI 正在分析群聊事件...</p>
      <p class="text-sm text-slate-400 mt-1">右下角可取消，事件将逐步出现</p>
    </div>

    <!-- 分析中 + 已有事件 -->
    <div v-if="analyzing && events.length > 0" class="mb-4 p-3 bg-indigo-50 rounded-lg text-sm text-indigo-600 flex items-center gap-2">
      <Loader2 class="w-4 h-4 animate-spin" />
      分析中，已发现 {{ events.length }} 个事件...
    </div>

    <!-- 事件时间轴（有事件时始终显示） -->
    <EventTimeline v-if="events.length > 0" :events="events" :group-id="currentGroup?.id" />
  </div>
</template>
