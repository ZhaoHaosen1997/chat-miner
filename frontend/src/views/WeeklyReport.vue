<script setup>
import { ref, inject, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getWeeklyReport, generateWeekly, getPeriods } from '../api/index.js'
import { ArrowLeft, ArrowRight, ArrowRightToLine, ArrowLeftToLine, Sparkles, Loader2, Hash, TrendingUp, Quote, Calendar, MessageSquare, Users, Newspaper, Flame, Trophy, BookOpen } from 'lucide-vue-next'

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

// 根据情绪氛围选择头条颜色
const moodColors = {
  '欢乐': { bg: 'linear-gradient(135deg, #dc2626, #ea580c, #f59e0b)', badge: 'bg-red-500/20 text-red-200' },
  '热闹': { bg: 'linear-gradient(135deg, #e11d48, #f43f5e, #fb7185)', badge: 'bg-rose-500/20 text-rose-200' },
  '沙雕': { bg: 'linear-gradient(135deg, #d946ef, #a855f7, #6366f1)', badge: 'bg-purple-500/20 text-purple-200' },
  '温馨': { bg: 'linear-gradient(135deg, #f97316, #fb923c, #fbbf24)', badge: 'bg-orange-500/20 text-orange-200' },
  '吐槽': { bg: 'linear-gradient(135deg, #475569, #334155, #1e293b)', badge: 'bg-slate-500/20 text-slate-200' },
  '吃瓜': { bg: 'linear-gradient(135deg, #ca8a04, #eab308, #facc15)', badge: 'bg-yellow-500/20 text-yellow-200' },
  '摸鱼': { bg: 'linear-gradient(135deg, #0891b2, #06b6d4, #22d3ee)', badge: 'bg-cyan-500/20 text-cyan-200' },
  '伤感': { bg: 'linear-gradient(135deg, #6366f1, #818cf8, #a5b4fc)', badge: 'bg-indigo-500/20 text-indigo-200' },
  '破防': { bg: 'linear-gradient(135deg, #be123c, #e11d48, #fb7185)', badge: 'bg-rose-600/20 text-rose-200' },
  '离谱': { bg: 'linear-gradient(135deg, #7c3aed, #8b5cf6, #c084fc)', badge: 'bg-purple-600/20 text-purple-200' },
  '平淡': { bg: 'linear-gradient(135deg, #334155, #475569, #64748b)', badge: 'bg-slate-600/20 text-slate-200' },
}
const defaultMood = { bg: 'linear-gradient(135deg, #dc2626, #ea580c, #f59e0b)', badge: 'bg-red-500/20 text-red-200' }

