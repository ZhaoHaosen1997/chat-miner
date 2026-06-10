<script setup>
import { ref, computed, watch, nextTick, inject } from 'vue'
import {
  getMembers, adoptFish, feedFish, touchFish,
  exploreFish, showoffFish, trainFish, battleFish, renameFish,
  fishItems, buyFromMarket, giftItem, logSimCommand, getFishDetail
} from '../api/index.js'
import {
  MessageCircle, Send, User, ChevronDown, X, Terminal,
  Dices, Zap, Coins, Heart, TrendingUp, RefreshCw
} from 'lucide-vue-next'

const currentGroup = inject('currentGroup')
const emit = defineEmits(['pond-refresh'])

// State
const isOpen = ref(false)
const members = ref([])
const selectedWxid = ref('')
const input = ref('')
const messages = ref([])
const loading = ref(false)
const showCommands = ref(false)
const cmdFilter = ref('')
const membersLoading = ref(false)

const gid = computed(() => currentGroup.value?.id)

// All available commands
const COMMANDS = [
  { cmd: '/领养', desc: '随机品种+稀有度+属性，创建你的鱼', icon: '🐟', color: 'text-green-600 bg-green-50' },
  { cmd: '/喂食', desc: 'DEX检定 DC10，+成长+幸福', icon: '🎲', color: 'text-sky-600 bg-sky-50' },
  { cmd: '/摸鱼', desc: '魅力检定 · +亲密度', icon: '👆', color: 'text-pink-600 bg-pink-50' },
  { cmd: '/探索', desc: '感知/智力检定 · 获得鳞币', icon: '🔍', color: 'text-amber-600 bg-amber-50' },
  { cmd: '/晒鱼', desc: '魅力检定 · 观众打赏鳞币', icon: '📸', color: 'text-purple-600 bg-purple-50' },
  { cmd: '/购买 商品名', desc: '从今日黑市抢购道具', icon: '🛒', color: 'text-cyan-600 bg-cyan-50' },
  { cmd: '/赠予 @XX 道具名', desc: '把道具送给群友', icon: '🎁', color: 'text-pink-600 bg-pink-50' },
  { cmd: '/道具 库存', desc: '查看库存/装备/卸下/使用', icon: '🎒', color: 'text-slate-600 bg-slate-50' },
  { cmd: '/训练 力量', desc: '消耗30鳞币 · 训练属性 · 每天1次', icon: '🏋️', color: 'text-orange-600 bg-orange-50' },
  { cmd: '/斗鱼 @', desc: 'STR对抗检定，胜者+鳞币', icon: '⚔️', color: 'text-red-600 bg-red-50' },
  { cmd: '/鱼塘', desc: '查看鱼塘总览', icon: '🐟', color: 'text-slate-600 bg-slate-50' },
  { cmd: '/改名 ', desc: '给鱼改名（首次免费）', icon: '✏️', color: 'text-indigo-600 bg-indigo-50' },
]

const filteredCommands = computed(() => {
  if (!cmdFilter.value) return COMMANDS
  return COMMANDS.filter(c => c.cmd.includes(cmdFilter.value))
})

const selectedMember = computed(() =>
  members.value.find(m => m.wxid === selectedWxid.value)
)

// Load members when opened
watch(isOpen, async (open) => {
  if (open && gid.value) {
    membersLoading.value = true
    try {
      members.value = await getMembers(gid.value)
      if (members.value.length && !selectedWxid.value) {
        // Default to first member with a display_name
        const first = members.value.find(m => m.display_name && m.display_name !== 'null') || members.value[0]
        selectedWxid.value = first.wxid
      }
    } catch (e) { console.error(e) }
    finally { membersLoading.value = false }
  }
})

// Watch for group changes
watch(gid, () => {
  selectedWxid.value = ''
  members.value = []
  messages.value = []
})

// Input handling
function onInputChange(e) {
  const val = e.target.value
  input.value = val
  if (val.startsWith('/')) {
    cmdFilter.value = val
    showCommands.value = true
  } else {
    showCommands.value = false
  }
}

