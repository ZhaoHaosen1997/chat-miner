<script setup>
import { ref, inject, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getAnnualReport, generateAnnual, getPeriods } from '../api/index.js'
import { ArrowLeft, Sparkles, Loader2, Trophy, Star, Calendar, MessageSquare, Users, TrendingUp } from 'lucide-vue-next'
import WordCloud from '../components/WordCloud.vue'

const props = defineProps({ yearId: String })
const router = useRouter()
const currentGroup = inject('currentGroup')
const activeTaskId = inject('activeTaskId')
const triggerRefresh = inject('triggerRefresh')

const report = ref(null)
const loading = ref(true)
const generating = ref(false)
const error = ref('')

function formatTime(ts) {
  if (!ts) return ''
  const t = String(ts).replace(' ', 'T') + 'Z'
  const d = new Date(t)
  if (isNaN(d.getTime())) return ts
  return d.toLocaleString('zh', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function load() {
  if (!currentGroup.value || !props.yearId) return
  loading.value = true
  error.value = ''
  try {
    const data = await getAnnualReport(currentGroup.value.id, props.yearId)
    if (typeof data.report_json === 'string') {
      data.report_json = JSON.parse(data.report_json)
    }
    report.value = data
  } catch (e) {
    if (e.message?.includes('404') || e.message?.includes('尚未生成')) {
      error.value = 'not_generated'
    } else {
      error.value = e.message
    }
  } finally {
    loading.value = false
  }
}

async function startGenerate() {
  if (generating.value || activeTaskId.value) return
  generating.value = true
  try {
    const result = await generateAnnual(currentGroup.value.id, parseInt(props.yearId), true)
    if (result?.task_id) {
      activeTaskId.value = result.task_id
    } else {
      generating.value = false
      error.value = 'not_generated'
    }
  } catch (e) {
    error.value = e.message
    generating.value = false
  }
}

watch([currentGroup, () => props.yearId], load, { immediate: true })

watch(activeTaskId, (newVal, oldVal) => {
  if (oldVal && !newVal) {
    generating.value = false
    load()
    triggerRefresh?.()
  }
})

function goBack() { router.push('/') }

// 奖项卡片颜色池
const awardColors = [
  { bg: 'from-amber-500 to-yellow-600', glow: 'rgba(245,158,11,0.3)' },
  { bg: 'from-rose-500 to-pink-600', glow: 'rgba(244,63,94,0.3)' },
  { bg: 'from-violet-500 to-purple-600', glow: 'rgba(139,92,246,0.3)' },
  { bg: 'from-emerald-500 to-teal-600', glow: 'rgba(16,185,129,0.3)' },
  { bg: 'from-blue-500 to-indigo-600', glow: 'rgba(99,102,241,0.3)' },
  { bg: 'from-orange-500 to-red-500', glow: 'rgba(249,115,22,0.3)' },
  { bg: 'from-cyan-500 to-blue-600', glow: 'rgba(6,182,212,0.3)' },
  { bg: 'from-fuchsia-500 to-pink-600', glow: 'rgba(217,70,239,0.3)' },
  { bg: 'from-lime-500 to-green-600', glow: 'rgba(132,204,22,0.3)' },
  { bg: 'from-red-500 to-rose-600', glow: 'rgba(239,68,68,0.3)' },
  { bg: 'from-indigo-500 to-blue-600', glow: 'rgba(99,102,241,0.3)' },
  { bg: 'from-yellow-500 to-amber-600', glow: 'rgba(234,179,8,0.3)' },
]

function openPortrait(memberId) {
  if (memberId) router.push(`/portrait/${memberId}`)
}

// Build monthly timeline data from the report
function buildTimeline() {
  const rj = report.value?.report_json
  if (!rj?.monthly_trend) return []
  return rj.monthly_trend.map((t, i) => ({
    month: t.month,
    count: t.count,
    emoji: ['❄️','🎆','🌸','🌿','🌻','🏖️','🌊','🍂','🌾','🎃','🍁','🎄'][i % 12],
  }))
}

// Gather all words from monthly data for word cloud
const wordCloudWords = ref([])
watch(report, (r) => {
  if (!r?.report_json) return
  const rj = r.report_json
  const words = []
  // Extract words from annual awards
  if (rj.annual_awards) {
    rj.annual_awards.forEach(a => {
      if (a.award_name) words.push({ text: a.award_name, weight: 5 })
      if (a.award_reason) {
        a.award_reason.split(/[，,、\s]+/).forEach(w => {
          if (w.length >= 2) words.push({ text: w, weight: 2 })
        })
      }
    })
  }
  // Add top speakers
  if (rj.top_speakers) {
    rj.top_speakers.slice(0, 5).forEach(s => {
      if (s.alias) words.push({ text: s.alias, weight: 3 })
    })
  }
  // Add meme
  if (rj.meme_of_the_year) {
    words.push({ text: rj.meme_of_the_year, weight: 6 })
  }
  wordCloudWords.value = words.slice(0, 60)
})
</script>

<template>
  <div>
    <button @click="goBack" class="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 mb-5 transition-colors group">
      <ArrowLeft class="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
      返回仪表盘
    </button>

    <div v-if="loading" class="flex items-center justify-center py-32">
      <Loader2 class="w-8 h-8 animate-spin text-amber-400" />
    </div>

    <!-- 未生成 -->
    <div v-else-if="error === 'not_generated'" class="card p-16 text-center animate-scale-in">
      <div class="text-6xl mb-4">🏆</div>
      <h2 class="text-xl font-bold text-slate-700 mb-2">{{ props.yearId }} 年度颁奖典礼</h2>
      <p class="text-slate-400 mb-3">年度报告尚未生成，点击下方按钮让 AI 为你打造专属颁奖典礼</p>
      <p class="text-xs text-slate-300 mb-6">💡 建议先生成各月月报，年报数据会更丰富精彩</p>
      <button
        @click="startGenerate"
        :disabled="generating || !!activeTaskId"
        class="px-6 py-3 rounded-xl font-semibold text-white transition-all inline-flex items-center gap-2.5 disabled:opacity-50 shadow-lg hover:shadow-xl active:scale-[0.98]"
        style="background: linear-gradient(135deg, #F59E0B, #D97706)"
      >
        <Loader2 v-if="generating" class="w-5 h-5 animate-spin" />
        <Sparkles v-else class="w-5 h-5" />
        {{ generating ? 'AI 正在生成...' : '🏆 生成年度报告' }}
      </button>
    </div>

    <div v-else-if="error" class="card p-10 text-center animate-fade-in">
      <div class="text-4xl mb-3">😵</div>
      <p class="text-red-400 font-medium">加载失败</p>
      <p class="text-sm text-slate-400 mt-1">{{ error }}</p>
    </div>

    <template v-else-if="report">
      <div class="animate-scale-in space-y-8">
        <!-- ===== HERO: 年度主题 ===== -->
        <div class="rounded-2xl p-10 md:p-16 text-white text-center relative overflow-hidden"
          style="background: linear-gradient(135deg, #1A1006 0%, #3D2E0A 30%, #5C3D0A 60%, #1A1006 100%); box-shadow: 0 20px 60px -12px rgba(245,158,11,0.25);">
          <div class="absolute inset-0 opacity-10"
            style="background: radial-gradient(circle at 50% 30%, rgba(245,158,11,0.5) 0%, transparent 60%),
                         radial-gradient(circle at 20% 80%, rgba(217,119,6,0.3) 0%, transparent 50%);">
          </div>
          <div class="relative z-10">
            <p class="text-xs font-semibold tracking-[0.3em] uppercase text-amber-400/60 mb-4">🏆 {{ props.yearId }} Annual Awards Ceremony</p>
            <h1 class="text-3xl md:text-5xl font-black tracking-tight mb-4 bg-gradient-to-r from-amber-300 via-yellow-200 to-amber-400 bg-clip-text text-transparent">
              {{ report.report_json?.year_theme || props.yearId + '年度颁奖典礼' }}
            </h1>
            <div class="flex items-center justify-center gap-4 text-sm text-amber-200/50 mt-6">
              <span>{{ report.report_json?.date_start }} ~ {{ report.report_json?.date_end }}</span>
            </div>
            <div class="flex items-center justify-center gap-5 mt-4 pt-4 border-t border-amber-500/10 text-xs text-amber-300/50">
              <span>📅 {{ report.report_json?.day_count || report.day_count }}天</span>
              <span>💬 {{ (report.report_json?.total_messages || report.total_messages)?.toLocaleString() }}条</span>
              <span>👥 {{ report.report_json?.active_members || report.active_members }}人</span>
            </div>
          </div>
        </div>

        <!-- ===== 年度叙事 ===== -->
        <div v-if="report.report_json?.year_narrative" class="card p-6 md:p-8 border-l-4" style="border-left-color: #F59E0B;">
          <div class="flex items-start gap-4">
            <span class="text-4xl text-amber-300 leading-none select-none flex-shrink-0">"</span>
            <div>
              <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2 text-sm">
                <Star class="w-4 h-4 text-amber-400" /> 年度叙事
              </h3>
              <p class="text-sm text-slate-600 leading-relaxed whitespace-pre-line">{{ report.report_json.year_narrative }}</p>
            </div>
          </div>
        </div>

        <!-- ===== 年度热梗 + 演变 ===== -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div v-if="report.report_json?.meme_of_the_year" class="rounded-2xl p-5 text-white"
            style="background: linear-gradient(135deg, #1E1B4B, #312E81)">
            <h3 class="font-semibold mb-3 flex items-center gap-2 text-sm text-amber-300">🔥 年度热梗</h3>
            <p class="text-xl font-bold text-amber-100">"{{ report.report_json.meme_of_the_year }}"</p>
          </div>
          <div v-if="report.report_json?.group_evolution" class="rounded-2xl p-5 card">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2 text-sm">
              <TrendingUp class="w-4 h-4 text-emerald-400" /> 群聊变迁
            </h3>
            <p class="text-sm text-slate-600 leading-relaxed">{{ report.report_json.group_evolution }}</p>
          </div>
        </div>

        <!-- ===== 年度时光轴 ===== -->
        <div v-if="buildTimeline().length > 0" class="card p-5 overflow-hidden">
          <h3 class="font-semibold text-slate-700 mb-4 flex items-center gap-2 text-sm">
            <Calendar class="w-4 h-4 text-indigo-400" /> 年度时光轴
          </h3>
          <div class="flex gap-0 overflow-x-auto pb-2 timeline-scroll" style="scrollbar-width: thin;">
            <div v-for="(t, i) in buildTimeline()" :key="t.month" class="flex items-center flex-shrink-0">
              <div class="flex flex-col items-center w-20">
                <span class="text-2xl mb-1">{{ t.emoji }}</span>
                <span class="text-[10px] font-semibold text-slate-500">{{ t.month }}</span>
                <span class="text-[9px] text-slate-300">{{ t.count?.toLocaleString() }}条</span>
              </div>
              <div v-if="i < buildTimeline().length - 1"
                class="w-8 md:w-12 h-0.5 bg-gradient-to-r from-indigo-200 to-slate-200 flex-shrink-0 mx-1">
              </div>
            </div>
          </div>
        </div>

        <!-- ===== 颁奖典礼 奖项区 ===== -->
        <div v-if="report.report_json?.annual_awards?.length">
          <div class="flex items-center gap-3 mb-4">
            <span class="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-400 to-yellow-600 flex items-center justify-center">
              <Trophy class="w-4 h-4 text-white" />
            </span>
            <h2 class="text-lg font-bold text-slate-800">年度颁奖典礼</h2>
            <span class="text-xs text-slate-300">{{ report.report_json.annual_awards.length }}项大奖</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div
              v-for="(award, i) in report.report_json.annual_awards" :key="i"
              @click="openPortrait(award.member_id)"
              class="rounded-2xl p-5 cursor-pointer transition-all hover:-translate-y-1 hover:shadow-xl group relative overflow-hidden"
              :class="award.member_id ? '' : 'cursor-default'"
              style="background: linear-gradient(135deg, #1A1D23 0%, #252830 100%); border: 1px solid #333;"
            >
              <div class="absolute top-0 right-0 w-24 h-24 rounded-full -mr-8 -mt-8 opacity-10"
                :style="{ background: `radial-gradient(circle, ${awardColors[i%12].glow} 0%, transparent 70%)` }">
              </div>
              <div class="relative z-10">
                <div class="text-3xl mb-2">{{ award.award_emoji || '🏆' }}</div>
                <div class="text-sm font-bold text-white mb-1.5">{{ award.award_name }}</div>
                <div v-if="award.award_reason" class="text-xs text-slate-400 leading-relaxed mb-2">{{ award.award_reason }}</div>
                <div class="flex items-center gap-1.5 mt-3 pt-3 border-t border-white/5">
                  <span class="w-5 h-5 rounded-full bg-gradient-to-br flex items-center justify-center text-[8px] text-white"
                    :class="awardColors[i%12].bg">
                    {{ (award.winner_name || award.display_name || '?').charAt(0) }}
                  </span>
                  <span class="text-xs text-slate-300 font-medium">{{ award.winner_name || award.display_name || '群友' }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ===== 年度词云 ===== -->
        <div v-if="wordCloudWords.length > 5" class="card p-5">
          <h3 class="font-semibold text-slate-700 mb-4 flex items-center gap-2 text-sm">
            <Sparkles class="w-4 h-4 text-amber-400" /> 年度关键词云
          </h3>
          <WordCloud :words="wordCloudWords" />
        </div>

        <!-- ===== 新年寄语 ===== -->
        <div v-if="report.report_json?.next_year_wish" class="rounded-2xl p-8 text-center"
          style="background: linear-gradient(135deg, #FFFBEB 0%, #FEF3C7 50%, #FFFBEB 100%); border: 2px dashed #FCD34D;">
          <p class="text-3xl mb-3">🎇</p>
          <p class="text-sm font-medium text-amber-700 italic leading-relaxed">"{{ report.report_json.next_year_wish }}"</p>
        </div>
      </div>

      <!-- 底部统计 -->
      <div class="mt-8 pt-6 border-t border-slate-100 flex items-center justify-between text-xs text-slate-400">
        <span>{{ report.report_json?.date_start }} ~ {{ report.report_json?.date_end }}</span>
        <span>{{ report.report_json?._version || 'v0.11.0' }} · {{ report.model_used }} · {{ formatTime(report.created_at) }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.timeline-scroll::-webkit-scrollbar { height: 3px; }
.timeline-scroll::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 2px; }
</style>
