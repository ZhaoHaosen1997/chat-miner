<script setup>
import { ref, inject, watch, computed } from 'vue'
import { getFishPond, adoptFish, settleFishPond, feedFish,
         touchFish, exploreFish, showoffFish, trainFish, battleFish, deleteFish,
         renameFish, parseFishCommands, getFishDetail, getFishLeaderboard }
  from '../api/index.js'
import FishTank from '../components/FishTank.vue'
import FishCard from '../components/FishCard.vue'
import FishLeaderboard from '../components/FishLeaderboard.vue'
import ChatSimulator from '../components/ChatSimulator.vue'
import PondEventTimeline from '../components/PondEventTimeline.vue'  // v1.16.1
import PondManagement from './PondManagement.vue'  // v1.16.2
import { Fish, RefreshCw, Coins, Search, X, BookOpen, Clock } from 'lucide-vue-next'

const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')
const showError = inject('showError')  // v0.13.3: 统一错误弹窗

const pondState = ref(null)
const loading = ref(false)
const selectedFish = ref(null)
const showCard = ref(false)
const actionLoading = ref('')
const leaderboardSort = ref('growth')
const parseLog = ref(null)
const showParseLog = ref(false)
const showTutorial = ref(false)
let _pondRefreshTimer = null  // v1.16.2: 被动事件轮询

const gid = computed(() => currentGroup.value?.id)

// v1.16.2: 静默鱼塘开启时自动轮询刷新（每60s），关掉时停止
watch(() => pondState.value?.auto_events_enabled, (enabled) => {
  if (_pondRefreshTimer) { clearInterval(_pondRefreshTimer); _pondRefreshTimer = null }
  if (enabled) {
    _pondRefreshTimer = setInterval(() => loadPond(true), 60000)
  }
})

watch(() => gid.value, () => loadPond(), { immediate: true })

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

function handleFishClick(fish) {
  selectedFish.value = fish
  showCard.value = true
}