function selectCommand(cmd) {
  input.value = cmd.cmd + (cmd.cmd.endsWith(' ') ? '' : '')
  showCommands.value = false
  // Focus back on input
  nextTick(() => {
    const el = document.getElementById('simulator-input')
    if (el) el.focus()
  })
}

// Parse and execute command
async function sendCommand() {
  const text = input.value.trim()
  if (!text || !selectedWxid.value) return

  const wxid = selectedWxid.value
  const member = selectedMember.value
  const senderName = member?.display_name || member?.nickname || wxid.slice(0, 12)

  // Add user message
  const msgEntry = {
    id: Date.now(),
    type: 'command',
    sender: senderName,
    wxid,
    text,
    time: new Date().toLocaleTimeString('zh'),
  }

  loading.value = true
  input.value = ''
  showCommands.value = false

  try {
    let result, d20Result
    const seed = `sim_${wxid}_${Date.now()}`

    // Parse and route command
    if (text === '/领养') {
      result = await adoptFish(gid.value, wxid, senderName)
      msgEntry.resultType = 'adopt'
    } else if (text === '/喂食') {
      result = await feedFish(gid.value, wxid)
      d20Result = result.check
      msgEntry.resultType = 'feed'
    } else if (text === '/摸鱼') {
      result = await touchFish(gid.value, wxid)
      d20Result = result.check
      msgEntry.resultType = 'touch'
    } else if (text === '/探索') {
      result = await exploreFish(gid.value, wxid)
      d20Result = result.check
      msgEntry.resultType = 'explore'
    } else if (text === '/晒鱼') {
      result = await showoffFish(gid.value, wxid)
      d20Result = result.check
      msgEntry.resultType = 'showoff'
    } else if (text.startsWith('/购买')) {
      const itemKey = text.replace('/购买', '').trim()
      result = await buyFromMarket(gid.value, wxid, itemKey)
      msgEntry.resultType = 'buy_market'
      msgEntry.buyResult = result
    } else if (text.startsWith('/赠予')) {
      const args = text.replace('/赠予', '').trim()
      const match = args.match(/@(\S+)\s+(.+)/)
      if (match) {
        result = await giftItem(gid.value, wxid, match[1], match[2].trim())
        msgEntry.resultType = 'gift'
        msgEntry.giftResult = result
      } else {
        msgEntry.error = '格式: /赠予 @XX 道具名'
      }
    } else if (text === '/道具' || text.startsWith('/道具 ')) {
      const args = text.replace('/道具', '').trim()
      const parts = args ? args.split(/\s+/) : []
      const action = parts[0] || '库存'
      const itemKey = parts.slice(1).join(' ')
      result = await fishItems(gid.value, wxid, action, itemKey)
      msgEntry.resultType = 'item'
      msgEntry.itemAction = action
      msgEntry.itemResult = result
    } else if (text.startsWith('/训练')) {
      const attrName = text.replace('/训练', '').trim()
      result = await trainFish(gid.value, wxid, attrName)
      d20Result = result.check
      msgEntry.resultType = 'train'
      msgEntry.trainAttr = attrName
      msgEntry.trainResult = result
    } else if (text.startsWith('/斗鱼')) {
      const targetName = text.replace('/斗鱼', '').replace('@', '').trim()
      // 精准匹配：display_name > nickname > group_nickname > wxid前缀
      const target = members.value.find(m =>
        (m.display_name && m.display_name === targetName) ||
        (m.nickname && m.nickname === targetName) ||
        (m.group_nickname && m.group_nickname === targetName) ||
        (m.wxid && m.wxid === targetName) ||
        (m.wxid && m.wxid.startsWith(targetName))
      )
      if (target) {
        result = await battleFish(gid.value, wxid, target.wxid)
        // 对抗检定：结构为 {attacker: {roll,modifier,total,...}, defender: {...}, winner}
        const mySide = result.check.winner === 'attacker' ? result.check.attacker : result.check.defender
        const theirSide = result.check.winner === 'attacker' ? result.check.defender : result.check.attacker
        d20Result = {
          roll: mySide.roll,
          modifier: mySide.modifier,
          total: mySide.total,
          dc: theirSide.total,
          success: result.check.winner === 'attacker',
          critical_hit: mySide.roll === 20,
          critical_miss: mySide.roll === 1,
        }
        msgEntry.resultType = 'battle'
        msgEntry.targetName = target.display_name || target.nickname || target.wxid
        msgEntry.battleWinner = result.winner
      } else {
        msgEntry.error = `找不到目标: "${targetName}"。可用成员: ${members.value.map(m => m.display_name || m.nickname || m.wxid.slice(0,12)).filter(n => n && n !== 'null').join(', ')}`
      }
    } else if (text.startsWith('/改名')) {
      const newName = text.replace('/改名', '').trim()
      if (newName) {
        result = await renameFish(gid.value, wxid, newName)
        msgEntry.resultType = 'rename'
        msgEntry.newName = newName
      }
    } else if (text === '/鱼塘') {
      msgEntry.resultType = 'pond'
    } else {
      msgEntry.error = `未知指令: ${text}`
    }

    // Attach results
    if (d20Result) {
      msgEntry.d20 = d20Result
      msgEntry.d20Summary = `d20(${d20Result.roll})+${d20Result.modifier}=${d20Result.total} vs DC${d20Result.dc}`
      if (d20Result.critical_hit) msgEntry.d20Summary += ' 🎉大成功!'
      else if (d20Result.critical_miss) msgEntry.d20Summary += ' 💀大失败!'
    }
    if (result) {
      msgEntry.result = result
      if (result.coin_amount !== undefined) msgEntry.coinAmount = result.coin_amount
      if (result.growth_bonus !== undefined) msgEntry.growthBonus = result.growth_bonus
      if (result.happiness_bonus !== undefined) msgEntry.happinessBonus = result.happiness_bonus
      if (result.evolved) msgEntry.evolved = true
    }

    // Refresh pond
    emit('pond-refresh')
  } catch (e) {
    msgEntry.error = e.message
  } finally {
    loading.value = false
    messages.value.push(msgEntry)
    // Auto scroll
    nextTick(() => {
      const log = document.getElementById('simulator-log')
      if (log) log.scrollTop = log.scrollHeight
    })
  }

  // Log to backend (outside try-catch, fires even if the command itself had an error in processing)
  if (gid.value) {
    logSimCommand(gid.value, {
      wxid: selectedWxid.value,
      command: text,
      display_name: selectedMember.value?.display_name || selectedWxid.value?.slice(0, 12) || '',
      d20: msgEntry.d20 || null,
      growth: msgEntry.growthBonus || 0,
      coin_amount: msgEntry.coinAmount || 0,
      happiness: msgEntry.happinessBonus || 0,
      evolved: msgEntry.evolved || false,
      fish_info: msgEntry.result?.fish || null,
      battle_winner: msgEntry.battleWinner || '',
      error: msgEntry.error || '',
    }).catch(() => {})
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    if (showCommands.value && filteredCommands.value.length === 1) {
      selectCommand(filteredCommands.value[0])
    } else {
      sendCommand()
    }
  } else if (e.key === 'Tab' && showCommands.value && filteredCommands.value.length > 0) {
    e.preventDefault()
    selectCommand(filteredCommands.value[0])
  } else if (e.key === 'Escape') {
    showCommands.value = false
  }
}

