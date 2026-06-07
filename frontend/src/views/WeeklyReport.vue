<script setup>
import { ref, inject, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getWeeklyReport, generateWeekly, getPeriods } from '../api/index.js'
import { ArrowLeft, ArrowRight, ArrowRightToLine, ArrowLeftToLine, Sparkles, Loader2, Hash, TrendingUp, Quote, Calendar, MessageSquare, Users } from 'lucide-vue-next'

const props = defineProps({ weekId: String })
const router = useRouter()
const currentGroup = inject('currentGroup')
const activeTaskId = inject('activeTaskId')
const triggerRefresh = inject('triggerRefresh')

const report = ref(null)
const loading = ref(true)
const generating = ref(false)
const error = ref('')
const weekRange = ref('')

// 相邻周
const adjacentWeeks = ref({ prev: null, next: null })

async function load() {
  if (!currentGroup.value || !props.weekId) return
  loading.value = true
  error.value = ''
  try {
    const data = await getWeeklyReport(currentGroup.value.id, props.weekId)
    report.value = data
    weekRange.value = `${data.date_start} ~ ${data.date_end}`
  } catch (e) {
    if (e.message?.includes('404') || e.message?.includes('尚未生成')) {
      error.value = 'not_generated'
      // 解析周范围
      const parts = props.weekId.split('-W')
      if (parts.length === 2) {
        const y = parseInt(parts[0]), w = parseInt(parts[1])
        // ISO week date calculation
        const jan4 = new Date(y, 0, 4)
        const dow = jan4.getDay() || 7
        const firstMonday = new Date(jan4)
        firstMonday.setDate(jan4.getDate() - (dow - 1))
        const monday = new Date(firstMonday)
        monday.setDate(firstMonday.getDate() + (w - 1) * 7)
        const sunday = new Date(monday)
        sunday.setDate(monday.getDate() + 6)
        const fmt = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
        weekRange.value = `${fmt(monday)} ~ ${fmt(sunday)}`
      }
    } else {
      error.value = e.message
    }
  } finally {
    loading.value = false
  }

  // 加载相邻周
  try {
    const periods = await getPeriods(currentGroup.value.id, 'weekly')
    const weeks = periods.filter(p => p.status !== 'insufficient')
    const idx = weeks.findIndex(p => p.period_key === props.weekId)
    adjacentWeeks.value.prev = idx > 0 ? weeks[idx - 1].period_key : null
    adjacentWeeks.value.next = idx < weeks.length - 1 ? weeks[idx + 1].period_key : null
  } catch (e) { /* ignore */ }
}

async function startGenerate() {
  if (generating.value || activeTaskId.value) return
  generating.value = true
  try {
    const result = await generateWeekly(currentGroup.value.id, props.weekId)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    } else if (result === null) {
      error.value = '本周数据不足，无法生成'
      generating.value = false
    }
  } catch (e) {
    error.value = e.message
    generating.value = false
  }
}

watch([currentGroup, () => props.weekId], load, { immediate: true })

watch(activeTaskId, (newVal, oldVal) => {
  if (oldVal && !newVal) {
    generating.value = false
    load()
    triggerRefresh?.()
  }
})

function goBack() { router.push('/') }
function goWeek(key) { if (key) router.push(`/weekly/${key}`) }
</script>

