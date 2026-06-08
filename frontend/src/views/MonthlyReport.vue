<script setup>
import { ref, inject, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getMonthlyReport, generateMonthly, getPeriods } from '../api/index.js'
import { ArrowLeft, ArrowRight, Sparkles, Loader2, Hash, TrendingUp, Calendar, MessageSquare, Users, Brain, GitBranch, Telescope, Activity, Film } from 'lucide-vue-next'

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

// 根据人格类型选择主题色
const personalityThemes = [
  { keys: ['辩论','技术','理性','逻辑'], bg: 'linear-gradient(135deg, rgba(30,64,175,0.5), rgba(37,99,235,0.3))', accent: '#60a5fa', label: 'text-blue-200', tag: 'bg-blue-500/20 text-blue-200' },
  { keys: ['吃瓜','社交','八卦','娱乐'], bg: 'linear-gradient(135deg, rgba(217,119,6,0.5), rgba(245,158,11,0.3))', accent: '#fbbf24', label: 'text-amber-200', tag: 'bg-amber-500/20 text-amber-200' },
  { keys: ['摸鱼','摆烂','佛系','养生'], bg: 'linear-gradient(135deg, rgba(8,145,178,0.5), rgba(6,182,212,0.3))', accent: '#22d3ee', label: 'text-cyan-200', tag: 'bg-cyan-500/20 text-cyan-200' },
  { keys: ['沙雕','搞笑','欢乐','段子'], bg: 'linear-gradient(135deg, rgba(217,70,239,0.5), rgba(168,85,247,0.3))', accent: '#c084fc', label: 'text-purple-200', tag: 'bg-purple-500/20 text-purple-200' },
  { keys: ['内卷','奋斗','努力'], bg: 'linear-gradient(135deg, rgba(220,38,38,0.5), rgba(239,68,68,0.3))', accent: '#f87171', label: 'text-red-200', tag: 'bg-red-500/20 text-red-200' },
  { keys: ['温馨','治愈','温暖'], bg: 'linear-gradient(135deg, rgba(249,115,22,0.5), rgba(251,146,60,0.3))', accent: '#fb923c', label: 'text-orange-200', tag: 'bg-orange-500/20 text-orange-200' },
  { keys: ['抽象','离谱','魔幻'], bg: 'linear-gradient(135deg, rgba(124,58,237,0.5), rgba(139,92,246,0.3))', accent: '#a78bfa', label: 'text-purple-200', tag: 'bg-purple-500/20 text-purple-200' },
]
const defaultPersonality = { bg: 'linear-gradient(135deg, rgba(124,58,237,0.4), rgba(99,102,241,0.3))', accent: '#a78bfa', label: 'text-purple-200', tag: 'bg-purple-500/20 text-purple-200' }

