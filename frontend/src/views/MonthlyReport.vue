<script setup>
import { ref, inject, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getMonthlyReport, generateMonthly, getPeriods } from '../api/index.js'
import { ArrowLeft, ArrowRight, Sparkles, Loader2, Hash, TrendingUp, Calendar, MessageSquare, Users } from 'lucide-vue-next'

const props = defineProps({ monthId: String })
const router = useRouter()
const currentGroup = inject('currentGroup')
const activeTaskId = inject('activeTaskId')
const triggerRefresh = inject('triggerRefresh')

const report = ref(null)
const loading = ref(true)
const generating = ref(false)
const error = ref('')
const monthLabel = ref('')

// 相邻月
const adjacentMonths = ref({ prev: null, next: null })

function parseMonth(key) {
  const parts = key.split('-')
  const y = parseInt(parts[0]), m = parseInt(parts[1])
  const monthNames = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
  return { year: y, month: m, label: `${y}年${monthNames[m-1]}` }
}

async function load() {
  if (!currentGroup.value || !props.monthId) return
  loading.value = true
  error.value = ''
  try {
    const data = await getMonthlyReport(currentGroup.value.id, props.monthId)
    report.value = data
    monthLabel.value = parseMonth(props.monthId).label
  } catch (e) {
    if (e.message?.includes('404') || e.message?.includes('尚未生成')) {
      error.value = 'not_generated'
      monthLabel.value = parseMonth(props.monthId).label
    } else {
      error.value = e.message
    }
  } finally {
    loading.value = false
  }

  try {
    const periods = await getPeriods(currentGroup.value.id, 'monthly')
    const months = periods.filter(p => p.status !== 'insufficient')
    const idx = months.findIndex(p => p.period_key === props.monthId)
    adjacentMonths.value.prev = idx > 0 ? months[idx - 1].period_key : null
    adjacentMonths.value.next = idx < months.length - 1 ? months[idx + 1].period_key : null
  } catch (e) { /* ignore */ }
}

async function startGenerate() {
  if (generating.value || activeTaskId.value) return
  generating.value = true
  try {
    const result = await generateMonthly(currentGroup.value.id, props.monthId)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    } else if (result === null) {
      error.value = '本月数据不足，无法生成'
      generating.value = false
    }
  } catch (e) {
    error.value = e.message
    generating.value = false
  }
}

watch([currentGroup, () => props.monthId], load, { immediate: true })

watch(activeTaskId, (newVal, oldVal) => {
  if (oldVal && !newVal) {
    generating.value = false
    load()
    triggerRefresh?.()
  }
})

function goBack() { router.push('/') }
function goMonth(key) { if (key) router.push(`/monthly/${key}`) }
</script>

