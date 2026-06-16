<script setup>
import { ref, inject, watch, computed, onUnmounted } from 'vue'
import { getFishPond, adoptFish, settleFishPond, feedFish, batchAdopt,
         touchFish, exploreFish, showoffFish, trainFish, battleFish, deleteFish,
         renameFish, parseFishCommands, getFishDetail, getFishLeaderboard,
         getAppSettings }
  from '../api/index.js'
import FishTank from '../components/FishTank.vue'
import FishCard from '../components/FishCard.vue'
import FishLeaderboard from '../components/FishLeaderboard.vue'
import ChatSimulator from '../components/ChatSimulator.vue'
import PondEventTimeline from '../components/PondEventTimeline.vue'
import PondManagement from './PondManagement.vue'
import { Fish, RefreshCw, X, BookOpen, Clock, Crown, Anchor, Sparkles } from 'lucide-vue-next'

const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')
const showError = inject('showError')

const pondState = ref(null)
const loading = ref(false)
const selectedFish = ref(null)
const showCard = ref(false)
const actionLoading = ref('')
const leaderboardSort = ref('growth')
const parseLog = ref(null)
const showParseLog = ref(false)
const showTutorial = ref(false)
const tutorialTab = ref('basics')
const tutorialTabs = [
  { key: 'basics', icon: '🐟', label: '鱼塘教程' },
  { key: 'd20', icon: '🎲', label: 'D20系统' },
  { key: 'commands', icon: '📋', label: '指令参考' },
  { key: 'cheat', icon: '🎮', label: '作弊模式' },
]
// v1.16.5: 作弊模式
const cheatMode = ref(false)
async function loadCheatMode() {
  try {
    const settings = await getAppSettings()
    if (!Array.isArray(settings)) return
    const s = settings.find(s => s.key === 'pond_cheat_mode')
    if (s) cheatMode.value = s.value === 'true'
  } catch {}
}
const activeTab = ref('events')
let _pondRefreshTimer = null

const gid = computed(() => currentGroup.value?.id)

// v1.16.2: auto-refresh when silent pond is enabled
watch(() => pondState.value?.auto_events_enabled, (enabled) => {
  if (_pondRefreshTimer) { clearInterval(_pondRefreshTimer); _pondRefreshTimer = null }
  if (enabled) {
    _pondRefreshTimer = setInterval(() => loadPond(true), 60000)
  }
})
onUnmounted(() => { if (_pondRefreshTimer) clearInterval(_pondRefreshTimer) })

watch(() => gid.value, () => { loadPond(); loadCheatMode() }, { immediate: true })

async function loadPond(silent) {
  if (!gid.value) return
  if (!silent) loading.value = true
  try {
    pondState.value = await getFishPond(gid.value)
  } catch (e) {
    console.error('Failed to load pond:', e)
    pondState.value = null
  } finally { loading.value = false }
}

async function handleSettle() {
  actionLoading.value = 'settle'
  try {
    await settleFishPond(gid.value)
    await loadPond()
  } catch (e) { console.error(e) }
  finally { actionLoading.value = '' }
}

async function handleParseCommands() {
  actionLoading.value = 'parse'
  try {
    const result = await parseFishCommands(gid.value)
    parseLog.value = result
    showParseLog.value = true
    await loadPond()
  } catch (e) { showError('指令解析失败', e.message) }
  finally { actionLoading.value = '' }
}

async function handleAdopt(wxid, displayName) {
  try {
    await adoptFish(gid.value, wxid, displayName)
    await loadPond()
  } catch (e) { showError('领养失败', e.message) }
}

const showBatchConfirm = ref(false)
const batchLoading = ref(false)
async function handleBatchAdopt() {
  showBatchConfirm.value = false
  batchLoading.value = true
  try {
    await batchAdopt(gid.value)
    await loadPond()
  } catch (e) { showError('一键领养失败', e.message) }
  finally { batchLoading.value = false }
}

function handleFishClick(fish) {
  selectedFish.value = fish
  showCard.value = true
}

