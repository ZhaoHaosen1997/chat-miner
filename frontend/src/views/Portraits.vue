<script setup>
import { ref, computed, inject, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getPortraits, analyzePortrait, analyzeAllPortraits, getMembers, getRelations } from '../api/index.js'
import { Loader2, Sparkles, RefreshCw, User, Zap, Clock, Share2, LayoutGrid } from 'lucide-vue-next'
const router = useRouter()
const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')
const activeTaskId = inject('activeTaskId')

const portraits = ref([])
const members = ref([])
const loading = ref(false)
const refreshing = ref(null)      // 单个刷新的 memberId
const viewMode = ref('cards')     // 'cards' | 'network'
const batchAnalyzing = ref(false)
// v0.12.2: 画像模型选择
function getPortraitModelId() {
  const v = localStorage.getItem('portraitModelId')
  return v ? parseInt(v) : null
} // 批量分析中
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
    const result = await analyzePortrait(currentGroup.value.id, memberId, getPortraitModelId())
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
    const result = await analyzePortrait(currentGroup.value.id, memberId, getPortraitModelId())
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
    const result = await analyzeAllPortraits(currentGroup.value.id, getPortraitModelId())
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
const relationsLoading = ref(false)
const hoveredNodeWxid = ref(null)
const networkTooltip = ref(null)  // { x, y, name, msgCount, connectionCount }

async function loadRelations() {
  if (!currentGroup.value || relationsLoading.value) return
  relationsLoading.value = true
  try {
    relationsData.value = await getRelations(currentGroup.value.id)
  } catch (e) { console.error(e) }
  finally { relationsLoading.value = false }
}
watch(viewMode, (v) => { if (v === 'network') loadRelations() })

// 节点颜色池
const nodeColors = [
  { fill: '#6366F1', glow: '#818CF8' },  // indigo
  { fill: '#8B5CF6', glow: '#A78BFA' },  // violet
  { fill: '#EC4899', glow: '#F472B6' },  // pink
  { fill: '#14B8A6', glow: '#5EEAD4' },  // teal
  { fill: '#F59E0B', glow: '#FBBF24' },  // amber
  { fill: '#3B82F6', glow: '#60A5FA' },  // blue
  { fill: '#EF4444', glow: '#F87171' },  // red
  { fill: '#10B981', glow: '#34D399' },  // emerald
  { fill: '#F97316', glow: '#FB923C' },  // orange
  { fill: '#06B6D4', glow: '#22D3EE' },  // cyan
]

// 增强版网络布局：中心-边缘 + 连接度加权
const networkLayout = computed(() => {
  const data = relationsData.value
  if (!data?.nodes?.length) return { nodes: [], links: [], svgSize: 560 }

  const rawNodes = data.nodes
  const rawLinks = data.links || []

  // 计算每个节点的连接度（总交互权重）
  const connDegrees = {}
  rawLinks.forEach(l => {
    connDegrees[l.source] = (connDegrees[l.source] || 0) + l.weight
    connDegrees[l.target] = (connDegrees[l.target] || 0) + l.weight
  })

  // 节点按连接度排序（高连接度靠近中心）
  const maxMsg = Math.max(...rawNodes.map(n => n.msg_count || 0), 1)

  // 按连接度降序排列（高连接度靠中心）
  const sorted = [...rawNodes].sort((a, b) =>
    (connDegrees[b.wxid] || 0) - (connDegrees[a.wxid] || 0)
  )

  const n = sorted.length
  const cx = 280, cy = 260

  // 内圈半径 (核心成员) 和 外圈半径
  const innerR = n <= 6 ? 100 : 90
  const outerR = n <= 6 ? 180 : 200

  // 给每个节点分配角度和半径
  const positioned = sorted.map((nd, i) => {
    // 前 40% 的节点放内圈，其余放外圈
    const isCore = i < Math.ceil(n * 0.4) && n > 3
    const baseR = isCore ? innerR : outerR
    // 加一点随机偏移避免重叠
    const rJitter = (Math.sin(i * 2.7) * 15)

    // 角度：均匀分布，内圈和外圈错开
    const angleOffset = isCore ? 0 : Math.PI / n
    const angle = (2 * Math.PI * i) / n + angleOffset - Math.PI / 2

    const r = baseR + rJitter
    const x = cx + r * Math.cos(angle)
    const y = cy + r * Math.sin(angle)

    // 节点大小：消息数越多越大
    const msgRatio = (nd.msg_count || 0) / maxMsg
    const radius = 16 + msgRatio * 18  // 16-34px

    // 颜色分配
    const colorIdx = i % nodeColors.length

    return {
      ...nd,
      x, y, radius,
      colorIdx,
      fill: nodeColors[colorIdx].fill,
      glow: nodeColors[colorIdx].glow,
      connDegree: connDegrees[nd.wxid] || 0,
      isCore,
    }
  })

  // 映射坐标到 links
  const nodeMap = {}
  positioned.forEach(nd => { nodeMap[nd.wxid] = nd })

  const maxWeight = Math.max(...rawLinks.map(l => l.weight), 1)

  const links = rawLinks.map(l => {
    const s = nodeMap[l.source], t = nodeMap[l.target]
    if (!s || !t) return null
    const weightRatio = l.weight / maxWeight
    return {
      ...l,
      x1: s.x, y1: s.y,
      x2: t.x, y2: t.y,
      strokeWidth: 0.8 + weightRatio * 5,
      opacity: 0.15 + weightRatio * 0.7,
      sourceNode: s,
      targetNode: t,
    }
  }).filter(Boolean)

  // 确定哪些 links 应该高亮（hovered 节点的连线）
  const hoveredLinks = new Set()
  if (hoveredNodeWxid.value) {
    links.forEach(l => {
      if (l.source === hoveredNodeWxid.value || l.target === hoveredNodeWxid.value) {
        hoveredLinks.add(l)
      }
    })
  }

  return {
    nodes: positioned,
    links,
    hoveredLinks,
    svgSize: 560,
    cx, cy,
    maxWeight,
    maxMsg,
  }
})

