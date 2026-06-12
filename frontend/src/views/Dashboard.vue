<script setup>
import { ref, inject, watch, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  getDates, getRecentReports, getGroupStats, analyzeDateAsync, analyzeAll, getPortraits,
  getTaskHistory, getTrending, getPeriods, generateWeekly, generateMonthly, generateAnnual,
  generateAllWeekly, generateAllMonthly,
} from '../api/index.js'
import { MessageSquare, Users, Calendar, Sparkles, Loader2, Upload, Zap, CheckCircle2, XCircle, Clock, FileText, RefreshCw, ArrowRight } from 'lucide-vue-next'
import UploadModal from '../components/UploadModal.vue'

const router = useRouter()
const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')
const activeTaskId = inject('activeTaskId')
const showError = inject('showError')
const gid = computed(() => currentGroup.value?.id)

// 批量任务运行时定时刷新（逐个标绿）
let _refreshTimer = null
watch(activeTaskId, (newVal) => {
  if (newVal) {
    _refreshTimer = setInterval(() => loadAll(true), 3000)  // 静默刷新，不显示loading
  } else {
    if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null }
  }
})
onUnmounted(() => { if (_refreshTimer) clearInterval(_refreshTimer) })

const stats = ref(null)
const dates = ref([])
const recentReports = ref([])
const loading = ref(false)
const analyzing = ref(false)
const portraits = ref([])
const taskHistory = ref([])
const trending = ref(null)
const showUpload = ref(false)
const dayPopup = ref(null)  // { date, count, analyzed }
const dayPopupLoading = ref('')  // 'report' | 'settle'
const dayPopupError = ref('')  // v0.12.4: 内联错误提示
const monthOffset = ref(0)  // 日历翻页偏移：0=当月

// 防止快速切群时的竞态条件
let _loadVersion = 0

// 周报/月报/年报（按需加载，不在 polling 时调用）
const weeklyPeriods = ref([])
const monthlyPeriods = ref([])
const annualPeriods = ref([])
const periodsLoading = ref(false)
const periodsLoaded = ref(false)
const showPeriods = ref(true)   // 默认展开
const generatingPeriod = ref('')  // 正在生成的 period_key
// v0.12.0: 从设置页读取每日分析默认模型
function getDailyModelId() {
  const v = localStorage.getItem('dailyModelId')
  if (v === null || v === '') return null
  const n = Number(v)
  return isNaN(n) ? null : n
}
// v1.0.3: 分页展开（每次+10条）
const PAGE_SIZE = 10
const DEFAULT_SHOW = 8
const weeklyShowCount = ref(DEFAULT_SHOW)
const monthlyShowCount = ref(DEFAULT_SHOW)
function expandWeekly() {
  weeklyShowCount.value = Math.min(weeklyShowCount.value + PAGE_SIZE, weeklyPeriods.value.length)
}
function collapseWeekly() {
  weeklyShowCount.value = DEFAULT_SHOW
}
function expandMonthly() {
  monthlyShowCount.value = Math.min(monthlyShowCount.value + PAGE_SIZE, monthlyPeriods.value.length)
}
function collapseMonthly() {
  monthlyShowCount.value = DEFAULT_SHOW
}
const showAnnualConfirm = ref(false)  // 年报月报不足确认弹窗
const pendingAnnualYear = ref('')

async function loadAll(silent = false) {
  if (!currentGroup.value) return
  if (!silent) loading.value = true
  const gid = currentGroup.value.id
  const version = ++_loadVersion
  try {
    const results = await Promise.allSettled([
      getGroupStats(gid),
      getDates(gid),
      getRecentReports(gid, 14),
      getPortraits(gid),
      getTaskHistory(gid, 8),
      getTrending(gid, 7),
    ])
    if (version !== _loadVersion) return
    const [s, d, r, p, h, t] = results.map(r => r.status === 'fulfilled' ? r.value : null)
    // 数组字段失败时保持 []，避免模板中 .length / v-for 报错
    stats.value = s
    dates.value = Array.isArray(d) ? d : []
    recentReports.value = Array.isArray(r) ? r : []
    portraits.value = Array.isArray(p) ? p : []
    taskHistory.value = Array.isArray(h) ? h : []
    trending.value = t  // 对象，null 是合法的
  } catch (e) { console.error(e) }
  finally {
    if (version === _loadVersion) loading.value = false
  }
}

watch(currentGroup, () => { monthOffset.value = 0; loadAll(); loadPeriods() }, { immediate: true })

// 监听全局任务完成
watch(activeTaskId, (newVal, oldVal) => {
  if (oldVal && !newVal) {
    // 任务 ID 被清空 = 任务结束
    analyzing.value = false
    batchTotal.value = 0
    generatingPeriod.value = ''
    loadAll()
    triggerRefresh?.()
  }
})

// 最新未分析的一天（自动跳过消息太少 <5 的日期）
const latestUnanalyzed = ref(null)
const skippedDates = ref(new Set())
watch(dates, (d) => {
  const sorted = [...d].sort((a, b) => b.date.localeCompare(a.date))
  latestUnanalyzed.value = sorted.find(dt => !dt.analyzed && !skippedDates.value.has(dt.date) && dt.text_messages >= 5) || null
})

async function analyzeLatest() {
  if (!latestUnanalyzed.value || analyzing.value || activeTaskId.value) return
  analyzing.value = true
  const date = latestUnanalyzed.value.date
  try {
    const result = await analyzeDateAsync(currentGroup.value.id, date, getDailyModelId())
    if (result.skipped) {
      skippedDates.value.add(date)
      analyzing.value = false
      await loadAll()
    } else if (result.task_id) {
      activeTaskId.value = result.task_id
    } else if (result.cached) {
      await loadAll(); triggerRefresh?.(); analyzing.value = false
    }
  } catch (e) { showError?.('分析失败', e.message, e.stack, '仪表盘·分析最新'); analyzing.value = false }
}