async function handleFishAction(action, wxid, extra) {
  actionLoading.value = action
  try {
    switch (action) {
      case 'feed': await feedFish(gid.value, wxid); break
      case 'touch': await touchFish(gid.value, wxid); break
      case 'explore': await exploreFish(gid.value, wxid); break
      case 'showoff': await showoffFish(gid.value, wxid); break
      case 'train': await trainFish(gid.value, wxid, extra); break
      case 'rename': await renameFish(gid.value, wxid, extra); break
      case 'battle': await battleFish(gid.value, wxid, extra); break
      case 'delete':
        await deleteFish(gid.value, wxid)
        showCard.value = false; selectedFish.value = null
        break
    }
    if (showCard.value && selectedFish.value?.wxid === wxid) {
      const detail = await getFishDetail(gid.value, wxid)
      selectedFish.value = { ...selectedFish.value, ...detail.fish }
    }
    await loadPond()
  } catch (e) { showError('操作失败', e.message) }
  finally { actionLoading.value = '' }
}

const aliveFish = computed(() =>
  pondState.value?.fish?.filter(f => f.is_alive) || []
)
const deadFish = computed(() =>
  pondState.value?.fish?.filter(f => !f.is_alive) || []
)
const weather = computed(() => pondState.value?.weather)
const season = computed(() => pondState.value?.season)
const recentEvents = computed(() => pondState.value?.recent_events || [])

const tabs = [
  { key: 'events', icon: Clock, label: '事件线', desc: '今日鱼塘动态' },
  { key: 'leaderboard', icon: Crown, label: '排行榜', desc: '最强鱼儿角逐' },
  { key: 'management', icon: Anchor, label: '管理', desc: '升级·决议·称号' },
]

// Weather display config
const weatherConfig = {
  sunny:  { emoji: '☀️', label: '晴天', bg: 'from-amber-400/20 via-yellow-400/10 to-transparent', border: 'border-amber-300/40', text: 'text-amber-700' },
  rain:   { emoji: '🌧️', label: '雨天', bg: 'from-blue-400/20 via-indigo-400/10 to-transparent', border: 'border-blue-300/40', text: 'text-blue-700' },
  storm:  { emoji: '⛈️', label: '暴风雨', bg: 'from-slate-500/25 via-gray-400/15 to-transparent', border: 'border-slate-400/40', text: 'text-slate-700' },
  rainbow:{ emoji: '🌈', label: '彩虹', bg: 'from-pink-400/15 via-purple-400/10 to-transparent', border: 'border-pink-300/40', text: 'text-pink-700' },
}
</script>