function clearLog() {
  messages.value = []
}

// Quick select a command button
function quickCommand(cmd) {
  input.value = cmd
  showCommands.value = false
  nextTick(() => {
    const el = document.getElementById('simulator-input')
    if (el) el.focus()
  })
}
</script>

<template>
  <!-- Toggle Button -->
  <button
    @click="isOpen = !isOpen"
    class="fixed bottom-6 right-6 z-40 flex items-center gap-2 px-4 py-3 bg-slate-800 text-white
           rounded-full shadow-lg hover:bg-slate-700 transition-all hover:scale-105 active:scale-95"
    :title="isOpen ? '关闭模拟器' : '打开聊天模拟器'"
  >
    <Terminal :size="18" />
    <span class="text-sm font-medium">{{ isOpen ? '关闭模拟器' : '指令模拟器' }}</span>
    <span v-if="!isOpen" class="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
  </button>

  <!-- Simulator Panel -->
  <Teleport to="body">
    <Transition name="slide-up">
      <div v-if="isOpen"
        class="fixed bottom-20 right-6 z-50 w-[480px] h-[600px] max-h-[70vh]
               bg-white rounded-2xl shadow-2xl border border-slate-200 flex flex-col overflow-hidden">
        <!-- Header -->
        <div class="flex items-center justify-between px-4 py-3 border-b border-slate-100 bg-slate-50 shrink-0">
          <div class="flex items-center gap-2">
            <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
            <span class="font-semibold text-slate-700 text-sm">聊天指令模拟器</span>
            <span class="text-xs text-slate-400">测试鱼塘功能</span>
          </div>
          <div class="flex items-center gap-1">
            <button @click="clearLog" class="p-1.5 hover:bg-slate-200 rounded text-slate-400" title="清空日志">
              <RefreshCw :size="14" />
            </button>
            <button @click="isOpen = false" class="p-1.5 hover:bg-slate-200 rounded text-slate-400">
              <X :size="16" />
            </button>
          </div>
        </div>

        <!-- Member Selector -->
        <div class="px-3 py-2 border-b border-slate-100 bg-white shrink-0">
          <div class="flex items-center gap-2">
            <User :size="14" class="text-slate-400 shrink-0" />
            <select
              v-model="selectedWxid"
              :disabled="membersLoading"
              class="flex-1 text-sm bg-transparent border-none outline-none text-slate-700 cursor-pointer
                     disabled:opacity-50 py-1"
            >
              <option value="" disabled>选择群成员身份...</option>
              <option v-for="m in members" :key="m.wxid" :value="m.wxid">
                {{ m.display_name || m.nickname || m.wxid.slice(0, 12) }}
                {{ m.message_count ? `(${m.message_count}条)` : '' }}
              </option>
            </select>
            <span v-if="membersLoading" class="text-xs text-slate-400">加载中...</span>
            <span v-else class="text-xs text-slate-400">{{ members.length }}人</span>
          </div>
        </div>

        <!-- Chat Log -->
        <div id="simulator-log" ref="logRef"
          class="flex-1 overflow-y-auto px-3 py-3 space-y-3 bg-slate-50/50">
          <!-- Empty state -->
          <div v-if="messages.length === 0" class="text-center py-10">
            <MessageCircle :size="32" class="mx-auto text-slate-300 mb-2" />
            <p class="text-sm text-slate-400">选择成员身份后，输入 / 指令开始模拟</p>
            <p class="text-xs text-slate-300 mt-1">输入 / 查看可用指令列表</p>
          </div>

          <!-- Messages -->
          <div v-for="msg in messages" :key="msg.id" class="space-y-1.5">
            <!-- Command bubble -->
            <div class="flex items-start gap-2 justify-end">
              <div class="max-w-[80%]">
                <div class="text-[10px] text-slate-400 text-right mb-0.5">
                  {{ msg.sender }} · {{ msg.time }}
                </div>
                <div class="px-3 py-1.5 rounded-xl rounded-tr-sm text-sm font-medium"
                  :class="msg.error
                    ? 'bg-red-50 text-red-600 border border-red-200'
                    : 'bg-slate-800 text-white'">
                  {{ msg.text }}
                </div>
              </div>
              <div class="w-7 h-7 rounded-full bg-slate-200 flex items-center justify-center shrink-0 mt-3">
                <User :size="12" class="text-slate-500" />
              </div>
            </div>

            <!-- Result bubble -->
            <div v-if="!msg.error && msg.resultType" class="flex items-start gap-2">
              <div class="w-7 h-7 rounded-full bg-amber-100 flex items-center justify-center shrink-0 mt-1">
                <Dices :size="12" class="text-amber-600" />
              </div>
              <div class="max-w-[85%] space-y-1">
                <!-- D20 roll -->
                <div v-if="msg.d20" class="px-3 py-1.5 rounded-xl rounded-tl-sm text-xs"
                  :class="{
                    'bg-amber-50 text-amber-800 border border-amber-200': msg.d20.success && !msg.d20.critical_hit,
                    'bg-yellow-50 text-yellow-800 border border-yellow-300': msg.d20.critical_hit,
                    'bg-red-50 text-red-600 border border-red-200': !msg.d20.success || msg.d20.critical_miss,
                  }">
                  <div class="font-mono font-bold">{{ msg.d20Summary }}</div>
                  <div class="mt-0.5">
                    {{ msg.d20.success ? (msg.d20.critical_hit ? '🎉 大成功！效果翻倍' : '✅ 检定成功') :
                       (msg.d20.critical_miss ? '💀 大失败！效果减半' : '❌ 检定失败') }}
                  </div>
                </div>

                <!-- Adopt result -->
                <div v-if="msg.resultType === 'adopt' && msg.result?.fish"
                  class="px-3 py-2 rounded-xl rounded-tl-sm bg-green-50 border border-green-200 text-xs space-y-1">
                  <div class="font-medium text-green-700">
                    🐟 领养成功！{{ msg.result.fish.fish_name }}
                  </div>
                  <div class="text-green-600">
                    品种: {{ msg.result.species_info?.name }} |
                    稀有度:
                    <span :class="{
                      'text-gray-500': msg.result.fish.rarity === '普通',
                      'text-blue-600': msg.result.fish.rarity === '稀有',
                      'text-purple-600': msg.result.fish.rarity === '史诗',
                      'text-orange-500': msg.result.fish.rarity === '传说',
                    }">{{ msg.result.fish.rarity }}</span>
                  </div>
                </div>

                <!-- Growth/Happiness/Coins -->
                <div v-if="msg.growthBonus || msg.happinessBonus || msg.coinAmount !== undefined"
                  class="flex flex-wrap gap-1.5">
                  <span v-if="msg.growthBonus" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]
                    bg-emerald-50 text-emerald-700 border border-emerald-200">
                    <TrendingUp :size="10" /> 成长+{{ msg.growthBonus }}
                  </span>
                  <span v-if="msg.happinessBonus" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]
                    bg-pink-50 text-pink-700 border border-pink-200">
                    <Heart :size="10" /> 幸福+{{ msg.happinessBonus }}
                  </span>
                  <span v-if="msg.coinAmount !== undefined" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full
                    text-[10px] bg-amber-50 text-amber-700 border border-amber-200">
                    <Coins :size="10" /> 鳞币+{{ msg.coinAmount }}
                  </span>
                  <span v-if="msg.evolved" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px]
                    bg-purple-50 text-purple-700 border border-purple-200">
                    <Zap :size="10" /> 进化!
                  </span>
                </div>

                <!-- Buy from market -->
                <div v-if="msg.resultType === 'buy_market' && !msg.error"
                  class="px-3 py-2 rounded-xl rounded-tl-sm bg-cyan-50 border border-cyan-200 text-xs">
                  <span class="font-medium text-cyan-700">🛒 购买 {{ msg.buyResult.item }}</span>
                  <span class="text-cyan-600"> · {{ msg.buyResult.rarity }} · 花费{{ msg.buyResult.price }}鳞币</span>
                </div>
                <!-- Gift -->
                <div v-if="msg.resultType === 'gift' && !msg.error"
                  class="px-3 py-2 rounded-xl rounded-tl-sm bg-pink-50 border border-pink-200 text-xs">
                  <span class="font-medium text-pink-700">🎁 赠予 {{ msg.giftResult.item }}</span>
                  <span class="text-pink-600"> → {{ msg.giftResult.to }}</span>
                </div>

                <!-- Item result -->
                <div v-if="msg.resultType === 'item' && !msg.error"
                  class="px-3 py-2 rounded-xl rounded-tl-sm bg-cyan-50 border border-cyan-200 text-xs">
                  <span class="font-medium text-cyan-700">🎒 {{ {buy:'购买',sell:'卖出',equip:'装备',unequip:'卸下',use:'使用',inventory:'库存',shop:'商店'}[msg.itemAction] || msg.itemAction }}</span>
                  <!-- Buy/Sell -->
                  <span v-if="msg.itemAction === 'buy' || msg.itemAction === 'sell'" class="text-cyan-600">
                    {{ msg.itemResult.item }} x{{ msg.itemResult.qty }}
                    {{ msg.itemAction === 'buy' ? '花费' + msg.itemResult.cost : '获得' + msg.itemResult.earned }}鳞币
                  </span>
                  <!-- Equip/Unequip -->
                  <span v-else-if="msg.itemAction === 'equip'" class="text-cyan-600">
                    {{ msg.itemResult.item }} · {{ msg.itemResult.stat ? (msg.itemResult.stat==='all'?'全属性':{strength:'力量',dexterity:'敏捷',constitution:'体质',intelligence:'智力',wisdom:'感知',charisma:'魅力'}[msg.itemResult.stat]) : '' }}+{{ msg.itemResult.bonus }}
                  </span>
                  <!-- Use -->
                  <span v-else-if="msg.itemAction === 'use'" class="text-cyan-600">
                    {{ msg.itemResult.item }} · {{ msg.itemResult.hint }}
                  </span>
                  <!-- Shop -->
                  <div v-else-if="msg.itemAction === '商店' && msg.itemResult.shop" class="mt-1 space-y-0.5 max-h-40 overflow-y-auto">
                    <div v-for="(items, cat) in msg.itemResult.shop" :key="cat" class="text-[10px]">
                      <span class="font-medium text-slate-600">{{ cat }}</span>
                      <span v-for="it in items.slice(0,3)" :key="it.key" class="ml-1 text-slate-400">{{ it.name }}({{ it.buy }}币)</span>
                    </div>
                    <div class="text-[10px] text-slate-400 mt-0.5">共{{ Object.values(msg.itemResult.shop).flat().length }}件道具，/道具 库存 查看已拥有</div>
                  </div>
                  <!-- Inventory -->
                  <div v-else-if="msg.itemAction === '库存'" class="mt-1 text-[10px]">
                    <div v-if="msg.itemResult.equipped" class="text-green-600 font-medium">装备中: {{ msg.itemResult.equipped.name }}</div>
                    <div v-if="msg.itemResult.inventory.length === 0" class="text-slate-400">空空如也，从黑市 /购买 或等群友 /赠予</div>
                    <div v-for="inv in msg.itemResult.inventory.slice(0,8)" :key="inv.item_key" class="text-slate-500">
                      {{ inv.name }} x{{ inv.quantity }} · {{ inv.rarity }}
                    </div>
                  </div>
                </div>

                <!-- Train result -->
                <div v-if="msg.resultType === 'train' && !msg.error"
                  class="px-3 py-2 rounded-xl rounded-tl-sm text-xs"
                  :class="msg.trainResult?.increased
                    ? 'bg-orange-50 border border-orange-200'
                    : 'bg-slate-100 border border-slate-200'">
                  <span class="font-medium"
                    :class="msg.trainResult?.increased ? 'text-orange-700' : 'text-slate-500'">
                    🏋️ 训练{{ msg.trainAttr }}
                    {{ msg.trainResult?.increased ? '成功!' : '失败' }}
                    ({{ msg.trainResult?.old_val }}→{{ msg.trainResult?.new_val }})
                  </span>
                  <span class="text-slate-400 ml-1">消耗{{ msg.trainResult?.coin_cost }}鳞币</span>
                </div>

                <!-- Battle result -->
                <div v-if="msg.resultType === 'battle' && !msg.error"
                  class="px-3 py-2 rounded-xl rounded-tl-sm text-xs"
                  :class="msg.battleWinner === msg.wxid
                    ? 'bg-green-50 border border-green-200'
                    : 'bg-red-50 border border-red-200'">
                  <span class="font-medium"
                    :class="msg.battleWinner === msg.wxid ? 'text-green-700' : 'text-red-700'">
                    ⚔️ {{ msg.battleWinner === msg.wxid ? '你赢了！' : '你输了...' }}
                  </span>
                  <span class="text-slate-500 ml-1">vs {{ msg.targetName }}</span>
                </div>

                <!-- Rename -->
                <div v-if="msg.resultType === 'rename'"
                  class="px-3 py-2 rounded-xl rounded-tl-sm bg-indigo-50 border border-indigo-200 text-xs">
                  <span class="text-indigo-700">✏️ 改名成功 → {{ msg.newName }}</span>
                </div>

                <!-- Pond view -->
                <div v-if="msg.resultType === 'pond'"
                  class="px-3 py-2 rounded-xl rounded-tl-sm bg-slate-100 text-xs text-slate-600">
                  🐟 查看了鱼塘
                </div>
              </div>
            </div>

            <!-- Error -->
            <div v-if="msg.error" class="flex items-start gap-2">
              <div class="w-7 h-7 rounded-full bg-red-100 flex items-center justify-center shrink-0 mt-1">
                <X :size="12" class="text-red-500" />
              </div>
              <div class="px-3 py-1.5 rounded-xl rounded-tl-sm bg-red-50 border border-red-200 text-xs text-red-600">
                ❌ {{ msg.error }}
              </div>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="loading" class="flex items-center gap-2 text-xs text-slate-400 px-1">
            <Dices :size="14" class="animate-spin" />
            正在掷 D20...
          </div>
        </div>

        <!-- Quick Commands -->
        <div class="px-3 py-2 border-t border-slate-100 bg-white shrink-0">
          <div class="flex flex-wrap gap-1">
            <button v-for="cmd in COMMANDS.slice(0, 6)" :key="cmd.cmd"
              @click="quickCommand(cmd.cmd + (cmd.cmd.endsWith(' ') ? '' : ''))"
              class="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium transition"
              :class="cmd.color">
              <span>{{ cmd.icon }}</span>
              <span>{{ cmd.cmd.split(' ')[0] }}</span>
            </button>
            <button
              @click="input = '/'"
              class="flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium
                     bg-slate-100 text-slate-500 hover:bg-slate-200 transition">
              ···
            </button>
          </div>
        </div>

        <!-- Input -->
        <div class="px-3 py-2 border-t border-slate-200 bg-white shrink-0 relative">
          <div class="flex items-center gap-2">
            <div class="flex-1 relative">
              <input
                id="simulator-input"
                v-model="input"
                @input="onInputChange"
                @keydown="handleKeydown"
                :disabled="loading || !selectedWxid"
                :placeholder="selectedWxid ? '输入 / 指令...' : '请先选择成员'"
                class="w-full px-3 py-2 text-sm border border-slate-300 rounded-lg
                       focus:outline-none focus:ring-2 focus:ring-slate-400 focus:border-transparent
                       disabled:bg-slate-50 disabled:text-slate-400"
              />
              <!-- Command autocomplete dropdown -->
              <Transition name="fade">
                <div v-if="showCommands && filteredCommands.length > 0"
                  class="absolute bottom-full left-0 right-0 mb-1 bg-white border border-slate-200
                         rounded-lg shadow-lg max-h-48 overflow-y-auto z-10">
                  <button v-for="cmd in filteredCommands" :key="cmd.cmd"
                    @click="selectCommand(cmd.cmd)"
                    class="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-slate-50 transition text-xs">
                    <span class="text-base">{{ cmd.icon }}</span>
                    <span class="font-mono font-medium text-slate-700">{{ cmd.cmd }}</span>
                    <span class="text-slate-400 ml-auto">{{ cmd.desc }}</span>
                  </button>
                </div>
              </Transition>
            </div>
            <button
              @click="sendCommand"
              :disabled="loading || !input.trim() || !selectedWxid"
              class="p-2 bg-slate-800 text-white rounded-lg hover:bg-slate-700
                     disabled:opacity-30 disabled:cursor-not-allowed transition shrink-0">
              <Send :size="16" />
            </button>
          </div>
          <div class="text-[10px] text-slate-400 mt-1 px-1">
            输入 <kbd class="px-1 py-0.5 bg-slate-100 rounded text-[9px]">/</kbd> 查看指令 ·
            <kbd class="px-1 py-0.5 bg-slate-100 rounded text-[9px]">Tab</kbd> 补全 ·
            <kbd class="px-1 py-0.5 bg-slate-100 rounded text-[9px]">Enter</kbd> 发送
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px) scale(0.95);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