const batchTotal = ref(0)

async function startAnalyzeAll() {
  if (analyzing.value || activeTaskId.value) return
  analyzing.value = true
  try {
    const result = await analyzeAll(currentGroup.value.id, getDailyModelId())
    if (result.task_id) {
      activeTaskId.value = result.task_id
      batchTotal.value = result.total_unanalyzed || 0
    } else if (result.total_unanalyzed === 0) {
      analyzing.value = false
    }
  } catch (e) { showError?.('批量分析失败', e.message, e.stack, '仪表盘·一键分析全部'); analyzing.value = false }
}

function onTaskDone(data) {
  if (data.status === 'done' || data.status === 'failed') {
    analyzing.value = false
    batchTotal.value = 0
    loadAll()
    triggerRefresh?.()
  }
}

function goReport(date) {
  router.push(`/report/${date}`)
}

function viewReportFromPopup() {
  const d = dayPopup.value.date
  dayPopup.value = null
  goReport(d)
}

function openDayPopup(day) {
  dayPopup.value = day
  dayPopupLoading.value = ''
  dayPopupError.value = ''
}

async function handleGenerateReport() {
  if (!dayPopup.value) return
  dayPopupLoading.value = 'report'
  try {
    const force = dayPopup.value.analyzed  // 已分析过 = 强制重新生成
    const result = await analyzeDateAsync(gid.value, dayPopup.value.date, getDailyModelId(), force)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    }
    dayPopup.value = null  // v0.12.4: 生成后自动关闭弹窗
    setTimeout(() => {
      if (gid.value) loadAll(true)
    }, 2000)
  } catch (e) { dayPopupError.value = e.message }
  finally { dayPopupLoading.value = '' }
}

async function handleResettleDay() {
  if (!dayPopup.value) return
  dayPopupLoading.value = 'settle'
  try {
    const { resettleFishPond } = await import('../api/index.js')
    await resettleFishPond(gid.value, dayPopup.value.date)
    dayPopup.value = null
  } catch (e) { dayPopupError.value = e.message }
  finally { dayPopupLoading.value = '' }
}

// ---- 月视图日历（分月翻页） ----
const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

// 构建 日期字符串 -> 日期信息 的索引
const dateMap = computed(() => {
  const m = {}
  for (const d of dates.value) {
    m[d.date] = d
  }
  return m
})

// 根据 stats.group 得到有数据的月份范围
const dataRange = computed(() => {
  const s = stats.value?.group
  if (!s?.date_range_start || !s?.date_range_end) return null
  return { start: new Date(s.date_range_start), end: new Date(s.date_range_end) }
})

// 当前展示的月份
const displayMonth = computed(() => {
  const now = new Date()
  const m = now.getMonth() + monthOffset.value
  const y = now.getFullYear() + Math.floor(m / 12)
  const mm = ((m % 12) + 12) % 12
  return new Date(y, mm, 1)
})

// 是否有上月/下月（限制在数据范围内）
const canGoPrev = computed(() => {
  if (!dataRange.value) return false
  const prev = new Date(displayMonth.value.getFullYear(), displayMonth.value.getMonth() - 1, 1)
  return prev >= new Date(dataRange.value.start.getFullYear(), dataRange.value.start.getMonth(), 1)
})

const canGoNext = computed(() => {
  if (!dataRange.value) return false
  const next = new Date(displayMonth.value.getFullYear(), displayMonth.value.getMonth() + 1, 1)
  return next <= new Date(dataRange.value.end.getFullYear(), dataRange.value.end.getMonth(), 1)
})

function goPrevMonth() { if (canGoPrev.value) monthOffset.value-- }
function goNextMonth() { if (canGoNext.value) monthOffset.value++ }

// 生成当前展示月份的日历网格
const calendarWeeks = computed(() => {
  const year = displayMonth.value.getFullYear()
  const month = displayMonth.value.getMonth()
  const firstDay = new Date(year, month, 1)
  const lastDay = new Date(year, month + 1, 0)
  const range = dataRange.value

  const weeks = []
  let currentWeek = []
  // 补齐第一周空白天（周一=0, 周日=6）
  let dow = firstDay.getDay()
  dow = dow === 0 ? 6 : dow - 1
  for (let i = 0; i < dow; i++) currentWeek.push(null)

  for (let d = 1; d <= lastDay.getDate(); d++) {
    const dateObj = new Date(year, month, d)
    // 用本地时间格式化，避免 UTC 时区偏移导致日期差一天
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const info = dateMap.value[dateStr]
    const inRange = range ? dateObj >= range.start && dateObj <= range.end : false

    currentWeek.push({
      date: dateStr,
      day: d,
      hasData: !!info,
      analyzed: info?.analyzed || false,
      count: info?.total_messages || 0,
      inRange,
    })

    if (currentWeek.length === 7) { weeks.push(currentWeek); currentWeek = [] }
  }
  if (currentWeek.length > 0) {
    while (currentWeek.length < 7) currentWeek.push(null)
    weeks.push(currentWeek)
  }
  return weeks
})

// 情绪 emoji
const moodIcons = { '欢乐':'😄','温馨':'🥰','严肃':'🧐','吐槽':'😤','平淡':'😐','热闹':'🎉','伤感':'😢','沙雕':'🤪','吃瓜':'🍉','摸鱼':'🎣','摆烂':'🫠','内卷':'💪','开车':'🚗','破防':'💔','凡尔赛':'👑','社死':'💀','真香':'🍚','画饼':'🫓','CPU':'🔥','离谱':'👽','上头':'🤯' }

