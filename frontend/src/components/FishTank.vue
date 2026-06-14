<script setup>
import { ref } from 'vue'
import { Icon } from '@iconify/vue'

const props = defineProps({
  fish: { type: Array, default: () => [] },
  deadFish: { type: Array, default: () => [] },
})

const emit = defineEmits(['fish-click', 'adopt'])

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

function isIconify(f) {
  const emoji = f?.emoji_variant || speciesEmoji[f?.species] || '🐟'
  return emoji.includes(':')
}

function fishEmoji(f) {
  return f?.emoji_variant || speciesEmoji[f?.species] || '🐟'
}

const stageScale = { '鱼苗': 0.6, '幼鱼': 0.8, '成鱼': 1.0, '大鱼': 1.3, '传说': 1.6 }
const stageOpacity = { '鱼苗': 0.7, '幼鱼': 0.85, '成鱼': 1, '大鱼': 1, '传说': 1 }

function getStyle(f, index) {
  const scale = stageScale[f.stage] || 1
  const opacity = stageOpacity[f.stage] || 1
  // Random but deterministic positioning
  const seed = (f.wxid || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const left = 5 + (seed % 85)
  const top = 5 + ((seed * 7) % 80)
  const delay = (index * 0.7) % 10
  const duration = 8 + (seed % 8)

  return {
    position: 'absolute',
    left: `${left}%`,
    top: `${top}%`,
    transform: `scale(${scale})`,
    opacity,
    animationDelay: `${delay}s`,
    animationDuration: `${duration}s`,
    cursor: 'pointer',
  }
}

function getAnimation(f) {
  const seed = (f.wxid || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const name = seed % 3 === 0 ? 'swim1' : seed % 3 === 1 ? 'swim2' : 'swim3'
  return name
}
</script>

<template>
  <div class="bg-gradient-to-b from-sky-100 via-cyan-50 to-blue-100 rounded-xl border border-sky-200 overflow-hidden">
    <!-- Tank decor -->
    <div class="h-2 bg-gradient-to-r from-sky-300 via-cyan-300 to-sky-300"></div>

    <!-- Fish swimming area -->
    <div class="relative h-[450px] overflow-hidden"
      style="background: linear-gradient(180deg, #e0f2fe 0%, #bae6fd 30%, #7dd3fc 60%, #38bdf8 100%)">
      <!-- Bubbles -->
      <div v-for="i in 8" :key="'bubble-'+i"
        class="bubble absolute"
        :style="{
          left: `${5 + i * 11}%`,
          animationDelay: `${i * 0.8}s`,
          animationDuration: `${3 + i * 0.5}s`
        }">
      </div>

      <!-- Seaweed -->
      <div v-for="i in 5" :key="'weed-'+i"
        class="seaweed absolute bottom-0"
        :style="{ left: `${2 + i * 19}%`, height: `${40 + i * 15}px` }">
      </div>

      <!-- Sand bottom -->
      <div class="absolute bottom-0 left-0 right-0 h-12 bg-gradient-to-t from-amber-200/60 to-transparent"></div>

      <!-- Fish -->
      <div
        v-for="(f, i) in fish"
        :key="f.wxid || i"
        :class="['fish-sprite', getAnimation(f)]"
        :style="getStyle(f, i)"
        @click="$emit('fish-click', f)"
        :title="f.fish_name"
      >
        <Icon v-if="isIconify(f)" :icon="fishEmoji(f)" class="text-3xl drop-shadow-md" />
        <span v-else class="text-3xl select-none drop-shadow-md">{{ fishEmoji(f) }}</span>
        <span class="block text-[10px] text-slate-700 font-medium truncate max-w-[60px] text-center"
          :class="{
            'text-slate-500': f.rarity === '普通',
            'text-blue-600': f.rarity === '稀有',
            'text-purple-600': f.rarity === '史诗',
            'text-orange-500': f.rarity === '传说',
          }">
          {{ f.fish_name?.replace(/的.*/, '') || '' }}
        </span>
      </div>

      <!-- Empty tank message -->
      <div v-if="fish.length === 0" class="absolute inset-0 flex items-center justify-center">
        <p class="text-slate-400 text-sm">鱼塘空空如也，点击上方"结算"或"解析指令"来引入鱼群</p>
      </div>
    </div>

    <!-- Dead fish memorial -->
    <div v-if="deadFish.length" class="bg-slate-800/90 p-3 border-t border-slate-700">
      <p class="text-xs text-slate-400">
        🪦 纪念: <span v-for="(f, i) in deadFish" :key="i" class="text-slate-500">
          {{ f.fish_name }}{{ i < deadFish.length - 1 ? ' · ' : '' }}
        </span>
      </p>
    </div>
  </div>
</template>

<style scoped>
.bubble {
  width: 8px;
  height: 8px;
  background: rgba(255, 255, 255, 0.5);
  border-radius: 50%;
  bottom: -10px;
  animation: bubble-up 4s ease-in infinite;
}

@keyframes bubble-up {
  0% { transform: translateY(0) scale(1); opacity: 0.6; }
  100% { transform: translateY(-480px) scale(0.5); opacity: 0; }
}

.seaweed {
  width: 12px;
  background: linear-gradient(to top, #15803d, #22c55e, #4ade80);
  border-radius: 50% 50% 0 0;
  animation: sway 3s ease-in-out infinite;
  transform-origin: bottom center;
}

@keyframes sway {
  0%, 100% { transform: rotate(-5deg); }
  50% { transform: rotate(8deg); }
}

.fish-sprite {
  transition: transform 0.3s ease;
  z-index: 10;
}

.fish-sprite:hover {
  transform: scale(1.3) !important;
  z-index: 30;
}

.swim1 {
  animation: swim-horizontal 10s ease-in-out infinite;
}

.swim2 {
  animation: swim-diagonal 12s ease-in-out infinite;
}

.swim3 {
  animation: swim-vertical 9s ease-in-out infinite;
}

@keyframes swim-horizontal {
  0%, 100% { transform: translate(0, 0) scaleX(1); }
  25% { transform: translate(60px, -20px) scaleX(1); }
  50% { transform: translate(-30px, 10px) scaleX(-1); }
  75% { transform: translate(-50px, -15px) scaleX(-1); }
}

@keyframes swim-diagonal {
  0%, 100% { transform: translate(0, 0) scaleX(1); }
  25% { transform: translate(40px, -35px) scaleX(1); }
  50% { transform: translate(-20px, 15px) scaleX(-1); }
  75% { transform: translate(-60px, -25px) scaleX(-1); }
}

@keyframes swim-vertical {
  0%, 100% { transform: translate(0, 0) scaleX(1); }
  25% { transform: translate(30px, -40px) scaleX(1); }
  50% { transform: translate(-40px, 0) scaleX(-1); }
  75% { transform: translate(-20px, -30px) scaleX(-1); }
}
</style>
