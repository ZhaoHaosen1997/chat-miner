<script setup>
import { ref, inject, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  getDates, getRecentReports, getGroupStats, analyzeDateAsync, analyzeAll, getPortraits,
} from '../api/index.js'
import { MessageSquare, Users, Calendar, Sparkles, Loader2, Upload, Zap } from 'lucide-vue-next'
import UploadModal from '../components/UploadModal.vue'

const router = useRouter()
const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')
const activeTaskId = inject('activeTaskId')

const stats = ref(null)
const dates = ref([])
const recentReports = ref([])
const loading = ref(false)
const analyzing = ref(false)
const portraits = ref([])
const showUpload = ref(false)

async function loadAll() {
  if (!currentGroup.value) return
  loading.value = true
  const gid = currentGroup.value.id
  try {
    const [s, d, r, p] = await Promise.all([
      getGroupStats(gid),
      getDates(gid),
      getRecentReports(gid, 14),
      getPortraits(gid),
    ])
    stats.value = s
    dates.value = d
    recentReports.value = r
    portraits.value = p
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

watch(currentGroup, () => { monthOffset.value = 0; loadAll() }, { immediate: true })

// 监听全局任务完成
watch(activeTaskId, (newVal, oldVal) => {
  if (oldVal && !newVal) {
    // 任务 ID 被清空 = 任务结束
    analyzing.value = false
    batchTotal.value = 0
    loadAll()
    triggerRefresh?.()
  }
})

// 最新未分析的一天
const latestUnanalyzed = ref(null)
watch(dates, (d) => {
  const sorted = [...d].sort((a, b) => b.date.localeCompare(a.date))
  latestUnanalyzed.value = sorted.find(dt => !dt.analyzed) || null
})

async function analyzeLatest() {
  if (!latestUnanalyzed.value || analyzing.value) return
  analyzing.value = true
  try {
    const result = await analyzeDateAsync(currentGroup.value.id, latestUnanalyzed.value.date)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    } else if (result.cached) {
      await loadAll(); triggerRefresh?.(); analyzing.value = false
    }
  } catch (e) { console.error(e); analyzing.value = false }
}

const batchTotal = ref(0)

async function startAnalyzeAll() {
  if (analyzing.value || activeTaskId.value) return
  analyzing.value = true
  try {
    const result = await analyzeAll(currentGroup.value.id)
    if (result.task_id) {
      activeTaskId.value = result.task_id
      batchTotal.value = result.total_unanalyzed || 0
    } else if (result.total_unanalyzed === 0) {
      analyzing.value = false
    }
  } catch (e) { console.error(e); analyzing.value = false }
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

// 当月偏移（0=当前月, -1=上月, 1=下月）
const monthOffset = ref(0)

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
    const dateStr = dateObj.toISOString().slice(0, 10)
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
const moodIcons = { '欢乐': '😄', '温馨': '🥰', '严肃': '🧐', '吐槽': '😤', '平淡': '😐', '热闹': '🎉', '伤感': '😢', '沙雕': '🤪' }
</script>

<template>
  <div v-if="currentGroup">
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <template v-else>
      <!-- 数据日期横幅 -->
      <div v-if="stats?.group?.date_range_start" class="card p-3 mb-5 flex items-center gap-2 text-sm text-slate-500">
        <span class="text-base">📅</span>
        <span class="font-medium text-slate-700">数据范围：{{ stats.group.date_range_start }} ~ {{ stats.group.date_range_end }}</span>
        <span class="text-slate-300">·</span>
        <span>共 <strong class="text-slate-700">{{ stats.total_days_with_data }}</strong> 天有消息</span>
        <span class="text-slate-300">·</span>
        <span>已分析 <strong class="text-emerald-600">{{ stats.analyzed_count }}</strong> 天</span>
        <span v-if="stats.analyzed_count > 0" class="text-slate-300">·</span>
        <span v-if="stats.analyzed_count > 0">
          进度 <strong class="text-indigo-600">{{ stats.progress_pct }}%</strong>
        </span>
      </div>

      <!-- 概览卡片 -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div class="card p-4 flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-indigo-100 flex items-center justify-center">
            <MessageSquare class="w-5 h-5 text-indigo-600" />
          </div>
          <div>
            <div class="text-2xl font-bold text-slate-800">{{ (stats?.group?.message_count || 0).toLocaleString() }}</div>
            <div class="text-xs text-slate-400">总消息数</div>
          </div>
        </div>

        <div class="card p-4 flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-emerald-100 flex items-center justify-center">
            <Calendar class="w-5 h-5 text-emerald-600" />
          </div>
          <div>
            <div class="text-2xl font-bold text-slate-800">{{ stats?.analyzed_count || 0 }}<span class="text-base font-normal text-slate-400">/{{ dates.length }}</span></div>
            <div class="text-xs text-slate-400">已分析天数</div>
          </div>
        </div>

        <div class="card p-4 flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-amber-100 flex items-center justify-center">
            <Users class="w-5 h-5 text-amber-600" />
          </div>
          <div>
            <div class="text-2xl font-bold text-slate-800">{{ stats?.member_count || 0 }}</div>
            <div class="text-xs text-slate-400">群成员</div>
          </div>
        </div>

        <div class="card p-4 flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-rose-100 flex items-center justify-center">
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
              <div class="font-semibold text-slate-700">每日分析</div>
              <div class="text-sm text-slate-400 mt-0.5 truncate">
                最新未分析：
                <span class="font-medium text-slate-600">{{ latestUnanalyzed?.date || '全部已分析' }}</span>
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
                @click="analyzeLatest"
                :disabled="!latestUnanalyzed || analyzing"
                :class="[
                  'flex items-center gap-2 px-4 py-2.5 rounded-xl font-medium text-sm transition-all',
                  latestUnanalyzed && !analyzing
                    ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-lg shadow-indigo-200'
                    : 'bg-slate-100 text-slate-400',
                ]"
              >
                <Loader2 v-if="analyzing" class="w-4 h-4 animate-spin" />
                <Sparkles v-else class="w-4 h-4" />
                {{ analyzing ? 'AI 分析中...' : '分析最新一天' }}
              </button>
              <button
                v-if="(stats?.total_days_with_data - (stats?.analyzed_count || 0)) > 1"
                @click="startAnalyzeAll"
                :disabled="analyzing"
                :class="[
                  'flex items-center gap-2 px-4 py-2.5 rounded-xl font-medium text-sm transition-all',
                  !analyzing
                    ? 'bg-emerald-600 text-white hover:bg-emerald-700 shadow-lg shadow-emerald-200'
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
                   @click="day?.analyzed && goReport(day.date)">
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
            <h3 class="font-semibold text-slate-700 mb-3">最近报告</h3>
            <div v-if="recentReports.length === 0" class="text-sm text-slate-400 py-8 text-center">
              还没有分析过，点击"分析最新一天"开始吧 ✨
            </div>
            <div v-else class="space-y-2">
              <button
                v-for="r in recentReports.slice(0, 7)"
                :key="r.date"
                @click="goReport(r.date)"
                class="w-full text-left card p-3 hover:border-indigo-200 transition-colors flex items-center gap-3 group"
              >
                <span class="text-2xl">{{ r.mood_emoji || '💬' }}</span>
                <div class="flex-1 min-w-0">
                  <div class="text-sm font-medium text-slate-700 truncate group-hover:text-indigo-600 transition-colors">
                    {{ r.one_line || r.date }}
                  </div>
                  <div class="text-xs text-slate-400 mt-0.5">
                    {{ r.date }} · {{ r.message_count }} 条消息 · {{ r.active_members }} 人活跃
                  </div>
                </div>
                <div class="flex gap-1">
                  <span
                    v-for="kw in (r.keywords || []).slice(0, 3)"
                    :key="kw"
                    class="px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full text-[11px]"
                  >{{ kw }}</span>
                </div>
              </button>
            </div>
          </div>
        </div>

        <!-- 右列：统计 -->
        <div class="space-y-6">
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
  </div>
</template>