<template>
  <div>
    <button @click="goBack" class="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 mb-4 transition-colors">
      <ArrowLeft class="w-4 h-4" /> 返回仪表盘
    </button>

    <!-- 加载 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <!-- 未生成 -->
    <div v-else-if="error === 'not_generated'" class="card p-12 text-center">
      <Sparkles class="w-12 h-12 text-slate-300 mx-auto mb-3" />
      <p class="text-slate-500 mb-2">第 {{ props.weekId }} 周 （{{ weekRange }}） 尚未生成周报</p>
      <button
        @click="startGenerate"
        :disabled="generating || !!activeTaskId"
        class="px-5 py-2.5 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 transition-all inline-flex items-center gap-2 disabled:opacity-50"
      >
        <Loader2 v-if="generating" class="w-4 h-4 animate-spin" />
        <Sparkles v-else class="w-4 h-4" />
        {{ generating ? 'AI 生成中...' : '生成周报' }}
      </button>
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="card p-8 text-center">
      <p class="text-red-400">加载失败：{{ error }}</p>
    </div>

    <!-- 报告内容 -->
    <template v-else-if="report">
      <!-- 头部 -->
      <div class="card p-6 mb-6 text-center">
        <div class="text-3xl mb-2">📊</div>
        <h2 class="text-xl font-bold text-slate-800 mb-1">
          第 {{ props.weekId }} 周 · 群聊周报
        </h2>
        <p class="text-sm text-slate-400 mb-2">{{ report.date_start }} 周一 ~ {{ report.date_end }} 周日</p>
        <div class="flex items-center justify-center gap-4 text-sm text-slate-500">
          <span>📅 {{ report.day_count }}天有数据</span>
          <span>💬 {{ report.total_messages?.toLocaleString() }}条消息</span>
          <span>👥 日均 {{ report.active_members_avg }}人活跃</span>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2 space-y-6">
          <!-- AI 综述 -->
          <div v-if="report.overview" class="card p-5 bg-gradient-to-r from-indigo-50 to-purple-50 border-indigo-100">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <Sparkles class="w-4 h-4 text-indigo-400" /> 本周综述
            </h3>
            <p class="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{{ report.overview }}</p>
          </div>

          <!-- 情绪过山车 -->
          <div v-if="report.mood_rollercoaster" class="card p-5">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <TrendingUp class="w-4 h-4 text-amber-400" /> 情绪过山车
            </h3>
            <!-- 情绪时间线 -->
            <div v-if="report.mood_timeline?.length" class="flex flex-wrap gap-1 mb-3">
              <span
                v-for="e in report.mood_timeline"
                :key="e.date"
                :title="`${e.date} ${e.mood}`"
                class="text-sm cursor-default hover:scale-125 transition-transform"
              >{{ e.mood_emoji || '💬' }}</span>
            </div>
            <p class="text-sm text-slate-600 leading-relaxed">{{ report.mood_rollercoaster }}</p>
          </div>

          <!-- 名场面回顾 -->
          <div v-if="report.highlight_quotes?.length" class="card p-5">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <Quote class="w-4 h-4 text-amber-400" /> 名场面回顾
            </h3>
            <div class="space-y-3">
              <div
                v-for="(q, i) in report.highlight_quotes"
                :key="i"
                class="p-3 bg-amber-50/50 rounded-xl border border-amber-100"
              >
                <div class="flex items-start gap-2 mb-1">
                  <span class="text-sm font-medium text-amber-700">{{ q.speaker }}</span>
                  <span class="text-[10px] text-slate-400">{{ q.date }}</span>
                </div>
                <p class="text-sm text-slate-700 leading-relaxed mb-1">"{{ q.quote }}"</p>
                <div class="flex items-center justify-between">
                  <p v-if="q.comment" class="text-xs text-amber-500 italic">— {{ q.comment }}</p>
                  <p v-if="report.highlight_comments?.[i]" class="text-xs text-indigo-500 font-medium ml-auto">
                    🤖 {{ report.highlight_comments[i] }}
                  </p>
                </div>
              </div>
            </div>
          </div>

          <!-- 下周预告 -->
          <div v-if="report.next_week_preview" class="card p-5 bg-gradient-to-r from-emerald-50 to-teal-50 border-emerald-100">
            <p class="text-sm text-emerald-700 font-medium">🔮 {{ report.next_week_preview }}</p>
          </div>
        </div>

        <!-- 侧栏 -->
        <div class="space-y-4">
          <!-- 热门话题 -->
          <div v-if="report.top_topics?.length" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-1.5 text-sm">
              <Hash class="w-3.5 h-3.5 text-indigo-400" /> 话题热度 TOP 5
            </h3>
            <div class="space-y-2">
              <div
                v-for="(t, i) in report.top_topics.slice(0, 5)"
                :key="i"
                class="flex items-center gap-2"
              >
                <span :class="[
                  'w-5 h-5 rounded text-[10px] font-bold flex items-center justify-center flex-shrink-0',
                  i === 0 ? 'bg-red-500 text-white' :
                  i === 1 ? 'bg-orange-400 text-white' :
                  i === 2 ? 'bg-amber-400 text-white' :
                  'bg-slate-200 text-slate-500',
                ]">{{ i + 1 }}</span>
                <span class="text-sm text-slate-600 flex-1 truncate">{{ t.text }}</span>
                <span class="text-xs text-slate-400">{{ t.heat }}</span>
              </div>
            </div>
          </div>

          <!-- 关键词 -->
          <div v-if="report.top_keywords?.length" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-2 text-sm">关键词</h3>
            <div class="flex flex-wrap gap-1">
              <span
                v-for="kw in report.top_keywords.slice(0, 8)"
                :key="kw.text"
                class="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-xs"
              >{{ kw.text }}</span>
            </div>
          </div>

          <!-- 最热/最冷日 -->
          <div v-if="report.hottest_day" class="card p-4">
            <div class="text-xs text-slate-400 mb-1">最热闹的一天</div>
            <div class="text-sm font-medium text-slate-700">{{ report.hottest_day.date }}</div>
            <div class="text-xs text-slate-400">{{ report.hottest_day.msg_count }}条 · {{ report.hottest_day.mood_emoji }} {{ report.hottest_day.one_line }}</div>
          </div>
          <div v-if="report.coldest_day" class="card p-4">
            <div class="text-xs text-slate-400 mb-1">最冷清的一天</div>
            <div class="text-sm font-medium text-slate-700">{{ report.coldest_day.date }}</div>
            <div class="text-xs text-slate-400">{{ report.coldest_day.msg_count }}条</div>
          </div>

          <!-- 情绪分布 -->
          <div v-if="report.mood_ranking?.length" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-2 text-sm">情绪分布</h3>
            <div class="space-y-1.5">
              <div v-for="m in report.mood_ranking" :key="m.mood"
                   class="flex items-center justify-between text-xs">
                <span class="text-slate-500">{{ m.mood }}</span>
                <span class="font-medium text-slate-600">{{ m.count }}天</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 底部导航 -->
      <div class="flex items-center justify-between mt-6">
        <button
          v-if="adjacentWeeks.prev"
          @click="goWeek(adjacentWeeks.prev)"
          class="flex items-center gap-1 text-sm text-slate-400 hover:text-indigo-500 transition-colors"
        >
          <ArrowLeft class="w-4 h-4" /> {{ adjacentWeeks.prev }}
        </button>
        <span v-else class="text-sm text-slate-300">已是第一周</span>
        <button
          v-if="adjacentWeeks.next"
          @click="goWeek(adjacentWeeks.next)"
          class="flex items-center gap-1 text-sm text-slate-400 hover:text-indigo-500 transition-colors"
        >
          {{ adjacentWeeks.next }} <ArrowRight class="w-4 h-4" />
        </button>
        <span v-else class="text-sm text-slate-300">已是最新周</span>
      </div>
    </template>
  </div>
</template>
