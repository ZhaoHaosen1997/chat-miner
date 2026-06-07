<script setup>
import { ref, computed, inject, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getPortraits, analyzePortrait, analyzeAllPortraits, getMembers, getRelations } from '../api/index.js'
import { Loader2, Sparkles, RefreshCw, User, Zap, Clock, Share2 } from 'lucide-vue-next'
const router = useRouter()
const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')
const activeTaskId = inject('activeTaskId')

const portraits = ref([])
const members = ref([])
const loading = ref(false)
const refreshing = ref(null)      // 单个刷新的 memberId
const viewMode = ref('cards')     // 'cards' | 'network'
const batchAnalyzing = ref(false) // 批量分析中
const error = ref('')

async function load(silent = false) {
  if (!currentGroup.value) return
  if (!silent) loading.value = true
  const gid = currentGroup.value.id
  try {
    const [p, m] = await Promise.all([getPortraits(gid), getMembers(gid)])
    portraits.value = p
    members.value = m
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(currentGroup, load, { immediate: true })

// 增量刷新（最近10天）
async function refreshOne(memberId) {
  if (refreshing.value === memberId || activeTaskId.value) return
  refreshing.value = memberId
  try {
    const result = await analyzePortrait(currentGroup.value.id, memberId)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    }
  } catch (e) {
    console.error(e)
    refreshing.value = null
  }
}

// 全量生成（无画像的成员）
async function generateOne(memberId) {
  if (refreshing.value === memberId || activeTaskId.value) return
  refreshing.value = memberId
  try {
    const result = await analyzePortrait(currentGroup.value.id, memberId, 0)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    }
  } catch (e) {
    console.error(e)
    refreshing.value = null
  }
}

// 一键分析全部
async function analyzeAll() {
  if (batchAnalyzing.value || activeTaskId.value) return
  batchAnalyzing.value = true
  try {
    const result = await analyzeAllPortraits(currentGroup.value.id)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    } else {
      batchAnalyzing.value = false
    }
  } catch (e) {
    console.error(e)
    batchAnalyzing.value = false
  }
}

// 批量任务运行时定时刷新（逐个展示已完成的画像）
let _refreshTimer = null
watch(activeTaskId, (newVal, oldVal) => {
  if (oldVal && !newVal) {
    refreshing.value = null
    batchAnalyzing.value = false
    if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null }
    load()
    triggerRefresh?.()
  }
  if (newVal && !oldVal) {
    _refreshTimer = setInterval(() => load(true), 3000)  // 静默刷新，不显示loading
  }
})
onUnmounted(() => { if (_refreshTimer) clearInterval(_refreshTimer) })

function openDetail(portrait) {
  router.push(`/portrait/${portrait.member_id}`)
}

// 合并 portraits 和 members
const mergedPortraits = ref([])
watch([portraits, members], ([p, m]) => {
  mergedPortraits.value = p.map(pt => {
    const member = m.find(mb => mb.id === pt.member_id) || {}
    return { ...pt, ...member }
  })
})

// ---- 关系网络图 ----
const relationsData = ref(null)
async function loadRelations() {
  if (!currentGroup.value) return
  try {
    relationsData.value = await getRelations(currentGroup.value.id)
  } catch (e) { console.error(e) }
}
watch(viewMode, (v) => { if (v === 'network') loadRelations() })

// 基于圆心布局计算节点坐标
const networkLayout = computed(() => {
  const data = relationsData.value
  if (!data?.nodes?.length) return { nodes: [], links: [], svgSize: 400 }
  const nodes = data.nodes
  const n = nodes.length
  const cx = 220, cy = 220, r = 160
  const positioned = nodes.map((nd, i) => {
    const angle = (2 * Math.PI * i) / n - Math.PI / 2
    return { ...nd, x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle), angle }
  })
  // 把 links 映射到坐标
  const nodeMap = {}
  positioned.forEach(nd => { nodeMap[nd.wxid] = nd })
  const links = (data.links || []).map(l => ({
    ...l,
    x1: nodeMap[l.source]?.x || 0, y1: nodeMap[l.source]?.y || 0,
    x2: nodeMap[l.target]?.x || 0, y2: nodeMap[l.target]?.y || 0,
  })).filter(l => l.x1 && l.x2)
  return { nodes: positioned, links, svgSize: 440 }
})