// 按需加载周报/月报可用时段
async function loadPeriods() {
  if (!currentGroup.value || periodsLoading.value) return
  periodsLoading.value = true
  try {
    const [wp, mp, ap] = await Promise.all([
      getPeriods(currentGroup.value.id, 'weekly').catch(() => []),
      getPeriods(currentGroup.value.id, 'monthly').catch(() => []),
      getPeriods(currentGroup.value.id, 'annual').catch(() => []),
    ])
    weeklyPeriods.value = wp || []
    monthlyPeriods.value = mp || []
    annualPeriods.value = ap || []
    periodsLoaded.value = true
  } catch (e) { console.error(e) }
  finally { periodsLoading.value = false }
}

function togglePeriods() {
  showPeriods.value = !showPeriods.value
  if (!periodsLoaded.value) loadPeriods()
}

// 生成周报
async function doGenerateWeekly(periodKey, force = false) {
  if (generatingPeriod.value || activeTaskId.value) return
  generatingPeriod.value = periodKey
  try {
    const result = await generateWeekly(currentGroup.value.id, periodKey, force)
    if (result?.task_id) {
      activeTaskId.value = result.task_id
    } else {
      generatingPeriod.value = ''  // v1.0.3: 防御性复位
    }
  } catch (e) { showError?.('周报生成失败', e.message, e.stack, '仪表盘·生成周报'); generatingPeriod.value = '' }
}

// 生成月报
async function doGenerateMonthly(periodKey, force = false) {
  if (generatingPeriod.value || activeTaskId.value) return
  generatingPeriod.value = periodKey
  try {
    const result = await generateMonthly(currentGroup.value.id, periodKey, force)
    if (result?.task_id) {
      activeTaskId.value = result.task_id
    } else {
      generatingPeriod.value = ''  // v1.0.3: 防御性复位
    }
  } catch (e) { showError?.('月报生成失败', e.message, e.stack, '仪表盘·生成月报'); generatingPeriod.value = '' }
}

// v1.0.3: 一键生成全部周报/月报
async function doGenerateAllWeekly() {
  if (generatingPeriod.value || activeTaskId.value) return
  const ready = weeklyPeriods.value.filter(p => p.status === 'ready')
  if (!ready.length) return
  generatingPeriod.value = 'weekly-all'
  try {
    const result = await generateAllWeekly(currentGroup.value.id)
    if (result?.task_id) {
      activeTaskId.value = result.task_id
    } else {
      generatingPeriod.value = ''
    }
  } catch (e) { showError?.('批量周报生成失败', e.message, e.stack, '仪表盘·一键生成周报'); generatingPeriod.value = '' }
}

async function doGenerateAllMonthly() {
  if (generatingPeriod.value || activeTaskId.value) return
  const ready = monthlyPeriods.value.filter(p => p.status === 'ready')
  if (!ready.length) return
  generatingPeriod.value = 'monthly-all'
  try {
    const result = await generateAllMonthly(currentGroup.value.id)
    if (result?.task_id) {
      activeTaskId.value = result.task_id
    } else {
      generatingPeriod.value = ''
    }
  } catch (e) { showError?.('批量月报生成失败', e.message, e.stack, '仪表盘·一键生成月报'); generatingPeriod.value = '' }
}

// 导航到周报/月报/年报详情
function goWeekly(key) { router.push(`/weekly/${key}`) }
function goMonthly(key) { router.push(`/monthly/${key}`) }
function goAnnual(key) { router.push(`/annual/${key}`) }

// 生成年度报告（先检查月报数量）
async function doGenerateAnnual(periodKey, force = false) {
  if (generatingPeriod.value || activeTaskId.value) return
  // 检查该年月报是否充足（>=6个月有月报）
  const yearMonthly = monthlyPeriods.value.filter(p => {
    const pYear = p.period_key.split('-')[0]
    return pYear === periodKey && p.status === 'generated'
  })
  if (yearMonthly.length < 6 && !force) {
    pendingAnnualYear.value = periodKey
    showAnnualConfirm.value = true
    return
  }
  await _executeAnnualGenerate(periodKey, force)
}

async function _executeAnnualGenerate(periodKey, force = false) {
  showAnnualConfirm.value = false
  generatingPeriod.value = periodKey
  try {
    const result = await generateAnnual(currentGroup.value.id, parseInt(periodKey), force)
    if (result?.task_id) {
      activeTaskId.value = result.task_id
    } else {
      // API 返回 code=200 但 data=null（如数据不足），清除 generating 状态
      generatingPeriod.value = ''
    }
  } catch (e) { showError?.('年报生成失败', e.message, e.stack, '仪表盘·生成年报'); generatingPeriod.value = '' }
}

</script>

