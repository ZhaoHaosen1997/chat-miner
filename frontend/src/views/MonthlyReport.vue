<script setup>
import { ref, inject, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getMonthlyReport, generateMonthly, getPeriods } from '../api/index.js'
import { ArrowLeft, ArrowRight, Sparkles, Loader2, TrendingUp, Calendar, MessageSquare, Users, Brain, GitBranch, Telescope, Activity, Film, Hash } from 'lucide-vue-next'
import RelatedEvents from '../components/RelatedEvents.vue'
import FloatingNav from '../components/FloatingNav.vue'

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

function formatTime(ts) {
  if (!ts) return ''
  const t = String(ts).replace(' ', 'T') + 'Z'
  const d = new Date(t)
  if (isNaN(d.getTime())) return ts
  return d.toLocaleString('zh', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

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
    // 循环翻页: 到头后绕到另一端（仅1条时隐藏按钮）
    if (months.length > 1) {
      adjacentMonths.value.prev = idx < months.length - 1 ? months[idx + 1].period_key : months[0].period_key
      adjacentMonths.value.next = idx > 0 ? months[idx - 1].period_key : months[months.length - 1].period_key
    }
  } catch (e) { /* ignore */ }
}

async function startGenerate() {
  if (generating.value || activeTaskId.value) return
  generating.value = true
  error.value = ''
  try {
    const result = await generateMonthly(currentGroup.value.id, props.monthId, true)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    } else if (result === null) {
      error.value = '本月数据不足，无法生成'
      generating.value = false
    } else {
      generating.value = false  // v1.0.3: 防御性复位
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

// ===== 人格/情绪自适应主题 =====
const personalityThemes = [
  {
    keys: ['辩论','技术','理性','逻辑','ENTP','INTJ','INTP','ENTJ','ESTJ'],
    heroGradient: 'linear-gradient(135deg, #1E3A5F 0%, #2563EB 40%, #3B82F6 70%, #60A5FA 100%)',
    sectionDark: 'linear-gradient(135deg, #0F172A 0%, #1E3A5F 100%)',
    accent: '#60A5FA', accentSoft: '#EFF6FF', accentBorder: '#BFDBFE',
    tagBg: 'rgba(96,165,250,0.15)', tagText: '#BFDBFE',
    icon: '🧠',
  },
  {
    keys: ['吃瓜','社交','八卦','娱乐','ESFP','ESFJ','ENFP','ENFJ'],
    heroGradient: 'linear-gradient(135deg, #78350F 0%, #D97706 40%, #F59E0B 70%, #FBBF24 100%)',
    sectionDark: 'linear-gradient(135deg, #1A1206 0%, #3D2E0A 100%)',
    accent: '#FBBF24', accentSoft: '#FFFBEB', accentBorder: '#FDE68A',
    tagBg: 'rgba(251,191,36,0.15)', tagText: '#FDE68A',
    icon: '🍿',
  },
  {
    keys: ['摸鱼','摆烂','佛系','养生','ISFP','ISTP','INFP'],
    heroGradient: 'linear-gradient(135deg, #164E63 0%, #0891B2 40%, #06B6D4 70%, #22D3EE 100%)',
    sectionDark: 'linear-gradient(135deg, #061F2C 0%, #0E4A5C 100%)',
    accent: '#22D3EE', accentSoft: '#ECFEFF', accentBorder: '#A5F3FC',
    tagBg: 'rgba(34,211,238,0.15)', tagText: '#A5F3FC',
    icon: '🎣',
  },
  {
    keys: ['沙雕','搞笑','欢乐','段子','ESTP','ENTP'],
    heroGradient: 'linear-gradient(135deg, #4C1D95 0%, #D946EF 40%, #A855F7 70%, #C084FC 100%)',
    sectionDark: 'linear-gradient(135deg, #1A0A2E 0%, #4A1A6B 100%)',
    accent: '#C084FC', accentSoft: '#FAF5FF', accentBorder: '#E9D5FF',
    tagBg: 'rgba(192,132,252,0.15)', tagText: '#E9D5FF',
    icon: '🤪',
  },
  {
    keys: ['内卷','奋斗','努力','ISTJ','ESTJ'],
    heroGradient: 'linear-gradient(135deg, #7F1D1D 0%, #DC2626 40%, #EF4444 70%, #F87171 100%)',
    sectionDark: 'linear-gradient(135deg, #1A0606 0%, #5C1A1A 100%)',
    accent: '#F87171', accentSoft: '#FEF2F2', accentBorder: '#FECACA',
    tagBg: 'rgba(248,113,113,0.15)', tagText: '#FECACA',
    icon: '💪',
  },
  {
    keys: ['温馨','治愈','温暖','INFJ','ISFJ'],
    heroGradient: 'linear-gradient(135deg, #7C2D12 0%, #F97316 40%, #FB923C 70%, #FDBA74 100%)',
    sectionDark: 'linear-gradient(135deg, #1A0E06 0%, #5C2D0A 100%)',
    accent: '#FDBA74', accentSoft: '#FFF7ED', accentBorder: '#FED7AA',
    tagBg: 'rgba(253,186,116,0.15)', tagText: '#FED7AA',
    icon: '💛',
  },
  {
    keys: ['抽象','离谱','魔幻','INFP','INTP'],
    heroGradient: 'linear-gradient(135deg, #2E1065 0%, #7C3AED 40%, #8B5CF6 70%, #A78BFA 100%)',
    sectionDark: 'linear-gradient(135deg, #0F0A2E 0%, #2D1A5C 100%)',
    accent: '#A78BFA', accentSoft: '#F5F3FF', accentBorder: '#DDD6FE',
    tagBg: 'rgba(167,139,250,0.15)', tagText: '#DDD6FE',
    icon: '👽',
  },
]

const defaultTheme = {
  heroGradient: 'linear-gradient(135deg, #1E1B4B 0%, #6366F1 40%, #8B5CF6 70%, #A78BFA 100%)',
  sectionDark: 'linear-gradient(135deg, #0F172A 0%, #1E293B 100%)',
  accent: '#A78BFA', accentSoft: '#F5F3FF', accentBorder: '#DDD6FE',
  tagBg: 'rgba(167,139,250,0.15)', tagText: '#DDD6FE',
  icon: '🎬',
}

const theme = computed(() => {
  if (!report.value) return defaultTheme
  const label = report.value?.group_personality?.type_label || ''
  const dm = report.value?.dominant_mood || report.value?.mood_ranking?.[0]?.mood || ''
  for (const t of personalityThemes) {
    if (t.keys.some(k => label.includes(k) || dm.includes(k))) return t
  }
  return defaultTheme
})

// Health gauge items
const healthItems = [
  { key: 'active_score', label: '活跃指数', emoji: '🔥', comment: 'active_comment', color: '#F59E0B' },
  { key: 'density_score', label: '信息密度', emoji: '💡', comment: 'density_comment', color: '#6366F1' },
  { key: 'harmony_score', label: '和谐指数', emoji: '☮️', comment: 'harmony_comment', color: '#10B981' },
  { key: 'nightowl_score', label: '夜猫子', emoji: '🦉', comment: 'nightowl_comment', color: '#8B5CF6' },
]
</script>

<template>
  <div>
    <FloatingNav
      :show-prev="!!adjacentMonths.prev"
      :show-next="!!adjacentMonths.next"
      :prev-label="adjacentMonths.prev"
      :next-label="adjacentMonths.next"
      @prev="goMonth(adjacentMonths.prev)"
      @next="goMonth(adjacentMonths.next)"
    />
    <button @click="goBack" class="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 mb-5 transition-colors group">
      <ArrowLeft class="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
      返回仪表盘
    </button>

    <Transition name="page-slide" mode="out-in">
    <div :key="props.monthId" class="report-content">
    <div v-if="loading" class="flex items-center justify-center py-32">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <!-- 未生成 -->
    <div v-else-if="error === 'not_generated'" class="card p-16 text-center animate-scale-in">
      <div class="text-6xl mb-4">🎬</div>
      <h2 class="text-xl font-bold text-slate-700 mb-2">{{ monthLabel }}月报</h2>
      <p v-if="report" class="text-sm text-slate-400 mb-8">{{ report.date_start }} ~ {{ report.date_end }} · {{ report.day_count }}天</p>
      <button
        @click="startGenerate"
        :disabled="generating || !!activeTaskId"
        class="px-6 py-3 rounded-xl font-semibold text-white transition-all inline-flex items-center gap-2.5 disabled:opacity-50 shadow-lg hover:shadow-xl active:scale-[0.98]"
        style="background: linear-gradient(135deg, #6366F1, #8B5CF6)"
      >
        <Loader2 v-if="generating" class="w-5 h-5 animate-spin" />
        <Sparkles v-else class="w-5 h-5" />
        {{ generating ? 'AI 正在深度思考...' : '🎬 生成月报' }}
      </button>
    </div>

    <div v-else-if="error" class="card p-10 text-center animate-fade-in">
      <div class="text-4xl mb-3">😵</div>
      <p class="text-red-400 font-medium">加载失败</p>
      <p class="text-sm text-slate-400 mt-1">{{ error }}</p>
    </div>

    <!-- 报告内容 -->
    <template v-else-if="report">
      <!-- ===== SECTION 1: HERO — 群聊人格鉴定 ===== -->
      <div
        v-if="report.group_personality?.type_label"
        class="rounded-2xl p-10 md:p-14 mb-6 text-white text-center hero-gloss relative overflow-hidden animate-scale-in"
        :style="{ background: theme.heroGradient, boxShadow: `0 20px 60px -12px ${theme.accent}40` }"
      >
        <div class="absolute inset-0 opacity-10 pointer-events-none"
          style="background-image: radial-gradient(circle at 30% 40%, rgba(255,255,255,0.3) 0%, transparent 50%), radial-gradient(circle at 70% 60%, rgba(255,255,255,0.15) 0%, transparent 40%);">
        </div>
        <div class="relative z-10">
          <p class="text-xs font-semibold tracking-[0.2em] uppercase text-white/50 mb-5">🧬 群聊人格鉴定</p>
          <p class="text-3xl md:text-5xl font-black mb-4 tracking-tight">
            {{ report.group_personality.type_label }}
          </p>
          <p class="text-sm md:text-base text-white/70 max-w-lg mx-auto leading-relaxed mb-5">
            {{ report.group_personality.type_explanation }}
          </p>
          <div v-if="report.group_personality.core_traits?.length" class="flex justify-center gap-2 flex-wrap">
            <span v-for="t in report.group_personality.core_traits" :key="t"
              class="px-3.5 py-1.5 rounded-full text-xs font-medium backdrop-blur-sm"
              :style="{ background: theme.tagBg, color: theme.tagText }"
            >{{ t }}</span>
          </div>
        </div>
      </div>

      <!-- 月份统计条 -->
      <div class="flex items-center justify-center gap-6 mb-6 text-xs text-slate-400">
        <span>📅 {{ report.day_count }}天</span>
        <span>💬 {{ report.total_messages?.toLocaleString() }}条</span>
        <span>👥 {{ report.active_members_avg }}人</span>
      </div>

      <!-- ===== SECTION 2: 话题演变 + 健康度 (亮色区) ===== -->
      <div class="stagger space-y-5">
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <!-- 话题演变图鉴 -->
          <div v-if="report.topic_evolution" class="rounded-2xl p-6 card">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2 text-sm">
              <GitBranch class="w-4 h-4" :style="{ color: theme.accent }" /> 话题演变图鉴
            </h3>
            <p class="text-sm text-slate-600 leading-relaxed whitespace-pre-line">{{ report.topic_evolution }}</p>
          </div>

          <!-- 社群健康度 -->
          <div v-if="report.community_health" class="rounded-2xl p-6 card">
            <h3 class="font-semibold text-slate-700 mb-5 flex items-center gap-2 text-sm">
              <Activity class="w-4 h-4" :style="{ color: theme.accent }" /> 社群健康度
            </h3>
            <div class="space-y-4">
              <div v-for="item in healthItems" :key="item.key" class="space-y-1">
                <div class="flex items-center justify-between text-xs">
                  <span class="flex items-center gap-1.5 text-slate-600">
                    <span>{{ item.emoji }}</span> {{ item.label }}
                  </span>
                  <span class="font-semibold text-slate-400">{{ report.community_health[item.key] }}/5</span>
                </div>
                <!-- 健康度计量条 -->
                <div class="health-gauge">
                  <span v-for="pip in 5" :key="pip"
                    class="gauge-pip"
                    :class="{ filled: pip <= (report.community_health[item.key] || 0) }"
                    :style="pip <= (report.community_health[item.key] || 0) ? { background: item.color } : {}"
                  ></span>
                </div>
                <p v-if="report.community_health[item.comment]" class="text-[10px] text-slate-400 mt-0.5">
                  {{ report.community_health[item.comment] }}
                </p>
              </div>
            </div>
          </div>
        </div>

        <!-- ===== SECTION 3: 梗文化考古 (深色沉浸区) ===== -->
        <div v-if="report.meme_archaeology" class="rounded-2xl p-7 md:p-9 text-white relative overflow-hidden" :style="{ background: theme.sectionDark }">
          <div class="absolute top-0 right-0 w-48 h-48 rounded-full opacity-5 pointer-events-none"
            style="background: radial-gradient(circle, currentColor 0%, transparent 70%);">
          </div>
          <div class="relative z-10">
            <h3 class="font-semibold mb-4 flex items-center gap-2 text-sm" :style="{ color: theme.accent }">
              <Telescope class="w-4 h-4" /> 梗文化考古
            </h3>
            <p class="text-sm text-slate-300 leading-relaxed whitespace-pre-line">{{ report.meme_archaeology }}</p>
          </div>
        </div>

        <!-- ===== SECTION 4: 成员快照条 ===== -->
        <div v-if="report.top_speakers?.length" class="flex flex-wrap items-center justify-center gap-3 text-xs text-slate-400 py-2">
          <span v-if="report.top_speakers?.length" class="flex items-center gap-1">
            💬 TOP3: <span class="text-slate-600 font-medium">{{ report.top_speakers.slice(0,3).map(s=>s.alias).join('、') }}</span>
          </span>
          <span class="text-slate-200">|</span>
          <span v-if="report.night_owls?.length" class="flex items-center gap-1">
            🦉 <span class="text-slate-600 font-medium">{{ report.night_owls.map(n=>n.alias).join('、') }}</span>
          </span>
          <span class="text-slate-200">|</span>
          <span v-if="report.emoji_kings?.length" class="flex items-center gap-1">
            😂 <span class="text-slate-600 font-medium">{{ report.emoji_kings.map(e=>e.alias).join('、') }}</span>
          </span>
        </div>

        <!-- ===== SECTION 5: 旧版兼容 / 氛围诊断 + 群友聚光灯 ===== -->
        <div v-if="report.atmosphere_diagnosis || report.member_spotlight || report.overview"
          class="grid grid-cols-1 md:grid-cols-2 gap-5"
        >
          <div v-if="report.overview" class="rounded-2xl p-5 card">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2 text-sm">
              <Sparkles class="w-4 h-4" :style="{ color: theme.accent }" /> 月度综述
            </h3>
            <p class="text-sm text-slate-600 leading-relaxed whitespace-pre-line">{{ report.overview }}</p>
          </div>
          <div v-if="report.atmosphere_diagnosis" class="rounded-2xl p-5 card">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2 text-sm">
              <TrendingUp class="w-4 h-4" :style="{ color: theme.accent }" /> 氛围诊断
            </h3>
            <p class="text-sm text-slate-600 leading-relaxed">{{ report.atmosphere_diagnosis }}</p>
          </div>
          <div v-if="report.member_spotlight" class="rounded-2xl p-5 card md:col-span-2"
            :style="{ borderColor: theme.accentBorder, background: theme.accentSoft }"
          >
            <h3 class="font-semibold text-slate-700 mb-2 flex items-center gap-2 text-sm">
              <Users class="w-4 h-4" :style="{ color: theme.accent }" /> 群友聚光灯
            </h3>
            <p class="text-sm text-slate-600 leading-relaxed whitespace-pre-line">{{ report.member_spotlight }}</p>
          </div>
        </div>

        <!-- ===== SECTION 6: 电影预告片 (收官高潮) ===== -->
        <div v-if="report.next_month_trailer" class="rounded-2xl p-8 md:p-12 text-center relative overflow-hidden film-strip"
          :style="{ background: theme.sectionDark }"
        >
          <!-- Film perforations handled by CSS -->
          <div class="py-4 relative z-10">
            <p class="text-xs font-semibold tracking-[0.3em] uppercase mb-6" :style="{ color: theme.accent }">🎬 下月预告</p>
            <p class="text-xl md:text-2xl font-bold italic leading-relaxed max-w-lg mx-auto text-white">
              "{{ report.next_month_trailer }}"
            </p>
            <div class="mt-8 flex items-center justify-center gap-2 text-xs" :style="{ color: theme.accent }">
              <span class="w-8 h-px" :style="{ background: theme.accent, opacity: 0.4 }"></span>
              COMING SOON
              <span class="w-8 h-px" :style="{ background: theme.accent, opacity: 0.4 }"></span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="report.model_used" class="flex items-center justify-center mt-6">
        <p class="text-slate-300 text-[11px]">{{ report.model_used }} · {{ formatTime(report.created_at) }}</p>
      </div>

      <!-- ===== 底部导航 ===== -->
      <div class="flex items-center justify-between mt-10 pt-6 border-t" style="border-color: var(--color-hairline)">
        <button
          v-if="adjacentMonths.prev"
          @click="goMonth(adjacentMonths.prev)"
          class="flex items-center gap-1.5 text-sm font-medium text-slate-400 hover:text-slate-700 transition-colors group"
        >
          <ArrowLeft class="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
          {{ adjacentMonths.prev }}
        </button>
        <span v-else class="text-sm text-slate-300">已是第一个月</span>

        <span class="text-xs text-slate-300 font-mono">{{ props.monthId }}</span>

        <button
          v-if="adjacentMonths.next"
          @click="goMonth(adjacentMonths.next)"
          class="flex items-center gap-1.5 text-sm font-medium text-slate-400 hover:text-slate-700 transition-colors group"
        >
          {{ adjacentMonths.next }}
          <ArrowRight class="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
        </button>
        <span v-else class="text-sm text-slate-300">已是最新月</span>
      </div>
    </template>
    </div>
    </Transition>
    <RelatedEvents
      v-if="report?.date_start && report?.date_end"
      :group-id="currentGroup?.id"
      :date-from="report.date_start"
      :date-to="report.date_end"
      label="📅 本月事件回顾"
    />
  </div>
</template>
