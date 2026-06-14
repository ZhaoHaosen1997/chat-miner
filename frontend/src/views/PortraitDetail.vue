<script setup>
import { ref, inject, watch, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  getPortrait, getPortraitStats, getPortraitHistory,
  analyzePortrait, getArchaeology,
} from '../api/index.js'
import {
  ArrowLeft, Loader2, Sparkles, RefreshCw, User,
  MessageSquare, Clock, Tag, TrendingUp,
  ChevronRight, Hash, Smile, BarChart3, Users2,
  Search, MessageCircle, Activity, Zap, Quote, Trophy, Link2,
} from 'lucide-vue-next'

const props = defineProps({ memberId: String })
const router = useRouter()
const route = useRoute()  // v1.5.0: 读取 query 参数支持跨群跳转
const currentGroup = inject('currentGroup')
const activeTaskId = inject('activeTaskId')
const triggerRefresh = inject('triggerRefresh')
// v0.12.2: 画像模型选择
function getPortraitModelId() {
  const v = localStorage.getItem('portraitModelId')
  if (v === null || v === '') return null
  const n = Number(v)
  return isNaN(n) ? null : n
}

const portrait = ref(null)
const stats = ref(null)
const history = ref(null)
const archaeology = ref(null)
const loading = ref(true)
const statsLoading = ref(false)  // 统计数据独立加载，不阻塞页面
const error = ref('')
const activeTab = ref('overview')  // overview | activity | language | social | history
const analyzing = ref(false)
// v0.13.2: 快速切换成员竞态防护
let _loadVersion = 0

const tabs = [
  { key: 'overview', label: '概览', icon: User },
  { key: 'activity', label: '活跃分析', icon: TrendingUp },
  { key: 'language', label: '语言风格', icon: Hash },
  { key: 'social', label: '社交关系', icon: Users2 },
  { key: 'history', label: '版本历史', icon: Clock },
  { key: 'archaeology', label: '考古', icon: Search },
  { key: 'cross-group', label: '跨群身份', icon: Link2 },
]

async function load() {
  // v1.5.0: 支持跨群跳转 — query.group_id 优先于 currentGroup
  const groupId = route.query.group_id ? Number(route.query.group_id) : (currentGroup.value?.id)
  if (!groupId || !props.memberId) return
  const myVersion = ++_loadVersion
  loading.value = true
  statsLoading.value = true
  error.value = ''
  try {
    // 第一阶段：快速加载核心数据（portrait + history + archaeology）
    const [p, h, a] = await Promise.all([
      getPortrait(groupId, props.memberId),
      getPortraitHistory(groupId, props.memberId).catch(() => null),
      getArchaeology(groupId, props.memberId).catch(() => null),
    ])
    if (myVersion !== _loadVersion) return  // 竞态：已切换到其他成员
    portrait.value = p
    history.value = h
    archaeology.value = a
    loading.value = false  // 页面已可用

    // 第二阶段：后台加载统计数据（计算密集，可能较慢）
    stats.value = await getPortraitStats(groupId, props.memberId).catch(() => null)
    if (myVersion !== _loadVersion) return  // 竞态检查
  } catch (e) {
    if (myVersion !== _loadVersion) return
    error.value = e.message
    loading.value = false
  } finally {
    if (myVersion === _loadVersion) statsLoading.value = false
  }
}

async function doAnalyze() {
  if (analyzing.value || activeTaskId.value) return
  analyzing.value = true
  try {
    const result = await analyzePortrait(currentGroup.value.id, props.memberId, getPortraitModelId())
    if (result.task_id) {
      activeTaskId.value = result.task_id
    }
  } catch (e) {
    console.error(e)
    analyzing.value = false
  }
}

const hasPortrait = computed(() => !!portrait.value?.portrait?.personality?.length)

// v1.5.0: 跨群对比
const showLinkDialog = ref(false)
const hasCrossGroup = computed(() => !!portrait.value?.cross_group?.other_members?.length)
const hasPersona = computed(() => !!portrait.value?.persona?.members?.length)
const crossGroupData = computed(() => portrait.value?.cross_group || {})
const personaData = computed(() => portrait.value?.persona || {})

function platformLabel(platform, wxid) {
  if (platform === 'wechat') return '微信'
  if (platform === 'qq') return 'QQ'
  if (wxid?.startsWith('wxid_')) return '微信'
  if (wxid?.startsWith('u_') && !wxid?.includes('@chatroom')) return 'QQ'
  return '未知'
}

function parsePortraitJson(json) {
  if (!json) return {}
  try { return typeof json === 'string' ? JSON.parse(json) : json } catch { return {} }
}

function goToOtherPortrait(member) {
  router.push(`/portrait/${member.id}?group_id=${member.group_id}`)
}

function goToPersonaMember(member) {
  router.push(`/portrait/${member.id}?group_id=${member.group_id}`)
}

watch([currentGroup, () => props.memberId], load, { immediate: true })