const headlineColors = computed(() => {
  if (!report.value?.mood_ranking?.length) return defaultMood
  // 取出现最多的情绪
  const top = report.value.mood_ranking[0]
  return moodColors[top.mood] || defaultMood
})
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

    <!-- 报告内容 v0.7.3: Bento Grid 杂志布局 -->
    <template v-else-if="report">
      <!-- 头部 -->
      <div class="text-center mb-8">
        <div class="text-4xl mb-2">📰</div>
        <h2 class="text-2xl font-bold text-slate-800 mb-1">群聊周报</h2>
        <p class="text-sm text-slate-400">{{ report.date_start }} 周一 ~ {{ report.date_end }} 周日</p>
        <div class="flex items-center justify-center gap-5 mt-2 text-xs text-slate-400">
          <span>📅 {{ report.day_count }}天</span>
          <span>💬 {{ report.total_messages?.toLocaleString() }}条</span>
          <span>👥 {{ report.active_members_avg }}人</span>
        </div>
      </div>

      <!-- Hero: 群聊头条（情绪自适应配色） -->
      <div v-if="report.week_headline" class="rounded-2xl p-8 mb-8 text-white text-center shadow-xl" :style="{ background: headlineColors.bg }">
        <p class="text-xs font-medium text-white/70 uppercase tracking-widest mb-3">📰 本周群聊头条</p>
        <p class="text-xl md:text-3xl font-black leading-tight">{{ report.week_headline }}</p>
      </div>

      <!-- Row 1: AI 锐评 + 数据快照 -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-5 mb-6">
        <div v-if="report.ai_roast" class="rounded-2xl p-6 text-white shadow-lg" style="background: linear-gradient(135deg, #1e293b, #334155)">
          <h3 class="font-semibold mb-3 flex items-center gap-2 text-amber-400"><Flame class="w-4 h-4" /> AI 锐评</h3>
          <p class="text-sm leading-relaxed text-slate-100 whitespace-pre-line">{{ report.ai_roast }}</p>
        </div>
        <div v-else-if="report.overview && !report.week_headline" class="rounded-2xl p-6 shadow-sm border border-indigo-100" style="background: linear-gradient(135deg, #eef2ff, #f5f3ff)">
          <h3 class="font-semibold mb-3 flex items-center gap-2 text-indigo-600"><Sparkles class="w-4 h-4" /> 本周综述</h3>
          <p class="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{{ report.overview }}</p>
        </div>

        <!-- 数据快照 -->
        <div class="space-y-3">
          <div v-if="report.top_speakers?.length" class="rounded-2xl p-4 shadow-sm border border-slate-100 bg-white">
            <div class="text-xs text-slate-400 mb-2 font-medium">💬 发言排行</div>
            <div class="space-y-1.5">
              <div v-for="(s, i) in report.top_speakers.slice(0, 5)" :key="i" class="flex items-center justify-between text-xs">
                <span class="text-slate-600">{{ i+1 }}. {{ s.alias }}</span>
                <span class="font-medium text-slate-400">{{ s.count }}条</span>
              </div>
            </div>
          </div>
          <div v-if="report.night_owls?.length" class="rounded-2xl p-3 shadow-sm border border-indigo-100 bg-indigo-50/30 text-xs">
            <span class="text-slate-400">🦉 深夜守群 </span>
            <span v-for="(n, i) in report.night_owls.slice(0, 3)" :key="i" class="text-slate-600">{{ n.alias }}{{ i < report.night_owls.slice(0,3).length-1 ? '、' : '' }}</span>
          </div>
          <div v-if="report.emoji_kings?.length" class="rounded-2xl p-3 shadow-sm border border-slate-100 bg-white text-xs">
            <span class="text-slate-400">😂 表情达人 </span>
            <span v-for="(e, i) in report.emoji_kings.slice(0, 3)" :key="i" class="text-slate-600">{{ e.alias }}{{ i < report.emoji_kings.slice(0,3).length-1 ? '、' : '' }}</span>
          </div>
          <div v-if="report.lurkers?.length" class="rounded-2xl p-3 shadow-sm border border-slate-100 bg-white text-xs">
            <span class="text-slate-400">🤿 潜水观察 </span>
            <span v-for="(l, i) in report.lurkers.slice(0, 3)" :key="i" class="text-slate-600">{{ l.alias }}{{ i < report.lurkers.slice(0,3).length-1 ? '、' : '' }}</span>
          </div>
        </div>
      </div>

      <!-- Row 2: 奖项 三列 -->
      <div v-if="report.weekly_awards?.length" class="mb-6">
        <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2 text-sm"><Trophy class="w-4 h-4 text-amber-400" /> 本周群聊奖项</h3>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <div v-for="(award, i) in report.weekly_awards" :key="i"
               class="rounded-2xl p-4 text-center shadow-sm border transition-all hover:shadow-md"
               :class="[i === 0 ? 'bg-amber-50 border-amber-200' : i === 1 ? 'bg-indigo-50 border-indigo-100' : 'bg-slate-50 border-slate-100']">
            <div class="text-3xl mb-2">{{ award.emoji || '🏆' }}</div>
            <div class="text-sm font-bold text-slate-700 mb-1">{{ award.award_name }}</div>
            <p class="text-xs text-slate-500"><span class="font-medium text-indigo-600">{{ award.winner }}</span> · {{ award.reason }}</p>
          </div>
        </div>
      </div>

      <!-- Row 3: 群聊故事 全宽 -->
      <div v-if="report.week_narrative" class="rounded-2xl p-6 mb-6 shadow-sm border border-blue-100" style="background: linear-gradient(135deg, #eff6ff, #eef2ff)">
        <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2"><BookOpen class="w-4 h-4 text-blue-400" /> 本周群聊故事</h3>
        <div class="flex items-start gap-4">
          <span class="text-4xl leading-none text-blue-300 flex-shrink-0">"</span>
          <p class="text-sm text-slate-600 leading-relaxed whitespace-pre-line italic">{{ report.week_narrative }}</p>
        </div>
      </div>

      <!-- Row 4: 情绪 + 预告 双栏 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-5 mb-6">
        <div v-if="report.mood_rollercoaster" class="rounded-2xl p-5 shadow-sm border border-amber-100 bg-white">
          <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2 text-sm"><TrendingUp class="w-4 h-4 text-amber-400" /> 情绪过山车</h3>
          <div v-if="report.mood_timeline?.length" class="flex flex-wrap gap-1 mb-3">
            <span v-for="e in report.mood_timeline" :key="e.date" :title="`${e.date} ${e.mood}`"
                  class="text-base cursor-default hover:scale-125 transition-transform">{{ e.mood_emoji || '💬' }}</span>
          </div>
          <p class="text-sm text-slate-600 leading-relaxed">{{ report.mood_rollercoaster }}</p>
        </div>
        <div v-if="report.next_week_preview" class="rounded-2xl p-5 shadow-sm border border-emerald-100 flex flex-col justify-center" style="background: linear-gradient(135deg, #ecfdf5, #f0fdf4)">
          <p class="text-3xl mb-2 text-center">🔮</p>
          <p class="text-sm text-emerald-700 font-medium text-center">{{ report.next_week_preview }}</p>
        </div>
      </div>

      <!-- 旧版兼容：话题+关键词+情绪分布（仅旧报告显示） -->
      <div v-if="report.top_topics?.length || report.top_keywords?.length" class="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
        <div v-if="report.top_topics?.length" class="rounded-2xl p-4 shadow-sm border border-slate-100 bg-white">
          <div class="text-xs text-slate-400 mb-2 font-medium">🔥 话题热度 TOP5</div>
          <div class="space-y-1.5">
            <div v-for="(t, i) in report.top_topics.slice(0, 5)" :key="i" class="flex items-center gap-2 text-xs">
              <span :class="['w-4 h-4 rounded text-[10px] font-bold flex items-center justify-center flex-shrink-0', i===0?'bg-red-500 text-white':i===1?'bg-orange-400 text-white':i===2?'bg-amber-400 text-white':'bg-slate-200 text-slate-500']">{{ i+1 }}</span>
              <span class="text-slate-600 truncate">{{ t.text }}</span>
            </div>
          </div>
        </div>
        <div v-if="report.top_keywords?.length" class="rounded-2xl p-4 shadow-sm border border-slate-100 bg-white">
          <div class="text-xs text-slate-400 mb-2 font-medium">🏷️ 关键词</div>
          <div class="flex flex-wrap gap-1">
            <span v-for="kw in report.top_keywords.slice(0, 6)" :key="kw.text" class="px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full text-[11px]">{{ kw.text }}</span>
          </div>
        </div>
        <div v-if="report.mood_ranking?.length" class="rounded-2xl p-4 shadow-sm border border-slate-100 bg-white">
          <div class="text-xs text-slate-400 mb-2 font-medium">🎭 情绪分布</div>
          <div class="space-y-1">
            <div v-for="m in report.mood_ranking" :key="m.mood" class="flex items-center justify-between text-xs">
              <span class="text-slate-500">{{ m.mood }}</span><span class="font-medium text-slate-600">{{ m.count }}天</span>
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
