<script setup>
import { ref, computed, watch } from 'vue'
import { Crown, Heart, Star, Swords, TrendingUp } from 'lucide-vue-next'

const props = defineProps({
  fish: { type: Array, default: () => [] },
  sort: { type: String, default: 'growth' },
})

const emit = defineEmits(['update:sort', 'fish-click'])

const PAGE_SIZE = 10
const showCount = ref(PAGE_SIZE)

// Reset pagination when sort changes
watch(() => props.sort, () => { showCount.value = PAGE_SIZE })

const speciesEmoji = {
  goldfish: '🐟', koi: '🎏', clownfish: '🤡', betta: '🐠', arowana: '🐉',
  angelfish: '👼', pufferfish: '🐡', shark: '🦈', crocodile: '🐊', orca: '🐳',
  octopus: '🐙', squid: '🦑', crab: '🦀', lobster: '🦞', jellyfish: '🪼',
  shrimp: '🦐', mantis_shrimp: '🦐', conch: '🐚', nautilus: '🌀',
  oyster: '🦪', whale: '🐋', dolphin: '🐬', seal: '🦭', otter: '🦦',
  otter2: '🦦', walrus: '🦭', turtle: '🐢', frog: '🐸', axolotl: '🦎',
  mermaid: '🧜‍♀️', plesiosaur: '🦕', sea_snake: '🐍', sea_slug: '🐌',
  sturgeon: '🐟', eel: '⚡',
}

const sortOptions = [
  { key: 'growth', label: '最大鱼王', icon: Crown },
  { key: 'happiness', label: '最幸福鱼', icon: Heart },
  { key: 'experience', label: '经验最高', icon: Star },
  { key: 'strength', label: '最强力量', icon: Swords },
]

const allRanked = computed(() => {
  const sorted = [...props.fish].sort((a, b) => (b[props.sort] || 0) - (a[props.sort] || 0))
  return sorted
})
const visibleRanked = computed(() => allRanked.value.slice(0, showCount.value))
const hasMore = computed(() => showCount.value < allRanked.value.length)
function showMore() { showCount.value += PAGE_SIZE }
</script>

<template>
  <div>
    <h3 class="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-1.5">
      <TrendingUp :size="14" class="text-amber-500" /> 排行榜
    </h3>

    <!-- Sort tabs -->
    <div class="flex flex-wrap gap-1 mb-3">
      <button v-for="opt in sortOptions" :key="opt.key"
        @click="$emit('update:sort', opt.key)"
        class="flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium transition"
        :class="sort === opt.key
          ? 'bg-amber-100 text-amber-700'
          : 'text-slate-500 hover:bg-slate-50'">
        <component :is="opt.icon" :size="12" />
        {{ opt.label }}
      </button>
    </div>

    <!-- Rank list -->
    <div v-if="visibleRanked.length" class="space-y-1">
      <div v-for="(f, i) in visibleRanked" :key="f.wxid || i"
        @click="$emit('fish-click', f)"
        class="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-slate-50 cursor-pointer transition text-xs">
        <!-- Rank -->
        <span class="w-5 text-center font-bold"
          :class="{
            'text-amber-500': i === 0,
            'text-slate-400': i === 1,
            'text-amber-700': i === 2,
            'text-slate-400': i > 2,
          }">
          {{ i <= 2 ? ['🥇','🥈','🥉'][i] : i + 1 }}
        </span>
        <!-- Emoji -->
        <span class="text-base">{{ speciesEmoji[f.species] || '🐟' }}</span>
        <!-- Name + value -->
        <span class="flex-1 truncate text-slate-700">{{ f.fish_name?.replace(/的.*/, '') || '' }}</span>
        <span class="font-mono font-semibold text-slate-500">
          {{ sort === 'growth' ? f.growth?.toFixed(0) || 0 :
             sort === 'happiness' ? f.happiness?.toFixed(0) || 0 :
             sort === 'experience' ? f.experience || 0 :
             f[sort] || 0 }}
        </span>
      </div>
    </div>
    <div v-else class="text-center py-4 text-xs text-slate-400">
      暂无数据
    </div>
    <!-- Show more -->
    <div v-if="hasMore" class="text-center pt-2">
      <button @click="showMore"
        class="text-xs font-medium text-indigo-500 hover:text-indigo-600 hover:bg-indigo-50 px-4 py-1.5 rounded-lg transition">
        展开更多（{{ allRanked.length - showCount }} 条剩余）
      </button>
    </div>
  </div>
</template>