// 格式化最后刷新时间为精确时间戳
function formatLastUpdated(dateStr) {
  if (!dateStr) return '未知'
  const then = new Date(dateStr)
  const now = new Date()
  const diffMs = now - then
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))

  if (diffHours < 1) return '刚刚'
  if (diffHours < 24) return `${diffHours}小时前`

  // 超过24小时显示完整日期时间
  const y = then.getFullYear()
  const m = String(then.getMonth() + 1).padStart(2, '0')
  const d = String(then.getDate()).padStart(2, '0')
  const hh = String(then.getHours()).padStart(2, '0')
  const mm = String(then.getMinutes()).padStart(2, '0')
  const ss = String(then.getSeconds()).padStart(2, '0')
  return `${y}-${m}-${d} ${hh}:${mm}:${ss}`
}

function daysSince(dateStr) {
  if (!dateStr) return 999
  const then = new Date(dateStr)
  const now = new Date()
  return Math.floor((now - then) / (1000 * 60 * 60 * 24))
}

function isStale(lastUpdated) {
  return daysSince(lastUpdated) > 10
}

// 未生成画像的成员数
const unanalyzedCount = computed(() =>
  members.value.filter(m => !portraits.value.find(p => p.member_id === m.id)).length
)
</script>

<template>
  <div>
    <!-- 头部 -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-xl font-bold text-slate-800">群友画像</h2>
        <p class="text-sm text-slate-400 mt-1">基于 AI 分析的成员性格、风格和角色</p>
      </div>
      <div class="flex items-center gap-3">
        <!-- 视图切换 -->
        <div class="flex bg-slate-100 rounded-lg p-0.5">
          <button @click="viewMode='cards'" :class="['px-2.5 py-1 text-xs rounded-md transition-colors', viewMode==='cards' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400']">卡片</button>
          <button @click="viewMode='network'" :class="['px-2.5 py-1 text-xs rounded-md transition-colors flex items-center gap-1', viewMode==='network' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400']"><Share2 class="w-3 h-3" />关系</button>
        </div>
        <div class="text-xs text-slate-400">
          {{ portraits.length }} / {{ members.length }} 人
        </div>
        <button
          v-if="members.length > 0"
          @click="analyzeAll"
          :disabled="batchAnalyzing || !!activeTaskId"
          class="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50"
        >
          <Zap :class="['w-3.5 h-3.5', batchAnalyzing && 'animate-spin']" />
          {{ batchAnalyzing ? '分析中...' : '一键分析全部' }}
        </button>
      </div>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <!-- 关系网络视图 -->
    <div v-if="viewMode === 'network'" class="card p-4">
      <div v-if="!relationsData?.nodes?.length" class="text-center py-10 text-sm text-slate-400">暂无关系数据</div>
      <svg v-else :viewBox="'0 0 ' + networkLayout.svgSize + ' ' + networkLayout.svgSize" class="w-full max-w-lg mx-auto">
        <!-- 连线 -->
        <line
          v-for="(l, i) in networkLayout.links" :key="'l'+i"
          :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2"
          :stroke-width="Math.max(1, Math.min(6, l.weight / 50))"
          stroke="#c7d2fe" stroke-linecap="round" opacity="0.6"
        />
        <!-- 节点 -->
        <g v-for="(nd, i) in networkLayout.nodes" :key="nd.wxid">
          <circle :cx="nd.x" :cy="nd.y" r="20" fill="#e0e7ff" stroke="#818cf8" stroke-width="2" />
          <text :x="nd.x" :y="nd.y + 4" text-anchor="middle" font-size="10" fill="#4338ca" font-weight="600">{{ nd.name.slice(0, 4) }}</text>
        </g>
      </svg>
    </div>

    <!-- 画像卡片网格 -->
    <div v-else class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      <div
        v-for="p in mergedPortraits"
        :key="p.member_id"
        @click="openDetail(p)"
        :class="[
          'card p-4 cursor-pointer hover:border-indigo-200 transition-all group',
          isStale(p.last_updated) && 'ring-1 ring-amber-200',
        ]"
      >
        <!-- 头像 + name -->
        <div class="flex items-center gap-3 mb-3">
          <img
            v-if="p.avatar"
            :src="p.avatar"
            :alt="p.display_name"
            class="w-10 h-10 rounded-full bg-slate-100"
            referrerpolicy="no-referrer"
            @error="$event.target.style.display='none'"
          />
          <div v-else class="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center">
            <User class="w-5 h-5 text-indigo-400" />
          </div>
          <div class="min-w-0">
            <div class="text-sm font-semibold text-slate-700 truncate">{{ p.display_name }}</div>
            <div v-if="p.remark && p.remark !== p.display_name" class="text-[11px] text-slate-400 truncate">{{ p.remark }}</div>
          </div>
        </div>

        <!-- 最后刷新时间（v0.6.4: 精确到时分秒） -->
        <div v-if="p.last_updated" class="flex items-center gap-1 mb-2 text-[10px]" :class="isStale(p.last_updated) ? 'text-amber-500' : 'text-slate-400'">
          <Clock class="w-3 h-3" />
          {{ formatLastUpdated(p.last_updated) }}
          <span v-if="isStale(p.last_updated)" class="text-amber-500 font-medium">· 建议刷新</span>
        </div>

        <!-- 一句话人设 -->
        <p class="text-sm text-slate-600 leading-relaxed mb-3 group-hover:text-indigo-600 transition-colors">
          {{ p.portrait?.one_line || '点击查看详情' }}
        </p>

        <!-- 标签 -->
        <div v-if="p.portrait?.personality" class="flex flex-wrap gap-1 mb-2">
          <span
            v-for="tag in p.portrait.personality"
            :key="tag"
            class="px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full text-[11px]"
          >{{ tag }}</span>
        </div>

        <!-- emoji + 刷新 -->
        <div class="flex items-center justify-between">
          <span class="text-lg">{{ p.portrait?.emoji_style || '👤' }}</span>
          <button
            @click.stop="refreshOne(p.member_id)"
            :disabled="refreshing === p.member_id || !!activeTaskId"
            :class="[
              'transition-colors',
              isStale(p.last_updated) ? 'text-amber-400 hover:text-amber-600' : 'text-slate-300 hover:text-indigo-500',
            ]"
            :title="isStale(p.last_updated) ? '超过10天未刷新，建议更新' : '增量刷新最近10天'"
          >
            <RefreshCw :class="['w-3.5 h-3.5', refreshing === p.member_id && 'animate-spin']" />
          </button>
        </div>
      </div>

      <!-- 未生成画像的成员 -->
      <div
        v-for="m in members.filter(mb => !portraits.find(p => p.member_id === mb.id))"
        :key="'nomem-' + m.id"
        class="card p-4 flex flex-col items-center justify-center text-center gap-2 min-h-[160px] opacity-60"
      >
        <User class="w-8 h-8 text-slate-300" />
        <div>
          <div class="text-sm font-medium text-slate-500">{{ m.display_name }}</div>
          <div class="text-xs text-slate-400">{{ m.message_count }} 条消息</div>
        </div>
        <button
          @click="generateOne(m.id)"
          :disabled="refreshing === m.id || !!activeTaskId"
          class="mt-1 px-3 py-1 text-xs text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors flex items-center gap-1"
        >
          <Sparkles class="w-3 h-3" /> 生成画像
        </button>
      </div>
    </div>

    <!-- 暂无数据 -->
    <div v-if="members.length === 0 && !loading" class="card p-12 text-center">
      <Sparkles class="w-12 h-12 text-slate-300 mx-auto mb-3" />
      <p class="text-slate-400">导入群聊并分析几天后，才能生成群友画像哦</p>
    </div>
  </div>
</template>
