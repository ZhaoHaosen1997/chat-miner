<script setup>
import { ref, inject, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  getDates, getRecentReports, getGroupStats, analyzeDate, getPortraits,
} from '../api/index.js'
import { MessageSquare, Users, Calendar, Sparkles, Loader2 } from 'lucide-vue-next'

const router = useRouter()
const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')

const stats = ref(null)
const dates = ref([])
const recentReports = ref([])
const loading = ref(false)
const analyzing = ref(false)
const portraits = ref([])

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

watch(currentGroup, loadAll, { immediate: true })

// 找到最新未分析的一天
const latestUnanalyzed = ref(null)
watch(dates, (d) => {
  const sorted = [...d].sort((a, b) => b.date.localeCompare(a.date))
  latestUnanalyzed.value = sorted.find(dt => !dt.analyzed) || null
})

async function analyzeLatest() {
  if (!latestUnanalyzed.value || analyzing.value) return
  analyzing.value = true
  try {
    await analyzeDate(currentGroup.value.id, latestUnanalyzed.value.date)
    await loadAll()
    triggerRefresh?.()
  } catch (e) {
    console.error(e)
  } finally {
    analyzing.value = false
  }
}

function goReport(date) {
  router.push(`/report/${date}`)
}

// 日历数据：最近60天
const calendarData = ref([])
watch(dates, (d) => {
  const now = new Date()
  const days = []
  for (let i = 59; i >= 0; i--) {
    const date = new Date(now)
    date.setDate(date.getDate() - i)
    const dateStr = date.toISOString().slice(0, 10)
    const info = d.find(dt => dt.date === dateStr)
    days.push({
      date: dateStr,
      label: date.toLocaleDateString('zh', { month: 'short', day: 'numeric' }),
      hasData: !!info,
      analyzed: info?.analyzed || false,
      count: info?.total_messages || 0,
    })
  }
  calendarData.value = days
})

// 情绪分布 emoji
const moodIcons = { '欢乐': '😄', '温馨': '🥰', '严肃': '🧐', '吐槽': '😤', '平淡': '😐', '热闹': '🎉', '伤感': '😢', '沙雕': '🤪' }

// 消息量给颜色
function barColor(count, max) {
  const pct = max > 0 ? count / max : 0
  if (pct > 0.7) return 'bg-indigo-500'
  if (pct > 0.4) return 'bg-indigo-400'
  if (pct > 0.15) return 'bg-indigo-300'
  return 'bg-indigo-200'
}
</script>

<template>
  <div v-if="currentGroup">
    <!-- 加载状态 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <template v-else>
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
          <!-- 分析最新一天 -->
          <div class="card p-4 flex items-center justify-between">
            <div>
              <div class="font-semibold text-slate-700">每日分析</div>
              <div class="text-sm text-slate-400 mt-0.5">
                最新未分析：
                <span class="font-medium text-slate-600">{{ latestUnanalyzed?.date || '全部已分析' }}</span>
                <span v-if="latestUnanalyzed" class="ml-2">({{ latestUnanalyzed.text_messages }} 条文本)</span>
              </div>
            </div>
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
          </div>

          <!-- 日历热力图 -->
          <div class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-3">数据日历</h3>
            <div class="grid grid-cols-10 gap-1">
              <div
                v-for="day in calendarData"
                :key="day.date"
                :title="`${day.date}: ${day.hasData ? day.count + '条消息' : '无数据'}${day.analyzed ? ' (已分析)' : ''}`"
                :class="[
                  'w-full aspect-square rounded-md text-[10px] flex items-center justify-center transition-colors',
                  !day.hasData ? 'bg-slate-50 border border-slate-100 text-transparent' :
                  day.analyzed ? 'bg-emerald-100 text-emerald-700 border border-emerald-200' :
                  'bg-indigo-50 text-indigo-400 border border-indigo-100',
                ]"
              >
                {{ day.label.slice(0, 2) }}
              </div>
            </div>
            <div class="flex items-center gap-4 mt-3 text-xs text-slate-400">
              <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-slate-50 border border-slate-100" /> 无数据</span>
              <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-indigo-50 border border-indigo-100" /> 有数据</span>
              <span class="flex items-center gap-1"><span class="w-3 h-3 rounded bg-emerald-100 border border-emerald-200" /> 已分析</span>
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
  </div>
</template>