const personalityColors = computed(() => {
  const label = report.value?.group_personality?.type_label || ''
  for (const theme of personalityThemes) {
    if (theme.keys.some(k => label.includes(k))) return theme
  }
  return defaultPersonality
})
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

    <!-- 报告内容 v0.7.3: 电影风深色主题 -->
    <div v-else-if="report" class="rounded-2xl overflow-hidden" style="background: linear-gradient(180deg, #0f172a 0%, #1e293b 40%, #1a1a2e 100%)">
      <!-- 头部 -->
      <div class="text-center py-10 px-6">
        <div class="text-5xl mb-3">🎬</div>
        <h2 class="text-2xl font-bold text-white mb-1">{{ monthLabel }} · 群聊月报</h2>
        <p class="text-sm text-slate-400">{{ report.date_start }} ~ {{ report.date_end }}</p>
        <div class="flex items-center justify-center gap-5 mt-2 text-xs text-slate-500">
          <span>📅 {{ report.day_count }}天</span>
          <span>💬 {{ report.total_messages?.toLocaleString() }}条</span>
          <span>👥 {{ report.active_members_avg }}人</span>
        </div>
      </div>

      <div class="px-5 pb-10 space-y-6 max-w-3xl mx-auto">
        <!-- Hero: 群聊人格鉴定（类型自适应配色） -->
        <div v-if="report.group_personality?.type_label" class="text-center py-8 px-6 rounded-2xl" :style="{ background: personalityColors.bg }">
          <p class="text-xs font-medium uppercase tracking-widest mb-4" :class="personalityColors.label">🧬 群聊人格鉴定</p>
          <p class="text-3xl font-black text-white mb-3">{{ report.group_personality.type_label }}</p>
          <p class="text-sm text-slate-300 max-w-md mx-auto leading-relaxed mb-4">{{ report.group_personality.type_explanation }}</p>
          <div v-if="report.group_personality.core_traits?.length" class="flex justify-center gap-2">
            <span v-for="t in report.group_personality.core_traits" :key="t"
                  class="px-3 py-1.5 rounded-full text-xs font-medium" :class="personalityColors.tag">{{ t }}</span>
          </div>
        </div>

        <!-- 数据快照 横排 -->
        <div v-if="report.top_speakers?.length" class="flex flex-wrap justify-center gap-4 text-xs text-slate-400">
          <span v-if="report.top_speakers?.length">💬 TOP: <span class="text-slate-300">{{ report.top_speakers.slice(0,3).map(s=>s.alias).join('、') }}</span></span>
          <span v-if="report.night_owls?.length">🦉 {{ report.night_owls.map(n=>n.alias).join('、') }}</span>
          <span v-if="report.emoji_kings?.length">😂 {{ report.emoji_kings.map(e=>e.alias).join('、') }}</span>
        </div>

        <!-- 话题演变 + 健康度 -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div v-if="report.topic_evolution" class="rounded-2xl p-5 bg-white/5 border border-white/10">
            <h3 class="font-semibold text-white mb-3 flex items-center gap-2 text-sm"><GitBranch class="w-4 h-4 text-indigo-400" /> 话题演变图鉴</h3>
            <p class="text-sm text-slate-300 leading-relaxed whitespace-pre-line">{{ report.topic_evolution }}</p>
          </div>
          <div v-if="report.community_health" class="rounded-2xl p-5 bg-white/5 border border-white/10">
            <h3 class="font-semibold text-white mb-4 flex items-center gap-2 text-sm"><Activity class="w-4 h-4 text-emerald-400" /> 社群健康度</h3>
            <div class="grid grid-cols-2 gap-2">
              <div v-for="item in [
                {label:'活跃指数', score:report.community_health.active_score, emoji:'🔥', comment:report.community_health.active_comment},
                {label:'信息密度', score:report.community_health.density_score, emoji:'💡', comment:report.community_health.density_comment},
                {label:'和谐指数', score:report.community_health.harmony_score, emoji:'☮️', comment:report.community_health.harmony_comment},
                {label:'夜猫子', score:report.community_health.nightowl_score, emoji:'🦉', comment:report.community_health.nightowl_comment},
              ]" :key="item.label" class="p-2 rounded-xl bg-white/5 text-center">
                <div class="text-lg mb-0.5">{{ item.emoji.repeat(item.score || 0) }}</div>
                <div class="text-[11px] text-slate-400">{{ item.label }}</div>
                <div class="text-[10px] text-slate-500 mt-0.5">{{ item.comment }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 梗文化考古 -->
        <div v-if="report.meme_archaeology" class="rounded-2xl p-6 border border-amber-500/20" style="background: linear-gradient(135deg, rgba(217,119,6,0.1), rgba(245,158,11,0.08))">
          <h3 class="font-semibold text-amber-400 mb-3 flex items-center gap-2 text-sm"><Telescope class="w-4 h-4" /> 梗文化考古</h3>
          <p class="text-sm text-slate-300 leading-relaxed whitespace-pre-line">{{ report.meme_archaeology }}</p>
        </div>

        <!-- 电影预告片 -->
        <div v-if="report.next_month_trailer" class="rounded-2xl p-8 text-center border-2 border-dashed border-amber-500/30" style="background: linear-gradient(135deg, rgba(0,0,0,0.4), rgba(30,41,59,0.3))">
          <p class="text-xs text-amber-400/60 uppercase tracking-widest mb-4">🎬 下月预告</p>
          <p class="text-lg text-amber-200 font-medium italic leading-relaxed">"{{ report.next_month_trailer }}"</p>
        </div>

        <!-- 旧版兼容内容 -->
        <div v-if="report.overview" class="rounded-2xl p-5 bg-white/5 border border-white/10">
          <h3 class="font-semibold text-white mb-3 flex items-center gap-2 text-sm"><Sparkles class="w-4 h-4 text-indigo-400" /> 月度综述</h3>
          <p class="text-sm text-slate-300 leading-relaxed whitespace-pre-line">{{ report.overview }}</p>
        </div>
        <div v-if="report.atmosphere_diagnosis" class="rounded-2xl p-5 bg-white/5 border border-white/10">
          <h3 class="font-semibold text-white mb-3 flex items-center gap-2 text-sm"><TrendingUp class="w-4 h-4 text-purple-400" /> 社群氛围诊断</h3>
          <p class="text-sm text-slate-300 leading-relaxed">{{ report.atmosphere_diagnosis }}</p>
        </div>
        <div v-if="report.member_spotlight" class="rounded-2xl p-5 border border-amber-500/20" style="background: linear-gradient(135deg, rgba(217,119,6,0.1), rgba(245,158,11,0.05))">
          <h3 class="font-semibold text-amber-400 mb-2 flex items-center gap-2 text-sm"><Users class="w-4 h-4" /> 群友聚光灯</h3>
          <p class="text-sm text-slate-300 leading-relaxed whitespace-pre-line">{{ report.member_spotlight }}</p>
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
    </div>
  </div>
</template>