<template>
  <div v-if="currentGroup">
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <template v-else>
      <!-- 数据日期横幅 -->
      <div v-if="stats?.group?.date_range_start" class="card p-3 mb-5 flex items-center gap-2 text-sm text-slate-500 flex-wrap">
        <span class="text-base">📅</span>
        <span class="font-medium text-slate-700">数据范围：{{ stats.group.date_range_start }} ~ {{ stats.group.date_range_end }}</span>
        <span class="text-slate-200">|</span>
        <span>共 <strong class="text-slate-700">{{ stats.total_days_with_data }}</strong> 天有消息</span>
        <span class="text-slate-200">|</span>
        <span>已分析 <strong class="text-emerald-600">{{ stats.analyzed_count }}</strong> 天</span>
        <template v-if="stats.analyzed_count > 0">
          <span class="text-slate-200">|</span>
          <span class="flex items-center gap-1.5">
            进度
            <span class="inline-block w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <span class="block h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-500"
                :style="{ width: `${stats.progress_pct}%` }"></span>
            </span>
            <strong class="text-indigo-600">{{ stats.progress_pct }}%</strong>
          </span>
        </template>
      </div>

      <!-- 概览卡片 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6 stagger">
        <div class="card p-4 flex items-center gap-3 group cursor-default">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-100 to-indigo-200 flex items-center justify-center group-hover:scale-105 transition-transform">
            <MessageSquare class="w-5 h-5 text-indigo-600" />
          </div>
          <div>
            <div class="text-2xl font-bold text-slate-800 stat-ticker">{{ (stats?.group?.message_count || 0).toLocaleString() }}</div>
            <div class="text-xs text-slate-400">总消息数</div>
          </div>
        </div>

        <div class="card p-4 flex items-center gap-3 group cursor-default">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-100 to-teal-100 flex items-center justify-center group-hover:scale-105 transition-transform">
            <Calendar class="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <div class="text-2xl font-bold text-slate-800 stat-ticker">{{ stats?.analyzed_count || 0 }}<span class="text-base font-normal text-slate-400">/{{ dates.length }}</span></div>
            <div class="text-xs text-slate-400">已分析天数</div>
          </div>
        </div>

        <div class="card p-4 flex items-center gap-3 group cursor-default">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-100 to-orange-100 flex items-center justify-center group-hover:scale-105 transition-transform">
            <Users class="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <div class="text-2xl font-bold text-slate-800 stat-ticker">{{ stats?.member_count || 0 }}</div>
            <div class="text-xs text-slate-400">群成员</div>
          </div>
        </div>

        <div class="card p-4 flex items-center gap-3 group cursor-default">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-rose-100 to-pink-100 flex items-center justify-center group-hover:scale-105 transition-transform">
            <Sparkles class="w-5 h-5 text-rose-600" />
          </div>
          <div>
            <div class="text-lg font-bold text-slate-800 truncate max-w-[100px]">
              {{ portraits.length > 0 ? portraits[0]?.portrait?.one_line : '—' }}
            </div>
            <div class="text-xs text-slate-400">已有画像</div>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- 左列：日历 + 分析按钮 -->
        <div class="lg:col-span-2 space-y-6">
          <!-- 操作按钮行 -->
          <div class="card p-4 flex items-center justify-between gap-4">
            <div class="flex-1 min-w-0">
              <div class="font-semibold text-slate-700 flex items-center gap-2">
                每日分析
                <span v-if="latestUnanalyzed" class="w-1.5 h-1.5 rounded-full bg-amber-400 pulse-dot"></span>
                <span v-else class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>
              </div>
              <div class="text-sm text-slate-400 mt-0.5 truncate">
                最新未分析：
                <span class="font-medium text-slate-600">{{ latestUnanalyzed?.date || '全部已分析 ✅' }}</span>
                <span v-if="latestUnanalyzed" class="ml-2">({{ latestUnanalyzed.text_messages }} 条文本)</span>
              </div>
            </div>
            <div class="flex items-center gap-2 flex-shrink-0">
              <button
                @click="showUpload = true"
                class="flex items-center gap-1.5 px-3 py-2 rounded-xl text-sm text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 transition-colors border border-slate-200 hover:border-indigo-200"
                title="追加导入数据"
              >
                <Upload class="w-4 h-4" />
                <span class="hidden sm:inline">导入数据</span>
              </button>
              <button
                v-if="(stats?.total_days_with_data - (stats?.analyzed_count || 0)) > 1"
                @click="startAnalyzeAll"
                :disabled="analyzing"
                :class="[
                  'flex items-center gap-2 px-4 py-2.5 rounded-xl font-medium text-sm transition-all active:scale-[0.98]',
                  !analyzing
                    ? 'bg-gradient-to-r from-emerald-500 to-teal-600 text-white hover:from-emerald-600 hover:to-teal-700 shadow-lg shadow-emerald-200'
                    : 'bg-slate-100 text-slate-400',
                ]"
                title="从新到旧逐天分析全部未分析日期"
              >
                <Zap class="w-4 h-4" />
                一键分析全部
              </button>
            </div>
          </div>

          <!-- 月视图日历（分月翻页） -->
          <div class="card p-4">
            <div class="flex items-center justify-between mb-3">
              <h3 class="font-semibold text-slate-700">数据日历</h3>
              <!-- 翻页按钮 -->
              <div class="flex items-center gap-1">
                <button @click="goPrevMonth" :disabled="!canGoPrev"
                        :class="['px-2 py-1 text-xs rounded-lg transition-colors', canGoPrev ? 'hover:bg-slate-100 text-slate-600' : 'text-slate-300 cursor-not-allowed']">
                  ◀
                </button>
                <span class="text-sm font-medium text-slate-700 min-w-[80px] text-center">
                  {{ displayMonth.getFullYear() }}年{{ displayMonth.getMonth() + 1 }}月
                </span>
                <button @click="goNextMonth" :disabled="!canGoNext"
                        :class="['px-2 py-1 text-xs rounded-lg transition-colors', canGoNext ? 'hover:bg-slate-100 text-slate-600' : 'text-slate-300 cursor-not-allowed']">
                  ▶
                </button>
              </div>
            </div>

            <!-- 星期表头 -->
            <div class="grid grid-cols-7 mb-1">
              <div v-for="wd in WEEKDAYS" :key="wd"
                   :class="['text-center text-[10px]', wd === '六' || wd === '日' ? 'text-slate-300' : 'text-slate-400']">
                {{ wd }}
              </div>
            </div>

            <!-- 日格子 -->
            <div v-for="(week, wi) in calendarWeeks" :key="wi" class="grid grid-cols-7 gap-[2px]">
              <div v-for="(day, di) in week" :key="di"
                   :title="day ? `${day.date}: ${day.count}条消息${day.analyzed ? ' (已分析)' : day.hasData ? ' (未分析)' : ''}` : ''"
                   :class="[
                     'aspect-square rounded-[3px] flex items-center justify-center text-[11px] transition-colors',
                     !day ? '' :
                     !day.inRange ? 'bg-slate-50 text-transparent' :
                     day.analyzed ? 'bg-emerald-100 text-emerald-700 font-medium cursor-pointer hover:bg-emerald-200' :
                     day.hasData ? 'bg-indigo-50 text-indigo-400 cursor-pointer hover:bg-indigo-100' :
                     'bg-slate-50 text-transparent',
                   ]"
                   @click="day?.hasData && openDayPopup(day)">
                {{ day ? day.day : '' }}
              </div>
            </div>

            <div v-if="calendarWeeks.length === 0" class="text-sm text-slate-400 py-4 text-center">
              暂无数据，请先导入群聊 JSON 文件
            </div>

            <!-- 图例 -->
            <div class="flex items-center gap-4 mt-4 pt-3 border-t border-slate-100 text-xs text-slate-400">
              <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-slate-50 border border-slate-100" /> 无数据</span>
              <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-indigo-50 border border-indigo-100" /> 有数据</span>
              <span class="flex items-center gap-1"><span class="w-3 h-3 rounded-sm bg-emerald-100 border border-emerald-200" /> 已分析</span>
              <span class="ml-auto text-slate-300">点击已分析日期查看报告</span>
            </div>
          </div>

          <!-- 最近报告列表 -->
          <div class="card p-4">
            <div class="flex items-center justify-between mb-3">
              <h3 class="font-semibold text-slate-700">最近报告</h3>
              <span class="text-[10px] text-slate-300">{{ recentReports.length }}篇</span>
            </div>
            <div v-if="recentReports.length === 0" class="text-sm text-slate-400 py-8 text-center">
              <div class="text-3xl mb-2">📝</div>
              还没有分析过，点击"分析最新一天"开始吧
            </div>
            <div v-else class="space-y-1.5">
              <button
                v-for="r in recentReports.slice(0, 7)"
                :key="r.date"
                @click="goReport(r.date)"
                class="w-full text-left card p-3 hover:border-indigo-200 transition-all flex items-center gap-3 group hover:shadow-md"
              >
                <span class="text-2xl flex-shrink-0 group-hover:scale-110 transition-transform">{{ r.mood_emoji || '💬' }}</span>
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium text-slate-700 truncate group-hover:text-indigo-600 transition-colors">
                    {{ r.one_line || r.date }}
                  </div>
                  <div class="text-xs text-slate-400 mt-0.5">
                    {{ r.date }} · {{ r.message_count }} 条消息 · {{ r.active_members }} 人活跃
                  </div>
                </div>
                <div class="flex gap-1 flex-shrink-0">
                  <span
                    v-for="kw in (r.keywords || []).slice(0, 3)"
                    :key="kw"
                    class="px-2 py-0.5 bg-slate-50 text-slate-400 rounded-full text-[10px] font-medium border border-slate-100"
                  >{{ kw }}</span>
                </div>
                <ArrowRight class="w-3.5 h-3.5 text-slate-300 group-hover:text-indigo-400 group-hover:translate-x-0.5 transition-all flex-shrink-0" />
              </button>
            </div>
          </div>
        </div>

        <!-- 右列：统计 -->
        <div class="space-y-6">
          <!-- 群聊热搜榜 -->
          <div v-if="trending?.topics?.length" class="card p-4 bg-gradient-to-b from-red-50 to-white">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-1.5">
              <span class="text-lg">🔥</span> 群聊热搜 <span class="text-xs text-slate-400 font-normal ml-auto">{{ trending.period }}</span>
            </h3>
            <div class="space-y-1">
              <div
                v-for="(t, i) in trending.topics.slice(0, 8)"
                :key="i"
                class="flex items-center gap-2 text-sm py-1.5 px-2 rounded-lg hover:bg-red-50/50 transition-colors"
              >
                <span :class="[
                  'w-5 h-5 rounded text-[11px] font-bold flex items-center justify-center flex-shrink-0',
                  i === 0 ? 'bg-red-500 text-white' :
                  i === 1 ? 'bg-orange-400 text-white' :
                  i === 2 ? 'bg-amber-400 text-white' :
                  'bg-slate-200 text-slate-500',
                ]">{{ i + 1 }}</span>
                <span class="flex-1 text-slate-700 truncate">{{ t.text }}</span>
                <span class="text-xs text-slate-400 flex-shrink-0">{{ t.heat }}℃</span>
                <span v-if="t.trend === 'new'" class="text-[10px] bg-green-100 text-green-600 px-1 rounded">新</span>
                <span v-else-if="t.trend === 'hot'" class="text-[10px] bg-red-100 text-red-500 px-1 rounded">沸</span>
                <span v-else-if="t.trend === 'up'" class="text-[10px] bg-orange-100 text-orange-500 px-1 rounded">↑</span>
              </div>
            </div>
          </div>

          <!-- 周报/月报（按需加载，点击展开） -->
          <div class="card p-4">
            <button
              @click="togglePeriods"
              class="w-full flex items-center justify-between"
            >
              <h3 class="font-semibold text-slate-700 flex items-center gap-2 text-sm">
                <span class="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-50 to-purple-50 flex items-center justify-center">
                  <FileText class="w-4 h-4 text-indigo-500" />
                </span>
                周报/月报
                <span v-if="weeklyPeriods.length + monthlyPeriods.length > 0"
                  class="text-[10px] text-slate-300 font-normal ml-1"
                >{{ weeklyPeriods.filter(p=>p.status==='ready').length + monthlyPeriods.filter(p=>p.status==='ready').length }}篇待生成</span>
              </h3>
              <span class="text-[10px] text-slate-300 px-2 py-0.5 rounded-full bg-slate-50 transition-colors">
                {{ showPeriods ? '收起 ▲' : '展开 ▼' }}
              </span>
            </button>

            <div v-if="showPeriods" class="mt-4 space-y-5 animate-slide-down">
              <div v-if="periodsLoading" class="text-xs text-slate-400 py-4 text-center">
                <Loader2 class="w-3.5 h-3.5 animate-spin inline mr-1.5" /> 加载时段列表...
              </div>

              <!-- 周报列表 -->
              <div v-if="weeklyPeriods.length > 0">
                <div class="flex items-center gap-2 mb-2.5">
                  <span class="text-xs font-semibold text-slate-500 tracking-wide">📊 自然周</span>
                  <span class="text-[10px] text-slate-300">{{ weeklyPeriods.filter(p=>p.status==='generated').length }}/{{ weeklyPeriods.length }}已生成</span>
                  <button v-if="weeklyPeriods.some(p=>p.status==='ready')"
                    @click="doGenerateAllWeekly"
                    :disabled="!!generatingPeriod || !!activeTaskId"
                    class="text-[10px] bg-indigo-50 text-indigo-500 px-1.5 py-0.5 rounded-full hover:bg-indigo-100 disabled:opacity-40 transition-colors flex items-center gap-0.5 ml-auto"
                    title="一键生成全部未生成的周报（从新到旧）"
                  ><Zap :size="10" /> 一键生成</button>
                </div>
                <div class="space-y-1 max-h-48 overflow-y-auto">
                  <div
                    v-for="p in weeklyPeriods.slice(0, weeklyShowCount)"
                    :key="'w'+p.period_key"
                    class="flex items-center gap-2.5 text-xs py-1.5 px-2.5 rounded-lg transition-all"
                    :class="p.status === 'generated' ? 'hover:bg-indigo-50 cursor-pointer border border-transparent hover:border-indigo-100' : p.status === 'ready' ? 'bg-amber-50/40 border border-amber-100/50' : 'opacity-35'"
                    @click="p.status === 'generated' ? goWeekly(p.period_key) : null"
                  >
                    <span class="font-mono font-medium text-slate-600 w-16 flex-shrink-0">{{ p.period_key }}</span>
                    <span class="flex-1 text-slate-400">{{ p.day_count }}天</span>
                    <template v-if="p.status === 'generated'">
                      <span class="text-[10px] bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded-full font-medium cursor-pointer border border-emerald-100" @click.stop="goWeekly(p.period_key)">已生成</span>
                      <button
                        @click.stop="doGenerateWeekly(p.period_key, true)"
                        :disabled="!!generatingPeriod || !!activeTaskId"
                        class="text-[10px] bg-amber-50 text-amber-600 px-1.5 py-0.5 rounded-full hover:bg-amber-100 disabled:opacity-40 transition-colors font-medium border border-amber-100"
                        title="重新生成"
                      >↻ 重生成</button>
                    </template>
                    <button
                      v-else-if="p.status === 'ready'"
                      @click.stop="doGenerateWeekly(p.period_key)"
                      :disabled="!!generatingPeriod || !!activeTaskId"
                      class="text-[10px] bg-indigo-500 text-white px-2 py-0.5 rounded-full hover:bg-indigo-600 disabled:opacity-40 transition-colors font-medium"
                    >生成</button>
                    <span v-else class="text-[10px] text-slate-300 font-medium">不足</span>
                  </div>
                </div>
                <button v-if="weeklyShowCount < weeklyPeriods.length"
                  @click="expandWeekly"
                  class="w-full text-[10px] text-slate-400 hover:text-indigo-500 py-1 mt-1 transition-colors">
                  展开更多 ({{ weeklyShowCount }}/{{ weeklyPeriods.length }}) ▼
                </button>
                <button v-if="weeklyShowCount >= weeklyPeriods.length && weeklyPeriods.length > DEFAULT_SHOW"
                  @click="collapseWeekly"
                  class="w-full text-[10px] text-slate-400 hover:text-indigo-500 py-1 mt-1 transition-colors">
                  收起 ▲
                </button>
              </div>

              <!-- 月报列表 -->
              <div v-if="monthlyPeriods.length > 0">
                <div class="flex items-center gap-2 mb-2.5">
                  <span class="text-xs font-semibold text-slate-500 tracking-wide">📅 自然月</span>
                  <span class="text-[10px] text-slate-300">{{ monthlyPeriods.filter(p=>p.status==='generated').length }}/{{ monthlyPeriods.length }}已生成</span>
                  <button v-if="monthlyPeriods.some(p=>p.status==='ready')"
                    @click="doGenerateAllMonthly"
                    :disabled="!!generatingPeriod || !!activeTaskId"
                    class="text-[10px] bg-indigo-50 text-indigo-500 px-1.5 py-0.5 rounded-full hover:bg-indigo-100 disabled:opacity-40 transition-colors flex items-center gap-0.5 ml-auto"
                    title="一键生成全部未生成的月报（从新到旧）"
                  ><Zap :size="10" /> 一键生成</button>
                </div>
                <div class="space-y-1 max-h-48 overflow-y-auto">
                  <div
                    v-for="p in monthlyPeriods.slice(0, monthlyShowCount)"
                    :key="'m'+p.period_key"
                    class="flex items-center gap-2.5 text-xs py-1.5 px-2.5 rounded-lg transition-all"
                    :class="p.status === 'generated' ? 'hover:bg-purple-50 cursor-pointer border border-transparent hover:border-purple-100' : p.status === 'ready' ? 'bg-amber-50/40 border border-amber-100/50' : 'opacity-35'"
                    @click="p.status === 'generated' ? goMonthly(p.period_key) : null"
                  >
                    <span class="font-mono font-medium text-slate-600 w-16 flex-shrink-0">{{ p.period_key }}</span>
                    <span class="flex-1 text-slate-400">{{ p.day_count }}天</span>
                    <template v-if="p.status === 'generated'">
                      <span class="text-[10px] bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded-full font-medium cursor-pointer border border-emerald-100" @click.stop="goMonthly(p.period_key)">已生成</span>
                      <button
                        @click.stop="doGenerateMonthly(p.period_key, true)"
                        :disabled="!!generatingPeriod || !!activeTaskId"
                        class="text-[10px] bg-amber-50 text-amber-600 px-1.5 py-0.5 rounded-full hover:bg-amber-100 disabled:opacity-40 transition-colors font-medium border border-amber-100"
                        title="重新生成"
                      >↻ 重生成</button>
                    </template>
                    <button
                      v-else-if="p.status === 'ready'"
                      @click.stop="doGenerateMonthly(p.period_key)"
                      :disabled="!!generatingPeriod || !!activeTaskId"
                      class="text-[10px] bg-purple-500 text-white px-2 py-0.5 rounded-full hover:bg-purple-600 disabled:opacity-40 transition-colors font-medium"
                    >生成</button>
                    <span v-else class="text-[10px] text-slate-300 font-medium">不足</span>
                  </div>
                </div>
                <button v-if="monthlyShowCount < monthlyPeriods.length"
                  @click="expandMonthly"
                  class="w-full text-[10px] text-slate-400 hover:text-purple-500 py-1 mt-1 transition-colors">
                  展开更多 ({{ monthlyShowCount }}/{{ monthlyPeriods.length }}) ▼
                </button>
                <button v-if="monthlyShowCount >= monthlyPeriods.length && monthlyPeriods.length > DEFAULT_SHOW"
                  @click="collapseMonthly"
                  class="w-full text-[10px] text-slate-400 hover:text-purple-500 py-1 mt-1 transition-colors">
                  收起 ▲
                </button>
              </div>

              <!-- 年报列表 -->
              <div v-if="annualPeriods.length > 0">
                <div class="flex items-center gap-2 mb-2.5">
                  <span class="text-xs font-semibold text-slate-500 tracking-wide">🏆 年度报告</span>
                  <span class="text-[10px] text-slate-300">{{ annualPeriods.filter(p=>p.status==='generated').length }}/{{ annualPeriods.length }}已生成</span>
                </div>
                <div class="space-y-1 max-h-32 overflow-y-auto">
                  <div
                    v-for="p in annualPeriods.slice(0, 5)"
                    :key="'a'+p.period_key"
                    class="flex items-center gap-2.5 text-xs py-1.5 px-2.5 rounded-lg transition-all"
                    :class="p.status === 'generated' ? 'hover:bg-amber-50 cursor-pointer border border-transparent hover:border-amber-100' : p.status === 'ready' ? 'bg-amber-50/40 border border-amber-100/50' : 'opacity-35'"
                    @click="p.status === 'generated' ? goAnnual(p.period_key) : null"
                  >
                    <span class="font-mono font-medium text-slate-600 w-16 flex-shrink-0">{{ p.period_key }}年</span>
                    <span class="flex-1 text-slate-400">{{ p.day_count }}天</span>
                    <template v-if="p.status === 'generated'">
                      <span class="text-[10px] bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded-full font-medium cursor-pointer border border-emerald-100" @click.stop="goAnnual(p.period_key)">已生成</span>
                      <button
                        @click.stop="doGenerateAnnual(p.period_key, true)"
                        :disabled="!!generatingPeriod || !!activeTaskId"
                        class="text-[10px] bg-amber-50 text-amber-600 px-1.5 py-0.5 rounded-full hover:bg-amber-100 disabled:opacity-40 transition-colors font-medium border border-amber-100"
                        title="重新生成"
                      >↻ 重生成</button>
                    </template>
                    <button
                      v-else-if="p.status === 'ready'"
                      @click.stop="doGenerateAnnual(p.period_key)"
                      :disabled="!!generatingPeriod || !!activeTaskId"
                      class="text-[10px] bg-amber-500 text-white px-2 py-0.5 rounded-full hover:bg-amber-600 disabled:opacity-40 transition-colors font-medium"
                    >生成</button>
                    <span v-else class="text-[10px] text-slate-300 font-medium">不足</span>
                  </div>
                </div>
              </div>

              <div v-if="!periodsLoading && weeklyPeriods.length === 0 && monthlyPeriods.length === 0 && annualPeriods.length === 0"
                   class="text-xs text-slate-400 py-4 text-center bg-slate-50 rounded-xl">
                📭 暂无足够的日报数据<br>
                <span class="text-[10px] text-slate-300">至少需要3天日报才能生成周报</span>
              </div>
            </div>
          </div>

          <!-- 情绪分布 -->
          <div v-if="stats?.mood_distribution" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-3">情绪分布</h3>
            <div class="space-y-2">
              <div
                v-for="(cnt, mood) in stats.mood_distribution"
                :key="mood"
                class="flex items-center justify-between text-sm"
              >
                <span class="text-slate-600">{{ moodIcons[mood] || '💬' }} {{ mood }}</span>
                <span class="font-medium text-slate-700">{{ cnt }}天</span>
              </div>
            </div>
            <div v-if="Object.keys(stats.mood_distribution).length === 0" class="text-sm text-slate-400 py-2">
              尚未分析，暂无情绪数据
            </div>
          </div>

          <!-- 群友活跃榜 -->
          <div v-if="stats?.member_ranking" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-3">发言排行 TOP 8</h3>
            <div class="space-y-1.5">
              <div
                v-for="(m, i) in stats.member_ranking.slice(0, 8)"
                :key="m.id"
                class="flex items-center gap-2.5 text-sm"
              >
                <span :class="[
                  'w-5 h-5 rounded-full text-[11px] font-bold flex items-center justify-center',
                  i === 0 ? 'bg-amber-100 text-amber-700' :
                  i === 1 ? 'bg-slate-200 text-slate-600' :
                  i === 2 ? 'bg-orange-100 text-orange-700' :
                  'text-slate-400',
                ]">{{ i + 1 }}</span>
                <span class="flex-1 text-slate-700 truncate">{{ m.display_name || m.remark || m.nickname }}</span>
                <span class="text-slate-400 font-mono text-xs">{{ m.message_count }}</span>
              </div>
            </div>
          </div>

          <!-- 最近任务 -->
          <div v-if="taskHistory.length > 0" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-1.5">
              <Clock class="w-4 h-4" /> 最近任务
            </h3>
            <div class="space-y-2">
              <div
                v-for="t in taskHistory.slice(0, 5)"
                :key="t.task_id"
                class="flex items-center gap-2 text-xs"
              >
                <CheckCircle2 v-if="t.status === 'done'" class="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
                <XCircle v-else-if="t.status === 'failed'" class="w-3.5 h-3.5 text-red-400 flex-shrink-0" />
                <Loader2 v-else class="w-3.5 h-3.5 text-slate-300 flex-shrink-0" />
                <div class="flex-1 min-w-0">
                  <div class="text-slate-600 truncate">{{ t.target }}</div>
                  <div class="text-slate-400">
                    {{ t.task_type === 'analyze_day' ? '日报' : t.task_type === 'analyze_all' ? '批量日报' : t.task_type === 'generate_weekly' ? '周报' : t.task_type === 'generate_monthly' ? '月报' : t.task_type === 'generate_annual' ? '年报' : t.task_type === 'full_portrait' ? '画像' : t.task_type === 'analyze_all_portraits' ? '批量画像' : t.task_type || '分析' }}
                    <span v-if="t.total_duration_ms"> · {{ (t.total_duration_ms / 1000).toFixed(0) }}s</span>
                    <span v-if="t.error_summary" class="text-red-400"> · {{ t.error_summary }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 导入数据弹窗（群内导入） -->
    <UploadModal
      v-if="showUpload"
      :group="currentGroup"
      @close="showUpload = false"
      @uploaded="showUpload = false; loadAll(); triggerRefresh?.()"
    />

    <!-- 日历日期弹窗 -->
    <Teleport to="body">
      <div v-if="dayPopup" class="fixed inset-0 z-50 flex items-center justify-center bg-black/30" @click.self="dayPopup = null">
        <div class="bg-white rounded-2xl shadow-2xl w-[360px] overflow-hidden">
          <div class="px-5 py-4 border-b border-slate-100">
            <h3 class="font-bold text-slate-800 text-lg">{{ dayPopup.date }}</h3>
            <p class="text-sm text-slate-400 mt-0.5">
              {{ dayPopup.count }} 条消息
              <span v-if="dayPopup.analyzed" class="text-emerald-500 ml-2">· 已分析</span>
              <span v-else class="text-amber-500 ml-2">· 未分析</span>
            </p>
          </div>
          <div class="px-5 py-4 space-y-3">
            <!-- v0.12.4: 内联错误提示 -->
            <div v-if="dayPopupError" class="mx-5 mb-2 px-3 py-2 bg-red-50 border border-red-200 rounded-lg text-sm text-red-600 flex items-center gap-2">
              <XCircle :size="14" class="flex-shrink-0" />
              {{ dayPopupError }}
              <button @click="dayPopupError = ''" class="ml-auto text-red-400 hover:text-red-600">
                <X :size="14" />
              </button>
            </div>
            <!-- 已分析：查看日报（主按钮） -->
            <button v-if="dayPopup.analyzed" @click="viewReportFromPopup"
              class="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-bold
                     bg-gradient-to-r from-indigo-600 to-purple-600 text-white hover:from-indigo-700 hover:to-purple-700 transition shadow-lg shadow-indigo-200 active:scale-[0.98]">
              <FileText :size="16" />
              查看群聊日报
            </button>
            <button @click="handleGenerateReport" :disabled="!!dayPopupLoading"
              class="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium
                     bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 transition shadow-sm">
              <Sparkles :size="16" :class="{ 'animate-spin': dayPopupLoading === 'report' }" />
              {{ dayPopupLoading === 'report' ? '提交中...' : dayPopup.analyzed ? '重新生成群聊日报' : '生成群聊日报' }}
            </button>
            <button @click="handleResettleDay" :disabled="!!dayPopupLoading"
              class="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl text-sm font-medium
                     bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50 transition shadow-sm">
              <RefreshCw :size="16" :class="{ 'animate-spin': dayPopupLoading === 'settle' }" />
              {{ dayPopupLoading === 'settle' ? '结算中...' : '结算鱼塘' }}
            </button>
          </div>
          <div class="px-5 py-3 border-t border-slate-100">
            <button @click="dayPopup = null"
              class="w-full px-4 py-2 text-sm text-slate-500 hover:bg-slate-50 rounded-lg transition">
              关闭
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 年报月报不足确认弹窗 -->
    <Teleport to="body">
      <div v-if="showAnnualConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="showAnnualConfirm = false">
        <div class="bg-white rounded-2xl shadow-2xl w-[400px] overflow-hidden animate-scale-in">
          <div class="px-6 py-5 text-center">
            <div class="text-5xl mb-4">📊</div>
            <h3 class="text-lg font-bold text-slate-800 mb-2">建议先生成月报</h3>
            <p class="text-sm text-slate-500 leading-relaxed">
              {{ pendingAnnualYear }} 年仅 {{ monthlyPeriods.filter(p => p.period_key.startsWith(pendingAnnualYear) && p.status === 'generated').length }} 个月有月报。
              年报会从月报中提取每月氛围和热梗，月报越丰富，年报越精彩。
            </p>
            <p class="text-xs text-slate-400 mt-3">
              也可以跳过此建议，年报仍会基于全年原始数据生成。
            </p>
          </div>
          <div class="px-6 py-4 border-t border-slate-100 flex gap-3">
            <button @click="showAnnualConfirm = false"
              class="flex-1 px-4 py-2.5 text-sm font-medium text-slate-500 hover:bg-slate-50 rounded-xl transition border border-slate-200">
              先去生成月报
            </button>
            <button @click="_executeAnnualGenerate(pendingAnnualYear)"
              class="flex-1 px-4 py-2.5 text-sm font-medium text-white rounded-xl transition bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 shadow-lg shadow-amber-200">
              仍然生成年报
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