<template>
  <div class="pond-page">
    <!-- ===== Header ===== -->
    <header class="pond-header">
      <div class="flex items-center gap-3">
        <div class="pond-brand-icon">
          <Fish :size="18" class="text-white" />
        </div>
        <div>
          <h1 class="text-lg font-bold text-slate-800 tracking-tight">群鱼塘</h1>
          <p v-if="pondState" class="text-xs text-slate-400">
            {{ pondState.alive_count }} 条活鱼 · {{ pondState.dead_count }} 条亡鱼
          </p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button @click="showTutorial = true"
          class="pond-btn pond-btn-ghost">
          <BookOpen :size="15" />
          <span class="hidden sm:inline">教程</span>
        </button>
      </div>
    </header>

    <!-- ===== Loading ===== -->
    <div v-if="loading" class="flex flex-col items-center justify-center py-32 text-slate-400">
      <div class="relative mb-4">
        <RefreshCw :size="48" class="animate-spin text-slate-300" />
        <span class="absolute inset-0 flex items-center justify-center text-xl">🐟</span>
      </div>
      <p class="text-sm font-medium">正在潜入鱼塘...</p>
    </div>

    <!-- ===== Empty State ===== -->
    <div v-else-if="!pondState || pondState.alive_count === 0" class="pond-empty">
      <div class="empty-illustration">
        <span class="text-8xl block mb-4">🐟</span>
        <div class="empty-ripple"></div>
      </div>
      <h2 class="text-xl font-bold text-slate-600 mb-1">鱼塘里还没有鱼</h2>
      <p class="text-slate-400 text-sm max-w-sm mx-auto mb-8">
        为所有群成员自动领养第一条鱼，或使用右下角<strong>指令模拟器</strong>逐个测试
      </p>
      <div v-if="!showBatchConfirm" class="flex items-center justify-center gap-3">
        <button @click="showBatchConfirm = true" :disabled="batchLoading"
          class="pond-btn pond-btn-primary px-6 py-3 text-base">
          🎁 {{ batchLoading ? '领养中...' : '一键领养' }}
        </button>
        <button @click="showTutorial = true"
          class="pond-btn pond-btn-ghost px-6 py-3 text-base">
          <BookOpen :size="18" /> 教程
        </button>
      </div>
      <div v-else class="flex flex-col items-center gap-3">
        <p class="text-sm text-slate-600">确定要为所有无鱼成员自动领养吗？</p>
        <div class="flex items-center gap-2">
          <button @click="handleBatchAdopt" :disabled="batchLoading"
            class="px-4 py-2 rounded-lg text-sm font-medium bg-sky-500 text-white hover:bg-sky-600 transition">
            {{ batchLoading ? '领养中...' : '确认' }}
          </button>
          <button @click="showBatchConfirm = false"
            class="px-4 py-2 rounded-lg text-sm border border-slate-200 text-slate-500 hover:bg-slate-50 transition">
            取消
          </button>
        </div>
      </div>
    </div>

    <!-- ===== Main Content ===== -->
    <template v-else>
      <!-- Hero Tank -->
      <section class="tank-hero">
        <!-- Weather pill overlay -->
        <div v-if="weather" class="weather-pill"
          :class="[
            weatherConfig[weather.type]?.border || 'border-slate-300/40',
            weatherConfig[weather.type]?.text || 'text-slate-600',
          ]">
          <span class="text-xl">{{ weatherConfig[weather.type]?.emoji || weather.emoji }}</span>
          <div>
            <div class="font-semibold text-sm leading-tight">{{ weather.name }}</div>
            <div class="text-[11px] opacity-70 leading-tight">{{ weather.effect }}</div>
          </div>
        </div>

        <FishTank
          :fish="aliveFish"
          :dead-fish="deadFish"
          :weather="weather"
          :season="season"
          @fish-click="handleFishClick"
          @adopt="handleAdopt"
        />
      </section>

      <!-- Dashboard Tabs -->
      <section class="pond-dashboard card">
        <!-- Tab nav -->
        <nav class="dashboard-tabs">
          <button
            v-for="tab in tabs" :key="tab.key"
            @click="activeTab = tab.key"
            :class="['dashboard-tab', activeTab === tab.key ? 'active' : '']"
            :title="tab.desc">
            <component :is="tab.icon" :size="15" />
            <span>{{ tab.label }}</span>
          </button>
        </nav>

        <!-- Tab content -->
        <div class="dashboard-content">
          <div v-if="activeTab === 'events'" class="animate-fade-in">
            <div class="tab-section-header">
              <Sparkles :size="14" class="text-indigo-400" />
              <span>今日事件流</span>
            </div>
            <PondEventTimeline :events="recentEvents" />
          </div>

          <div v-else-if="activeTab === 'leaderboard'" class="animate-fade-in">
            <FishLeaderboard
              :fish="aliveFish"
              :sort="leaderboardSort"
              @update:sort="leaderboardSort = $event"
              @fish-click="handleFishClick"
            />
          </div>

          <div v-else-if="activeTab === 'management'" class="animate-fade-in">
            <PondManagement @pond-refresh="loadPond" />
          </div>
        </div>
      </section>

    </template>

    <!-- Floating Chat Simulator — fixed bottom-right, always on top -->
    <Teleport to="body">
      <ChatSimulator v-if="cheatMode" @pond-refresh="loadPond" />
    </Teleport>

    <!-- ===== Fish Card Modal ===== -->
    <Teleport to="body">
      <FishCard
        v-if="showCard && selectedFish"
        :fish="selectedFish"
        :loading="actionLoading"
        :group-id="gid"
        @close="showCard = false"
        @action="handleFishAction"
        @refresh="loadPond"
      />
    </Teleport>

    <!-- ===== Parse Log Modal ===== -->
    <Teleport to="body">
      <div v-if="showParseLog && parseLog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        @click.self="showParseLog = false">
        <div class="bg-white rounded-2xl shadow-2xl w-[600px] max-h-[80vh] flex flex-col overflow-hidden animate-scale-in">
          <div class="flex items-center justify-between px-5 py-3 border-b border-slate-100">
            <div>
              <h2 class="font-bold text-slate-800">📋 今日解析日志</h2>
              <p class="text-xs text-slate-400 mt-0.5">
                {{ parseLog.today }} · 找到 {{ parseLog.commands_found }} 条指令 ·
                处理 {{ parseLog.events_processed }} 条 ·
                {{ parseLog.settle?.weather?.emoji || '' }} {{ parseLog.settle?.weather?.name || '' }}
              </p>
            </div>
            <button @click="showParseLog = false" class="p-1 hover:bg-slate-100 rounded text-slate-400">
              <X :size="18" />
            </button>
          </div>
          <div class="flex-1 overflow-y-auto px-5 py-3 space-y-2">
            <div v-if="parseLog.log.length === 0" class="text-center py-8 text-slate-400 text-sm">
              今天没有 / 开头的鱼塘指令
            </div>
            <div v-for="(entry, i) in parseLog.log" :key="i"
              class="border border-slate-100 rounded-lg p-3 text-xs"
              :class="{
                'bg-red-50/50 border-red-100': entry.error,
                'bg-green-50/50 border-green-100': entry.type === 'adopt',
                'bg-white': !entry.error && entry.type !== 'adopt',
              }">
              <div class="flex items-center justify-between mb-1.5">
                <div class="flex items-center gap-2">
                  <span class="text-slate-400 font-mono">{{ entry.time?.slice(11, 16) || '--:--' }}</span>
                  <span class="font-medium text-slate-700">{{ entry.sender || entry.wxid?.slice(0, 12) || '?' }}</span>
                </div>
                <span v-if="entry.type !== 'error'" class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                  :class="{
                    'bg-green-100 text-green-700': entry.type === 'adopt' || entry.type === 'evolve',
                    'bg-sky-100 text-sky-700': entry.type === 'feed',
                    'bg-teal-100 text-teal-700': entry.type === 'clean',
                    'bg-pink-100 text-pink-700': entry.type === 'touch',
                    'bg-amber-100 text-amber-700': entry.type === 'explore',
                    'bg-yellow-100 text-yellow-700': entry.type === 'treasure',
                    'bg-purple-100 text-purple-700': entry.type === 'showoff',
                    'bg-red-100 text-red-700': entry.type === 'battle',
                    'bg-slate-100 text-slate-600': true,
                  }">{{ {adopt:'领养',feed:'喂食',clean:'换水',touch:'摸鱼',explore:'探索',
                          treasure:'寻宝',showoff:'晒鱼',battle:'斗鱼',rename:'改名',pond:'鱼塘'
                         }[entry.type] || entry.type }}</span>
              </div>
              <div class="font-mono text-slate-600 mb-1">{{ entry.command }}</div>
              <div v-if="entry.error" class="text-red-600">❌ {{ entry.error }}</div>
              <div v-if="entry.d20" class="flex items-center gap-2 text-[10px]">
                <span class="font-mono font-bold"
                  :class="{
                    'text-amber-700': entry.d20.success && !entry.d20.critical_hit,
                    'text-yellow-600': entry.d20.critical_hit,
                    'text-red-500': !entry.d20.success,
                  }">
                  d20({{ entry.d20.roll }})+{{ entry.d20.modifier }}={{ entry.d20.total }}
                  vs DC{{ entry.d20.dc }}
                </span>
                <span :class="entry.d20.success ? 'text-green-600' : 'text-red-500'">
                  {{ entry.d20.critical_hit ? '🎉大成功!' : entry.d20.critical_miss ? '💀大失败!' : entry.d20.success ? '✅成功' : '❌失败' }}
                </span>
              </div>
              <div v-if="entry.growth || entry.happiness || entry.coin_amount" class="flex flex-wrap gap-1 mt-1">
                <span v-if="entry.growth" class="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[10px]">成长+{{ entry.growth }}</span>
                <span v-if="entry.happiness" class="px-1.5 py-0.5 rounded bg-pink-50 text-pink-700 text-[10px]">幸福+{{ entry.happiness }}</span>
                <span v-if="entry.coin_amount" class="px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 text-[10px]">鳞币+{{ entry.coin_amount }}</span>
                <span v-if="entry.evolved" class="px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 text-[10px]">进化→{{ entry.new_stage }}</span>
              </div>
              <div v-if="entry.fish" class="text-green-700 mt-1">🐟 {{ entry.fish.name }} ({{ entry.fish.rarity }})</div>
              <div v-if="entry.battle_winner" class="text-xs mt-1"
                :class="entry.battle_winner === entry.wxid ? 'text-green-600' : 'text-red-500'">
                ⚔️ {{ entry.battle_winner === entry.wxid ? '胜!' : '败...' }}
              </div>
            </div>
          </div>
          <div class="px-5 py-3 border-t border-slate-100 flex justify-between items-center">
            <span class="text-xs text-slate-400">
              {{ parseLog.settle?.fish_count || 0 }} 条鱼已结算 ·
              {{ parseLog.settle?.weather?.emoji || '' }} {{ parseLog.settle?.weather?.effect || '' }}
            </span>
            <div class="flex gap-2">
              <a :href="parseLog.report_url" @click="showParseLog = false"
                class="px-3 py-1.5 text-sm border border-indigo-200 text-indigo-600 rounded-lg
                       hover:bg-indigo-50 transition font-medium">
                📰 查看日报
              </a>
              <button @click="showParseLog = false"
                class="px-4 py-1.5 bg-slate-800 text-white text-sm rounded-lg hover:bg-slate-700 transition">
                关闭
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ===== Tutorial Modal (v1.16.5: 分栏布局) ===== -->
    <Teleport to="body">
      <div v-if="showTutorial" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        @click.self="showTutorial = false">
        <div class="bg-white rounded-2xl shadow-2xl w-[720px] max-h-[80vh] animate-scale-in flex flex-col">
          <div class="px-5 py-4 border-b border-slate-100 flex items-center justify-between shrink-0">
            <h2 class="font-bold text-slate-800 text-lg">🐟 群鱼塘教程</h2>
            <button @click="showTutorial = false" class="p-1 hover:bg-slate-100 rounded text-slate-400"><X :size="18" /></button>
          </div>
          <div class="flex flex-1 min-h-0">
            <!-- Left Nav -->
            <div class="w-32 shrink-0 border-r border-slate-100 py-3 px-2 space-y-1 bg-slate-50/50">
              <button v-for="tab in tutorialTabs" :key="tab.key"
                @click="tutorialTab = tab.key"
                :class="['w-full text-left px-3 py-2 rounded-lg text-xs font-medium transition',
                  tutorialTab === tab.key ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-400 hover:text-slate-600']">
                {{ tab.icon }} {{ tab.label }}
              </button>
            </div>
            <!-- Right Content -->
            <div class="flex-1 overflow-y-auto px-5 py-4 text-sm text-slate-600">
              <!-- 🐟 鱼塘教程 -->
              <div v-if="tutorialTab === 'basics'" class="space-y-4">
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">基本概念</h3>
                  <p>基于群聊活跃度的养鱼游戏。群成员各拥有一条鱼，发言活跃度驱动成长。</p>
                </div>
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">养成系统</h3>
                  <p>鱼有六维属性（STR/DEX/CON/INT/WIS/CHA）、成长阶段（鱼苗→幼鱼→成鱼→大鱼→传说）和稀有度（普通/稀有/史诗/传说）。通过指令互动获得经验和成长值。</p>
                </div>
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">互动指令</h3>
                  <p>/领养 /喂食 /摸鱼 /探索 /晒鱼 /训练 /斗鱼 /购买 /赠予 /道具 /改名。每条指令对应一次D20检定，成功与否取决于鱼的相关属性。</p>
                </div>
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">每日结算</h3>
                  <p>每天首次触发时自动结算：自动喂食活跃成员、应用天气和季节效果、检测鲨鱼袭击。结算产生黑市道具供购买。</p>
                </div>
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">鱼塘自动化</h3>
                  <p>在设置→鱼塘设置中开启后，鱼塘将按固定间隔自动触发被动事件（鲨鱼、宝藏、竞速等），无需手动操作。</p>
                </div>
              </div>
              <!-- 🎲 D20系统 -->
              <div v-else-if="tutorialTab === 'd20'" class="space-y-4">
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">六维属性</h3>
                  <p>💪力量(STR) 🏃敏捷(DEX) ❤️体质(CON) 🧠智力(INT) 👁️感知(WIS) 💋魅力(CHA)。每种指令使用不同属性检定。</p>
                </div>
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">检定机制</h3>
                  <p>掷D20 + 属性修正 + 熟练加值 vs DC（难度等级）。达到DC即成功。属性的正修正值越大，成功率越高。</p>
                </div>
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">熟练项</h3>
                  <p>每种鱼有专属熟练项（如运动、表演、隐匿），涉及熟练技能的检定额外加上等级对应的熟练加值。</p>
                </div>
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">性格修正</h3>
                  <p>鱼的性格标签（勇敢、好奇等22种）会在特定检定中提供优势/劣势或属性修正。例如勇敢的鱼面对鲨鱼时检定优势。</p>
                </div>
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">大成功/大失败</h3>
                  <p>掷出20为大成功，效果翻倍。掷出1为大失败，效果减半。不受修正影响，只看骰面。</p>
                </div>
              </div>
              <!-- 📋 指令参考 -->
              <div v-else-if="tutorialTab === 'commands'" class="space-y-1.5">
                <div v-for="cmd in [
                  {c:'/领养',d:'随机品种+稀有度+属性',cl:'bg-green-50 text-green-700 border-green-200'},
                  {c:'/喂食',d:'DEX检定·+成长+幸福·每日3次',cl:'bg-sky-50 text-sky-700 border-sky-200'},
                  {c:'/摸鱼',d:'CHA检定·+亲密度·每日5次',cl:'bg-pink-50 text-pink-700 border-pink-200'},
                  {c:'/探索',d:'WIS/INT检定·获得鳞币·每日3次',cl:'bg-amber-50 text-amber-700 border-amber-200'},
                  {c:'/晒鱼',d:'CHA检定·观众打赏·每日3次',cl:'bg-purple-50 text-purple-700 border-purple-200'},
                  {c:'/购买 商品名',d:'从黑市抢购道具',cl:'bg-cyan-50 text-cyan-700 border-cyan-200'},
                  {c:'/赠予 @XX 道具',d:'送道具给群友',cl:'bg-pink-50 text-pink-700 border-pink-200'},
                  {c:'/道具 库存',d:'查看/装备/使用道具',cl:'bg-slate-100 text-slate-700 border-slate-200'},
                  {c:'/训练 属性',d:'30鳞币训练属性·每日1次',cl:'bg-orange-50 text-orange-700 border-orange-200'},
                  {c:'/斗鱼 @某人',d:'STR对抗·胜者+鳞币·每日3次',cl:'bg-red-50 text-red-700 border-red-200'},
                  {c:'/鱼塘',d:'查看鱼塘总览',cl:'bg-slate-100 text-slate-700 border-slate-200'},
                  {c:'/改名 名字',d:'给鱼改名',cl:'bg-indigo-50 text-indigo-700 border-indigo-200'},
                ]" :key="cmd.c" class="rounded-lg p-2 border" :class="cmd.cl">
                  <span class="font-mono font-bold text-xs">{{ cmd.c }}</span>
                  <span class="ml-2 text-xs opacity-80">{{ cmd.d }}</span>
                </div>
              </div>
              <!-- 🎮 作弊模式 -->
              <div v-else-if="tutorialTab === 'cheat'" class="space-y-4">
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">开启方式</h3>
                  <p>设置→鱼塘设置→允许作弊，打开开关即可。鱼塘页面将出现指令模拟器和调试面板。</p>
                </div>
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">调试功能</h3>
                  <p>💰加减鳞币 · ⚡强制触发事件 · 🌤️设置天气 · 💀秒杀鱼 · ✨复活鱼。所有操作生成"被不明力量"风味事件。</p>
                </div>
                <div>
                  <h3 class="font-semibold text-slate-800 mb-1">注意事项</h3>
                  <p>作弊模式下成就系统暂停。关闭后恢复正常。调试操作不可撤销，请谨慎使用。</p>
                </div>
              </div>
            </div>
          </div>
          <div class="sticky bottom-0 bg-white px-5 py-3 border-t border-slate-100 shrink-0">
            <button @click="showTutorial = false"
              class="w-full px-4 py-2 bg-slate-800 text-white rounded-xl hover:bg-slate-700 transition text-sm font-medium">
              我知道了
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* ===== Page background ===== */
.pond-page {
  background: linear-gradient(175deg, #f0f4f8 0%, #e8eff5 30%, #eef3f8 100%);
  border-radius: var(--radius-2xl, 24px);
  padding: 24px;
  min-height: 100%;
}
@media (max-width: 640px) {
  .pond-page { padding: 12px; border-radius: var(--radius-lg, 16px); }
}

/* ===== Header ===== */
.pond-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
}
.pond-brand-icon {
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 50%, #0369a1 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(14, 165, 233, 0.3);
}

