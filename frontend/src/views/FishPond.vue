<script setup>
import { ref, inject, watch, computed } from 'vue'
import { getFishPond, adoptFish, settleFishPond, feedFish, cleanTank,
         touchFish, exploreFish, treasureFish, showoffFish, battleFish,
         renameFish, parseFishCommands, getFishDetail, getFishLeaderboard }
  from '../api/index.js'
import FishTank from '../components/FishTank.vue'
import FishCard from '../components/FishCard.vue'
import FishLeaderboard from '../components/FishLeaderboard.vue'
import ChatSimulator from '../components/ChatSimulator.vue'
import { Fish, RefreshCw, Sparkles, Coins, Zap, Search } from 'lucide-vue-next'

const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')

const pondState = ref(null)
const loading = ref(false)
const selectedFish = ref(null)
const showCard = ref(false)
const actionLoading = ref('')
const leaderboardSort = ref('growth')

const gid = computed(() => currentGroup.value?.id)

watch(() => gid.value, loadPond, { immediate: true })

async function loadPond() {
  if (!gid.value) return
  loading.value = true
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
    alert(`指令解析完成：找到 ${result.commands_found} 条指令，处理 ${result.events_processed} 条`)
    await loadPond()
  } catch (e) { console.error(e) }
  finally { actionLoading.value = '' }
}

async function handleAdopt(wxid, displayName) {
  try {
    await adoptFish(gid.value, wxid, displayName)
    await loadPond()
  } catch (e) { alert(e.message) }
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
      case 'clean': result = await cleanTank(gid.value, wxid); break
      case 'touch': result = await touchFish(gid.value, wxid); break
      case 'explore': result = await exploreFish(gid.value, wxid); break
      case 'treasure': result = await treasureFish(gid.value, wxid); break
      case 'showoff': result = await showoffFish(gid.value, wxid); break
      case 'rename': result = await renameFish(gid.value, wxid, extra); break
      case 'battle': result = await battleFish(gid.value, wxid, extra); break
    }
    // Refresh detail if card is open
    if (showCard.value && selectedFish.value?.wxid === wxid) {
      const detail = await getFishDetail(gid.value, wxid)
      selectedFish.value = { ...selectedFish.value, ...detail.fish }
    }
    await loadPond()
  } catch (e) { alert(e.message) }
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

// Rarity colors
const rarityColors = { '普通': 'bg-gray-400', '稀有': 'bg-blue-500', '史诗': 'bg-purple-500', '传说': 'bg-orange-500' }
const rarityLabels = { '普通': '白', '稀有': '蓝', '史诗': '紫', '传说': '橙' }
</script>

<template>
  <div class="max-w-6xl mx-auto px-4 py-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-3">
        <h1 class="text-2xl font-bold text-slate-800">群鱼塘</h1>
        <span class="text-3xl">🐟</span>
        <span v-if="pondState" class="text-sm text-slate-500">
          {{ pondState.alive_count }} 条活鱼 · {{ pondState.dead_count }} 条亡鱼
        </span>
      </div>
      <div class="flex items-center gap-2">
        <button @click="handleParseCommands" :disabled="!!actionLoading"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm border border-slate-300 rounded-lg
                 hover:bg-slate-50 disabled:opacity-50 transition">
          <Search :size="16" />
          {{ actionLoading === 'parse' ? '解析中...' : '解析指令' }}
        </button>
        <button @click="handleSettle" :disabled="!!actionLoading"
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-amber-500 text-white rounded-lg
                 hover:bg-amber-600 disabled:opacity-50 transition">
          <RefreshCw :size="16" :class="{ 'animate-spin': actionLoading === 'settle' }" />
          结算
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
    <div v-else-if="!pondState || pondState.alive_count === 0" class="text-center py-20">
      <span class="text-6xl">🐟</span>
      <h2 class="text-xl font-semibold text-slate-600 mt-4">鱼塘里还没有鱼</h2>
      <p class="text-slate-400 mt-2">点击"解析指令"从聊天记录中寻找 /领养 指令，或点击"结算"自动为活跃成员创建鱼</p>
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
        <FishLeaderboard
          :fish="aliveFish"
          :sort="leaderboardSort"
          @update:sort="leaderboardSort = $event"
          @fish-click="handleFishClick"
        />

        <!-- Quick Stats -->
        <div class="bg-white rounded-xl border border-slate-200 p-4">
          <h3 class="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-1.5">
            <Coins :size="14" class="text-amber-500" /> 稀有度分布
          </h3>
          <div class="space-y-1.5">
            <div v-for="(color, rarity) in rarityColors" :key="rarity"
              class="flex items-center justify-between text-xs">
              <div class="flex items-center gap-1.5">
                <span class="w-2 h-2 rounded-full" :class="color"></span>
                <span class="text-slate-600">{{ rarity }}({{ rarityLabels[rarity] }})</span>
              </div>
              <span class="text-slate-400 font-mono">
                {{ aliveFish.filter(f => f.rarity === rarity).length }}
              </span>
            </div>
          </div>
        </div>

        <!-- Recent Events -->
        <div v-if="recentEvents.length" class="bg-white rounded-xl border border-slate-200 p-4">
          <h3 class="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-1.5">
            <Zap :size="14" class="text-amber-500" /> 最近事件
          </h3>
          <div class="space-y-1.5 max-h-48 overflow-y-auto">
            <div v-for="evt in recentEvents.slice(0, 8)" :key="evt.id"
              class="text-xs text-slate-500 flex items-center gap-1.5">
              <span class="text-slate-300 flex-shrink-0">{{ evt.created_at?.slice(11, 16) || '' }}</span>
              <span class="px-1.5 py-0.5 rounded text-[10px] font-medium"
                :class="{
                  'bg-green-100 text-green-700': evt.event_type === 'born' || evt.event_type === 'evolve',
                  'bg-blue-100 text-blue-700': evt.event_type === 'feed' || evt.event_type === 'explore',
                  'bg-red-100 text-red-700': evt.event_type === 'battle' || evt.event_type === 'shark_attack',
                  'bg-slate-100 text-slate-600': true,
                }">
                {{ {born:'诞生', evolve:'进化', feed:'喂食', battle:'斗鱼', explore:'探索',
                    treasure:'寻宝', showoff:'晒鱼', shark_attack:'鲨鱼', level_up:'升级',
                    clean:'换水', touch:'摸鱼', rename:'改名'}[evt.event_type] || evt.event_type }}
              </span>
              <span class="truncate">{{ evt.wxid?.slice(0, 12) }}</span>
            </div>
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

    <!-- Chat Simulator -->
    <ChatSimulator @pond-refresh="loadPond" />
  </div>
</template>
