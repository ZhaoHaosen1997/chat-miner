<script setup>
import { ref, computed } from 'vue'
import { X, Dices, Droplets, Hand, Search, Gem, Sword, Share2, Edit3 } from 'lucide-vue-next'

const props = defineProps({
  fish: Object,
  loading: String,
  groupId: Number,
})

const emit = defineEmits(['close', 'action', 'refresh'])

const showRename = ref(false)
const renameInput = ref('')
const showBattle = ref(false)
const battleTarget = ref('')

const speciesEmoji = {
  goldfish: '🐟', koi: '🎏', clownfish: '🤡', betta: '🐠', arowana: '🐉',
  angelfish: '👼', pufferfish: '🐡', shark: '🦈', crocodile: '🐊', orca: '🐳',
  octopus: '🐙', squid: '🦑', crab: '🦀', lobster: '🦞', jellyfish: '🪼',
  shrimp: '🦐', whale: '🐋', dolphin: '🐬', seal: '🦭', otter: '🦦',
  turtle: '🐢', frog: '🐸', axolotl: '🦎',
}

const speciesInfo = computed(() => props.fish?.species_info || {})

function abilityMod(score) {
  const m = Math.floor((score - 10) / 2)
  return m >= 0 ? `+${m}` : `${m}`
}

const attrConfig = [
  { key: 'strength', label: '力量', abbr: 'STR', icon: '💪', color: '#EF4444' },
  { key: 'dexterity', label: '敏捷', abbr: 'DEX', icon: '🏃', color: '#22C55E' },
  { key: 'constitution', label: '体质', abbr: 'CON', icon: '❤️', color: '#3B82F6' },
  { key: 'intelligence', label: '智力', abbr: 'INT', icon: '🧠', color: '#A855F7' },
  { key: 'wisdom', label: '感知', abbr: 'WIS', icon: '👁️', color: '#EAB308' },
  { key: 'charisma', label: '魅力', abbr: 'CHA', icon: '💋', color: '#EC4899' },
]

const rarityGradient = computed(() => {
  const map = {
    '普通': 'from-gray-400 to-gray-500',
    '稀有': 'from-blue-400 to-blue-600',
    '史诗': 'from-purple-400 to-purple-600',
    '传说': 'from-orange-400 to-amber-500',
  }
  return map[props.fish?.rarity] || map['普通']
})

const xpProgress = computed(() => {
  const xp = props.fish?.experience || 0
  const lv = props.fish?.level || 1
  // XP table based
  const xpTable = [0, 100, 300, 600, 1000, 1500, 2100, 2800, 3600, 4500]
  const currentLevelXp = xpTable[lv - 1] || 0
  const nextLevelXp = xpTable[lv] || xpTable[xpTable.length - 1] + 1500
  const pct = Math.min(100, Math.round(((xp - currentLevelXp) / (nextLevelXp - currentLevelXp)) * 100))
  return { pct, next: nextLevelXp, current: xp }
})

