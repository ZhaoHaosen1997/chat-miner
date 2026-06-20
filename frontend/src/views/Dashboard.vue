<script setup>
import { ref, inject, watch, computed, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import {
  getDates, getRecentReports, getGroupStats, analyzeDateAsync, analyzeAll, getPortraits,
  getTaskHistory, getTrending, getPeriods, generateWeekly, generateMonthly, generateAnnual,
  generateAllWeekly, generateAllMonthly, getWeeklyReport, getMonthlyReport, getReport,
  getEvents, getEventWindows, detectEvents, analyzeWindow, reanalyzeEvent,
} from '../api/index.js'
import { MessageSquare, Users, Calendar, Sparkles, Loader2, Upload, Zap, CheckCircle2, XCircle, Clock, FileText, RefreshCw, ArrowRight, Radio, Search, PartyPopper, AlertTriangle } from 'lucide-vue-next'
import UploadModal from '../components/UploadModal.vue'
import WeFlowImportModal from '../components/WeFlowImportModal.vue'

const router = useRouter()
const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')
const activeTaskId = inject('activeTaskId')
const showError = inject('showError')
const gid = computed(() => currentGroup.value?.id)

// 批量任务运行时定时刷新（逐个标绿）— v1.5.2: 10s间隔 + 仅刷新关键数据
let _refreshTimer = null
watch(activeTaskId, (newVal, oldVal) => {
  if (newVal) {
    if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null }
    // v1.5.12: 提高到 30s 默认间隔，减少长时间运行时的磁盘 I/O 压力
    const interval = Math.max(5000, parseInt(localStorage.getItem('poll_interval_dashboard_ms')) || 30000)
    _refreshTimer = setInterval(() => loadTaskProgress(), interval)
  } else if (oldVal) {
    // 任务结束时清理状态 + 刷新数据
    if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null }
    analyzing.value = false
    batchTotal.value = 0
    generatingPeriod.value = ''
    loadAll()
    loadPeriods()
    triggerRefresh?.()
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
const showWeFlow = ref(false)
const dayPopup = ref(null)
const dayPopupLoading = ref('')
const dayPopupError = ref('')
const monthOffset = ref(0)

// v1.18.2: Dashboard 事件区域
const dashboardEvents = ref([])
const dashboardWindows = ref([])
const eventsLoading = ref(false)
const eventsScanning = ref(false)
const eventShowCount = ref(8)
const analyzingWindowId = ref(null)
const analyzingTarget = ref('')  // 事件操作互斥锁（scan/reanalyze/analyze/all）
const showRescanConfirm = ref(false)
const showPrivacyConfirm = ref(false)
const privacyDontShow = ref(false)
const pendingEventAction = ref(null)  // 待执行的事件操作函数

function checkPrivacyConsent(actionFn) {
  if (localStorage.getItem('event_privacy_consent') === '1') {
    actionFn()
    return
  }
  pendingEventAction.value = actionFn
  showPrivacyConfirm.value = true
}

function confirmPrivacyAndProceed() {
  if (privacyDontShow.value) {
    localStorage.setItem('event_privacy_consent', '1')
  }
  showPrivacyConfirm.value = false
  const fn = pendingEventAction.value
  pendingEventAction.value = null
  if (fn) fn()
}
const expandedEventMonths = ref(new Set())

function toggleEventMonth(month) {
  const s = new Set(expandedEventMonths.value)
  if (s.has(month)) { s.delete(month) } else { s.add(month) }
  expandedEventMonths.value = s
}

let _loadVersion = 0

const weeklyPeriods = ref([])
const monthlyPeriods = ref([])
const annualPeriods = ref([])
const periodsLoading = ref(false)
const periodsLoaded = ref(false)
const generatingPeriod = ref('')

// v1.0.3: Hero cards — latest generated report previews
const latestWeekly = ref(null)
const latestMonthly = ref(null)

function getDailyModelId() {
  const v = localStorage.getItem('dailyModelId')
  if (v === null || v === '') return null
  const n = Number(v)
  return isNaN(n) ? null : n
}

const PAGE_SIZE = 10
const DEFAULT_SHOW = 8
const weeklyShowCount = ref(DEFAULT_SHOW)
const monthlyShowCount = ref(DEFAULT_SHOW)
const weeklyListRef = ref(null)
const monthlyListRef = ref(null)

function expandWeekly() {
  weeklyShowCount.value = Math.min(weeklyShowCount.value + PAGE_SIZE, weeklyPeriods.value.length)
  nextTick(() => {
    const el = weeklyListRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}
function collapseWeekly() {
  weeklyShowCount.value = DEFAULT_SHOW
}
function expandMonthly() {
  monthlyShowCount.value = Math.min(monthlyShowCount.value + PAGE_SIZE, monthlyPeriods.value.length)
  nextTick(() => {
    const el = monthlyListRef.value
    if (el) el.scrollTop = el.scrollHeight
  })
}
function collapseMonthly() {
  monthlyShowCount.value = DEFAULT_SHOW
}
const showAnnualConfirm = ref(false)
const pendingAnnualYear = ref('')

async function loadTaskProgress() {
  // v1.5.2: 批量任务期间轻量刷新，仅取变化的数据（stats / dates / taskHistory）
  if (!currentGroup.value) return
  const gid = currentGroup.value.id
  try {
    const [s, d, h] = await Promise.allSettled([
      getGroupStats(gid),
      getDates(gid),
      getTaskHistory(gid, 8),
    ])
    stats.value = s.status === 'fulfilled' ? s.value : stats.value
    const datesArr = d.status === 'fulfilled' ? d.value : null
    if (datesArr) dates.value = Array.isArray(datesArr) ? datesArr : []
    const histArr = h.status === 'fulfilled' ? h.value : null
    if (histArr) taskHistory.value = Array.isArray(histArr) ? histArr : []
  } catch (e) { console.error('Dashboard轮询失败:', e) }
}

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
    stats.value = s
    dates.value = Array.isArray(d) ? d : []
    recentReports.value = Array.isArray(r) ? r : []
    portraits.value = Array.isArray(p) ? p : []
    taskHistory.value = Array.isArray(h) ? h : []
    trending.value = t
  } catch (e) { console.error(e) }
  finally {
    if (version === _loadVersion) loading.value = false
  }
}

watch(currentGroup, () => { monthOffset.value = 0; loadAll(); loadPeriods(); loadDashboardEvents() }, { immediate: true })

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

function goReport(date) {
  router.push(`/report/${date}`)
}

function viewReportFromPopup() {
  const d = dayPopup.value.date
  dayPopup.value = null
  goReport(d)
}

async function openDayPopup(day) {
  dayPopup.value = day
  dayPopupLoading.value = day.analyzed ? 'report' : ''
  dayPopupError.value = ''
  if (day.analyzed && gid.value) {
    try {
      const data = await getReport(gid.value, day.date)
      if (dayPopup.value?.date !== day.date) return  // v1.0.6: 防止快速点击后旧请求覆盖新弹窗
      dayPopup.value = { ...day, report: data.report }
    } catch (e) {
      dayPopupError.value = '加载报告失败'
    } finally {
      dayPopupLoading.value = ''
    }
  }
}

async function handleGenerateReport() {
  if (!dayPopup.value || dayPopupLoading.value) return  // v1.0.6: 防重复调用
  dayPopupLoading.value = 'report'
  try {
    const force = dayPopup.value.analyzed
    const result = await analyzeDateAsync(gid.value, dayPopup.value.date, getDailyModelId(), force)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    }
    dayPopup.value = null
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

const WEEKDAYS = ['一', '二', '三', '四', '五', '六', '日']

const dateMap = computed(() => {
  const m = {}
  for (const d of dates.value) {
    m[d.date] = d
  }
  return m
})

const dataRange = computed(() => {
  const s = stats.value?.group
  if (!s?.date_range_start || !s?.date_range_end) return null
  return { start: new Date(s.date_range_start), end: new Date(s.date_range_end) }
})

const displayMonth = computed(() => {
  const now = new Date()
  const m = now.getMonth() + monthOffset.value
  const y = now.getFullYear() + Math.floor(m / 12)
  const mm = ((m % 12) + 12) % 12
  return new Date(y, mm, 1)
})

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

const calendarWeeks = computed(() => {
  const year = displayMonth.value.getFullYear()
  const month = displayMonth.value.getMonth()
  const firstDay = new Date(year, month, 1)
  const lastDay = new Date(year, month + 1, 0)
  const range = dataRange.value

  const weeks = []
  let currentWeek = []
  let dow = firstDay.getDay()
  dow = dow === 0 ? 6 : dow - 1
  for (let i = 0; i < dow; i++) currentWeek.push(null)

  for (let d = 1; d <= lastDay.getDate(); d++) {
    const dateObj = new Date(year, month, d)
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const info = dateMap.value[dateStr]
    const inRange = range ? dateObj >= range.start && dateObj <= range.end : false

    currentWeek.push({
      date: dateStr,
      day: d,
      hasData: !!info,
      analyzed: info?.analyzed || false,
      count: info?.total_messages || 0,
      active_members: info?.active_members || 0,
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

const moodIcons = { '欢乐':'😄','温馨':'🥰','严肃':'🧐','吐槽':'😤','平淡':'😐','热闹':'🎉','伤感':'😢','沙雕':'🤪','吃瓜':'🍉','摸鱼':'🎣','摆烂':'🫠','内卷':'💪','开车':'🚗','破防':'💔','凡尔赛':'👑','社死':'💀','真香':'🍚','画饼':'🫓','CPU':'🔥','离谱':'👽','上头':'🤯' }

async function loadPeriods() {
  if (!currentGroup.value || periodsLoading.value) return
  periodsLoading.value = true
  const groupId = currentGroup.value.id  // v1.0.6: 防切群竞态
  try {
    const [wp, mp, ap] = await Promise.all([
      getPeriods(currentGroup.value.id, 'weekly').catch(() => []),
      getPeriods(currentGroup.value.id, 'monthly').catch(() => []),
      getPeriods(currentGroup.value.id, 'annual').catch(() => []),
    ])
    if (currentGroup.value?.id !== groupId) return  // v1.0.6: 切群后丢弃旧数据
    weeklyPeriods.value = wp || []
    monthlyPeriods.value = mp || []
    annualPeriods.value = ap || []
    weeklyShowCount.value = DEFAULT_SHOW   // v1.0.6: 复位展开计数
    monthlyShowCount.value = DEFAULT_SHOW
    periodsLoaded.value = true
    loadLatestReportPreviews()
  } catch (e) { console.error(e) }
  finally { periodsLoading.value = false }
}

// v1.18.2: 加载 Dashboard 事件数据
async function loadDashboardEvents() {
  if (!gid.value) return
  eventsLoading.value = true
  try {
    const [evts, wins] = await Promise.all([
      getEvents(gid.value, {}).catch(() => []),
      getEventWindows(gid.value).catch(() => []),
    ])
    dashboardEvents.value = Array.isArray(evts) ? evts : []
    dashboardWindows.value = Array.isArray(wins) ? wins : []
  } catch (e) {
    console.error('加载事件列表失败:', e)
  } finally { eventsLoading.value = false }
}

async function handleScanEvents(force = false) {
  if (!gid.value || analyzingTarget.value || eventsScanning.value) return
  analyzingTarget.value = 'scan'
  eventsScanning.value = true
  try {
    await detectEvents(gid.value, '', '', force)
    eventShowCount.value = 8
    await loadDashboardEvents()
  } catch (e) {
    showError?.('事件扫描失败', e.message, e.stack, '仪表盘·扫描事件')
  } finally { analyzingTarget.value = ''; eventsScanning.value = false }
}

function handleRescanConfirm() { showRescanConfirm.value = true }

async function handleRescanExecute() {
  showRescanConfirm.value = false
  await handleScanEvents(true)
}

async function handleReanalyzeEvent(event) {
  if (!gid.value || analyzingTarget.value) return
  const useEventId = !event.window_id
  const idForTracking = useEventId ? event.id : event.window_id
  analyzingTarget.value = 'reanalyze:' + idForTracking
  analyzingWindowId.value = idForTracking
  try {
    let result
    if (useEventId) {
      result = await reanalyzeEvent(gid.value, event.id)
    } else {
      result = await analyzeWindow(gid.value, event.window_id)
    }
    if (result?.status === 'empty') {
      showError?.('未发现事件', 'AI 判断该时段不构成值得记录的事件', '', '仪表盘·重新分析事件')
    }
    await loadDashboardEvents()
  } catch (e) {
    showError?.('重新分析失败', e.message, e.stack, '仪表盘·重新分析事件')
  } finally { analyzingTarget.value = ''; analyzingWindowId.value = null }
}

async function handleAnalyzeAllEvents() {
  if (!gid.value || analyzingTarget.value || activeTaskId.value) return
  analyzingTarget.value = 'all'
  try {
    const { analyzeAllWindows: analyzeAll } = await import('../api/index.js')
    const result = await analyzeAll(gid.value)
    if (result?.task_id) activeTaskId.value = result.task_id
  } catch (e) {
    showError?.('一键分析失败', e.message, e.stack, '仪表盘·一键分析全部')
  } finally { analyzingTarget.value = '' }
}

async function handleAnalyzeWindow(windowId) {
  if (!gid.value || analyzingTarget.value) return
  analyzingTarget.value = 'analyze:' + windowId
  analyzingWindowId.value = windowId
  try {
    const result = await analyzeWindow(gid.value, windowId)
    if (result?.event_id) {
      router.push(`/event/${result.event_id}`)
    } else if (result?.status === 'empty') {
      showError?.('未发现事件', 'AI 判断该时段不构成值得记录的事件', '', '仪表盘·分析窗口')
      await loadDashboardEvents()
    } else {
      await loadDashboardEvents()
    }
  } catch (e) {
    showError?.('窗口分析失败', e.message, e.stack, '仪表盘·分析窗口')
  } finally { analyzingTarget.value = ''; analyzingWindowId.value = null }
}

// ISO 周标识 → 日期范围（如 2026-W25 → 6/15-6/21）
function isoWeekToRange(key) {
  const m = key.match(/^(\d{4})-W(\d{2})$/)
  if (!m) return ''
  const y = parseInt(m[1]), w = parseInt(m[2])
  const jan4 = new Date(y, 0, 4)
  const dow = jan4.getDay() || 7
  const firstMonday = new Date(jan4)
  firstMonday.setDate(jan4.getDate() - (dow - 1))
  const monday = new Date(firstMonday)
  monday.setDate(firstMonday.getDate() + (w - 1) * 7)
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  const fmt = d => `${d.getMonth() + 1}/${d.getDate()}`
  return `${fmt(monday)}-${fmt(sunday)}`
}

// 月份标识 → 日期范围（如 2026-06 → 6/1-6/30）
function monthToRange(key) {
  const m = key.match(/^(\d{4})-(\d{2})$/)
  if (!m) return ''
  const y = parseInt(m[1]), mo = parseInt(m[2])
  const lastDay = new Date(y, mo, 0).getDate()
  return `${mo}/1-${mo}/${lastDay}`
}

const groupedDashboardEvents = computed(() => {
  const groups = {}
  for (const e of dashboardEvents.value) {
    const m = (e.start_time || '').slice(0, 7)
    if (!m) continue
    if (!groups[m]) groups[m] = { events: [], windows: [] }
    groups[m].events.push(e)
  }
  for (const w of dashboardWindows.value) {
    if (w.status !== 'pending') continue
    const m = (w.start_time || '').slice(0, 7)
    if (!m) continue
    if (!groups[m]) groups[m] = { events: [], windows: [] }
    groups[m].windows.push(w)
  }
  const entries = Object.entries(groups).sort((a, b) => b[0].localeCompare(a[0]))
  return entries
})

// 初始化：只展开当前月
watch(groupedDashboardEvents, (val) => {
  if (val.length > 0 && expandedEventMonths.value.size === 0) {
    expandedEventMonths.value = new Set([val[0][0]])
  }
}, { immediate: true })

const hasDashboardEvents = computed(() =>
  dashboardEvents.value.length > 0 || dashboardWindows.value.some(w => w.status === 'pending'))

function formatEventType(e) {
  const icons = { decision: '🎯', discussion: '💬', social: '🎉', announcement: '📢', meme: '🤣' }
  return icons[e.event_type] || '📌'
}

async function loadLatestReportPreviews() {
  const gid = currentGroup.value?.id
  if (!gid) return
  const latestW = weeklyPeriods.value.filter(p => p.status === 'generated').sort((a, b) => b.period_key.localeCompare(a.period_key))[0]
  const latestM = monthlyPeriods.value.filter(p => p.status === 'generated').sort((a, b) => b.period_key.localeCompare(a.period_key))[0]
  try {
    if (latestW) {
      const data = await getWeeklyReport(gid, latestW.period_key).catch(() => null)
      latestWeekly.value = { ...latestW, report: data }
    } else { latestWeekly.value = null }
  } catch (e) { latestWeekly.value = null }
  try {
    if (latestM) {
      const data = await getMonthlyReport(gid, latestM.period_key).catch(() => null)
      latestMonthly.value = { ...latestM, report: data }
    } else { latestMonthly.value = null }
  } catch (e) { latestMonthly.value = null }
}

async function doGenerateWeekly(periodKey, force = false) {
  if (generatingPeriod.value || activeTaskId.value) return
  generatingPeriod.value = periodKey
  try {
    const result = await generateWeekly(currentGroup.value.id, periodKey, force)
    if (result?.task_id) {
      activeTaskId.value = result.task_id
    } else {
      generatingPeriod.value = ''
    }
  } catch (e) { showError?.('周报生成失败', e.message, e.stack, '仪表盘·生成周报'); generatingPeriod.value = '' }
}

async function doGenerateMonthly(periodKey, force = false) {
  if (generatingPeriod.value || activeTaskId.value) return
  generatingPeriod.value = periodKey
  try {
    const result = await generateMonthly(currentGroup.value.id, periodKey, force)
    if (result?.task_id) {
      activeTaskId.value = result.task_id
    } else {
      generatingPeriod.value = ''
    }
  } catch (e) { showError?.('月报生成失败', e.message, e.stack, '仪表盘·生成月报'); generatingPeriod.value = '' }
}

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

function goWeekly(key) { router.push(`/weekly/${key}`) }
function goMonthly(key) { router.push(`/monthly/${key}`) }
function goAnnual(key) { router.push(`/annual/${key}`) }

async function doGenerateAnnual(periodKey, force = false) {
  if (generatingPeriod.value || activeTaskId.value) return
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
      <!-- v1.0.3: Hero — 最新周报 + 月报预览 -->
      <div v-if="latestWeekly || latestMonthly" class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-5">
        <div v-if="latestWeekly" @click="goWeekly(latestWeekly.period_key)"
             class="card p-5 cursor-pointer hover:shadow-lg transition-all group bg-gradient-to-br from-indigo-50/50 to-white border-indigo-100/50">
          <div class="flex items-start justify-between mb-3">
            <div>
              <span class="text-[10px] font-semibold tracking-wider text-indigo-400 uppercase">Latest Weekly</span>
              <h3 class="text-lg font-bold text-slate-800 mt-0.5">{{ latestWeekly.period_key }} <span class="text-sm font-normal text-slate-400">{{ isoWeekToRange(latestWeekly.period_key) }}</span></h3>
              <span v-if="latestWeekly.has_new_data" class="inline-block mt-1 text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">有新数据，可重新生成</span>
            </div>
            <span class="text-3xl group-hover:scale-110 transition-transform">{{ latestWeekly.report?.overall_mood_emoji || '📰' }}</span>
          </div>
          <p class="text-sm text-slate-600 line-clamp-2 leading-relaxed">{{ latestWeekly.report?.one_line || latestWeekly.report?.week_narrative || '点击查看周报 →' }}</p>
          <div class="flex items-center gap-3 mt-3 text-[11px] text-slate-400">
            <span>{{ latestWeekly.day_count }}天 · {{ latestWeekly.total_messages || latestWeekly.report?.total_messages }}条</span>
            <span v-if="latestWeekly.report?.model_used" class="text-slate-300">{{ latestWeekly.report.model_used }}</span>
          </div>
        </div>
        <div v-if="latestMonthly" @click="goMonthly(latestMonthly.period_key)"
             class="card p-5 cursor-pointer hover:shadow-lg transition-all group bg-gradient-to-br from-purple-50/50 to-white border-purple-100/50">
          <div class="flex items-start justify-between mb-3">
            <div>
              <span class="text-[10px] font-semibold tracking-wider text-purple-400 uppercase">Latest Monthly</span>
              <h3 class="text-lg font-bold text-slate-800 mt-0.5">{{ latestMonthly.period_key }} <span class="text-sm font-normal text-slate-400">{{ monthToRange(latestMonthly.period_key) }}</span></h3>
              <span v-if="latestMonthly.has_new_data" class="inline-block mt-1 text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">有新数据，可重新生成</span>
            </div>
            <span class="text-3xl group-hover:scale-110 transition-transform">{{ latestMonthly.report?.personality_type_emoji || '🌙' }}</span>
          </div>
          <p class="text-sm text-slate-600 line-clamp-2 leading-relaxed">{{ latestMonthly.report?.one_line || latestMonthly.report?.group_personality?.type_explanation || latestMonthly.report?.overview || '点击查看月报 →' }}</p>
          <div class="flex items-center gap-3 mt-3 text-[11px] text-slate-400">
            <span>{{ latestMonthly.day_count }}天 · {{ latestMonthly.total_messages || latestMonthly.report?.total_messages }}条</span>
            <span v-if="latestMonthly.report?.model_used" class="text-slate-300">{{ latestMonthly.report.model_used }}</span>
          </div>
        </div>
      </div>

      <!-- 数据横幅 + 操作按钮 -->
      <div class="flex items-center gap-3 mb-4 flex-wrap text-xs">
        <div v-if="stats?.group?.date_range_start" class="flex items-center gap-1.5 text-slate-400">
          <span>📅 {{ stats.group.date_range_start }} ~ {{ stats.group.date_range_end }}</span>
          <span class="text-slate-200">·</span>
          <span><strong class="text-slate-600">{{ stats.total_days_with_data }}</strong>天</span>
          <span class="text-slate-200">·</span>
          <span>已分析<strong class="text-emerald-600 ml-0.5">{{ stats.analyzed_count }}</strong>天</span>
          <template v-if="stats.analyzed_count > 0">
            <span class="text-slate-200">·</span>
            <span class="inline-block w-10 h-1 bg-slate-100 rounded-full overflow-hidden">
              <span class="block h-full rounded-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all" :style="{ width: `${stats.progress_pct}%` }"></span>
            </span>
            <strong class="text-indigo-500">{{ stats.progress_pct }}%</strong>
          </template>
        </div>
        <div class="flex gap-1.5 ml-auto">
          <button @click="showUpload = true" class="px-2.5 py-1 rounded-lg text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 border border-slate-200 transition-colors flex items-center gap-1"><Upload :size="12" />导入</button>
          <button @click="showWeFlow = true" class="px-2.5 py-1 rounded-lg text-slate-400 hover:text-emerald-600 hover:bg-emerald-50 border border-slate-200 transition-colors flex items-center gap-1"><Radio :size="12" />同步</button>
          <button v-if="(stats?.total_days_with_data - (stats?.analyzed_count || 0)) > 1" @click="startAnalyzeAll" :disabled="analyzing"
            :class="['px-2.5 py-1 rounded-lg font-medium transition-all flex items-center gap-1', !analyzing ? 'bg-gradient-to-r from-emerald-500 to-teal-600 text-white shadow-sm' : 'bg-slate-100 text-slate-300']"><Zap :size="12" />一键分析</button>
          <button @click="analyzeLatest" :disabled="analyzing || !latestUnanalyzed"
            class="px-2.5 py-1 rounded-lg font-medium bg-indigo-500 text-white hover:bg-indigo-600 disabled:bg-slate-100 disabled:text-slate-300 transition-colors">分析最新</button>
        </div>
      </div>

      <!-- 快捷统计 4 卡片 -->
      <div class="grid grid-cols-4 gap-3 mb-5">
        <div class="card p-3 flex items-center gap-2.5"><div class="w-8 h-8 rounded-lg bg-indigo-100 flex items-center justify-center flex-shrink-0"><MessageSquare class="w-4 h-4 text-indigo-600" /></div><div><div class="text-lg font-bold text-slate-800">{{ (stats?.group?.message_count || 0).toLocaleString() }}</div><div class="text-[10px] text-slate-400">总消息</div></div></div>
        <div class="card p-3 flex items-center gap-2.5"><div class="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center flex-shrink-0"><Calendar class="w-4 h-4 text-emerald-600" /></div><div><div class="text-lg font-bold text-slate-800">{{ stats?.analyzed_count || 0 }}</div><div class="text-[10px] text-slate-400">已分析天</div></div></div>
        <div class="card p-3 flex items-center gap-2.5"><div class="w-8 h-8 rounded-lg bg-amber-100 flex items-center justify-center flex-shrink-0"><FileText class="w-4 h-4 text-amber-600" /></div><div><div class="text-lg font-bold text-slate-800">{{ weeklyPeriods.filter(p=>p.status==='generated').length + monthlyPeriods.filter(p=>p.status==='generated').length }}</div><div class="text-[10px] text-slate-400">周期报告</div></div></div>
        <div class="card p-3 flex items-center gap-2.5"><div class="w-8 h-8 rounded-lg bg-rose-100 flex items-center justify-center flex-shrink-0"><Users class="w-4 h-4 text-rose-600" /></div><div><div class="text-lg font-bold text-slate-800">{{ stats?.member_count || 0 }}</div><div class="text-[10px] text-slate-400">成员</div></div></div>
      </div>

      <!-- 主体：左(周期报告主舞台) 右(日历+排行) -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2 space-y-5">
          <!-- v1.18.2: 事件时间轴 -->
          <div class="card p-5 mb-5">
            <div class="flex items-center justify-between mb-3">
              <h3 class="font-semibold text-slate-700 flex items-center gap-2 text-sm">
                <span class="w-7 h-7 rounded-lg bg-rose-100 flex items-center justify-center"><PartyPopper class="w-3.5 h-3.5 text-rose-600" /></span>
                事件时间轴
                <span class="text-xs text-slate-400 font-normal">{{ dashboardEvents.length + dashboardWindows.filter(w=>w.status==='pending').length }}</span>
              </h3>
              <div class="flex items-center gap-1.5">
                <button @click="checkPrivacyConsent(() => handleScanEvents(false))" :disabled="!!analyzingTarget || showPrivacyConfirm || eventsScanning"
                  class="text-[10px] bg-emerald-500 text-white px-2 py-1 rounded-full hover:bg-emerald-600 disabled:opacity-40 flex items-center gap-0.5">
                  <Search :size="10" />扫描新事件
                </button>
                <button @click="checkPrivacyConsent(() => handleRescanConfirm())" :disabled="!!analyzingTarget || showPrivacyConfirm || eventsScanning"
                  class="text-[10px] bg-red-500 text-white px-2 py-1 rounded-full hover:bg-red-600 disabled:opacity-40 flex items-center gap-0.5"
                  title="删除全部窗口后重新检测">
                  <RefreshCw :size="10" />重新扫描
                </button>
                <button v-if="dashboardWindows.some(w=>w.status==='pending')" @click="checkPrivacyConsent(() => handleAnalyzeAllEvents())"
                  :disabled="!!analyzingTarget || showPrivacyConfirm || !!activeTaskId || eventsScanning"
                  class="text-[10px] bg-indigo-500 text-white px-2 py-1 rounded-full hover:bg-indigo-600 disabled:opacity-40 flex items-center gap-0.5">
                  <Zap :size="10" />一键分析
                </button>
              </div>
            </div>

            <!-- 列表（限高 + 月份折叠） -->
            <div v-if="groupedDashboardEvents.length > 0" class="max-h-72 overflow-y-auto space-y-0.5">
              <div v-for="[month, group] in groupedDashboardEvents.slice(0, eventShowCount)" :key="month">
                <button @click="toggleEventMonth(month)"
                  class="flex items-center gap-1.5 w-full text-left py-1 px-1 hover:text-slate-600 transition-colors group">
                  <span class="text-[10px] text-slate-300 group-hover:text-slate-500 w-3 text-center">
                    {{ expandedEventMonths.has(month) ? '▼' : '▶' }}
                  </span>
                  <span class="text-[11px] font-semibold text-slate-400">{{ month }}</span>
                  <span class="text-[10px] text-slate-300">({{ group.events.length + group.windows.length }})</span>
                </button>

                <template v-if="expandedEventMonths.has(month)">
                  <!-- 候选窗口 -->
                  <div v-for="w in group.windows" :key="'w'+w.id"
                       class="flex items-center gap-2.5 text-xs py-1.5 px-2.5 rounded-lg border border-amber-100/50 bg-amber-50/30">
                    <span class="text-slate-300 w-4 text-center">○</span>
                    <span class="text-slate-400 w-16 flex-shrink-0">{{ (w.start_time||'').slice(5,10) }}</span>
                    <span class="flex-1 text-slate-500 truncate">{{ (w.summary?.preview||[])[0]?.content || '候选事件' }}</span>
                    <button @click.stop="checkPrivacyConsent(() => handleAnalyzeWindow(w.id))"
                      :disabled="!!analyzingTarget || showPrivacyConfirm || analyzingWindowId === w.id"
                      class="bg-indigo-500 text-white px-2 py-0.5 rounded-full text-[10px] hover:bg-indigo-600 disabled:opacity-40 flex-shrink-0">
                      {{ analyzingWindowId === w.id ? '...' : '分析' }}
                    </button>
                  </div>
                  <!-- 已分析事件 -->
                  <div v-for="e in group.events" :key="'e'+e.id"
                       @click="router.push(`/event/${e.id}`)"
                       class="flex items-center gap-2.5 text-xs py-1.5 px-2.5 rounded-lg hover:bg-slate-50 cursor-pointer border border-transparent hover:border-slate-100 transition-colors">
                    <span class="w-4 text-center flex-shrink-0">{{ formatEventType(e) }}</span>
                    <span class="text-slate-400 w-16 flex-shrink-0 font-mono">{{ (e.start_time||'').slice(5,10) }}</span>
                    <span class="flex-1 text-slate-700 font-medium truncate">{{ e.title }}</span>
                    <span class="text-slate-400 text-[10px] flex-shrink-0">{{ e.message_count || 0 }}条</span>
                    <span class="bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded-full text-[10px] flex-shrink-0">已分析</span>
                    <button @click.stop="checkPrivacyConsent(() => handleReanalyzeEvent(e))"
                      :disabled="!!analyzingTarget || showPrivacyConfirm || (analyzingWindowId != null && analyzingWindowId === e.window_id)"
                      class="bg-amber-50 text-amber-600 px-1.5 py-0.5 rounded-full text-[10px] hover:bg-amber-100 disabled:opacity-40 flex-shrink-0">
                      ↻
                    </button>
                  </div>
                </template>
              </div>
            </div>

            <!-- 展开/收起 -->
            <button v-if="eventShowCount < groupedDashboardEvents.length" @click="eventShowCount = Math.min(eventShowCount + 10, groupedDashboardEvents.length)"
              class="w-full text-[10px] text-slate-400 hover:text-rose-500 py-1 mt-1 transition-colors">
              展开更多 ({{ eventShowCount }}/{{ groupedDashboardEvents.length }}) ▼
            </button>
            <button v-if="eventShowCount >= groupedDashboardEvents.length && groupedDashboardEvents.length > 8" @click="eventShowCount = 8"
              class="w-full text-[10px] text-slate-400 hover:text-rose-500 py-1 transition-colors">
              收起 ▲
            </button>

            <!-- 空状态 -->
            <div v-if="!eventsLoading && dashboardEvents.length === 0 && dashboardWindows.length === 0"
                 class="text-center py-6 text-xs text-slate-400">
              点击"扫描新事件"让 AI 从群聊中发现事件
            </div>
            <div v-if="eventsLoading" class="text-center py-4 text-slate-400"><Loader2 class="w-4 h-4 animate-spin inline" /></div>
          </div>

          <!-- 重新扫描确认弹窗 -->
          <div v-if="showRescanConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <div class="bg-white rounded-2xl shadow-2xl p-6 max-w-sm mx-4">
              <p class="text-sm font-semibold text-slate-800 mb-2">⚠️ 确认重新扫描</p>
              <p class="text-xs text-slate-500 leading-relaxed mb-5">将删除所有事件窗口（含已分析）并重新检测。已生成的事件不会被删除，但与窗口的关联将丢失。确定继续？</p>
              <div class="flex gap-2 justify-end">
                <button @click="showRescanConfirm = false" class="px-4 py-2 text-xs rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors">取消</button>
                <button @click="handleRescanExecute" class="px-4 py-2 text-xs rounded-lg bg-red-500 text-white hover:bg-red-600 transition-colors">确认重新扫描</button>
              </div>
            </div>
          </div>

          <!-- 隐私确认弹窗（事件分析首次触发） -->
          <Teleport to="body">
            <div v-if="showPrivacyConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" @click.self="showPrivacyConfirm = false">
              <div class="bg-white rounded-2xl shadow-2xl p-6 max-w-sm mx-4">
                <p class="text-sm font-semibold text-slate-800 mb-2">🔒 数据隐私提醒</p>
                <p class="text-xs text-slate-500 leading-relaxed mb-4">
                  事件分析会将<strong>聊天消息内容</strong>提交给在线 AI 模型处理。消息中的敏感信息（手机号、身份证等）已自动过滤，发言者用数字 ID 替代。<br><br>
                  请确认你已获得群成员的知情同意，或确认群聊内容不包含个人隐私信息。
                </p>
                <label class="flex items-center gap-2 mb-5 text-xs text-slate-500 cursor-pointer">
                  <input type="checkbox" v-model="privacyDontShow" class="rounded border-slate-300" />
                  不再提示
                </label>
                <div class="flex gap-2 justify-end">
                  <button @click="showPrivacyConfirm = false" class="px-4 py-2 text-xs rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200 transition-colors">取消</button>
                  <button @click="confirmPrivacyAndProceed" class="px-4 py-2 text-xs rounded-lg bg-indigo-500 text-white hover:bg-indigo-600 transition-colors">确认并继续</button>
                </div>
              </div>
            </div>
          </Teleport>

          <!-- 加载时段 -->
          <template v-if="!periodsLoaded && !periodsLoading">
            <button @click="loadPeriods" class="card p-6 w-full text-center hover:border-indigo-200 transition-colors group">
              <div class="text-3xl mb-2 group-hover:scale-110 transition-transform">📰</div>
              <div class="text-sm font-medium text-slate-600">加载周报 / 月报 / 年报列表</div>
              <div class="text-xs text-slate-400 mt-1">点击加载所有可生成的周期报告</div>
            </button>
          </template>
          <div v-if="periodsLoading" class="text-center py-8 text-slate-400"><Loader2 class="w-5 h-5 animate-spin inline" /> 加载中...</div>

          <!-- 周报 -->
          <div v-if="weeklyPeriods.length > 0" class="card p-5">
            <div class="flex items-center justify-between mb-4">
              <h3 class="font-semibold text-slate-700 flex items-center gap-2 text-sm"><span class="w-7 h-7 rounded-lg bg-indigo-100 flex items-center justify-center"><FileText class="w-3.5 h-3.5 text-indigo-600" /></span>周报 <span class="text-xs text-slate-400 font-normal">{{ weeklyPeriods.filter(p=>p.status==='generated').length }}/{{ weeklyPeriods.length }}</span></h3>
              <button v-if="weeklyPeriods.some(p=>p.status==='ready')" @click="doGenerateAllWeekly" :disabled="!!generatingPeriod || !!activeTaskId" class="text-[10px] bg-indigo-500 text-white px-2 py-1 rounded-full hover:bg-indigo-600 disabled:opacity-40 flex items-center gap-0.5"><Zap :size="10" />一键生成</button>
            </div>
            <div ref="weeklyListRef" class="space-y-1 max-h-72 overflow-y-auto">
              <div v-for="p in weeklyPeriods.slice(0, weeklyShowCount)" :key="'w'+p.period_key"
                   class="flex items-center gap-2.5 text-xs py-2 px-2.5 rounded-lg transition-all"
                   :class="p.status === 'generated' ? 'hover:bg-indigo-50 cursor-pointer border border-transparent hover:border-indigo-100' : p.status === 'ready' ? 'bg-amber-50/40 border border-amber-100/50' : 'opacity-35'"
                   @click="p.status === 'generated' ? goWeekly(p.period_key) : null">
                <span class="font-mono font-medium text-slate-600 flex-shrink-0" style="min-width:7rem">{{ p.period_key }} <span class="text-slate-400 font-normal text-[10px]">{{ isoWeekToRange(p.period_key) }}</span></span>
                <span class="flex-1 text-slate-400">{{ p.day_count }}天</span>
                <template v-if="p.status === 'generated'"><span class="text-[10px] bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded-full font-medium">已生成</span><span v-if="p.has_new_data" class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">有新数据</span><button @click.stop="doGenerateWeekly(p.period_key, true)" :disabled="!!generatingPeriod || !!activeTaskId" class="text-[10px] bg-amber-50 text-amber-600 px-1.5 py-0.5 rounded-full hover:bg-amber-100 disabled:opacity-40">↻</button></template>
                <button v-else-if="p.status === 'ready'" @click.stop="doGenerateWeekly(p.period_key)" :disabled="!!generatingPeriod || !!activeTaskId" class="text-[10px] bg-indigo-500 text-white px-2 py-0.5 rounded-full hover:bg-indigo-600 disabled:opacity-40">生成</button>
                <span v-else class="text-[10px] text-slate-300">不足</span>
              </div>
            </div>
            <button v-if="weeklyShowCount < weeklyPeriods.length" @click="expandWeekly" class="w-full text-[10px] text-slate-400 hover:text-indigo-500 py-1 mt-1 transition-colors">展开更多 ({{ weeklyShowCount }}/{{ weeklyPeriods.length }}) ▼</button>
            <button v-if="weeklyShowCount >= weeklyPeriods.length && weeklyPeriods.length > DEFAULT_SHOW" @click="collapseWeekly" class="w-full text-[10px] text-slate-400 hover:text-indigo-500 py-1 mt-1 transition-colors">收起 ▲</button>
          </div>

          <!-- 月报 -->
          <div v-if="monthlyPeriods.length > 0" class="card p-5">
            <div class="flex items-center justify-between mb-4">
              <h3 class="font-semibold text-slate-700 flex items-center gap-2 text-sm"><span class="w-7 h-7 rounded-lg bg-purple-100 flex items-center justify-center"><FileText class="w-3.5 h-3.5 text-purple-600" /></span>月报 <span class="text-xs text-slate-400 font-normal">{{ monthlyPeriods.filter(p=>p.status==='generated').length }}/{{ monthlyPeriods.length }}</span></h3>
              <button v-if="monthlyPeriods.some(p=>p.status==='ready')" @click="doGenerateAllMonthly" :disabled="!!generatingPeriod || !!activeTaskId" class="text-[10px] bg-purple-500 text-white px-2 py-1 rounded-full hover:bg-purple-600 disabled:opacity-40 flex items-center gap-0.5"><Zap :size="10" />一键生成</button>
            </div>
            <div ref="monthlyListRef" class="space-y-1 max-h-72 overflow-y-auto">
              <div v-for="p in monthlyPeriods.slice(0, monthlyShowCount)" :key="'m'+p.period_key"
                   class="flex items-center gap-2.5 text-xs py-2 px-2.5 rounded-lg transition-all"
                   :class="p.status === 'generated' ? 'hover:bg-purple-50 cursor-pointer border border-transparent hover:border-purple-100' : p.status === 'ready' ? 'bg-amber-50/40 border border-amber-100/50' : 'opacity-35'"
                   @click="p.status === 'generated' ? goMonthly(p.period_key) : null">
                <span class="font-mono font-medium text-slate-600 flex-shrink-0" style="min-width:7rem">{{ p.period_key }} <span class="text-slate-400 font-normal text-[10px]">{{ monthToRange(p.period_key) }}</span></span>
                <span class="flex-1 text-slate-400">{{ p.day_count }}天</span>
                <template v-if="p.status === 'generated'"><span class="text-[10px] bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded-full font-medium">已生成</span><span v-if="p.has_new_data" class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">有新数据</span><button @click.stop="doGenerateMonthly(p.period_key, true)" :disabled="!!generatingPeriod || !!activeTaskId" class="text-[10px] bg-amber-50 text-amber-600 px-1.5 py-0.5 rounded-full hover:bg-amber-100 disabled:opacity-40">↻</button></template>
                <button v-else-if="p.status === 'ready'" @click.stop="doGenerateMonthly(p.period_key)" :disabled="!!generatingPeriod || !!activeTaskId" class="text-[10px] bg-purple-500 text-white px-2 py-0.5 rounded-full hover:bg-purple-600 disabled:opacity-40">生成</button>
                <span v-else class="text-[10px] text-slate-300">不足</span>
              </div>
            </div>
            <button v-if="monthlyShowCount < monthlyPeriods.length" @click="expandMonthly" class="w-full text-[10px] text-slate-400 hover:text-purple-500 py-1 mt-1 transition-colors">展开更多 ({{ monthlyShowCount }}/{{ monthlyPeriods.length }}) ▼</button>
            <button v-if="monthlyShowCount >= monthlyPeriods.length && monthlyPeriods.length > DEFAULT_SHOW" @click="collapseMonthly" class="w-full text-[10px] text-slate-400 hover:text-purple-500 py-1 mt-1 transition-colors">收起 ▲</button>
          </div>

          <!-- 年报 -->
          <div v-if="annualPeriods.length > 0" class="card p-5">
            <h3 class="font-semibold text-slate-700 flex items-center gap-2 text-sm mb-4"><span class="w-7 h-7 rounded-lg bg-amber-100 flex items-center justify-center"><FileText class="w-3.5 h-3.5 text-amber-600" /></span>年报 <span class="text-xs text-slate-400 font-normal">{{ annualPeriods.filter(p=>p.status==='generated').length }}/{{ annualPeriods.length }}</span></h3>
            <div class="space-y-1 max-h-32 overflow-y-auto">
              <div v-for="p in annualPeriods.slice(0, 5)" :key="'a'+p.period_key"
                   class="flex items-center gap-2.5 text-xs py-2 px-2.5 rounded-lg transition-all"
                   :class="p.status === 'generated' ? 'hover:bg-amber-50 cursor-pointer border border-transparent hover:border-amber-100' : p.status === 'ready' ? 'bg-amber-50/40 border border-amber-100/50' : 'opacity-35'"
                   @click="p.status === 'generated' ? goAnnual(p.period_key) : null">
                <span class="font-mono font-medium text-slate-600 w-20 flex-shrink-0">{{ p.period_key }}年</span>
                <span class="flex-1 text-slate-400">{{ p.day_count }}天</span>
                <template v-if="p.status === 'generated'"><span class="text-[10px] bg-emerald-50 text-emerald-600 px-1.5 py-0.5 rounded-full font-medium">已生成</span><span v-if="p.has_new_data" class="text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded-full font-medium">有新数据</span><button @click.stop="doGenerateAnnual(p.period_key, true)" :disabled="!!generatingPeriod || !!activeTaskId" class="text-[10px] bg-amber-50 text-amber-600 px-1.5 py-0.5 rounded-full hover:bg-amber-100 disabled:opacity-40">↻</button></template>
                <button v-else-if="p.status === 'ready'" @click.stop="doGenerateAnnual(p.period_key)" :disabled="!!generatingPeriod || !!activeTaskId" class="text-[10px] bg-amber-500 text-white px-2 py-0.5 rounded-full hover:bg-amber-600 disabled:opacity-40">生成</button>
                <span v-else class="text-[10px] text-slate-300">不足</span>
              </div>
            </div>
          </div>

          <div v-if="!periodsLoading && weeklyPeriods.length === 0 && monthlyPeriods.length === 0 && annualPeriods.length === 0 && periodsLoaded" class="card p-6 text-center text-sm text-slate-400">📭 暂无足够的日报数据<br><span class="text-[10px] text-slate-300">至少需要3天日报才能生成周报</span></div>

          <!-- 最近日报 -->
          <div v-if="recentReports.length > 0" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-3 text-sm flex items-center justify-between">最近日报 <span class="text-[10px] text-slate-300 font-normal">{{ recentReports.length }}篇</span></h3>
            <div class="space-y-1">
              <button v-for="r in recentReports.slice(0, 5)" :key="r.date" @click="goReport(r.date)" class="w-full text-left card p-2.5 hover:border-indigo-200 transition-all flex items-center gap-2.5 group">
                <span class="text-lg group-hover:scale-110 transition-transform flex-shrink-0">{{ r.mood_emoji || '💬' }}</span>
                <div class="flex-1 min-w-0"><div class="text-xs font-medium text-slate-700 truncate group-hover:text-indigo-600">{{ r.one_line || r.date }}</div><div class="text-[10px] text-slate-400">{{ r.date }} · {{ r.message_count }}条</div></div>
                <ArrowRight class="w-3 h-3 text-slate-300 group-hover:text-indigo-400 flex-shrink-0" />
              </button>
            </div>
          </div>
        </div>

        <!-- 右列：日历 + 排行 + 情绪 -->
        <div class="space-y-5">
          <div class="card p-3">
            <div class="flex items-center justify-between mb-2">
              <span class="text-xs font-semibold text-slate-600">数据日历</span>
              <div class="flex items-center gap-0.5">
                <button @click="goPrevMonth" :disabled="!canGoPrev" :class="['px-1.5 py-0.5 text-[10px] rounded', canGoPrev ? 'hover:bg-slate-100 text-slate-500' : 'text-slate-200']">◀</button>
                <span class="text-[11px] font-medium text-slate-600 w-[68px] text-center">{{ displayMonth.getFullYear() }}.{{ displayMonth.getMonth() + 1 }}</span>
                <button @click="goNextMonth" :disabled="!canGoNext" :class="['px-1.5 py-0.5 text-[10px] rounded', canGoNext ? 'hover:bg-slate-100 text-slate-500' : 'text-slate-200']">▶</button>
              </div>
            </div>
            <div class="grid grid-cols-7 mb-0.5"><div v-for="wd in WEEKDAYS" :key="wd" class="text-center text-[10px] text-slate-300">{{ wd }}</div></div>
            <div v-for="(week, wi) in calendarWeeks" :key="wi" class="grid grid-cols-7 gap-px">
              <div v-for="(day, di) in week" :key="di"
                   :title="day ? `${day.date}: ${day.count}条${day.analyzed ? '(已分析)' : day.hasData ? '(未分析)' : ''}` : ''"
                   :class="['aspect-square rounded-sm flex items-center justify-center text-[10px] transition-colors', !day ? '' : !day.inRange ? 'bg-slate-50 text-transparent' : day.analyzed ? 'bg-emerald-100 text-emerald-700 font-medium cursor-pointer hover:bg-emerald-200' : day.hasData ? 'bg-indigo-50 text-indigo-400 cursor-pointer hover:bg-indigo-100' : 'bg-slate-50 text-transparent']"
                   @click="day?.hasData && openDayPopup(day)">{{ day ? day.day : '' }}</div>
            </div>
            <div class="flex items-center gap-3 mt-2 pt-2 border-t border-slate-50 text-[10px] text-slate-300"><span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-indigo-50" />数据</span><span class="flex items-center gap-1"><span class="w-2.5 h-2.5 rounded-sm bg-emerald-100" />已分析</span></div>
          </div>

          <!-- 热搜 -->
          <div v-if="trending?.topics?.length" class="card p-4 bg-gradient-to-b from-red-50 to-white">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-1.5 text-sm"><span>🔥</span> 群聊热搜 <span class="text-xs text-slate-400 font-normal ml-auto">{{ trending.period }}</span></h3>
            <div class="space-y-1">
              <div v-for="(t, i) in trending.topics.slice(0, 8)" :key="i" class="flex items-center gap-2 text-xs py-1.5 px-2 rounded hover:bg-red-50/50 transition-colors">
                <span :class="['w-4 h-4 rounded text-[10px] font-bold flex items-center justify-center flex-shrink-0', i === 0 ? 'bg-red-500 text-white' : i === 1 ? 'bg-orange-400 text-white' : i === 2 ? 'bg-amber-400 text-white' : 'bg-slate-200 text-slate-500']">{{ i + 1 }}</span>
                <span class="text-slate-700 truncate flex-1">{{ t.text }}</span>
                <span class="text-[10px] text-slate-400 flex-shrink-0">{{ t.heat }}℃</span>
              </div>
            </div>
          </div>

          <div v-if="stats?.member_ranking" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-3 text-sm">发言排行</h3>
            <div class="space-y-1">
              <div v-for="(m, i) in stats.member_ranking.slice(0, 8)" :key="m.id" class="flex items-center gap-2 text-xs">
                <span :class="['w-4 h-4 rounded-full text-[10px] font-bold flex items-center justify-center flex-shrink-0', i === 0 ? 'bg-amber-100 text-amber-700' : i === 1 ? 'bg-slate-200 text-slate-600' : i === 2 ? 'bg-orange-100 text-orange-700' : 'text-slate-400']">{{ i + 1 }}</span>
                <span class="flex-1 text-slate-700 truncate">{{ m.display_name || m.nickname }}</span>
                <span class="text-slate-400 font-mono text-[10px]">{{ m.message_count }}</span>
              </div>
            </div>
          </div>

          <div v-if="stats?.mood_distribution && Object.keys(stats.mood_distribution).length > 0" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-2 text-sm">情绪分布</h3>
            <div class="space-y-1">
              <div v-for="(cnt, mood) in stats.mood_distribution" :key="mood" class="flex items-center justify-between text-xs"><span class="text-slate-600">{{ moodIcons[mood] || '💬' }} {{ mood }}</span><span class="font-medium text-slate-500">{{ cnt }}天</span></div>
            </div>
          </div>
        </div>
      </div>

      <!-- 弹窗：日报预览 -->
      <Teleport to="body">
        <div v-if="dayPopup" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" @click.self="dayPopup = null">
          <div class="bg-white rounded-2xl shadow-xl w-full max-w-md mx-4 max-h-[80vh] overflow-y-auto p-6">
            <div class="flex items-center justify-between mb-4"><h3 class="font-semibold text-slate-800">{{ dayPopup.date }}</h3><button @click="dayPopup = null" class="p-1 rounded-full hover:bg-slate-100"><XCircle :size="16" class="text-slate-400"/></button></div>
            <div class="space-y-3">
              <div class="grid grid-cols-2 gap-2 text-xs"><div class="bg-slate-50 rounded-lg p-2"><span class="text-slate-400">消息数</span><br><strong>{{ dayPopup.count }}</strong></div><div class="bg-slate-50 rounded-lg p-2"><span class="text-slate-400">活跃成员</span><br><strong>{{ dayPopup.active_members || '—' }}</strong></div></div>
              <div v-if="dayPopup.analyzed && dayPopup.report" class="bg-indigo-50 rounded-xl p-4"><div class="text-2xl mb-1">{{ dayPopup.report.mood_emoji }}</div><p class="text-sm font-medium text-slate-800">{{ dayPopup.report.one_line }}</p><p class="text-xs text-slate-500 mt-2">{{ dayPopup.report.mood }}</p><button @click="viewReportFromPopup()" class="mt-3 text-xs bg-indigo-500 text-white px-3 py-1.5 rounded-lg hover:bg-indigo-600 transition-colors">查看完整报告 →</button></div>
              <div v-else-if="dayPopup.hasData" class="bg-amber-50 rounded-xl p-4 text-center"><p class="text-sm text-amber-700">该日期尚未分析</p><button @click="handleGenerateReport()" class="mt-2 text-xs bg-amber-500 text-white px-3 py-1.5 rounded-lg hover:bg-amber-600 transition-colors">立即分析</button></div>
            </div>
          </div>
        </div>
      </Teleport>
    </template>
    <UploadModal v-if="showUpload" @close="showUpload = false" @uploaded="showUpload = false; loadAll(); loadPeriods()" />
    <WeFlowImportModal v-if="showWeFlow" :group="currentGroup" @close="showWeFlow = false" />

    <!-- 年报：月报不足确认弹窗 -->
    <Teleport to="body">
      <div v-if="showAnnualConfirm" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm" @click.self="showAnnualConfirm = false">
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-sm mx-4 p-6 text-center animate-scale-in">
          <div class="text-5xl mb-3">📋</div>
          <h3 class="text-lg font-bold text-slate-800 mb-2">月报数量不足</h3>
          <p class="text-sm text-slate-500 mb-1">
            {{ pendingAnnualYear }} 年仅生成了 <strong class="text-amber-600">{{ monthlyPeriods.filter(p => p.period_key.startsWith(pendingAnnualYear) && p.status === 'generated').length }}</strong> 个月报（建议至少 6 个）。
          </p>
          <p class="text-xs text-slate-400 mb-5">月报数据越丰富，年报的颁奖典礼越精彩。是否继续生成？</p>
          <div class="flex gap-3 justify-center">
            <button @click="showAnnualConfirm = false" class="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-xl transition-colors">取消</button>
            <button @click="_executeAnnualGenerate(pendingAnnualYear, true)" class="px-5 py-2 text-sm font-medium text-white bg-amber-500 hover:bg-amber-600 rounded-xl shadow-lg shadow-amber-200 transition-all">继续生成</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