async function handleFishAction(action, wxid, extra) {
  actionLoading.value = action
  try {
    let result
    switch (action) {
      case 'feed': result = await feedFish(gid.value, wxid); break
      case 'touch': result = await touchFish(gid.value, wxid); break
      case 'explore': result = await exploreFish(gid.value, wxid); break
      case 'showoff': result = await showoffFish(gid.value, wxid); break
      case 'train': result = await trainFish(gid.value, wxid, extra); break
      case 'rename': result = await renameFish(gid.value, wxid, extra); break
      case 'battle': result = await battleFish(gid.value, wxid, extra); break
      case 'delete':
        result = await deleteFish(gid.value, wxid)
        showCard.value = false; selectedFish.value = null
        break
    }
    // Refresh detail if card is open
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
const recentEvents = computed(() => pondState.value?.recent_events || [])
const sidebarTab = ref('events')  // v1.16.1: 'events' | 'leaderboard'

// Rarity colors
const rarityColors = { '普通': 'bg-gray-400', '稀有': 'bg-blue-500', '史诗': 'bg-purple-500', '传说': 'bg-orange-500' }
const rarityLabels = { '普通': '白', '稀有': '蓝', '史诗': '紫', '传说': '橙' }
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <span class="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-100 to-blue-100 flex items-center justify-center">
          <Fish class="w-4 h-4 text-cyan-600" />
        </span>
        <h1 class="text-xl font-bold text-slate-800">群鱼塘</h1>
        <span v-if="pondState" class="text-sm text-slate-400">
          {{ pondState.alive_count }} 条活鱼 · {{ pondState.dead_count }} 条亡鱼
        </span>
      </div>
      <div class="flex items-center gap-2">
        <button @click="showTutorial = true"
          class="flex items-center gap-1.5 px-3 py-2 text-sm border border-slate-200 rounded-xl
                 hover:bg-slate-50 hover:border-slate-300 transition-all text-slate-500 font-medium">
          <BookOpen :size="16" />
          教程
        </button>
      </div>
    </div>

    <!-- Weather Bar -->
    <div v-if="weather" class="rounded-xl p-4 bg-gradient-to-r"
      :class="{
        'from-amber-50 to-yellow-50 border border-amber-200': weather.type === 'sunny',
        'from-blue-50 to-indigo-50 border border-blue-200': weather.type === 'rain',
        'from-slate-100 to-gray-200 border border-slate-300': weather.type === 'storm',
        'from-pink-50 to-purple-50 border border-pink-200': weather.type === 'rainbow',
      }">
      <div class="flex items-center gap-3">
        <span class="text-4xl">{{ weather.emoji }}</span>
        <div>
          <div class="font-semibold text-slate-800">{{ weather.name }}</div>
          <div class="text-sm text-slate-500">{{ weather.effect }}</div>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-20 text-slate-400">
      <RefreshCw :size="40" class="mx-auto mb-3 animate-spin" />
      <p>正在加载鱼塘...</p>
    </div>

    <!-- Empty State -->
    <div v-else-if="!pondState || pondState.alive_count === 0" class="card p-16 text-center animate-scale-in">
      <span class="text-7xl mb-4 block">🐟</span>
      <h2 class="text-xl font-semibold text-slate-600">鱼塘里还没有鱼</h2>
      <p class="text-slate-400 mt-2 mb-6 max-w-sm mx-auto">点击"解析指令"从聊天记录中寻找 /领养 指令，或点击"结算"自动为活跃成员创建鱼</p>
      <div class="flex items-center justify-center gap-3">
        <button @click="handleParseCommands" :disabled="!!actionLoading"
          class="px-5 py-2.5 bg-gradient-to-r from-amber-500 to-orange-500 text-white rounded-xl font-medium hover:from-amber-600 hover:to-orange-600 transition-all shadow-lg shadow-amber-200 flex items-center gap-2">
          <Search :size="16" /> 解析指令
        </button>
        <button @click="handleSettle" :disabled="!!actionLoading"
          class="px-5 py-2.5 bg-white border border-slate-200 text-slate-600 rounded-xl font-medium hover:bg-slate-50 transition-all flex items-center gap-2">
          <RefreshCw :size="16" /> 结算
        </button>
      </div>
    </div>

    <!-- Main Content -->
    <div v-else class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Fish Tank -->
      <div class="lg:col-span-2">
        <FishTank
          :fish="aliveFish"
          :dead-fish="deadFish"
          @fish-click="handleFishClick"
          @adopt="handleAdopt"
        />
      </div>

      <!-- Sidebar -->
      <div class="space-y-4">

            <!-- Quick Stats -->
        <div class="card p-4">
          <h3 class="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-1.5">
            <Coins :size="14" class="text-amber-500" /> 稀有度分布
          </h3>
          <div class="space-y-2">
            <div v-for="(color, rarity) in rarityColors" :key="rarity"
              class="flex items-center justify-between text-xs">
              <div class="flex items-center gap-2">
                <span class="w-2.5 h-2.5 rounded-full flex-shrink-0" :class="color"></span>
                <span class="text-slate-600 font-medium">{{ rarity }}</span>
                <span class="text-[10px] text-slate-300">{{ rarityLabels[rarity] }}</span>
              </div>
              <span class="text-slate-500 font-semibold stat-ticker">
                {{ aliveFish.filter(f => f.rarity === rarity).length }}
              </span>
            </div>
          </div>
        </div>

        <!-- v1.16.1: Sidebar Tabs: Events / Stats -->
        <div class="card overflow-hidden">
          <div class="flex border-b border-slate-100">
            <button @click="sidebarTab = 'events'"
              :class="['flex-1 py-2.5 text-xs font-semibold transition', sidebarTab === 'events' ? 'text-indigo-600 border-b-2 border-indigo-500 bg-indigo-50/50' : 'text-slate-400 hover:text-slate-600']">
              <Clock :size="12" class="inline mr-1" /> 事件
            </button>
            <button @click="sidebarTab = 'leaderboard'"
              :class="['flex-1 py-2.5 text-xs font-semibold transition', sidebarTab === 'leaderboard' ? 'text-indigo-600 border-b-2 border-indigo-500 bg-indigo-50/50' : 'text-slate-400 hover:text-slate-600']">
              🏆 排行
            </button>
          </div>
          <div class="p-3 max-h-80 overflow-y-auto">
            <PondEventTimeline v-if="sidebarTab === 'events'" :events="recentEvents" />
            <FishLeaderboard
              v-else
              :fish="aliveFish"
              :sort="leaderboardSort"
              @update:sort="leaderboardSort = $event"
              @fish-click="handleFishClick"
            />
          </div>
        </div>
      </div>
    </div>

    <!-- Fish Card Modal -->
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

    <!-- v1.16.2: Pond Management -->
    <PondManagement v-if="pondState" @pond-refresh="loadPond" />

    <!-- Chat Simulator -->
    <ChatSimulator @pond-refresh="loadPond" />

    <!-- Parse Log Modal -->
    <Teleport to="body">
      <div v-if="showParseLog && parseLog"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        @click.self="showParseLog = false">
        <div class="bg-white rounded-2xl shadow-2xl w-[600px] max-h-[80vh] flex flex-col overflow-hidden">
          <!-- Header -->
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

          <!-- Log entries -->
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
              <!-- Time + Sender -->
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
              <!-- Command -->
              <div class="font-mono text-slate-600 mb-1">{{ entry.command }}</div>
              <!-- Error -->
              <div v-if="entry.error" class="text-red-600">❌ {{ entry.error }}</div>
              <!-- D20 result -->
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
              <!-- Rewards -->
              <div v-if="entry.growth || entry.happiness || entry.coin_amount" class="flex flex-wrap gap-1 mt-1">
                <span v-if="entry.growth" class="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 text-[10px]">成长+{{ entry.growth }}</span>
                <span v-if="entry.happiness" class="px-1.5 py-0.5 rounded bg-pink-50 text-pink-700 text-[10px]">幸福+{{ entry.happiness }}</span>
                <span v-if="entry.coin_amount" class="px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 text-[10px]">鳞币+{{ entry.coin_amount }}</span>
                <span v-if="entry.evolved" class="px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 text-[10px]">进化→{{ entry.new_stage }}</span>
              </div>
              <!-- Adopt result -->
              <div v-if="entry.fish" class="text-green-700 mt-1">🐟 {{ entry.fish.name }} ({{ entry.fish.rarity }})</div>
              <!-- Battle result -->
              <div v-if="entry.battle_winner" class="text-xs mt-1"
                :class="entry.battle_winner === entry.wxid ? 'text-green-600' : 'text-red-500'">
                ⚔️ {{ entry.battle_winner === entry.wxid ? '胜!' : '败...' }}
              </div>
            </div>
          </div>

          <!-- Footer -->
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

    <!-- Tutorial Modal -->
    <Teleport to="body">
      <div v-if="showTutorial" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
        @click.self="showTutorial = false">
        <div class="bg-white rounded-2xl shadow-2xl w-[560px] max-h-[80vh] overflow-y-auto">
          <div class="sticky top-0 bg-white px-5 py-4 border-b border-slate-100 flex items-center justify-between">
            <h2 class="font-bold text-slate-800 text-lg">🐟 群鱼塘教程</h2>
            <button @click="showTutorial = false" class="p-1 hover:bg-slate-100 rounded text-slate-400"><X :size="18" /></button>
          </div>
          <div class="px-5 py-4 space-y-4 text-sm text-slate-600">
            <div>
              <h3 class="font-semibold text-slate-800 mb-2">🎮 基本概念</h3>
              <p>群鱼塘是基于群聊活跃度的<strong>养鱼游戏</strong>。每个群成员拥有一条水生生物，发言活跃度驱动鱼的成长。</p>
              <p class="mt-1">鱼有 <strong>六维属性</strong>（力量/敏捷/体质/智力/感知/魅力）、<strong>成长阶段</strong>（鱼苗→幼鱼→成鱼→大鱼→传说）和 <strong>稀有度</strong>（普通/稀有/史诗/传说）。</p>
            </div>
            <div>
              <h3 class="font-semibold text-slate-800 mb-2">📋 全部指令</h3>
              <div class="space-y-1.5">
                <div v-for="cmd in [
                  {c:'/领养',d:'随机品种+稀有度+属性，创建你的第一条鱼',cl:'bg-green-50 text-green-700 border-green-200'},
                  {c:'/喂食',d:'敏捷检定 · +成长+幸福 · 每天3次',cl:'bg-sky-50 text-sky-700 border-sky-200'},
                  {c:'/摸鱼',d:'魅力检定 · +亲密度 · 每天5次',cl:'bg-pink-50 text-pink-700 border-pink-200'},
                  {c:'/探索',d:'感知/智力检定 · 获得鳞币 · 每天3次',cl:'bg-amber-50 text-amber-700 border-amber-200'},
                  {c:'/晒鱼',d:'魅力检定 · 观众打赏鳞币 · 每天3次',cl:'bg-purple-50 text-purple-700 border-purple-200'},
                  {c:'/购买 商品名',d:'从今日黑市抢购道具（先到先得）',cl:'bg-cyan-50 text-cyan-700 border-cyan-200'},
                  {c:'/赠予 @XX 道具',d:'把道具送给群友',cl:'bg-pink-50 text-pink-700 border-pink-200'},
                  {c:'/道具 库存',d:'查看库存/装备/卸下/使用道具',cl:'bg-slate-100 text-slate-700 border-slate-200'},
                  {c:'/训练 属性',d:'消耗30鳞币训练属性 · 每天1次 · 属值越高越难',cl:'bg-orange-50 text-orange-700 border-orange-200'},
                  {c:'/斗鱼 @某人',d:'力量对抗 · 胜者+成长+鳞币 · 每天3次',cl:'bg-red-50 text-red-700 border-red-200'},
                  {c:'/鱼塘',d:'查看鱼塘总览',cl:'bg-slate-100 text-slate-700 border-slate-200'},
                  {c:'/改名 新名字',d:'给鱼改名（首次免费，之后需改名符）',cl:'bg-indigo-50 text-indigo-700 border-indigo-200'},
                ]" :key="cmd.c" class="rounded-lg p-2.5 border" :class="cmd.cl">
                  <span class="font-mono font-bold">{{ cmd.c }}</span>
                  <span class="ml-2 opacity-80">{{ cmd.d }}</span>
                </div>
              </div>
            </div>
            <div>
              <h3 class="font-semibold text-slate-800 mb-2">🎲 互动判定</h3>
              <p>所有互动通过 <strong>掷骰检定</strong>判定成败。每条鱼有六项属性（力量/敏捷/体质/智力/感知/魅力），检定结果取决于属性高低。</p>
              <ul class="list-disc ml-5 mt-1 space-y-0.5 text-xs">
                <li>掷出 <strong class="text-amber-600">满点</strong>：🎉 大成功！效果翻倍</li>
                <li>掷出 <strong class="text-red-500">1点</strong>：💀 大失败！效果减半</li>
                <li>属性越高，检定成功率越高</li>
              </ul>
            </div>
            <div>
              <h3 class="font-semibold text-slate-800 mb-2">🪙 鳞币</h3>
              <p>通过 /探索 /晒鱼 /斗鱼 赚取。可在商店购买道具。鳞币绑定到 (群聊+wxid)，与鱼的生命周期无关。</p>
            </div>
            <div>
              <h3 class="font-semibold text-slate-800 mb-2">📅 每日结算</h3>
              <p>从<strong>仪表盘日历</strong>点击某天可触发结算。开启<strong>静默鱼塘</strong>（设置→高级选项）后鱼塘将自动运转，无需手动操作。</p>
            </div>
          </div>
          <div class="sticky bottom-0 bg-white px-5 py-3 border-t border-slate-100">
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