watch(activeTaskId, (newVal, oldVal) => {
  if (oldVal && !newVal) {
    analyzing.value = false
    load()
    triggerRefresh?.()
  }
})

function goBack() { router.push('/portraits') }

// 活跃时段热力图颜色
function heatColor(count, max) {
  if (!count || max === 0) return 'bg-slate-50'
  const ratio = count / max
  if (ratio > 0.8) return 'bg-indigo-500'
  if (ratio > 0.6) return 'bg-indigo-400'
  if (ratio > 0.4) return 'bg-indigo-300'
  if (ratio > 0.2) return 'bg-indigo-200'
  return 'bg-indigo-100'
}

const maxHourCount = computed(() => {
  if (!stats.value?.activity?.hourly_heatmap) return 1
  return Math.max(1, ...Object.values(stats.value.activity.hourly_heatmap))
})

const hourlyData = computed(() => {
  const h = stats.value?.activity?.hourly_heatmap || {}
  return Array.from({ length: 24 }, (_, i) => ({
    hour: i,
    label: `${i}:00`,
    count: h[String(i).padStart(2, '0')] || 0,
  }))
})

const monthlyTrend = computed(() => {
  return stats.value?.activity?.monthly_trend || []
})

const msgLenDist = computed(() => {
  return stats.value?.language?.msg_length_distribution || {}
})

// 版本历史
const historyList = computed(() => {
  return history.value?.history || []
})

const currentVersion = computed(() => {
  return history.value?.current || null
})
</script>