function onNodeEnter(wxid, evt) {
  hoveredNodeWxid.value = wxid
  const nd = networkLayout.value.nodes.find(n => n.wxid === wxid)
  if (nd) {
    networkTooltip.value = {
      x: evt.clientX,
      y: evt.clientY - 50,
      name: nd.name,
      msgCount: nd.msg_count || 0,
      connCount: nd.connDegree,
    }
  }
}
function onNodeLeave() {
  hoveredNodeWxid.value = null
  networkTooltip.value = null
}

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
        <h2 class="text-xl font-bold text-slate-800 flex items-center gap-2">
          <span class="w-8 h-8 rounded-lg bg-gradient-to-br from-purple-100 to-rose-100 flex items-center justify-center">
            <Users class="w-4 h-4 text-purple-500" />
          </span>
          群友画像
        </h2>
        <p class="text-sm text-slate-400 mt-1.5 ml-10">AI 分析生成的成员性格、风格和角色</p>
      </div>
      <div class="flex items-center gap-3">
        <!-- 视图切换 -->
        <div class="flex bg-slate-100 rounded-lg p-0.5">
          <button @click="viewMode='cards'"
            :class="['px-3 py-1.5 text-xs rounded-md transition-all flex items-center gap-1.5 font-medium',
              viewMode==='cards' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400 hover:text-slate-600']">
            <LayoutGrid class="w-3 h-3" />卡片
          </button>
          <button @click="viewMode='network'"
            :class="['px-3 py-1.5 text-xs rounded-md transition-all flex items-center gap-1.5 font-medium',
              viewMode==='network' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400 hover:text-slate-600']">
            <Share2 class="w-3 h-3" />关系
          </button>
        </div>
        <div class="text-xs text-slate-400">
          <span class="font-semibold text-slate-600">{{ portraits.length }}</span> / {{ members.length }} 人
        </div>
        <button
          v-if="members.length > 0"
          @click="analyzeAll"
          :disabled="batchAnalyzing || !!activeTaskId"
          class="flex items-center gap-1.5 px-4 py-2 text-xs font-medium bg-gradient-to-r from-indigo-600 to-purple-600 text-white rounded-xl hover:from-indigo-700 hover:to-purple-700 transition-all disabled:opacity-50 shadow-lg shadow-indigo-200 active:scale-[0.98]"
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
    <div v-if="viewMode === 'network'" class="card p-4 animate-scale-in">
      <!-- 图例 -->
      <div class="flex items-center justify-center gap-6 mb-4 text-[10px] text-slate-400">
        <span class="flex items-center gap-1.5">
          <span class="w-4 h-4 rounded-full bg-indigo-100 border-2 border-indigo-300"></span>
          节点大小 = 发言量
        </span>
        <span class="flex items-center gap-1.5">
          <svg width="24" height="8"><line x1="0" y1="4" x2="24" y2="4" stroke="#6366F1" stroke-width="3" stroke-linecap="round" opacity="0.7"/></svg>
          连线粗细 = 互动强度
        </span>
        <span class="flex items-center gap-1.5">
          <span class="w-3.5 h-3.5 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500"></span>
          内圈 = 核心成员
        </span>
      </div>

      <div v-if="relationsLoading" class="flex flex-col items-center justify-center py-16 gap-3">
        <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
        <p class="text-sm text-slate-400">正在分析群友关系网络...</p>
      </div>
      <div v-else-if="!relationsData?.nodes?.length" class="text-center py-10 text-sm text-slate-400">
        暂无关系数据，请先生成群友画像
      </div>

      <div v-else class="relative" style="max-width: 560px; margin: 0 auto;">
        <svg
          :viewBox="'0 0 ' + networkLayout.svgSize + ' ' + networkLayout.svgSize"
          class="w-full"
          style="background: radial-gradient(circle at center, #F8FAFC 0%, #F1F5F9 100%); border-radius: 16px;"
        >
          <defs>
            <!-- 节点发光滤镜 -->
            <filter v-for="(c, ci) in nodeColors" :key="'glow'+ci" :id="'glow-'+ci" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <!-- 中心光晕 -->
            <radialGradient id="centerGlow">
              <stop offset="0%" stop-color="#6366F1" stop-opacity="0.06" />
              <stop offset="100%" stop-color="#6366F1" stop-opacity="0" />
            </radialGradient>
          </defs>

          <!-- 背景光晕 -->
          <circle :cx="networkLayout.cx" :cy="networkLayout.cy" r="220" fill="url(#centerGlow)" />

          <!-- 内圈参考圆 -->
          <circle :cx="networkLayout.cx" :cy="networkLayout.cy" r="100"
            fill="none" stroke="#E2E8F0" stroke-width="0.5" stroke-dasharray="4 4" opacity="0.5" />

          <!-- ===== 连线层 ===== -->
          <g class="links">
            <line
              v-for="(l, i) in networkLayout.links" :key="'l'+i"
              :x1="l.x1" :y1="l.y1" :x2="l.x2" :y2="l.y2"
              :stroke="l.sourceNode.fill"
              :stroke-width="l.strokeWidth"
              :opacity="networkLayout.hoveredLinks.size === 0 || networkLayout.hoveredLinks.has(l) ? l.opacity : 0.03"
              stroke-linecap="round"
              class="transition-all duration-300"
            />
          </g>

          <!-- ===== 节点层 ===== -->
          <g
            v-for="nd in networkLayout.nodes" :key="nd.wxid"
            class="cursor-pointer transition-all duration-300"
            :class="hoveredNodeWxid && hoveredNodeWxid !== nd.wxid ? 'opacity-30' : ''"
            @mouseenter="onNodeEnter(nd.wxid, $event)"
            @mouseleave="onNodeLeave"
            @click="openDetail({ member_id: nd.id })"
          >
            <!-- 外发光 -->
            <circle
              :cx="nd.x" :cy="nd.y"
              :r="nd.radius + 8"
              :fill="nd.glow"
              opacity="0.12"
            />
            <!-- 主体圆 -->
            <circle
              :cx="nd.x" :cy="nd.y"
              :r="nd.radius"
              :fill="nd.fill"
              :stroke="nd.fill"
              stroke-width="1.5"
              :filter="'url(#glow-'+nd.colorIdx+')'"
            />
            <!-- 内圈高光 -->
            <circle
              :cx="nd.x" :cy="nd.y"
              :r="nd.radius - 4"
              fill="none"
              stroke="white"
              stroke-width="1.5"
              opacity="0.3"
            />
            <!-- 名称 -->
            <text
              :x="nd.x" :y="nd.y + 1"
              text-anchor="middle"
              :font-size="nd.radius > 22 ? 11 : 10"
              font-weight="700"
              fill="white"
              style="pointer-events: none; text-shadow: 0 1px 2px rgba(0,0,0,0.2);"
            >{{ nd.name.slice(0, 5) }}</text>
          </g>
        </svg>

        <!-- 悬浮提示 -->
        <Teleport to="body">
          <div v-if="networkTooltip"
            class="fixed z-50 pointer-events-none bg-slate-800/95 backdrop-blur-sm text-white rounded-xl px-4 py-3 shadow-2xl text-xs animate-scale-in"
            :style="{ left: networkTooltip.x + 'px', top: networkTooltip.y + 'px' }"
          >
            <div class="font-bold text-sm mb-1">{{ networkTooltip.name }}</div>
            <div class="space-y-0.5 text-slate-300">
              <div>💬 {{ networkTooltip.msgCount.toLocaleString() }} 条消息</div>
              <div>🔗 {{ networkTooltip.connCount }} 次互动</div>
            </div>
          </div>
        </Teleport>
      </div>
    </div>

    <!-- 画像卡片网格 -->
    <div v-else class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 stagger">
      <div
        v-for="p in mergedPortraits"
        :key="p.member_id"
        @click="openDetail(p)"
        :class="[
          'card p-4 cursor-pointer hover:border-indigo-200 transition-all group hover:shadow-lg hover:-translate-y-0.5',
          isStale(p.last_updated) && 'ring-1 ring-amber-200',
        ]"
      >
        <!-- 头像 + name -->
        <div class="flex items-center gap-3 mb-3">
          <div class="relative flex-shrink-0">
            <img
              v-if="p.avatar"
              :src="p.avatar"
              :alt="p.display_name"
              class="w-10 h-10 rounded-full bg-slate-100 ring-2 ring-slate-100"
              referrerpolicy="no-referrer"
              @error="$event.target.style.display='none'"
            />
            <div v-else class="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-100 to-purple-100 flex items-center justify-center ring-2 ring-slate-100">
              <User class="w-5 h-5 text-indigo-400" />
            </div>
            <span class="absolute -bottom-0.5 -right-0.5 text-sm leading-none">{{ p.portrait?.emoji_style || '👤' }}</span>
          </div>
          <div class="min-w-0">
            <div class="text-sm font-semibold text-slate-700 truncate">{{ p.display_name }}</div>
            <div v-if="p.remark && p.remark !== p.display_name" class="text-[11px] text-slate-400 truncate">{{ p.remark }}</div>
          </div>
        </div>

        <!-- 最后刷新时间 -->
        <div v-if="p.last_updated" class="flex items-center gap-1 mb-2 text-[10px]" :class="isStale(p.last_updated) ? 'text-amber-500' : 'text-slate-400'">
          <Clock class="w-3 h-3" />
          {{ formatLastUpdated(p.last_updated) }}
          <span v-if="isStale(p.last_updated)" class="text-amber-500 font-medium">· 建议刷新</span>
        </div>

        <!-- 一句话人设 -->
        <p class="text-sm text-slate-600 leading-relaxed mb-3 group-hover:text-indigo-600 transition-colors line-clamp-2">
          {{ p.portrait?.one_line || '点击查看详情 →' }}
        </p>

        <!-- 标签 -->
        <div v-if="p.portrait?.personality" class="flex flex-wrap gap-1 mb-2">
          <span
            v-for="tag in p.portrait.personality.slice(0, 3)"
            :key="tag"
            class="px-2 py-0.5 bg-gradient-to-r from-indigo-50 to-purple-50 text-indigo-600 rounded-full text-[10px] font-medium border border-indigo-100"
          >{{ tag }}</span>
        </div>

        <!-- 年度奖项徽章 -->
        <div v-if="p.awards?.count" class="flex items-center gap-1 mb-2 text-[10px]">
          <span class="flex items-center gap-0.5 bg-gradient-to-r from-amber-50 to-yellow-50 text-amber-700 px-1.5 py-0.5 rounded-full font-medium border border-amber-200">
            🏆 {{ p.awards.count }}项大奖
          </span>
          <span v-if="p.awards.latest?.[0]?.name" class="text-slate-400 truncate">{{ p.awards.latest[0].name }}</span>
        </div>

        <!-- 刷新 -->
        <div class="flex items-center justify-end">
          <button
            @click.stop="refreshOne(p.member_id)"
            :disabled="refreshing === p.member_id || !!activeTaskId"
            :class="[
              'p-1.5 rounded-lg transition-all',
              isStale(p.last_updated) ? 'text-amber-400 hover:text-amber-600 hover:bg-amber-50' : 'text-slate-300 hover:text-indigo-500 hover:bg-indigo-50',
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
        class="card p-4 flex flex-col items-center justify-center text-center gap-2.5 min-h-[180px] border-dashed border-2 border-slate-200 bg-slate-50/50 hover:border-indigo-200 hover:bg-indigo-50/30 transition-all group"
      >
        <div class="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center group-hover:bg-indigo-100 transition-colors">
          <User class="w-6 h-6 text-slate-300 group-hover:text-indigo-400 transition-colors" />
        </div>
        <div>
          <div class="text-sm font-medium text-slate-500">{{ m.display_name }}</div>
          <div class="text-xs text-slate-400">{{ m.message_count }} 条消息</div>
        </div>
        <button
          @click="generateOne(m.id)"
          :disabled="refreshing === m.id || !!activeTaskId"
          class="mt-1 px-3 py-1.5 text-xs font-medium text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors flex items-center gap-1.5 border border-indigo-200 hover:border-indigo-300"
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
