<script setup>
import { ref, computed, inject, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { getPortraits, analyzePortrait, analyzeAllPortraits, getMembers, getRelations, getPersonas, getCrossGroupWxids, autoLinkPersonas, manualLinkMembers, listGroups, analyzeComprehensivePortrait } from '../api/index.js'
import { Loader2, Sparkles, RefreshCw, User, Zap, Clock, Share2, LayoutGrid, Users, Link2, ArrowRight, Plus, Search, X } from 'lucide-vue-next'
const router = useRouter()
const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')
const activeTaskId = inject('activeTaskId')

const portraits = ref([])
const members = ref([])
const loading = ref(false)
const activeTab = ref('members')  // v1.5.0: 'members' | 'cross'

// v1.5.0: 跨群身份
const personas = ref([])
const crossGroupList = ref([])
const crossLoading = ref(false)

async function loadCrossGroup() {
  if (crossLoading.value) return
  crossLoading.value = true
  try {
    const [p, c] = await Promise.all([
      getPersonas().catch(() => []),
      getCrossGroupWxids().catch(() => []),
    ])
    personas.value = p
    crossGroupList.value = c
  } catch (e) { /* ignore */ }
  finally { crossLoading.value = false }
}

function platformLabel(platform, wxid) {
  if (platform === 'wechat') return '微信'
  if (platform === 'qq') return 'QQ'
  if (wxid?.startsWith('wxid_')) return '微信'
  if (wxid?.startsWith('u_') && !wxid?.includes('@chatroom')) return 'QQ'
  return '未知'
}

async function doAutoLink() {
  try {
    await autoLinkPersonas()
    await loadCrossGroup()
  } catch (e) { console.error(e) }
}

async function doComprehensivePortrait(personaId) {
  if (activeTaskId.value) return
  try {
    const result = await analyzeComprehensivePortrait(personaId)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    }
  } catch (e) { console.error(e) }
}

// v1.5.0: 手动关联弹窗
const showManualLink = ref(false)
const linkGroups = ref([])
const linkGroupA = ref(null)
const linkGroupB = ref(null)
const linkMembersA = ref([])
const linkMembersB = ref([])
const linkMemberA = ref(null)
const linkMemberB = ref(null)
const linkLoading = ref(false)
const linkError = ref('')

async function openManualLink() {
  linkError.value = ''
  linkMemberA.value = null
  linkMemberB.value = null
  linkMembersA.value = []
  linkMembersB.value = []
  try {
    linkGroups.value = await listGroups()
  } catch (e) { linkGroups.value = [] }
  showManualLink.value = true
}

async function onLinkGroupChange(side) {
  const gid = side === 'A' ? linkGroupA.value : linkGroupB.value
  try {
    const members = gid ? await getMembers(Number(gid)) : []
    if (side === 'A') linkMembersA.value = members
    else linkMembersB.value = members
  } catch (e) {
    if (side === 'A') linkMembersA.value = []
    else linkMembersB.value = []
  }
}

async function doManualLink() {
  if (!linkMemberA.value || !linkMemberB.value) {
    linkError.value = '请选择两个成员'
    return
  }
  if (linkMemberA.value === linkMemberB.value) {
    linkError.value = '不能关联同一个成员'
    return
  }
  linkLoading.value = true
  linkError.value = ''
  try {
    await manualLinkMembers(Number(linkMemberA.value), Number(linkMemberB.value))
    showManualLink.value = false
    await loadCrossGroup()
  } catch (e) {
    linkError.value = e.message || '关联失败'
  } finally {
    linkLoading.value = false
  }
}

const refreshing = ref(null)      // 单个刷新的 memberId
const viewMode = ref('cards')     // 'cards' | 'network'
const batchAnalyzing = ref(false)
// v0.12.2: 画像模型选择
function getPortraitModelId() {
  const v = localStorage.getItem('portraitModelId')
  if (v === null || v === '') return null
  const n = Number(v)
  return isNaN(n) ? null : n
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
watch(activeTab, (tab) => { if (tab === 'cross') loadCrossGroup() })

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
    loadCrossGroup()  // v1.5.2: 任务完成后刷新跨群数据
    triggerRefresh?.()
  }
  if (newVal && !oldVal) {
    // v1.5.12: 提高到 30s 默认间隔，减少长时间运行时的磁盘 I/O 压力
    const interval = Math.max(5000, parseInt(localStorage.getItem('poll_interval_portraits_ms')) || 30000)
    _refreshTimer = setInterval(() => load(true), interval)
  }
})
onUnmounted(() => { if (_refreshTimer) clearInterval(_refreshTimer) })

function openDetail(portrait) {
  router.push(`/portrait/${portrait.member_id}`)
}