/* ===== Buttons ===== */
.pond-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.2s ease;
  white-space: nowrap;
}
.pond-btn-primary {
  background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%);
  color: white;
  box-shadow: 0 2px 6px rgba(14, 165, 233, 0.25);
}
.pond-btn-primary:hover:not(:disabled) {
  box-shadow: 0 4px 12px rgba(14, 165, 233, 0.35);
  transform: translateY(-1px);
}
.pond-btn-ghost {
  background: white;
  color: #475569;
  border: 1px solid #e2e8f0;
}
.pond-btn-ghost:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #cbd5e1;
}
.pond-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ===== Empty state ===== */
.pond-empty {
  text-align: center;
  padding: 64px 16px;
}
.empty-illustration {
  position: relative;
  display: inline-block;
}
.empty-ripple {
  position: absolute;
  inset: -20px;
  border-radius: 50%;
  border: 2px solid rgba(14, 165, 233, 0.1);
  animation: empty-pulse 2.5s ease-in-out infinite;
}
@keyframes empty-pulse {
  0%, 100% { transform: scale(1); opacity: 0.3; }
  50% { transform: scale(1.15); opacity: 0.05; }
}

/* ===== Tank hero ===== */
.tank-hero {
  position: relative;
  margin-bottom: 20px;
}

/* Weather pill */
.weather-pill {
  position: absolute;
  top: 14px;
  right: 16px;
  z-index: 25;
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid;
  border-radius: 14px;
  padding: 10px 16px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
@media (max-width: 640px) {
  .weather-pill {
    top: 8px;
    right: 8px;
    padding: 6px 12px;
    gap: 6px;
    border-radius: 10px;
  }
  .weather-pill .text-xl { font-size: 1rem; }
}

/* ===== Dashboard tabs ===== */
.pond-dashboard {
  margin-bottom: 16px;
  overflow: hidden;
}
.dashboard-tabs {
  display: flex;
  border-bottom: 1px solid #e8ecf0;
  background: #fafbfc;
}
.dashboard-tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #94a3b8;
  transition: all 0.2s ease;
  position: relative;
}
.dashboard-tab::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 20%;
  right: 20%;
  height: 2px;
  background: transparent;
  border-radius: 1px 1px 0 0;
  transition: all 0.25s ease;
}
.dashboard-tab:hover { color: #64748b; background: rgba(255,255,255,0.5); }
.dashboard-tab.active {
  color: #0ea5e9;
  background: white;
}
.dashboard-tab.active::after {
  left: 10%;
  right: 10%;
  background: #0ea5e9;
}
.dashboard-content {
  padding: 16px;
  min-height: 120px;
}

.tab-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 12px;
}

</style>