<template>
  <div>
    <button @click="goBack" class="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 mb-4 transition-colors">
      <ArrowLeft class="w-4 h-4" /> 返回仪表盘
    </button>

    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <div v-else-if="error === 'not_generated'" class="card p-12 text-center">
      <Sparkles class="w-12 h-12 text-slate-300 mx-auto mb-3" />
      <p class="text-slate-500 mb-2">{{ monthLabel }}月报尚未生成</p>
      <button
        @click="startGenerate"
        :disabled="generating || !!activeTaskId"
        class="px-5 py-2.5 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 transition-all inline-flex items-center gap-2 disabled:opacity-50"
      >
        <Loader2 v-if="generating" class="w-4 h-4 animate-spin" />
        <Sparkles v-else class="w-4 h-4" />
        {{ generating ? 'AI 生成中...' : '生成月报' }}
      </button>
    </div>

    <div v-else-if="error" class="card p-8 text-center">
      <p class="text-red-400">加载失败：{{ error }}</p>
    </div>

    <template v-else-if="report">
      <!-- 头部 -->
      <div class="card p-6 mb-6 text-center">
        <div class="text-4xl mb-2">📅</div>
        <h2 class="text-xl font-bold text-slate-800 mb-1">{{ monthLabel }} · 群聊月报</h2>
        <p class="text-sm text-slate-400 mb-2">{{ report.date_start }} ~ {{ report.date_end }}</p>
        <div class="flex items-center justify-center gap-4 text-sm text-slate-500">
          <span>📅 {{ report.day_count }}天有数据</span>
          <span>💬 {{ report.total_messages?.toLocaleString() }}条消息</span>
          <span>👥 日均 {{ report.active_members_avg }}人活跃</span>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div class="lg:col-span-2 space-y-6">
          <!-- 月度综述 -->
          <div v-if="report.overview" class="card p-5 bg-gradient-to-r from-indigo-50 to-purple-50 border-indigo-100">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <Sparkles class="w-4 h-4 text-indigo-400" /> 月度综述
            </h3>
            <p class="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{{ report.overview }}</p>
          </div>

          <!-- 社群氛围诊断 -->
          <div v-if="report.atmosphere_diagnosis" class="card p-5">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <TrendingUp class="w-4 h-4 text-purple-400" /> 社群氛围诊断
            </h3>
            <p class="text-sm text-slate-600 leading-relaxed">{{ report.atmosphere_diagnosis }}</p>
          </div>

          <!-- 群友聚光灯 -->
          <div v-if="report.member_spotlight" class="card p-5 bg-gradient-to-r from-amber-50 to-orange-50 border-amber-100">
            <h3 class="font-semibold text-slate-700 mb-2 flex items-center gap-2">
              <Users class="w-4 h-4 text-amber-400" /> 群友聚光灯
            </h3>
            <p class="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{{ report.member_spotlight }}</p>
          </div>

          <!-- 下月展望 -->
          <div v-if="report.next_month_preview" class="card p-5 bg-gradient-to-r from-emerald-50 to-teal-50 border-emerald-100">
            <p class="text-sm text-emerald-700 font-medium">🔮 {{ report.next_month_preview }}</p>
          </div>
        </div>

        <!-- 侧栏 -->
        <div class="space-y-4">
          <!-- 热门话题 -->
          <div v-if="report.top_topics?.length" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-1.5 text-sm">
              <Hash class="w-3.5 h-3.5 text-indigo-400" /> 本月热议 TOP 5
            </h3>
            <div class="space-y-2">
              <div v-for="(t, i) in report.top_topics.slice(0, 5)" :key="i" class="flex items-center gap-2">
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
              <span v-for="kw in report.top_keywords.slice(0, 8)" :key="kw.text"
                    class="px-2 py-0.5 bg-slate-100 text-slate-600 rounded-full text-xs">{{ kw.text }}</span>
            </div>
          </div>

          <!-- 情绪时间线 -->
          <div v-if="report.mood_timeline?.length" class="card p-4">
            <h3 class="font-semibold text-slate-700 mb-2 text-sm">每日情绪</h3>
            <div class="flex flex-wrap gap-[2px]">
              <span v-for="e in report.mood_timeline" :key="e.date"
                    :title="`${e.date} ${e.mood}`"
                    class="text-sm leading-none cursor-default hover:scale-125 transition-transform"
              >{{ e.mood_emoji || '💬' }}</span>
            </div>
          </div>

          <!-- 最热/最冷 -->
          <div v-if="report.hottest_day" class="card p-4">
            <div class="text-xs text-slate-400 mb-1">最热闹的一天</div>
            <div class="text-sm font-medium text-slate-700">{{ report.hottest_day.date }}</div>
            <div class="text-xs text-slate-400">{{ report.hottest_day.msg_count }}条 · {{ report.hottest_day.mood_emoji }} {{ report.hottest_day.one_line }}</div>
          </div>
        </div>
      </div>

      <!-- 底部导航 -->
      <div class="flex items-center justify-between mt-6">
        <button v-if="adjacentMonths.prev" @click="goMonth(adjacentMonths.prev)"
                class="flex items-center gap-1 text-sm text-slate-400 hover:text-indigo-500 transition-colors">
          <ArrowLeft class="w-4 h-4" /> {{ adjacentMonths.prev }}
        </button>
        <span v-else class="text-sm text-slate-300">已是第一个月</span>
        <button v-if="adjacentMonths.next" @click="goMonth(adjacentMonths.next)"
                class="flex items-center gap-1 text-sm text-slate-400 hover:text-indigo-500 transition-colors">
          {{ adjacentMonths.next }} <ArrowRight class="w-4 h-4" />
        </button>
        <span v-else class="text-sm text-slate-300">已是最新月</span>
      </div>
    </template>
  </div>
</template>
