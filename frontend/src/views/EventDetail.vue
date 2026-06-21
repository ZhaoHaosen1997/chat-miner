<script setup>
import { ref, computed, watch, inject, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Calendar, MessageSquare, Users, Clock, Loader2, Flag, Quote } from 'lucide-vue-next'
import FloatingNav from '../components/FloatingNav.vue'
import { getEventDetail, getEvents } from '../api/index.js'

const props = defineProps({ eventId: String })
const router = useRouter()
const currentGroup = inject('currentGroup', ref(null))
const event = ref(null)
const loading = ref(true)
const error = ref('')
const adjacent = ref({ prev: null, next: null })

// 事件类型配色
const typePalettes = {
  decision:   { hero: 'linear-gradient(135deg, #DC2626 0%, #EA580C 40%, #F59E0B 100%)', accent: '#F59E0B', accentSoft: '#FFFBEB', accentBorder: '#FDE68A', icon: '🎯', label: '决策', dark: 'linear-gradient(135deg, #1F1A16 0%, #2D2420 100%)' },
  discussion: { hero: 'linear-gradient(135deg, #4F46E5 0%, #818CF8 50%, #A78BFA 100%)', accent: '#818CF8', accentSoft: '#EEF2FF', accentBorder: '#C7D2FE', icon: '💬', label: '讨论', dark: 'linear-gradient(135deg, #151830 0%, #1E2140 100%)' },
  social:     { hero: 'linear-gradient(135deg, #E11D48 0%, #F472B6 50%, #FBCFE8 100%)', accent: '#F472B6', accentSoft: '#FFF1F2', accentBorder: '#FECDD3', icon: '🎉', label: '社交', dark: 'linear-gradient(135deg, #1F1014 0%, #2D1A20 100%)' },
  announcement: { hero: 'linear-gradient(135deg, #059669 0%, #34D399 50%, #6EE7B7 100%)', accent: '#34D399', accentSoft: '#ECFDF5', accentBorder: '#A7F3D0', icon: '📢', label: '公告', dark: 'linear-gradient(135deg, #0A1F17 0%, #122D22 100%)' },
  meme:       { hero: 'linear-gradient(135deg, #9333EA 0%, #D946EF 50%, #FBBF24 100%)', accent: '#D946EF', accentSoft: '#FAF5FF', accentBorder: '#E9D5FF', icon: '🤣', label: '梗', dark: 'linear-gradient(135deg, #1A1028 0%, #281A38 100%)' },
}
const defaultPalette = { hero: 'linear-gradient(135deg, #6366F1 0%, #8B5CF6 50%, #A78BFA 100%)', accent: '#6366F1', accentSoft: '#EEF2FF', accentBorder: '#C7D2FE', icon: '📌', label: '事件', dark: 'linear-gradient(135deg, #1A1D23 0%, #252830 100%)' }

const palette = computed(() => typePalettes[event.value?.event_type] || defaultPalette)
const report = computed(() => {
  if (!event.value) return null
  const rj = event.value.report_json
  if (typeof rj === 'string') {
    try { return JSON.parse(rj) } catch { return null }
  }
  return rj || null
})

const safeTitle = computed(() => {
  const t = event.value?.title
  return typeof t === 'string' ? t : (report.value?.headline || '')
})
const hasEnriched = computed(() => report.value && report.value.narrative)

const participants = computed(() => {
  if (hasEnriched.value && report.value.participants) return report.value.participants
  const names = event.value?.participant_names || {}
  return Object.values(names).map(name => ({ name, role: '' }))
})

const keyMoments = computed(() => report.value?.key_moments || [])
const keyQuotes = computed(() => {
  if (hasEnriched.value && report.value.key_quotes) return report.value.key_quotes
  let q = event.value?.key_quotes
  if (typeof q === 'string') { try { q = JSON.parse(q) } catch { q = [] } }
  return Array.isArray(q) ? q : []
})

function formatTime(ts) {
  if (!ts) return ''
  return ts.slice(0, 16) || ts
}

function goBack() { router.push('/') }
function goEvent(id) { if (id) router.push(`/event/${id}`) }

