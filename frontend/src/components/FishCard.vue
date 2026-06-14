<script setup>
import { ref, computed } from 'vue'
import { X, Dices, Trash2 } from 'lucide-vue-next'
import { Icon } from '@iconify/vue'
import EnergyBar from './EnergyBar.vue'

const props = defineProps({
  fish: Object,
  loading: String,
  groupId: Number,
})

const emit = defineEmits(['close', 'action', 'refresh'])

const showDeleteConfirm = ref(false)

const speciesEmoji = {
  goldfish: '🐟', koi: '🎏', clownfish: '🤡', betta: '🐠', arowana: '🐉',
  angelfish: '👼', pufferfish: '🐡', shark: '🦈', crocodile: '🐊', orca: '🐳',
  octopus: '🐙', squid: '🦑', crab: '🦀', lobster: '🦞', jellyfish: '🪼',
  shrimp: '🦐', whale: '🐋', dolphin: '🐬', seal: '🦭', otter: '🦦',
  turtle: '🐢', frog: '🐸', axolotl: '🦎',
  // v1.16.0: new iconify species
  seahorse: 'mdi:seahorse', manta: 'mdi:stingray', urchin: 'mdi:sea-urchin',
  starfish: 'twemoji:starfish', mantis_shrimp: 'twemoji:shrimp',
  conch: 'twemoji:conch-shell', otter2: 'twemoji:otter', walrus: 'twemoji:walrus',
}

const speciesInfo = computed(() => props.fish?.species_info || {})

const isIconifyEmoji = computed(() => {
  const emoji = props.fish?.emoji_variant || speciesEmoji[props.fish?.species] || '🐟'
  return emoji.includes(':')
})

const displayEmoji = computed(() => {
  return props.fish?.emoji_variant || speciesEmoji[props.fish?.species] || '🐟'
})

const personalityTraits = computed(() => {
  const raw = props.fish?.personality_traits
  if (!raw) return []
  // 可能是 JSON 字符串或已解析的数组
  if (typeof raw === 'string') {
    try { return JSON.parse(raw) } catch { return [] }
  }
  return Array.isArray(raw) ? raw : []
})

// v1.16.0: 性格图标映射（前端 JSON 字符串解析后需要查表）
const traitIcons = {
  '勇敢': '🦁', '好奇': '🔍', '活泼': '🤸', '勤奋': '💪', '谨慎': '🛡️',
  '乐天': '😊', '傲娇': '💅', '贪吃': '🍔', '社牛': '🎤', '胆小': '😨',
  '懒惰': '😴', '暴躁': '💢', '沉稳': '🧘', '机灵': '🧠', '粘人': '🥰',
  '孤僻': '🏚️', '贪睡': '😴', '迷糊': '😵', '浪漫': '💕',
  '倔强': '🤨', '戏精': '🎪', '冒险家': '🧭',
}
function traitIcon(name) {
  return traitIcons[name] || '🎭'
}

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

function confirmDelete() {
  emit('action', 'delete', props.fish.wxid)
  showDeleteConfirm.value = false
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
          <div class="text-5xl">
            <Icon v-if="isIconifyEmoji" :icon="displayEmoji" :width="40" />
            <span v-else>{{ displayEmoji }}</span>
          </div>
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
            <!-- v1.16.0: 性格标签 -->
            <div v-if="personalityTraits?.length" class="flex flex-wrap gap-1 mt-2">
              <span v-for="trait in personalityTraits" :key="(typeof trait === 'string' ? trait : trait.key)"
                class="px-1.5 py-0.5 rounded-full text-[10px] font-medium
                       bg-gradient-to-r from-indigo-50 to-purple-50 text-indigo-600 border border-indigo-100">
                {{ typeof trait === 'string' ? traitIcon(trait) + ' ' + trait : (trait.icon || '🎭') + ' ' + trait.key }}
              </span>
            </div>
          </div>
        </div>
      </div>

      <!-- 属性面板 -->
      <div class="px-6 pb-4">
        <h3 class="text-xs font-semibold text-slate-500 mb-2 uppercase tracking-wider">属性面板</h3>
        <div class="grid grid-cols-3 gap-2">
          <div v-for="attr in attrConfig" :key="attr.key"
            class="rounded-lg p-2.5 text-center border"
            :style="{ borderColor: attr.color + '40', background: attr.color + '08' }">
            <div class="text-lg">{{ attr.icon }}</div>
            <div class="text-[10px]" :style="{ color: attr.color }">{{ attr.label }}</div>
            <div class="text-lg font-bold text-slate-800">
              {{ fish[attr.key] || 0 }}
            </div>
            <div class="text-[10px] font-medium text-slate-400">
              调整 {{ abilityMod(fish[attr.key] || 0) }}
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
        <!-- v1.16.0: 精力条 -->
        <EnergyBar
          :current="fish.energy || 100"
          :max="fish.max_energy || 100"
          label="精力"
          color="#22C55E"
        />
        <div class="flex justify-between text-xs text-slate-400">
          <span>阶段: <b class="text-slate-600">{{ fish.stage }}</b></span>
          <span>连活: <b class="text-slate-600">{{ fish.consecutive_days || 0 }}天</b></span>
        </div>
      </div>

      <!-- Delete -->
      <div class="px-6 pb-4">
        <div v-if="!showDeleteConfirm">
          <button @click="showDeleteConfirm = true"
            class="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs
                   text-slate-400 hover:text-red-500 hover:bg-red-50 border border-slate-200 hover:border-red-200 transition">
            <Trash2 :size="14" />
            删除此鱼
          </button>
        </div>
        <div v-else class="flex gap-2">
          <button @click="confirmDelete"
            class="flex-1 px-3 py-2 rounded-lg text-xs font-medium bg-red-500 text-white hover:bg-red-600 transition">
            确认删除
          </button>
          <button @click="showDeleteConfirm = false"
            class="flex-1 px-3 py-2 rounded-lg text-xs border border-slate-200 text-slate-500 hover:bg-slate-50 transition">
            取消
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