function emitAction(action, extra) {
  emit('action', action, props.fish.wxid, extra)
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="$emit('close')">
    <div class="bg-white rounded-2xl shadow-2xl w-[420px] max-h-[90vh] overflow-y-auto">
      <!-- Header -->
      <div class="relative p-6 pb-4">
        <button @click="$emit('close')" class="absolute top-4 right-4 p-1 hover:bg-slate-100 rounded">
          <X :size="20" class="text-slate-400" />
        </button>
        <div class="flex items-center gap-4">
          <div class="text-5xl">{{ speciesEmoji[fish.species] || '🐟' }}</div>
          <div>
            <h2 class="text-lg font-bold text-slate-800">{{ fish.fish_name }}</h2>
            <div class="flex items-center gap-2 mt-1">
              <span class="text-sm text-slate-500">{{ speciesInfo.name || fish.species }}</span>
              <span class="px-1.5 py-0.5 rounded text-xs font-medium text-white"
                :class="{
                  'bg-gray-400': fish.rarity === '普通',
                  'bg-blue-500': fish.rarity === '稀有',
                  'bg-purple-500': fish.rarity === '史诗',
                  'bg-orange-500': fish.rarity === '传说',
                }">
                {{ fish.rarity }}
              </span>
              <span class="text-xs text-slate-400">Lv{{ fish.level }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- D&D Hex Attributes -->
      <div class="px-6 pb-4">
        <h3 class="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wider">D&D 属性面板</h3>
        <div class="grid grid-cols-3 gap-2">
          <div v-for="attr in attrConfig" :key="attr.key"
            class="rounded-lg p-2.5 text-center border"
            :style="{ borderColor: attr.color + '40', background: attr.color + '08' }">
            <div class="text-lg">{{ attr.icon }}</div>
            <div class="text-[10px] text-slate-400">{{ attr.abbr }}</div>
            <div class="text-lg font-bold" :style="{ color: attr.color }">
              {{ fish[attr.key] || 0 }}
            </div>
            <div class="text-xs font-medium"
              :style="{ color: attr.color }">
              {{ abilityMod(fish[attr.key] || 0) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Proficiencies -->
      <div v-if="fish.proficiencies?.length" class="px-6 pb-4">
        <div class="flex items-center gap-1.5 text-xs text-slate-400">
          <Dices :size="14" /> 熟练项:
          <span v-for="p in fish.proficiencies" :key="p"
            class="px-1.5 py-0.5 bg-slate-100 rounded text-slate-600 text-[10px]">
            {{ {athletics:'运动', acrobatics:'特技', endurance:'坚韧', investigation:'调查',
               nature:'自然', performance:'表演', stealth:'隐匿', insight:'洞悉',
               intimidation:'威吓'}[p] || p }}
          </span>
        </div>
      </div>

      <!-- Stats bars -->
      <div class="px-6 pb-4 space-y-2">
        <div>
          <div class="flex justify-between text-xs text-slate-500 mb-1">
            <span>成长值</span>
            <span>{{ fish.growth?.toFixed(0) || 0 }}</span>
          </div>
          <div class="h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div class="h-full bg-gradient-to-r rounded-full transition-all"
              :class="rarityGradient"
              :style="{ width: `${Math.min(100, (fish.growth || 0) / 50)}%` }">
            </div>
          </div>
        </div>
        <div>
          <div class="flex justify-between text-xs text-slate-500 mb-1">
            <span>幸福值</span>
            <span>{{ fish.happiness?.toFixed(0) || 0 }}/100</span>
          </div>
          <div class="h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div class="h-full bg-gradient-to-r from-pink-400 to-rose-400 rounded-full transition-all"
              :style="{ width: `${fish.happiness || 0}%` }">
            </div>
          </div>
        </div>
        <div>
          <div class="flex justify-between text-xs text-slate-500 mb-1">
            <span>经验值 ({{ fish.level === 10 ? 'MAX' : `Lv${fish.level}→${fish.level+1}` }})</span>
            <span>{{ fish.experience || 0 }}{{ fish.level < 10 ? ` / ${xpProgress.next}` : '' }}</span>
          </div>
          <div class="h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div class="h-full bg-gradient-to-r from-cyan-400 to-blue-400 rounded-full transition-all"
              :style="{ width: `${xpProgress.pct}%` }">
            </div>
          </div>
        </div>
        <div>
          <div class="flex justify-between text-xs text-slate-500 mb-1">
            <span>HP</span>
            <span>{{ fish.hp || 0 }}</span>
          </div>
          <div class="h-1.5 bg-slate-100 rounded-full overflow-hidden">
            <div class="h-full bg-gradient-to-r from-red-400 to-red-500 rounded-full transition-all"
              :style="{ width: `${Math.min(100, ((fish.hp || 0) / 50) * 100)}%` }">
            </div>
          </div>
        </div>
        <div class="flex justify-between text-xs text-slate-400">
          <span>阶段: <b class="text-slate-600">{{ fish.stage }}</b></span>
          <span>连活: <b class="text-slate-600">{{ fish.consecutive_days || 0 }}天</b></span>
        </div>
      </div>

      <!-- Actions -->
      <div class="px-6 pb-4">
        <h3 class="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wider">互动指令</h3>
        <div class="grid grid-cols-3 gap-2">
          <button @click="emitAction('feed')" :disabled="!!loading"
            class="flex items-center justify-center gap-1 px-2 py-2 rounded-lg text-xs font-medium
                   bg-sky-50 text-sky-700 hover:bg-sky-100 disabled:opacity-50 border border-sky-200 transition">
            🎲 /喂食
          </button>
          <button @click="emitAction('clean')" :disabled="!!loading"
            class="flex items-center justify-center gap-1 px-2 py-2 rounded-lg text-xs font-medium
                   bg-teal-50 text-teal-700 hover:bg-teal-100 disabled:opacity-50 border border-teal-200 transition">
            🪣 /换水
          </button>
          <button @click="emitAction('touch')" :disabled="!!loading"
            class="flex items-center justify-center gap-1 px-2 py-2 rounded-lg text-xs font-medium
                   bg-pink-50 text-pink-700 hover:bg-pink-100 disabled:opacity-50 border border-pink-200 transition">
            👆 /摸鱼
          </button>
          <button @click="emitAction('explore')" :disabled="!!loading"
            class="flex items-center justify-center gap-1 px-2 py-2 rounded-lg text-xs font-medium
                   bg-amber-50 text-amber-700 hover:bg-amber-100 disabled:opacity-50 border border-amber-200 transition">
            🔍 /探索
          </button>
          <button @click="emitAction('treasure')" :disabled="!!loading"
            class="flex items-center justify-center gap-1 px-2 py-2 rounded-lg text-xs font-medium
                   bg-yellow-50 text-yellow-700 hover:bg-yellow-100 disabled:opacity-50 border border-yellow-200 transition">
            💎 /寻宝
          </button>
          <button @click="emitAction('showoff')" :disabled="!!loading"
            class="flex items-center justify-center gap-1 px-2 py-2 rounded-lg text-xs font-medium
                   bg-purple-50 text-purple-700 hover:bg-purple-100 disabled:opacity-50 border border-purple-200 transition">
            📸 /晒鱼
          </button>
        </div>
        <!-- Battle & Rename row -->
        <div class="flex gap-2 mt-2">
          <div class="flex-1">
            <div v-if="!showBattle" class="flex gap-2">
              <button @click="showBattle = true"
                class="flex-1 flex items-center justify-center gap-1 px-2 py-2 rounded-lg text-xs font-medium
                       bg-red-50 text-red-700 hover:bg-red-100 border border-red-200 transition">
                ⚔️ /斗鱼
              </button>
              <button @click="showRename = !showRename"
                class="flex items-center justify-center gap-1 px-2 py-2 rounded-lg text-xs font-medium
                       bg-slate-100 text-slate-600 hover:bg-slate-200 border border-slate-200 transition">
                <Edit3 :size="12" />
              </button>
            </div>
            <div v-else class="flex gap-1">
              <input v-model="battleTarget" placeholder="对手wxid"
                class="flex-1 px-2 py-1.5 text-xs border rounded-lg focus:outline-none focus:ring-1 focus:ring-red-300" />
              <button @click="emitAction('battle', battleTarget); showBattle = false; battleTarget = ''"
                class="px-2 py-1.5 text-xs bg-red-500 text-white rounded-lg hover:bg-red-600">GO</button>
              <button @click="showBattle = false" class="px-2 py-1.5 text-xs border rounded-lg">取消</button>
            </div>
          </div>
        </div>
        <!-- Rename input -->
        <div v-if="showRename" class="flex gap-1 mt-2">
          <input v-model="renameInput" placeholder="新名字"
            class="flex-1 px-2 py-1.5 text-xs border rounded-lg focus:outline-none focus:ring-1 focus:ring-blue-300" />
          <button @click="emitAction('rename', renameInput); showRename = false; renameInput = ''"
            class="px-3 py-1.5 text-xs bg-blue-500 text-white rounded-lg hover:bg-blue-600">确认</button>
        </div>
      </div>
    </div>
  </div>
</template>