function onEsc(e) { if (e.key === 'Escape' && e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') goBack() }
onMounted(() => window.addEventListener('keydown', onEsc))
onUnmounted(() => window.removeEventListener('keydown', onEsc))

async function load() {
  const gid = currentGroup.value?.id
  if (!props.eventId || !gid) return
  loading.value = true
  error.value = ''
  try {
    const data = await getEventDetail(gid, parseInt(props.eventId))
    event.value = data
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }

  // 加载相邻事件
  try {
    const allEvents = await getEvents(gid, {})
    const ids = allEvents.map(e => e.id)
    const idx = ids.indexOf(parseInt(props.eventId))
    if (ids.length > 1) {
      adjacent.value.prev = idx < ids.length - 1 ? ids[idx + 1] : ids[0]
      adjacent.value.next = idx > 0 ? ids[idx - 1] : ids[ids.length - 1]
    }
  } catch { /* ignore */ }
}

watch(() => props.eventId, load, { immediate: true })

// 从 URL 提取 group_id 用于 API
watch(event, (evt) => {
  if (!evt) return
  // 重试 adjacent 查询如果有 group_id
})
</script>

<template>
  <div v-if="loading" class="flex items-center justify-center py-32">
    <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
  </div>

  <div v-else-if="error" class="flex flex-col items-center justify-center py-32 text-slate-400">
    <p class="text-lg font-medium text-slate-500 mb-1">{{ error }}</p>
    <button @click="goBack" class="text-sm text-indigo-500 hover:underline mt-2">返回仪表盘</button>
  </div>

  <template v-else-if="event">
    <!-- FloatingNav -->
    <FloatingNav
      :show-prev="!!adjacent.prev"
      :show-next="!!adjacent.next"
      :prev-label="'上一个事件'"
      :next-label="'下一个事件'"
      @prev="goEvent(adjacent.prev)"
      @next="goEvent(adjacent.next)"
    />

    <div class="max-w-4xl mx-auto">
      <!-- Hero Banner -->
      <div class="relative rounded-2xl overflow-hidden mb-8" :style="{ background: palette.hero }">
        <div class="relative z-10 px-8 py-12 md:py-16 text-center">
          <div class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/15 backdrop-blur-sm text-white/90 text-xs font-medium mb-5">
            {{ palette.icon }} {{ palette.label }}
          </div>
          <h1 class="text-2xl md:text-4xl lg:text-5xl font-black leading-tight tracking-tight text-white mb-5">
            {{ safeTitle }}
          </h1>
          <div class="flex items-center justify-center gap-2 text-sm text-white/60 mb-6">
            <Calendar class="w-3.5 h-3.5" />
            <span>{{ formatTime(event.start_time) }} ~ {{ formatTime(event.end_time) }}</span>
          </div>
          <!-- 统计条 -->
          <div class="flex items-center justify-center gap-6 pt-5 border-t border-white/10">
            <div class="flex items-center gap-1.5 text-white/70 text-xs">
              <MessageSquare class="w-3.5 h-3.5" />
              <span class="font-semibold text-white">{{ event.message_count || 0 }}</span> 条消息
            </div>
            <div class="w-px h-4 bg-white/10" />
            <div class="flex items-center gap-1.5 text-white/70 text-xs">
              <Users class="w-3.5 h-3.5" />
              <span class="font-semibold text-white">{{ participants.length || 0 }}</span> 人参与
            </div>
            <div class="w-px h-4 bg-white/10" />
            <div v-if="report?.mood_emoji" class="flex items-center gap-1.5 text-xs text-white/70">
              <span class="text-base">{{ report.mood_emoji }}</span>
              {{ report.mood || '' }}
            </div>
          </div>
        </div>
        <div class="absolute inset-0 opacity-10 pointer-events-none"
          style="background: radial-gradient(circle at 30% 20%, rgba(255,255,255,0.4) 0%, transparent 60%);">
        </div>
      </div>

      <!-- 叙事 + 角色卡 -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5 mb-8">
        <!-- 叙事 -->
        <div v-if="hasEnriched" class="lg:col-span-2 card p-6">
          <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">AI 叙事</h3>
          <p class="text-sm md:text-base leading-relaxed text-slate-700 whitespace-pre-line">{{ report.narrative }}</p>
          <p v-if="report.aftermath" class="mt-4 pt-4 border-t border-slate-100 text-sm text-slate-500 italic">
            💨 {{ report.aftermath }}
          </p>
        </div>
        <!-- 旧事件降级 -->
        <div v-else class="lg:col-span-2 card p-6">
          <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">事件描述</h3>
          <p class="text-sm leading-relaxed text-slate-700">{{ event.description }}</p>
        </div>

        <!-- 角色卡 -->
        <div class="card p-6">
          <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4">参与角色</h3>
          <div class="space-y-2">
            <div v-for="(p, i) in participants.slice(0, 8)" :key="i"
              class="flex items-center gap-2.5 text-sm py-1.5 border-b border-slate-50 last:border-0">
              <div class="w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0"
                :style="{ background: palette.accentSoft, color: palette.accent }">
                {{ (p.name || '?')[0] }}
              </div>
              <span class="flex-1 text-slate-700 text-xs truncate">{{ p.name }}</span>
              <span v-if="p.role" class="text-[10px] px-2 py-0.5 rounded-full font-medium"
                :style="{ background: palette.accentSoft, color: palette.accent }">{{ p.role }}</span>
            </div>
            <div v-if="participants.length === 0" class="text-xs text-slate-400 text-center py-4">暂无参与者数据</div>
          </div>
        </div>
      </div>

      <!-- 关键时刻时间线 -->
      <div v-if="keyMoments.length > 0" class="card p-6 mb-8">
        <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-5 flex items-center gap-2">
          <Flag class="w-3.5 h-3.5" :style="{ color: palette.accent }" /> 关键时刻
        </h3>
        <div class="relative">
          <div class="absolute left-[7px] top-2 bottom-2 w-px bg-slate-200" />
          <div v-for="(m, i) in keyMoments" :key="i" class="flex gap-4 pb-5 last:pb-0">
            <div class="w-[15px] h-[15px] rounded-full border-2 flex-shrink-0 mt-0.5 z-10 bg-white"
              :style="{ borderColor: palette.accent }" />
            <div class="flex-1 min-w-0">
              <span class="text-[10px] font-mono text-slate-400">{{ m.time }}</span>
              <p class="text-sm text-slate-700 mt-0.5">{{ m.description }}</p>
              <p v-if="m.quote" class="text-xs text-slate-400 italic mt-1">"{{ m.quote }}"</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 名场面金句 -->
      <div v-if="keyQuotes.length > 0" class="card p-6">
        <h3 class="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-5 flex items-center gap-2">
          <Quote class="w-3.5 h-3.5" :style="{ color: palette.accent }" /> 名场面
        </h3>
        <div class="space-y-4">
          <div v-for="(q, i) in keyQuotes" :key="i"
            class="border-l-2 pl-4 py-1"
            :style="{ borderColor: palette.accentBorder }">
            <p class="text-base italic leading-relaxed text-slate-600">{{ q }}</p>
          </div>
        </div>
      </div>
    </div>
  </template>
</template>