// 合并 portraits 和 members
const mergedPortraits = ref([])
watch([portraits, members], ([p, m]) => {
  mergedPortraits.value = p
    .map(pt => {
      const member = m.find(mb => mb.id === pt.member_id)
      return member ? { ...pt, ...member } : null
    })
    .filter(Boolean)
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
    <!-- v1.5.0: Tab 切换栏 -->
    <div class="flex items-center justify-between mb-4">
      <div class="flex bg-slate-100 rounded-lg p-0.5">
        <button @click="activeTab='members'"
          :class="['flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all',
            activeTab==='members' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400 hover:text-slate-600']">
          <Users class="w-4 h-4" />本群画像
        </button>
        <button @click="activeTab='cross'"
          :class="['flex items-center gap-1.5 px-4 py-2 rounded-md text-sm font-medium transition-all',
            activeTab==='cross' ? 'bg-white text-slate-700 shadow-sm' : 'text-slate-400 hover:text-slate-600']">
          <Link2 class="w-4 h-4" />跨群身份
        </button>
      </div>
    </div>

    <!-- 跨群身份内容 -->
    <div v-if="activeTab==='cross'">
      <div v-if="crossLoading" class="flex items-center justify-center py-16">
        <Loader2 class="w-6 h-6 animate-spin text-indigo-400" />
      </div>
      <div v-else-if="!personas.length && !crossGroupList.length" class="text-center py-16">
        <Users class="w-12 h-12 text-slate-200 mx-auto mb-3" />
        <p class="text-sm text-slate-500 mb-2">暂无跨群身份</p>
        <p class="text-xs text-slate-400 mb-4">同一个 wxid 出现在多个群时会自动发现</p>
        <div class="flex items-center justify-center gap-3">
          <button @click="doAutoLink"
                  class="text-sm text-indigo-500 hover:text-indigo-600 font-medium">
            扫描自动关联
          </button>
          <span class="text-slate-300">|</span>
          <button @click="openManualLink"
                  class="text-sm text-indigo-500 hover:text-indigo-600 font-medium flex items-center gap-1">
            <Plus class="w-3.5 h-3.5" />手动关联
          </button>
        </div>
      </div>
      <div v-else class="space-y-4">
        <!-- 已关联 Personas -->
        <div v-if="personas.length" class="card p-4">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
              <Link2 class="w-4 h-4 text-amber-500" />已关联身份 ({{ personas.length }})
            </h3>
            <button @click="openManualLink"
                    class="text-xs text-indigo-500 hover:text-indigo-600 font-medium flex items-center gap-1">
              <Plus class="w-3 h-3" />手动关联
            </button>
          </div>
          <div class="space-y-3">
            <div v-for="p in personas" :key="p.id" class="bg-slate-50 rounded-lg p-3">
              <div class="flex items-center gap-2 mb-2">
                <span class="text-sm font-medium text-slate-700">{{ p.name || '未命名' }}</span>
                <span class="text-xs text-slate-400">{{ p.member_count }} 个身份</span>
              </div>
              <div class="space-y-1.5">
                <div v-for="m in p.members" :key="m.id"
                     class="flex items-center justify-between bg-white rounded-md px-3 py-2 hover:bg-indigo-50 transition-colors cursor-pointer"
                     @click="$router.push(`/portrait/${m.id}?group_id=${m.group_id}`)">
                  <span class="text-sm text-slate-700">{{ m.display_name }} <span class="text-xs text-slate-400">({{ m.id }})</span></span>
                  <span class="text-[11px] px-1.5 py-0.5 rounded-full"
                    :class="platformLabel(m.platform, m.wxid) === '微信' ? 'bg-green-50 text-green-600' : platformLabel(m.platform, m.wxid) === 'QQ' ? 'bg-blue-50 text-blue-600' : 'bg-slate-100 text-slate-500'">
                    {{ platformLabel(m.platform, m.wxid) }}
                  </span>
                </div>
              </div>
              <!-- v1.5.2: 全面画像 -->
              <div v-if="p.comprehensive_portrait" class="mt-3 bg-white rounded-lg p-3 border border-indigo-100 cursor-pointer hover:border-indigo-300 transition-colors"
                   @click="$router.push(`/comprehensive/${p.id}?group_id=${currentGroup?.id}`)">
                <div class="flex items-center gap-1.5 mb-1.5">
                  <Sparkles class="w-3.5 h-3.5 text-indigo-500" />
                  <span class="text-xs font-medium text-indigo-600">全面画像</span>
                  <span class="text-[10px] text-indigo-400 ml-auto">查看 →</span>
                </div>
                <p class="text-sm text-slate-700 font-medium">{{ p.comprehensive_portrait.unified_oneline }}</p>
                <p class="text-xs text-slate-500 mt-0.5 line-clamp-2">{{ p.comprehensive_portrait.core_personality }}</p>
              </div>
              <button v-else-if="p.member_count >= 2" @click="doComprehensivePortrait(p.id)"
                      class="mt-2 text-xs text-indigo-500 hover:text-indigo-600 font-medium flex items-center gap-1">
                <Sparkles class="w-3 h-3" />生成全面画像
              </button>
            </div>
          </div>
        </div>
        <!-- 自动发现的跨群 wxid -->
        <div v-if="crossGroupList.length" class="card p-4">
          <h3 class="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-1.5">
            <Users class="w-4 h-4 text-indigo-500" />自动发现 ({{ crossGroupList.length }})
          </h3>
          <div class="space-y-2">
            <div v-for="item in crossGroupList" :key="item.wxid"
                 class="flex items-center justify-between p-3 bg-slate-50 rounded-lg hover:bg-indigo-50 transition-colors">
              <div>
                <div class="text-sm font-medium text-slate-700">{{ item.names }}</div>
                <div class="text-xs text-slate-400">{{ item.groups }} · {{ item.group_cnt }} 个群</div>
              </div>
              <span class="text-[11px] px-1.5 py-0.5 rounded-full"
                :class="platformLabel('', item.wxid) === '微信' ? 'bg-green-50 text-green-600' : platformLabel('', item.wxid) === 'QQ' ? 'bg-blue-50 text-blue-600' : 'bg-slate-100 text-slate-500'">
                {{ platformLabel('', item.wxid) }}
              </span>
            </div>
          </div>
          <button v-if="crossGroupList.length && !personas.length"
                  @click="doAutoLink"
                  class="mt-3 text-sm text-indigo-500 hover:text-indigo-600 font-medium">
            一键关联所有
          </button>
        </div>
      </div>
    </div>

    <!-- 本群画像内容 -->
    <div v-if="activeTab==='members'">
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

    <!-- v0.13.2: 错误状态 -->
    <div v-else-if="error" class="card p-8 text-center">
      <p class="text-red-400 mb-2">加载失败：{{ error }}</p>
      <button @click="load()" class="text-sm text-indigo-500 hover:text-indigo-600">重试</button>
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
  </div><!-- /members tab -->

  <!-- v1.5.0: 手动关联弹窗 -->
  <Teleport to="body">
    <div v-if="showManualLink" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
         @click.self="showManualLink = false">
      <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6 space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-lg font-semibold text-slate-800 flex items-center gap-2">
            <Link2 class="w-5 h-5 text-indigo-500" />手动关联身份
          </h3>
          <button @click="showManualLink = false" class="text-slate-400 hover:text-slate-600">
            <X class="w-5 h-5" />
          </button>
        </div>
        <p class="text-xs text-slate-500">将不同平台（微信/QQ）或不同群的同一人关联起来</p>

        <!-- 选择 A -->
        <div class="space-y-2">
          <label class="text-xs font-medium text-slate-600">身份 A</label>
          <select v-model="linkGroupA" @change="onLinkGroupChange('A'); linkMemberA = null"
                  class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none">
            <option :value="null">选择群...</option>
            <option v-for="g in linkGroups" :key="g.id" :value="g.id">{{ g.name || g.display_name }}</option>
          </select>
          <select v-model="linkMemberA" v-if="linkMembersA.length"
                  class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none">
            <option :value="null">选择成员...</option>
            <option v-for="m in linkMembersA" :key="m.id" :value="m.id">{{ m.display_name || m.wxid }} ({{ m.id }})</option>
          </select>
        </div>

        <!-- 选择 B -->
        <div class="space-y-2">
          <label class="text-xs font-medium text-slate-600">身份 B</label>
          <select v-model="linkGroupB" @change="onLinkGroupChange('B'); linkMemberB = null"
                  class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none">
            <option :value="null">选择群...</option>
            <option v-for="g in linkGroups" :key="g.id" :value="g.id">{{ g.name || g.display_name }}</option>
          </select>
          <select v-model="linkMemberB" v-if="linkMembersB.length"
                  class="w-full px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 outline-none">
            <option :value="null">选择成员...</option>
            <option v-for="m in linkMembersB" :key="m.id" :value="m.id">{{ m.display_name || m.wxid }} ({{ m.id }})</option>
          </select>
        </div>

        <div v-if="linkError" class="text-xs text-red-500 bg-red-50 rounded-lg px-3 py-2">{{ linkError }}</div>

        <div class="flex gap-2 pt-2">
          <button @click="showManualLink = false"
                  class="flex-1 py-2 text-sm text-slate-600 border border-slate-200 rounded-lg hover:bg-slate-50 transition-colors">
            取消
          </button>
          <button @click="doManualLink" :disabled="linkLoading || !linkMemberA || !linkMemberB"
                  class="flex-1 py-2 text-sm text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-1.5">
            <Loader2 v-if="linkLoading" class="w-3.5 h-3.5 animate-spin" />
            <Link2 v-else class="w-3.5 h-3.5" />
            确认关联
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