<template>
  <div>
    <!-- 返回 -->
    <button @click="goBack" class="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 mb-4 transition-colors">
      <ArrowLeft class="w-4 h-4" /> 返回画像列表
    </button>

    <!-- 加载 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="card p-8 text-center">
      <p class="text-red-400">加载失败：{{ error }}</p>
    </div>

    <template v-else-if="portrait">
      <!-- 头部 -->
      <div class="card p-6 mb-6">
        <div class="flex items-start gap-4">
          <img
            v-if="portrait.avatar"
            :src="portrait.avatar"
            class="w-16 h-16 rounded-full bg-slate-100 flex-shrink-0"
            referrerpolicy="no-referrer"
            @error="$event.target.style.display='none'"
          />
          <div v-else class="w-16 h-16 rounded-full bg-indigo-100 flex items-center justify-center flex-shrink-0">
            <User class="w-8 h-8 text-indigo-400" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <h2 class="text-xl font-bold text-slate-800">{{ portrait.display_name }}</h2>
              <span class="text-2xl">{{ portrait.portrait?.emoji_style || '👤' }}</span>
            </div>
            <p class="text-sm text-slate-500 mt-1">{{ portrait.portrait?.one_line || '——' }}</p>
            <div class="flex items-center gap-3 mt-2 text-xs text-slate-400">
              <span>📅 {{ portrait.data_start_date || '-' }} ~ {{ portrait.data_end_date || '-' }}</span>
              <span>💬 {{ portrait.total_messages }} 条消息</span>
            </div>
          </div>
          <div class="flex items-center gap-2 flex-shrink-0">
            <button
              @click="doAnalyze"
              :disabled="analyzing || !!activeTaskId"
              :class="[
                'flex items-center gap-1.5 px-3 py-2 text-xs rounded-xl transition-colors disabled:opacity-50',
                hasPortrait
                  ? 'text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 border border-slate-200'
                  : 'bg-indigo-600 text-white hover:bg-indigo-700',
              ]"
            >
              <RefreshCw :class="['w-3.5 h-3.5', analyzing && 'animate-spin']" />
              {{ analyzing ? '分析中...' : hasPortrait ? '刷新画像' : '生成画像' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Tab 栏 -->
      <div class="flex gap-1 mb-6 bg-slate-100 rounded-xl p-1">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          @click="activeTab = tab.key"
          :class="[
            'flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-lg text-sm font-medium transition-all',
            activeTab === tab.key
              ? 'bg-white text-slate-800 shadow-sm'
              : 'text-slate-400 hover:text-slate-600',
          ]"
        >
          <component :is="tab.icon" class="w-4 h-4" />
          {{ tab.label }}
        </button>
      </div>

      <!-- Tab: 概览 -->
      <div v-if="activeTab === 'overview'" class="space-y-4">
        <div class="grid grid-cols-2 gap-3">
          <div class="card p-4">
            <div class="text-xs text-slate-400 mb-1 flex items-center gap-1">
              <Tag class="w-3 h-3" /> 性格
            </div>
            <div class="flex gap-1.5 flex-wrap">
              <span v-for="t in portrait.portrait?.personality || []" :key="t"
                    class="px-2.5 py-1 bg-indigo-100 text-indigo-700 rounded-full text-sm font-medium">{{ t }}</span>
              <span v-if="!(portrait.portrait?.personality || []).length" class="text-sm text-slate-400">——</span>
            </div>
          </div>
          <div class="card p-4">
            <div class="text-xs text-slate-400 mb-1">说话风格</div>
            <div class="text-sm font-medium text-slate-700">{{ portrait.portrait?.speaking_style || '——' }}</div>
          </div>
          <div class="card p-4">
            <div class="text-xs text-slate-400 mb-1">群内角色</div>
            <div class="text-sm font-medium text-slate-700">{{ portrait.portrait?.role || '——' }}</div>
          </div>
          <div class="card p-4">
            <div class="text-xs text-slate-400 mb-1">活跃时段</div>
            <div class="text-sm font-medium text-slate-700">{{ portrait.portrait?.active_hours || '——' }}</div>
          </div>
        </div>

        <div class="card p-4">
          <div class="text-xs text-slate-400 mb-2">兴趣话题</div>
          <div class="flex gap-1.5 flex-wrap">
            <span v-for="t in portrait.portrait?.interests || []" :key="t"
                  class="px-2.5 py-1 bg-amber-50 text-amber-700 rounded-full text-sm">{{ t }}</span>
            <span v-if="!(portrait.portrait?.interests || []).length" class="text-sm text-slate-400">——</span>
          </div>
        </div>

        <div v-if="portrait.portrait?.signature_phrases?.length" class="card p-4">
          <div class="text-xs text-slate-400 mb-1">口头禅</div>
          <div class="flex gap-2 flex-wrap">
            <span v-for="(ph, i) in portrait.portrait.signature_phrases" :key="i"
                  class="px-2.5 py-1 bg-purple-50 text-purple-700 rounded-full text-sm italic">"{{ ph }}"</span>
          </div>
        </div>
        <div v-else-if="portrait.portrait?.signature_phrase" class="card p-4">
          <div class="text-xs text-slate-400 mb-1">口头禅</div>
          <div class="text-sm text-slate-600 italic">"{{ portrait.portrait.signature_phrase }}"</div>
        </div>

        <!-- 趣味称号 + 关系解读 -->
        <div v-if="portrait.portrait?.fun_title" class="card p-4 bg-gradient-to-r from-amber-50 to-orange-50 border-amber-100">
          <div class="flex items-center gap-2">
            <span class="text-xl">{{ portrait.portrait?.emoji_style || '🏆' }}</span>
            <div>
              <p class="text-sm font-bold text-amber-700">{{ portrait.portrait.fun_title }}</p>
              <p v-if="portrait.portrait.fun_relation" class="text-xs text-amber-500 mt-0.5">{{ portrait.portrait.fun_relation }}</p>
            </div>
          </div>
        </div>

        <!-- 年度荣誉 v0.11 -->
        <div v-if="portrait.awards?.length" class="card p-4">
          <div class="text-xs text-slate-400 mb-3 flex items-center gap-1.5">
            <Trophy class="w-3.5 h-3.5 text-amber-400" /> 年度荣誉
          </div>
          <div class="flex flex-wrap gap-2">
            <div v-for="(award, i) in portrait.awards" :key="i"
              class="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border"
              style="background: linear-gradient(135deg, #FFFBEB, #FEF3C7); border-color: #FCD34D; color: #92400E;"
            >
              <span class="text-base leading-none">{{ award.emoji || '🏆' }}</span>
              <span>{{ award.name }}</span>
              <span class="text-[10px] opacity-50">{{ award.year }}</span>
            </div>
          </div>
        </div>

        <!-- 深度画像结果 -->
        <div v-if="portrait.portrait?.emotion_profile?.primary" class="card p-4 bg-gradient-to-r from-purple-50 to-indigo-50 border-purple-100">
          <div class="text-xs text-purple-400 mb-2 flex items-center gap-1">
            <Sparkles class="w-3 h-3" /> AI 深度洞察
          </div>
          <div class="space-y-2 text-sm text-slate-700">
            <p v-if="portrait.portrait.emotion_profile?.primary">
              <span class="text-purple-500 font-medium">情绪特征：</span>{{ portrait.portrait.emotion_profile.primary }}
            </p>
            <p v-if="portrait.portrait.emotion_profile?.trend">
              <span class="text-purple-500 font-medium">情绪趋势：</span>{{ portrait.portrait.emotion_profile.trend }}
            </p>
            <p v-if="portrait.portrait.language_style?.style_notes">
              <span class="text-purple-500 font-medium">语言洞察：</span>{{ portrait.portrait.language_style.style_notes }}
            </p>
            <p v-if="portrait.portrait.monthly_synthesis">
              <span class="text-purple-500 font-medium">月度趋势：</span>{{ portrait.portrait.monthly_synthesis }}
            </p>
          </div>
        </div>

        <!-- v0.6.4 统计数据加载中 -->
        <div v-if="statsLoading" class="card p-3 bg-slate-50 flex items-center gap-2 text-xs text-slate-400">
          <Loader2 class="w-3 h-3 animate-spin" /> 正在加载统计数据...
        </div>

        <!-- v0.6.4 最近状态 -->
        <div v-if="stats?.recent_status?.recent_msg_count > 0" class="card p-4 bg-gradient-to-r from-emerald-50 to-teal-50 border-emerald-100">
          <div class="text-xs text-emerald-400 mb-1 flex items-center gap-1">
            <Activity class="w-3 h-3" /> 最近30天状态
          </div>
          <div class="flex items-center gap-3">
            <span class="text-lg">{{ stats.recent_status.active_trend }}</span>
            <div>
              <p class="text-sm font-medium text-slate-700">{{ stats.recent_status.trend_label }}</p>
              <p class="text-xs text-slate-500 mt-0.5">
                发言 {{ stats.recent_status.recent_msg_count }} 条 · 活跃 {{ stats.recent_status.recent_days_active }} 天
                <span v-if="stats.recent_status.recent_mood"> · 情绪偏<span :title="stats.recent_status.recent_mood">{{ stats.recent_status.recent_mood_emoji }} {{ stats.recent_status.recent_mood }}</span></span>
              </p>
              <div v-if="stats.recent_status.recent_topics?.length" class="flex gap-1 mt-1 flex-wrap">
                <span v-for="t in stats.recent_status.recent_topics" :key="t"
                      class="px-1.5 py-0.5 bg-white/60 text-emerald-600 rounded text-[11px]">{{ t }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- v0.6.4 消息风格 + 话题角色 + 标志性表情 -->
        <div class="grid grid-cols-2 gap-3">
          <div v-if="stats?.message_style" class="card p-4">
            <div class="text-xs text-slate-400 mb-1 flex items-center gap-1">
              <MessageSquare class="w-3 h-3" /> 消息风格
            </div>
            <div class="text-sm font-medium text-slate-700">{{ stats.message_style.style_label }}</div>
            <div class="text-xs text-slate-400 mt-1">{{ stats.message_style.emoji_style_label }} · {{ stats.message_style.reply_style }}</div>
          </div>
          <div v-if="stats?.topic_role?.role_label" class="card p-4">
            <div class="text-xs text-slate-400 mb-1 flex items-center gap-1">
              <Zap class="w-3 h-3" /> 话题角色
            </div>
            <div class="text-sm font-medium text-slate-700">{{ stats.topic_role.role_label }}</div>
            <div class="text-xs text-slate-400 mt-1">
              话题发起率 {{ (stats.topic_role.topic_initiation_rate * 100).toFixed(0) }}%
            </div>
          </div>
        </div>

        <!-- v0.6.4 个人标志性表情 -->
        <div v-if="stats?.signature_emoji" class="card p-4">
          <div class="text-xs text-slate-400 mb-1 flex items-center gap-1">
            <Smile class="w-3 h-3" /> 标志性表情
          </div>
          <span class="text-2xl">{{ stats.signature_emoji }}</span>
          <span class="text-xs text-slate-400 ml-2">—— 这个人最常用的表情</span>
        </div>

        <!-- v0.6.4 高光语录 -->
        <div v-if="stats?.highlight_quotes?.length" class="card p-4 bg-gradient-to-r from-yellow-50 to-amber-50 border-yellow-100">
          <div class="text-xs text-yellow-500 mb-2 flex items-center gap-1">
            <Quote class="w-3 h-3" /> 高光语录
          </div>
          <div class="space-y-2">
            <div v-for="(q, i) in stats.highlight_quotes" :key="i"
                 class="bg-white/60 rounded-lg px-3 py-2">
              <p class="text-sm text-slate-600 italic">"{{ q.content }}"</p>
              <div class="flex items-center justify-between mt-1">
                <span class="text-[10px] text-slate-400">{{ q.date }}</span>
                <span v-if="q.comment" class="text-[10px] text-amber-500">{{ q.comment }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 情绪时间线 -->
        <div v-if="stats?.emotion_timeline?.length" class="card p-4">
          <h4 class="text-sm font-medium text-slate-600 mb-3 flex items-center gap-1.5">
            <TrendingUp class="w-3.5 h-3.5" /> 个人情绪轨迹
          </h4>
          <div class="flex flex-wrap gap-[2px]">
            <span
              v-for="(e, i) in stats.emotion_timeline"
              :key="i"
              :title="`${e.date} ${e.mood}`"
              class="text-sm leading-none cursor-default hover:scale-125 transition-transform"
            >{{ e.mood_emoji || '💬' }}</span>
          </div>
          <div class="flex justify-between mt-2 text-[10px] text-slate-300">
            <span>{{ stats.emotion_timeline[0]?.date }}</span>
            <span>{{ stats.emotion_timeline[stats.emotion_timeline.length - 1]?.date }}</span>
          </div>
        </div>

        <div v-if="!portrait.portrait?.emotion_profile?.primary && !hasPortrait" class="card p-6 text-center">
          <Sparkles class="w-8 h-8 text-slate-300 mx-auto mb-2" />
          <p class="text-sm text-slate-400">点击右上角「生成画像」开始分析</p>
        </div>
      </div>

      <!-- Tab: 活跃分析 -->
      <div v-if="activeTab === 'activity'" class="space-y-4">
        <div class="grid grid-cols-3 gap-3">
          <div class="card p-4 text-center">
            <div class="text-2xl font-bold text-indigo-600">{{ stats?.activity?.total_days_active || 0 }}</div>
            <div class="text-xs text-slate-400 mt-1">活跃天数</div>
          </div>
          <div class="card p-4 text-center">
            <div class="text-2xl font-bold text-emerald-600">{{ stats?.activity?.avg_daily_msgs || 0 }}</div>
            <div class="text-xs text-slate-400 mt-1">日均发言</div>
          </div>
          <div class="card p-4 text-center">
            <div class="text-2xl font-bold text-amber-600">{{ stats?.activity?.peak_hour ?? '-' }}h</div>
            <div class="text-xs text-slate-400 mt-1">最活跃时段</div>
          </div>
        </div>

        <!-- 24小时热力图 -->
        <div class="card p-4">
          <h4 class="text-sm font-medium text-slate-600 mb-3 flex items-center gap-1.5">
            <Clock class="w-3.5 h-3.5" /> 24小时发言分布
          </h4>
          <div class="flex items-end gap-[2px] h-20">
            <div
              v-for="h in hourlyData"
              :key="h.hour"
              :title="`${h.label}: ${h.count}条`"
              :style="{ height: h.count > 0 ? `${Math.max(4, (h.count / maxHourCount) * 100)}%` : '2px' }"
              :class="['flex-1 rounded-t-sm transition-colors', heatColor(h.count, maxHourCount)]"
            />
          </div>
          <div class="flex justify-between mt-1 text-[10px] text-slate-300">
            <span v-for="h in [0, 6, 12, 18, 23]" :key="h">{{ h }}h</span>
          </div>
        </div>

        <!-- 月度趋势 -->
        <div v-if="monthlyTrend.length > 0" class="card p-4">
          <h4 class="text-sm font-medium text-slate-600 mb-3 flex items-center gap-1.5">
            <TrendingUp class="w-3.5 h-3.5" /> 月度发言趋势
          </h4>
          <div class="flex items-end gap-1 h-24">
            <div
              v-for="(m, i) in monthlyTrend"
              :key="m.month"
              :title="`${m.month}: ${m.count}条, 活跃${m.days_active}天`"
              class="flex-1 flex flex-col items-center justify-end group"
            >
              <div
                :style="{ height: Math.max(2, (m.count / Math.max(...monthlyTrend.map(x => x.count))) * 100) + '%' }"
                class="w-full bg-indigo-400 rounded-t-sm hover:bg-indigo-500 transition-colors"
              />
              <div v-if="monthlyTrend.length <= 12" class="text-[9px] text-slate-400 mt-1 rotate-45 origin-left whitespace-nowrap">
                {{ m.month.slice(5) }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Tab: 语言风格 -->
      <div v-if="activeTab === 'language'" class="space-y-4">
        <div class="grid grid-cols-2 gap-3">
          <div class="card p-4 text-center">
            <div class="text-2xl font-bold text-indigo-600">{{ stats?.language?.avg_msg_len || 0 }}</div>
            <div class="text-xs text-slate-400 mt-1">平均消息长度（字）</div>
          </div>
          <div class="card p-4 text-center">
            <div class="text-2xl font-bold text-emerald-600">{{ stats?.language?.total_emoji_count || 0 }}</div>
            <div class="text-xs text-slate-400 mt-1">总 emoji 使用次数</div>
          </div>
        </div>

        <!-- 消息长度分布 -->
        <div v-if="msgLenDist && Object.values(msgLenDist).some(v => v > 0)" class="card p-4">
          <h4 class="text-sm font-medium text-slate-600 mb-3 flex items-center gap-1.5">
            <BarChart3 class="w-3.5 h-3.5" /> 消息长度分布
          </h4>
          <div class="space-y-2">
            <div v-for="(cnt, label) in msgLenDist" :key="label" class="flex items-center gap-2">
              <span class="text-xs text-slate-500 w-12">{{ label }}字</span>
              <div class="flex-1 h-5 bg-slate-100 rounded-full overflow-hidden">
                <div
                  :style="{ width: (cnt / Math.max(...Object.values(msgLenDist))) * 100 + '%' }"
                  class="h-full bg-gradient-to-r from-indigo-300 to-indigo-500 rounded-full flex items-center justify-end pr-2"
                >
                  <span v-if="cnt > 0" class="text-[10px] text-white font-medium">{{ cnt }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 常用 Emoji -->
        <div v-if="stats?.language?.top_emojis?.length" class="card p-4">
          <h4 class="text-sm font-medium text-slate-600 mb-2 flex items-center gap-1.5">
            <Smile class="w-3.5 h-3.5" /> 常用 Emoji
          </h4>
          <div class="flex gap-3 flex-wrap">
            <div v-for="e in stats.language.top_emojis.slice(0, 10)" :key="e.emoji"
                 class="flex items-center gap-1 bg-slate-50 rounded-lg px-3 py-1.5">
              <span class="text-xl">{{ e.emoji }}</span>
              <span class="text-xs text-slate-400">{{ e.count }}</span>
            </div>
          </div>
        </div>

        <!-- 高频词标签云 -->
        <div v-if="stats?.language?.top_words?.length" class="card p-4">
          <h4 class="text-sm font-medium text-slate-600 mb-2 flex items-center gap-1.5">
            <Hash class="w-3.5 h-3.5" /> 高频词
          </h4>
          <div class="flex gap-2 flex-wrap">
            <span v-for="w in stats.language.top_words.slice(0, 15)" :key="w.word"
                  :style="{ fontSize: Math.max(12, Math.min(24, 12 + w.count * 2)) + 'px' }"
                  class="text-slate-600 hover:text-indigo-500 transition-colors cursor-default"
            >{{ w.word }}</span>
          </div>
        </div>

        <!-- AI 语言洞察 -->
        <div v-if="portrait.portrait?.language_style?.style_notes" class="card p-4 bg-purple-50 border-purple-100">
          <div class="text-xs text-purple-400 mb-1 flex items-center gap-1">
            <Sparkles class="w-3 h-3" /> AI 语言洞察
          </div>
          <p class="text-sm text-slate-700">{{ portrait.portrait.language_style.style_notes }}</p>
        </div>
      </div>

      <!-- Tab: 社交关系 -->
      <div v-if="activeTab === 'social'" class="space-y-4">
        <div v-if="stats?.social_relations?.length" class="space-y-2">
          <div
            v-for="(r, i) in stats.social_relations"
            :key="r.member_id"
            class="card p-4 flex items-center gap-3 hover:border-indigo-200 transition-colors"
          >
            <div :class="[
              'w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold flex-shrink-0',
              i === 0 ? 'bg-amber-100 text-amber-700' :
              i === 1 ? 'bg-slate-200 text-slate-600' :
              i === 2 ? 'bg-orange-100 text-orange-700' :
              'bg-slate-100 text-slate-400',
            ]">{{ i + 1 }}</div>
            <div class="flex-1 min-w-0">
              <div class="text-sm font-medium text-slate-700">{{ r.name }}</div>
              <div class="text-xs text-slate-400">
                共现 {{ r.co_msg_count }} 次
                <span v-if="r.mention_count"> · @提及 {{ r.mention_count }} 次</span>
              </div>
            </div>
            <div class="text-right flex-shrink-0">
              <div class="text-sm font-bold text-indigo-600">{{ r.total_interactions }}</div>
              <div class="text-[10px] text-slate-400">互动指数</div>
            </div>
            <div v-if="r.relation_type" class="flex-shrink-0">
              <span class="px-2 py-1 bg-purple-50 text-purple-600 rounded-full text-xs font-medium">{{ r.relation_type }}</span>
            </div>
          </div>
        </div>

        <!-- 深度画像中的社交关系（含 AI 判断） -->
        <div v-if="portrait.portrait?.social_relations?.length" class="space-y-2">
          <h4 class="text-sm font-medium text-slate-600 flex items-center gap-1.5">
            <Sparkles class="w-3.5 h-3.5 text-purple-400" /> AI 关系洞察
          </h4>
          <div
            v-for="r in portrait.portrait.social_relations"
            :key="r.member_id"
            class="card p-3 bg-purple-50 border-purple-100"
          >
            <div class="flex items-center justify-between">
              <div>
                <span class="text-sm font-medium text-slate-700">{{ r.name }}</span>
                <span class="ml-2 px-2 py-0.5 bg-purple-100 text-purple-600 rounded-full text-xs">{{ r.relation_type }}</span>
              </div>
              <span class="text-xs text-slate-400">互动 {{ r.interaction_count }} 次</span>
            </div>
            <p v-if="r.note" class="text-xs text-slate-500 mt-1">{{ r.note }}</p>
          </div>
        </div>

        <div v-if="!stats?.social_relations?.length && !portrait.portrait?.social_relations?.length"
             class="card p-8 text-center">
          <Users2 class="w-10 h-10 text-slate-300 mx-auto mb-2" />
          <p class="text-sm text-slate-400">暂无社交关系数据，生成深度画像后可查看</p>
        </div>
      </div>

      <!-- Tab: 版本历史 -->
      <div v-if="activeTab === 'history'" class="space-y-4">
        <!-- 当前版本 -->
        <div v-if="currentVersion" class="card p-4 bg-indigo-50 border-indigo-100">
          <div class="flex items-center justify-between mb-2">
            <span class="text-xs font-medium text-indigo-600 bg-indigo-100 px-2 py-0.5 rounded-full">当前版本</span>
            <span class="text-xs text-slate-400">{{ currentVersion.one_line || '画像已生成' }}</span>
          </div>
          <div class="flex gap-1 flex-wrap">
            <span v-for="t in currentVersion.personality || []" :key="t"
                  class="px-2 py-0.5 bg-indigo-100 text-indigo-700 rounded-full text-xs">{{ t }}</span>
          </div>
        </div>

        <!-- 历史版本时间线 -->
        <div v-if="historyList.length > 0" class="space-y-0 pl-4 border-l-2 border-slate-100">
          <div v-for="v in historyList" :key="v.version" class="relative pb-4 pl-4">
            <div class="absolute left-0 top-2 w-3 h-3 -translate-x-[7px] rounded-full border-2 border-slate-200 bg-white" />
            <div class="card p-3">
              <div class="flex items-center justify-between mb-1">
                <span class="text-xs font-medium text-slate-500">v{{ v.version }}</span>
                <span class="text-[10px] text-slate-400">{{ v.created_at?.slice(0, 10) }}</span>
              </div>
              <p class="text-xs text-slate-600 mb-1">{{ v.one_line || '——' }}</p>
              <div class="flex items-center gap-2 text-[10px] text-slate-400">
                <span>{{ v.analyzed_msg_count }} 条消息</span>
                <span v-if="v.data_start_date">· {{ v.data_start_date }} ~ {{ v.data_end_date }}</span>
              </div>
              <div class="flex gap-1 mt-1.5 flex-wrap">
                <span v-for="t in v.personality || []" :key="t"
                      class="px-1.5 py-0.5 bg-slate-100 text-slate-500 rounded-full text-[10px]">{{ t }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="!historyList.length" class="card p-8 text-center">
          <Clock class="w-10 h-10 text-slate-300 mx-auto mb-2" />
          <p class="text-sm text-slate-400">暂无历史版本。刷新画像后旧版本会自动存档。</p>
        </div>
      </div>

      <!-- Tab: 考古 -->
      <div v-if="activeTab === 'archaeology'" class="space-y-4">
        <div v-if="!archaeology" class="card p-8 text-center">
          <Loader2 class="w-8 h-8 animate-spin text-indigo-400 mx-auto mb-2" />
          <p class="text-sm text-slate-400">加载中...</p>
        </div>
        <template v-else>
          <!-- 数据概览 -->
          <div class="grid grid-cols-3 gap-3">
            <div class="card p-3 text-center">
              <div class="text-2xl font-bold text-indigo-600">{{ archaeology.total_msgs }}</div>
              <div class="text-xs text-slate-400">条消息</div>
            </div>
            <div class="card p-3 text-center">
              <div class="text-lg font-bold text-emerald-600">{{ archaeology.date_range?.[0] || '-' }}</div>
              <div class="text-xs text-slate-400">首次发言</div>
            </div>
            <div class="card p-3 text-center">
              <div class="text-lg font-bold text-amber-600">{{ archaeology.date_range?.[1] || '-' }}</div>
              <div class="text-xs text-slate-400">最近发言</div>
            </div>
          </div>

          <!-- 第一条消息 -->
          <div v-if="archaeology.first_msg" class="card p-4 bg-amber-50 border-amber-100">
            <div class="flex items-center gap-1.5 mb-2">
              <MessageCircle class="w-4 h-4 text-amber-500" />
              <span class="text-sm font-medium text-amber-700">入群第一条消息</span>
              <span class="text-xs text-amber-400 ml-auto">{{ archaeology.first_msg.date }}</span>
            </div>
            <p class="text-sm text-slate-600 italic">"{{ archaeology.first_msg.content }}"</p>
          </div>

          <!-- 最长消息 -->
          <div v-if="archaeology.longest_msg" class="card p-4 bg-purple-50 border-purple-100">
            <div class="flex items-center gap-1.5 mb-2">
              <MessageSquare class="w-4 h-4 text-purple-500" />
              <span class="text-sm font-medium text-purple-700">最长发言</span>
              <span class="text-xs text-purple-400 ml-auto">{{ archaeology.longest_msg.length }}字 · {{ archaeology.longest_msg.date }}</span>
            </div>
            <p class="text-sm text-slate-600">"{{ archaeology.longest_msg.content.slice(0, 200) }}{{ archaeology.longest_msg.content.length > 200 ? '...' : '' }}"</p>
          </div>

          <!-- 历史上的今天 -->
          <div v-if="archaeology.on_this_day?.length" class="card p-4">
            <div class="flex items-center gap-1.5 mb-2">
              <Clock class="w-4 h-4 text-indigo-500" />
              <span class="text-sm font-medium text-slate-700">历史上的今天</span>
            </div>
            <div class="space-y-2">
              <div v-for="(m, i) in archaeology.on_this_day" :key="i" class="text-sm text-slate-500 bg-slate-50 rounded-lg px-3 py-2">
                <span class="text-xs text-slate-400">{{ m.date }}</span>
                <p class="mt-0.5">"{{ m.content.slice(0, 100) }}{{ m.content.length > 100 ? '...' : '' }}"</p>
              </div>
            </div>
          </div>

          <!-- 年度统计 -->
          <div v-if="archaeology.yearly_counts && Object.keys(archaeology.yearly_counts).length > 1" class="card p-4">
            <h4 class="text-sm font-medium text-slate-600 mb-2 flex items-center gap-1.5">
              <TrendingUp class="w-3.5 h-3.5" /> 年度发言统计
            </h4>
            <div class="flex items-end gap-2 h-16">
              <div v-for="(cnt, yr) in archaeology.yearly_counts" :key="yr"
                   :style="{ height: Math.max(4, (cnt / Math.max(...Object.values(archaeology.yearly_counts))) * 100) + '%' }"
                   class="flex-1 bg-indigo-300 rounded-t-sm hover:bg-indigo-400 transition-colors relative group"
                   :title="`${yr}: ${cnt}条`">
              </div>
            </div>
            <div class="flex justify-between mt-1 text-[10px] text-slate-400">
              <span v-for="(cnt, yr) in archaeology.yearly_counts" :key="yr">{{ yr }}</span>
            </div>
          </div>
        </template>
      </div>

      <!-- v1.5.0 Tab: 跨群身份 -->
      <div v-if="activeTab === 'cross-group'" class="space-y-4">
        <!-- 同 wxid 自动检测 -->
        <div v-if="hasCrossGroup" class="card p-4 bg-indigo-50/50 border border-indigo-100">
          <div class="flex items-center gap-2 mb-3">
            <span class="text-xs font-medium text-indigo-600 bg-indigo-100 px-2 py-0.5 rounded-full">自动发现</span>
            <span class="text-xs text-slate-500">同一 wxid 在 {{ crossGroupData.total_groups }} 个群出现</span>
          </div>
          <div class="grid gap-3 md:grid-cols-2">
            <div v-for="m in crossGroupData.other_members" :key="m.id"
                 class="bg-white rounded-lg p-3 border border-slate-200 hover:border-indigo-300 transition-colors cursor-pointer"
                 @click="goToOtherPortrait(m)">
              <div class="flex items-center justify-between mb-1">
                <span class="text-sm font-medium text-slate-800">{{ m.display_name }} <span class="text-xs text-slate-400 font-normal">({{ m.id }})</span></span>
                <span class="text-[11px] px-1.5 py-0.5 rounded-full"
                  :class="platformLabel(m.platform, m.wxid) === '微信' ? 'bg-green-50 text-green-600' : platformLabel(m.platform, m.wxid) === 'QQ' ? 'bg-blue-50 text-blue-600' : 'bg-slate-100 text-slate-500'">
                  {{ platformLabel(m.platform, m.wxid) }}
                </span>
              </div>
              <div class="text-xs text-slate-500">
                {{ m.group_name }}
                <span v-if="m.total_analyzed_messages" class="ml-2">· {{ m.total_analyzed_messages }}条分析</span>
              </div>
              <div v-if="parsePortraitJson(m.portrait_json)?.personality" class="mt-2 text-xs text-slate-600">
                <span class="text-slate-400">性格：</span>
                {{ parsePortraitJson(m.portrait_json).personality?.slice(0, 60) }}{{ (parsePortraitJson(m.portrait_json).personality || '').length > 60 ? '...' : '' }}
              </div>
            </div>
          </div>
        </div>

        <!-- Persona: 已关联身份 -->
        <div v-if="hasPersona" class="card p-4 bg-amber-50/50 border border-amber-100">
          <div class="flex items-center justify-between mb-3">
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-amber-600 bg-amber-100 px-2 py-0.5 rounded-full">已关联</span>
              <span class="text-xs text-slate-500">{{ personaData.members?.length || 0 }} 个身份</span>
            </div>
          </div>
          <div class="grid gap-3 md:grid-cols-2">
            <div v-for="m in personaData.members" :key="m.id"
                 class="bg-white rounded-lg p-3 border border-slate-200 hover:border-amber-300 transition-colors cursor-pointer"
                 @click="goToPersonaMember(m)">
              <div class="flex items-center justify-between mb-1">
                <span class="text-sm font-medium text-slate-800">{{ m.display_name }} <span class="text-xs text-slate-400 font-normal">({{ m.id }})</span></span>
                <span class="text-[11px] px-1.5 py-0.5 rounded-full"
                  :class="platformLabel(m.platform, m.wxid) === '微信' ? 'bg-green-50 text-green-600' : platformLabel(m.platform, m.wxid) === 'QQ' ? 'bg-blue-50 text-blue-600' : 'bg-slate-100 text-slate-500'">
                  {{ platformLabel(m.platform, m.wxid) }}
                </span>
              </div>
              <div class="text-xs text-slate-500">{{ m.group_name }}</div>
            </div>
          </div>
        </div>

        <!-- 无跨群数据 -->
        <div v-if="!hasCrossGroup && !hasPersona" class="card p-8 text-center">
          <Users2 class="w-10 h-10 text-slate-200 mx-auto mb-2" />
          <p class="text-sm text-slate-400">该成员暂未在其他群出现</p>
          <p class="text-xs text-slate-400 mt-1">同一 wxid 出现在多个群时会自动发现</p>
        </div>
      </div>
    </template>
  </div>
</template>
