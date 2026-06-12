<script setup>
import { ref, inject, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { getWeeklyReport, generateWeekly, getPeriods } from '../api/index.js'
import { ArrowLeft, ArrowRight, Sparkles, Loader2, TrendingUp, Calendar, MessageSquare, Users, Flame, Trophy, BookOpen, Hash, Zap } from 'lucide-vue-next'

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

function formatTime(ts) {
  if (!ts) return ''
  const t = String(ts).replace(' ', 'T') + 'Z'
  const d = new Date(t)
  if (isNaN(d.getTime())) return ts
  return d.toLocaleString('zh', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

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
      const parts = props.weekId.split('-W')
      if (parts.length === 2) {
        const y = parseInt(parts[0]), w = parseInt(parts[1])
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
  error.value = ''
  try {
    const result = await generateWeekly(currentGroup.value.id, props.weekId)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    } else if (result === null) {
      error.value = '本周数据不足，无法生成'
      generating.value = false
    } else {
      generating.value = false  // v1.0.3: 防御性复位
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

// ---- 情绪自适应配色系统 ----
const moodPalettes = {
  '欢乐': {
    hero: 'linear-gradient(135deg, #DC2626 0%, #EA580C 30%, #F59E0B 70%, #FBBF24 100%)',
    accent: '#F59E0B', accentSoft: '#FFFBEB', accentBorder: '#FDE68A',
    dark: 'linear-gradient(135deg, #1F1A16 0%, #2D2420 100%)',
    badge: 'bg-amber-100 text-amber-700',
    icon: '🎉',
  },
  '热闹': {
    hero: 'linear-gradient(135deg, #E11D48 0%, #F43F5E 40%, #FB7185 80%, #FDA4AF 100%)',
    accent: '#F43F5E', accentSoft: '#FFF1F2', accentBorder: '#FECDD3',
    dark: 'linear-gradient(135deg, #1F1618 0%, #2D1F22 100%)',
    badge: 'bg-rose-100 text-rose-700',
    icon: '🎊',
  },
  '沙雕': {
    hero: 'linear-gradient(135deg, #D946EF 0%, #A855F7 35%, #6366F1 70%, #8B5CF6 100%)',
    accent: '#A855F7', accentSoft: '#FAF5FF', accentBorder: '#E9D5FF',
    dark: 'linear-gradient(135deg, #1A1520 0%, #251F2D 100%)',
    badge: 'bg-purple-100 text-purple-700',
    icon: '🤪',
  },
  '温馨': {
    hero: 'linear-gradient(135deg, #F97316 0%, #FB923C 35%, #FBBF24 70%, #FDE68A 100%)',
    accent: '#FB923C', accentSoft: '#FFF7ED', accentBorder: '#FED7AA',
    dark: 'linear-gradient(135deg, #1F1814 0%, #2D211A 100%)',
    badge: 'bg-orange-100 text-orange-700',
    icon: '💛',
  },
  '吐槽': {
    hero: 'linear-gradient(135deg, #475569 0%, #334155 40%, #1E293B 80%, #0F172A 100%)',
    accent: '#64748B', accentSoft: '#F8FAFC', accentBorder: '#E2E8F0',
    dark: 'linear-gradient(135deg, #0F172A 0%, #1E293B 100%)',
    badge: 'bg-slate-100 text-slate-700',
    icon: '🎭',
  },
  '吃瓜': {
    hero: 'linear-gradient(135deg, #CA8A04 0%, #EAB308 35%, #FACC15 70%, #FEF08A 100%)',
    accent: '#EAB308', accentSoft: '#FEFCE8', accentBorder: '#FEF08A',
    dark: 'linear-gradient(135deg, #1F1C0A 0%, #2D2812 100%)',
    badge: 'bg-yellow-100 text-yellow-700',
    icon: '🍉',
  },
  '摸鱼': {
    hero: 'linear-gradient(135deg, #0891B2 0%, #06B6D4 40%, #22D3EE 80%, #67E8F9 100%)',
    accent: '#06B6D4', accentSoft: '#ECFEFF', accentBorder: '#A5F3FC',
    dark: 'linear-gradient(135deg, #0A1A20 0%, #12232D 100%)',
    badge: 'bg-cyan-100 text-cyan-700',
    icon: '🎣',
  },
  '伤感': {
    hero: 'linear-gradient(135deg, #6366F1 0%, #818CF8 35%, #A5B4FC 70%, #C7D2FE 100%)',
    accent: '#818CF8', accentSoft: '#EEF2FF', accentBorder: '#C7D2FE',
    dark: 'linear-gradient(135deg, #151830 0%, #1E2140 100%)',
    badge: 'bg-indigo-100 text-indigo-700',
    icon: '💙',
  },
  '破防': {
    hero: 'linear-gradient(135deg, #BE123C 0%, #E11D48 35%, #FB7185 70%, #FDA4AF 100%)',
    accent: '#E11D48', accentSoft: '#FFF1F2', accentBorder: '#FECDD3',
    dark: 'linear-gradient(135deg, #1F1014 0%, #2D1A20 100%)',
    badge: 'bg-rose-100 text-rose-700',
    icon: '💔',
  },
  '离谱': {
    hero: 'linear-gradient(135deg, #7C3AED 0%, #8B5CF6 35%, #A78BFA 70%, #C4B5FD 100%)',
    accent: '#7C3AED', accentSoft: '#F5F3FF', accentBorder: '#DDD6FE',
    dark: 'linear-gradient(135deg, #1A1430 0%, #241E40 100%)',
    badge: 'bg-violet-100 text-violet-700',
    icon: '👽',
  },
  '平淡': {
    hero: 'linear-gradient(135deg, #334155 0%, #475569 40%, #64748B 80%, #94A3B8 100%)',
    accent: '#64748B', accentSoft: '#F8FAFC', accentBorder: '#E2E8F0',
    dark: 'linear-gradient(135deg, #1A1D23 0%, #252830 100%)',
    badge: 'bg-slate-100 text-slate-600',
    icon: '😐',
  },
}

const defaultMood = {
  hero: 'linear-gradient(135deg, #6366F1 0%, #8B5CF6 50%, #A78BFA 100%)',
  accent: '#6366F1', accentSoft: '#EEF2FF', accentBorder: '#C7D2FE',
  dark: 'linear-gradient(135deg, #1A1D23 0%, #252830 100%)',
  badge: 'bg-indigo-100 text-indigo-700',
  icon: '📰',
}

const palette = computed(() => {
  const dm = report.value?.dominant_mood
  if (dm && moodPalettes[dm]) return moodPalettes[dm]
  const top = report.value?.mood_ranking?.[0]
  if (top?.mood && moodPalettes[top.mood]) return moodPalettes[top.mood]
  return defaultMood
})

// 情绪emoji映射
const moodIcons = { '欢乐':'😄','温馨':'🥰','严肃':'🧐','吐槽':'😤','平淡':'😐','热闹':'🎉','伤感':'😢','沙雕':'🤪','吃瓜':'🍉','摸鱼':'🎣','摆烂':'🫠','内卷':'💪','开车':'🚗','破防':'💔','凡尔赛':'👑','社死':'💀','真香':'🍚','画饼':'🫓','CPU':'🔥','离谱':'👽','上头':'🤯' }
</script>

<template>
  <div>
    <!-- 返回导航 -->
    <button @click="goBack" class="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 mb-5 transition-colors group">
      <ArrowLeft class="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
      返回仪表盘
    </button>

    <!-- 加载 -->
    <div v-if="loading" class="flex items-center justify-center py-32">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <!-- 未生成 -->
    <div v-else-if="error === 'not_generated'" class="card p-16 text-center animate-scale-in">
      <div class="text-6xl mb-4">📰</div>
      <h2 class="text-xl font-bold text-slate-700 mb-2">{{ props.weekId }} 周报</h2>
      <p class="text-slate-400 mb-2">{{ weekRange }}</p>
      <p class="text-sm text-slate-400 mb-8">本周报尚未生成，点击下方按钮让 AI 为你撰写</p>
      <button
        @click="startGenerate"
        :disabled="generating || !!activeTaskId"
        class="px-6 py-3 rounded-xl font-semibold text-white transition-all inline-flex items-center gap-2.5 disabled:opacity-50 shadow-lg hover:shadow-xl active:scale-[0.98]"
        style="background: linear-gradient(135deg, #6366F1, #8B5CF6)"
      >
        <Loader2 v-if="generating" class="w-5 h-5 animate-spin" />
        <Sparkles v-else class="w-5 h-5" />
        {{ generating ? 'AI 正在撰写...' : '✨ 生成周报' }}
      </button>
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="card p-10 text-center animate-fade-in">
      <div class="text-4xl mb-3">😵</div>
      <p class="text-red-400 font-medium">加载失败</p>
      <p class="text-sm text-slate-400 mt-1">{{ error }}</p>
    </div>

    <!-- 报告内容 -->
    <template v-else-if="report">
      <!-- ===== HERO: 情绪自适应封面 ===== -->
      <div
        class="rounded-2xl p-10 md:p-14 mb-8 text-white text-center hero-gloss animate-scale-in relative overflow-hidden"
        :style="{ background: palette.hero, boxShadow: `0 20px 60px -12px ${palette.accent}40` }"
      >
        <!-- 装饰背景 -->
        <div class="absolute inset-0 opacity-10 pointer-events-none"
          style="background-image: radial-gradient(circle at 20% 30%, rgba(255,255,255,0.4) 0%, transparent 50%), radial-gradient(circle at 80% 70%, rgba(255,255,255,0.2) 0%, transparent 40%);">
        </div>

        <div class="relative z-10">
          <p class="text-xs font-semibold tracking-[0.2em] uppercase text-white/50 mb-4">📰 群聊周报</p>
          <p class="text-2xl md:text-4xl lg:text-5xl font-black leading-tight tracking-tight mb-6">
            {{ report.week_headline || report.overview || '本周群聊回顾' }}
          </p>
          <div class="flex items-center justify-center gap-3 text-sm text-white/60">
            <span class="px-3 py-1 rounded-full bg-white/10 backdrop-blur-sm text-xs font-medium">
              {{ report.date_start }} 周一 ~ {{ report.date_end }} 周日
            </span>
          </div>
        </div>

        <!-- 底部统计条 -->
        <div class="relative z-10 flex items-center justify-center gap-6 mt-8 pt-6 border-t border-white/10">
          <div class="flex items-center gap-1.5 text-white/70 text-xs">
            <Calendar class="w-3.5 h-3.5" />
            <span class="font-semibold text-white">{{ report.day_count }}</span> 天
          </div>
          <div class="w-px h-4 bg-white/10" />
          <div class="flex items-center gap-1.5 text-white/70 text-xs">
            <MessageSquare class="w-3.5 h-3.5" />
            <span class="font-semibold text-white">{{ report.total_messages?.toLocaleString() }}</span> 条
          </div>
          <div class="w-px h-4 bg-white/10" />
          <div class="flex items-center gap-1.5 text-white/70 text-xs">
            <Users class="w-3.5 h-3.5" />
            <span class="font-semibold text-white">{{ report.active_members_avg }}</span> 人活跃
          </div>
        </div>
        <div v-if="report.model_used" class="relative z-10 flex items-center justify-center mt-3">
          <p class="text-white/40 text-[11px]">{{ report.model_used }} · {{ formatTime(report.created_at) }}</p>
        </div>
      </div>

      <div class="stagger space-y-5">
        <!-- ===== Row 1: AI 锐评 (深色卡片) + 数据快照 ===== -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <!-- AI 锐评 -->
          <div v-if="report.ai_roast" class="rounded-2xl p-6 text-white relative overflow-hidden" :style="{ background: palette.dark }">
            <div class="absolute top-0 right-0 w-32 h-32 opacity-5 pointer-events-none"
              style="background: radial-gradient(circle, currentColor 0%, transparent 70%);">
            </div>
            <div class="relative z-10">
              <h3 class="font-semibold mb-4 flex items-center gap-2 text-sm" :style="{ color: palette.accent }">
                <Flame class="w-4 h-4" /> AI 锐评
              </h3>
              <p class="text-sm leading-relaxed text-slate-200 whitespace-pre-line">{{ report.ai_roast }}</p>
            </div>
          </div>

          <!-- 数据快照 -->
          <div class="space-y-3">
            <!-- 发言排行 -->
            <div v-if="report.top_speakers?.length" class="rounded-2xl p-4 card">
              <div class="text-xs text-slate-400 mb-3 font-semibold tracking-wide">💬 发言排行 TOP 5</div>
              <div class="space-y-2">
                <div v-for="(s, i) in report.top_speakers.slice(0, 5)" :key="i"
                  class="flex items-center gap-2.5 text-sm"
                >
                  <span class="w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0"
                    :class="i === 0 ? 'bg-amber-400 text-white' : i === 1 ? 'bg-slate-300 text-white' : i === 2 ? 'bg-orange-300 text-white' : 'bg-slate-100 text-slate-400'"
                  >{{ i + 1 }}</span>
                  <span class="flex-1 text-slate-700 truncate text-xs">{{ s.alias }}</span>
                  <span class="font-semibold text-slate-500 text-xs stat-ticker">{{ s.count }}条</span>
                </div>
              </div>
            </div>
            <!-- 迷你统计 -->
            <div class="grid grid-cols-3 gap-2">
              <div v-if="report.night_owls?.length" class="rounded-xl p-3 card text-center">
                <div class="text-lg mb-0.5">🦉</div>
                <div class="text-[10px] text-slate-400 mb-0.5">深夜守群</div>
                <div class="text-[11px] font-medium text-slate-600 truncate">{{ report.night_owls[0]?.alias }}</div>
              </div>
              <div v-if="report.emoji_kings?.length" class="rounded-xl p-3 card text-center">
                <div class="text-lg mb-0.5">😂</div>
                <div class="text-[10px] text-slate-400 mb-0.5">表情达人</div>
                <div class="text-[11px] font-medium text-slate-600 truncate">{{ report.emoji_kings[0]?.alias }}</div>
              </div>
              <div v-if="report.lurkers?.length" class="rounded-xl p-3 card text-center">
                <div class="text-lg mb-0.5">🤿</div>
                <div class="text-[10px] text-slate-400 mb-0.5">潜水观察</div>
                <div class="text-[11px] font-medium text-slate-600 truncate">{{ report.lurkers[0]?.alias }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- ===== 奖项区 ===== -->
        <div v-if="report.weekly_awards?.length">
          <div class="section-ornament mb-4">
            <span class="ornament-dot" :style="{ background: palette.accent }"></span>
          </div>
          <h3 class="font-semibold text-slate-700 mb-4 flex items-center gap-2 text-sm">
            <Trophy class="w-4 h-4" :style="{ color: palette.accent }" /> 本周群聊奖项
          </h3>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div v-for="(award, i) in report.weekly_awards" :key="i"
              class="award-card rounded-2xl p-5 text-center border cursor-default"
              :style="{ borderColor: i === 0 ? palette.accentBorder : 'var(--color-hairline)', background: i === 0 ? palette.accentSoft : 'var(--color-surface)' }"
            >
              <div class="text-4xl mb-3">{{ award.emoji || '🏆' }}</div>
              <div class="text-sm font-bold text-slate-800 mb-1.5">{{ award.award_name }}</div>
              <p class="text-xs text-slate-500 leading-relaxed">
                <span class="font-semibold" :style="{ color: palette.accent }">{{ award.winner }}</span>
                <span class="mx-1">·</span>{{ award.reason }}
              </p>
            </div>
          </div>
        </div>

        <!-- ===== 群聊故事 (全宽叙事区) ===== -->
        <div v-if="report.week_narrative" class="rounded-2xl p-6 md:p-8 border relative overflow-hidden"
          style="background: linear-gradient(135deg, #FAFBFC 0%, #F8FAFC 100%); border-color: #E2E8F0;">
          <div class="flex items-start gap-4 md:gap-6">
            <span class="quote-mark flex-shrink-0 leading-none mt-1">"</span>
            <div class="flex-1">
              <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2 text-sm">
                <BookOpen class="w-4 h-4" :style="{ color: palette.accent }" /> 本周群聊故事
              </h3>
              <p class="text-sm text-slate-600 leading-relaxed whitespace-pre-line">{{ report.week_narrative }}</p>
            </div>
          </div>
        </div>

        <!-- ===== 情绪过山车 + 下周预告 双栏 ===== -->
        <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
          <!-- 情绪过山车 -->
          <div v-if="report.mood_rollercoaster" class="rounded-2xl p-5 card">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2 text-sm">
              <TrendingUp class="w-4 h-4" :style="{ color: palette.accent }" /> 情绪过山车
            </h3>
            <!-- Emoji 时间线 -->
            <div v-if="report.mood_timeline?.length" class="flex flex-wrap gap-1.5 mb-4 p-3 rounded-xl bg-slate-50">
              <span v-for="e in report.mood_timeline" :key="e.date"
                :title="`${e.date} ${e.mood}`"
                class="text-lg cursor-default hover:scale-125 transition-transform"
              >{{ e.mood_emoji || '💬' }}</span>
            </div>
            <p class="text-sm text-slate-600 leading-relaxed">{{ report.mood_rollercoaster }}</p>
          </div>

          <!-- 下周预告 -->
          <div v-if="report.next_week_preview" class="rounded-2xl p-6 flex flex-col items-center justify-center text-center relative overflow-hidden"
            style="background: linear-gradient(135deg, #ECFDF5 0%, #F0FDF4 100%); border: 1px solid #A7F3D0;">
            <div class="text-4xl mb-3">🔮</div>
            <p class="text-xs font-semibold tracking-widest uppercase text-emerald-400 mb-3">下周预告</p>
            <p class="text-sm text-emerald-700 font-medium leading-relaxed">{{ report.next_week_preview }}</p>
          </div>
        </div>

        <!-- ===== 旧版兼容：话题 + 关键词 + 情绪分布 ===== -->
        <div v-if="report.top_topics?.length || report.top_keywords?.length" class="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div v-if="report.top_topics?.length" class="rounded-2xl p-4 card">
            <div class="text-xs text-slate-400 mb-3 font-semibold tracking-wide">🔥 话题热度</div>
            <div class="space-y-2">
              <div v-for="(t, i) in report.top_topics.slice(0, 5)" :key="i" class="flex items-center gap-2 text-xs">
                <span :class="[
                  'w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0',
                  i===0?'bg-red-500 text-white':i===1?'bg-orange-500 text-white':i===2?'bg-amber-500 text-white':'bg-slate-200 text-slate-500'
                ]">{{ i+1 }}</span>
                <span class="text-slate-600 truncate">{{ t.text }}</span>
              </div>
            </div>
          </div>
          <div v-if="report.top_keywords?.length" class="rounded-2xl p-4 card">
            <div class="text-xs text-slate-400 mb-3 font-semibold tracking-wide">🏷️ 关键词</div>
            <div class="flex flex-wrap gap-1.5">
              <span v-for="kw in report.top_keywords.slice(0, 6)" :key="kw.text"
                class="px-2.5 py-1 rounded-full text-[11px] font-medium"
                :style="{ background: palette.accentSoft, color: palette.accent }"
              >{{ kw.text }}</span>
            </div>
          </div>
          <div v-if="report.mood_ranking?.length" class="rounded-2xl p-4 card">
            <div class="text-xs text-slate-400 mb-3 font-semibold tracking-wide">🎭 情绪分布</div>
            <div class="space-y-1.5">
              <div v-for="m in report.mood_ranking" :key="m.mood" class="flex items-center justify-between text-xs">
                <span class="text-slate-500 flex items-center gap-1">
                  <span>{{ moodIcons[m.mood] || '💬' }}</span> {{ m.mood }}
                </span>
                <span class="font-semibold text-slate-600">{{ m.count }}天</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ===== 底部导航 ===== -->
      <div class="flex items-center justify-between mt-10 pt-6 border-t" style="border-color: var(--color-hairline)">
        <button
          v-if="adjacentWeeks.prev"
          @click="goWeek(adjacentWeeks.prev)"
          class="flex items-center gap-1.5 text-sm font-medium text-slate-400 hover:text-slate-700 transition-colors group"
        >
          <ArrowLeft class="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
          {{ adjacentWeeks.prev }}
        </button>
        <span v-else class="text-sm text-slate-300">已是第一周</span>

        <span class="text-xs text-slate-300 font-mono">{{ props.weekId }}</span>

        <button
          v-if="adjacentWeeks.next"
          @click="goWeek(adjacentWeeks.next)"
          class="flex items-center gap-1.5 text-sm font-medium text-slate-400 hover:text-slate-700 transition-colors group"
        >
          {{ adjacentWeeks.next }}
          <ArrowRight class="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
        </button>
        <span v-else class="text-sm text-slate-300">已是最新周</span>
      </div>
    </template>
  </div>
</template>
