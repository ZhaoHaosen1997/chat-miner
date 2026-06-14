<script setup>
import { Icon } from '@iconify/vue'

const props = defineProps({
  fish: { type: Array, default: () => [] },
  deadFish: { type: Array, default: () => [] },
  weather: { type: Object, default: null },
})

const emit = defineEmits(['fish-click', 'adopt'])

const speciesEmoji = {
  goldfish: '🐟', koi: '🎏', clownfish: '🤡', betta: '🐠', arowana: '🐉',
  angelfish: '👼', pufferfish: '🐡', shark: '🦈', crocodile: '🐊', orca: '🐳',
  octopus: '🐙', squid: '🦑', crab: '🦀', lobster: '🦞', jellyfish: '🪼',
  shrimp: '🦐', whale: '🐋', dolphin: '🐬', seal: '🦭', otter: '🦦',
  turtle: '🐢', frog: '🐸', axolotl: '🦎',
  seahorse: '🐟', manta: '🐟', urchin: '🐟', starfish: '⭐',
  mantis_shrimp: '🦐', conch: '🐚', otter2: '🦦', walrus: '🦭',
}

const rarityGlow = {
  '普通': '',
  '稀有': 'drop-shadow-[0_0_6px_rgba(59,130,246,0.5)]',
  '史诗': 'drop-shadow-[0_0_8px_rgba(168,85,247,0.5)]',
  '传说': 'drop-shadow-[0_0_10px_rgba(251,191,36,0.6)]',
}

function isIconify(f) {
  const emoji = f?.emoji_variant || speciesEmoji[f?.species] || '🐟'
  return emoji.includes(':')
}
function fishEmoji(f) {
  return f?.emoji_variant || speciesEmoji[f?.species] || '🐟'
}

const stageScale = { '鱼苗': 0.55, '幼鱼': 0.75, '成鱼': 1.0, '大鱼': 1.25, '传说': 1.5 }
const stageOpacity = { '鱼苗': 0.6, '幼鱼': 0.8, '成鱼': 1, '大鱼': 1, '传说': 1 }

const lightRays = Array.from({ length: 6 }, (_, i) => ({
  left: 5 + i * 17,
  delay: i * 1.2,
  duration: 7 + i * 2,
}))

function getStyle(f, index) {
  const seed = (f.wxid || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  const left = 5 + (seed % 85)
  const top = 10 + ((seed * 7) % 70)
  const delay = (index * 0.7) % 10
  const duration = 8 + (seed % 8)
  return {
    position: 'absolute',
    left: `${left}%`,
    top: `${top}%`,
    animationDelay: `${delay}s`,
    animationDuration: `${duration}s`,
    cursor: 'pointer',
  }
}

function getAnimName(f) {
  const seed = (f.wxid || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
  return seed % 3 === 0 ? 'swim1' : seed % 3 === 1 ? 'swim2' : 'swim3'
}
</script>

<template>
  <div class="fish-tank-wrapper rounded-2xl overflow-hidden border border-slate-300/60 shadow-lg shadow-slate-300/40">
    <!-- Tank body -->
    <div class="tank-body relative h-[480px] overflow-hidden">
      <!-- Deep water gradient layers -->
      <div class="water-layer water-surface"></div>
      <div class="water-layer water-sunlit"></div>
      <div class="water-layer water-mid"></div>
      <div class="water-layer water-deep"></div>

      <!-- Light rays from surface -->
      <div
        v-for="ray in lightRays" :key="'ray-'+ray.left"
        class="light-ray"
        :style="{
          left: `${ray.left}%`,
          animationDelay: `${ray.delay}s`,
          animationDuration: `${ray.duration}s`,
        }">
      </div>

      <!-- Floating particles / plankton -->
      <div v-for="i in 12" :key="'particle-'+i"
        class="particle"
        :style="{
          left: `${3 + i * 7.5}%`,
          top: `${10 + (i * 13) % 70}%`,
          animationDelay: `${i * 0.6}s`,
          animationDuration: `${5 + i * 0.7}s`,
          width: `${2 + (i % 3)}px`,
          height: `${2 + (i % 3)}px`,
        }">
      </div>

      <!-- Bubbles -->
      <div v-for="i in 10" :key="'bubble-'+i"
        class="bubble"
        :style="{
          left: `${4 + i * 9}%`,
          animationDelay: `${i * 0.7}s`,
          animationDuration: `${3.5 + i * 0.6}s`,
          width: `${5 + (i % 6)}px`,
          height: `${5 + (i % 6)}px`,
        }">
      </div>

      <!-- Seaweed -->
      <div v-for="i in 6" :key="'weed-'+i"
        class="seaweed"
        :style="{
          left: `${1 + i * 16}%`,
          height: `${45 + i * 18}px`,
          animationDelay: `${i * 0.3}s`,
        }">
      </div>

      <!-- Sandy bottom with texture -->
      <div class="sandy-bottom">
        <div class="sand-texture"></div>
        <div class="sand-grains"></div>
      </div>

      <!-- Rocks -->
      <div class="rock rock-1"></div>
      <div class="rock rock-2"></div>
      <div class="rock rock-3"></div>

      <!-- Glass surface reflection (top overlay) -->
      <div class="glass-surface">
        <div class="glass-shine"></div>
        <div class="glass-ripple"></div>
      </div>

      <!-- Fish -->
      <div
        v-for="(f, i) in fish"
        :key="f.wxid || i"
        class="fish-sprite"
        :class="rarityGlow[f.rarity] || ''"
        :style="getStyle(f, i)"
        @click="$emit('fish-click', f)"
        :title="f.fish_name"
      >
        <!-- Swim mover: handles translate + scaleX flip on emoji only -->
        <div
          :class="['fish-mover', getAnimName(f) + '-pos']"
          :style="{
            animationDelay: getStyle(f, i).animationDelay,
            animationDuration: getStyle(f, i).animationDuration,
          }">
          <!-- Stage scale wrapper -->
          <div :style="{ transform: `scale(${stageScale[f.stage] || 1})`, opacity: stageOpacity[f.stage] || 1 }">
            <!-- Emoji with flip animation + fallback for failed icon loads -->
            <div
              :class="['fish-flip', getAnimName(f) + '-flip']"
              :style="{
                animationDelay: getStyle(f, i).animationDelay,
                animationDuration: getStyle(f, i).animationDuration,
              }">
              <span class="fish-icon-wrap">
                <Icon v-if="isIconify(f)" :icon="fishEmoji(f)" class="text-3xl fish-icon-svg" />
                <span v-else class="text-3xl select-none block">{{ fishEmoji(f) }}</span>
              </span>
            </div>
          </div>
          <!-- Name label -->
          <span class="fish-name-label"
            :class="{
              'text-slate-500': f.rarity === '普通',
              'text-blue-500': f.rarity === '稀有',
              'text-purple-500': f.rarity === '史诗',
              'text-amber-400': f.rarity === '传说',
            }">
            {{ f.fish_name?.replace(/的.*/, '') || '' }}
          </span>
          <!-- Bars: HP + Energy (two rows) -->
          <div class="fish-bars">
            <div class="fish-bar hp-bar" v-if="f.max_hp">
              <div class="fish-bar-fill hp-fill" :style="{ width: Math.max(0, Math.min(100, (f.hp || 0) / f.max_hp * 100)) + '%' }"></div>
            </div>
            <div class="fish-bar energy-bar" v-if="f.max_energy">
              <div class="fish-bar-fill energy-fill" :style="{ width: Math.max(0, Math.min(100, (f.energy || 0) / f.max_energy * 100)) + '%' }"></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty tank state -->
      <div v-if="fish.length === 0" class="absolute inset-0 flex items-center justify-center z-20">
        <div class="text-center">
          <span class="text-7xl block mb-3 opacity-50">🐟</span>
          <p class="text-slate-400/80 text-sm font-medium">鱼塘空空如也</p>
          <p class="text-slate-400/50 text-xs mt-1">在设置中开启静默鱼塘，或使用指令模拟器来引入鱼群</p>
        </div>
      </div>
    </div>

    <!-- Dead fish memorial -->
    <div v-if="deadFish.length" class="memorial-strip">
      <span class="memorial-icon">🪦</span>
      <span class="memorial-label">纪念</span>
      <span v-for="(f, i) in deadFish" :key="i"
        class="memorial-fish group relative">
        {{ f.fish_name?.replace(/的.*/, '') || f.fish_name }}
        <span v-if="f.death_info"
          class="memorial-tooltip">
          {{ f.death_info }}
        </span>
        <span v-if="i < deadFish.length - 1">·</span>
      </span>
    </div>
  </div>
</template>

<style scoped>
/* ===== Water gradient layers ===== */
.water-layer {
  position: absolute;
  inset: 0;
}
.water-surface {
  background: linear-gradient(180deg,
    rgba(186, 230, 253, 1) 0%,
    rgba(125, 211, 252, 0.95) 8%,
    rgba(56, 189, 248, 0.7) 20%,
    transparent 35%);
  z-index: 1;
}
.water-sunlit {
  background: linear-gradient(180deg,
    transparent 15%,
    rgba(14, 165, 233, 0.3) 30%,
    rgba(3, 105, 161, 0.5) 55%,
    transparent 70%);
  z-index: 0;
}
.water-mid {
  background: linear-gradient(180deg,
    transparent 40%,
    rgba(12, 74, 110, 0.6) 65%,
    rgba(8, 47, 73, 0.8) 85%,
    rgba(4, 30, 50, 0.95) 100%);
  z-index: 0;
}
.water-deep {
  background: linear-gradient(180deg,
    transparent 70%,
    rgba(2, 20, 38, 0.7) 90%,
    rgba(2, 16, 32, 0.9) 100%);
  z-index: 0;
}

/* ===== Light rays ===== */
.light-ray {
  position: absolute;
  top: 0;
  width: 8px;
  height: 100%;
  background: linear-gradient(180deg,
    rgba(255, 255, 255, 0.25) 0%,
    rgba(255, 255, 255, 0.08) 30%,
    transparent 70%);
  transform: skewX(-8deg);
  animation: ray-shift 8s ease-in-out infinite;
  z-index: 2;
  pointer-events: none;
}
@keyframes ray-shift {
  0%, 100% { opacity: 0.5; transform: skewX(-8deg) translateX(0); }
  50% { opacity: 0.8; transform: skewX(-8deg) translateX(8px); }
}

/* ===== Floating particles ===== */
.particle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.4);
  animation: particle-drift 6s ease-in-out infinite;
  z-index: 3;
  pointer-events: none;
}
@keyframes particle-drift {
  0%, 100% { transform: translate(0, 0); opacity: 0.2; }
  25% { transform: translate(8px, -12px); opacity: 0.6; }
  50% { transform: translate(-4px, -6px); opacity: 0.3; }
  75% { transform: translate(-10px, -18px); opacity: 0.5; }
}

/* ===== Bubbles ===== */
.bubble {
  position: absolute;
  bottom: -12px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%,
    rgba(255, 255, 255, 0.7),
    rgba(255, 255, 255, 0.15) 60%,
    transparent 70%);
  animation: bubble-rise 5s ease-in infinite;
  z-index: 4;
  pointer-events: none;
}
@keyframes bubble-rise {
  0% { transform: translateY(0) translateX(0) scale(1); opacity: 0.5; }
  30% { transform: translateY(-150px) translateX(6px) scale(1.1); opacity: 0.7; }
  70% { transform: translateY(-350px) translateX(-4px) scale(0.8); opacity: 0.3; }
  100% { transform: translateY(-500px) translateX(2px) scale(0.4); opacity: 0; }
}

/* ===== Seaweed ===== */
.seaweed {
  position: absolute;
  bottom: 0;
  width: 14px;
  background: linear-gradient(to top,
    #0f5c2e 0%, #16a34a 40%, #22c55e 70%, #4ade80 100%);
  border-radius: 50% 50% 0 0;
  animation: sway 3.5s ease-in-out infinite;
  transform-origin: bottom center;
  z-index: 5;
  opacity: 0.8;
}
@keyframes sway {
  0%, 100% { transform: rotate(-4deg) scaleX(1); }
  25% { transform: rotate(6deg) scaleX(0.9); }
  75% { transform: rotate(-7deg) scaleX(1.05); }
}

/* ===== Sandy bottom ===== */
.sandy-bottom {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 50px;
  background: linear-gradient(180deg,
    transparent 0%,
    rgba(194, 166, 128, 0.2) 15%,
    rgba(180, 148, 110, 0.5) 40%,
    rgba(160, 130, 95, 0.7) 70%,
    rgba(140, 112, 80, 0.85) 100%);
  z-index: 6;
}
.sand-texture {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle 1px, rgba(217, 196, 162, 0.6) 30%, transparent 70%) 10px 8px / 20px 12px,
    radial-gradient(circle 0.5px, rgba(217, 196, 162, 0.4) 30%, transparent 70%) 5px 4px / 15px 10px;
}
.sand-grains {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle 0.8px, rgba(255, 248, 220, 0.5) 30%, transparent 70%) 3px 10px / 25px 15px,
    radial-gradient(circle 0.6px, rgba(255, 248, 220, 0.3) 30%, transparent 70%) 12px 3px / 18px 14px;
}

/* ===== Rocks ===== */
.rock {
  position: absolute;
  bottom: 10px;
  border-radius: 40% 45% 35% 50%;
  z-index: 7;
  pointer-events: none;
}
.rock-1 {
  left: 8%;
  width: 40px;
  height: 28px;
  background: linear-gradient(135deg, #5c6b73, #3d4a52);
  box-shadow: inset 0 2px 4px rgba(255,255,255,0.1);
}
.rock-2 {
  left: 58%;
  width: 55px;
  height: 35px;
  background: linear-gradient(135deg, #4b5a62, #2d3a42);
  border-radius: 38% 42% 36% 45%;
  box-shadow: inset 0 2px 3px rgba(255,255,255,0.08);
}
.rock-3 {
  right: 10%;
  width: 32px;
  height: 22px;
  background: linear-gradient(135deg, #556068, #38454d);
  border-radius: 42% 38% 40% 44%;
}

/* ===== Glass surface ===== */
.glass-surface {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 35%;
  z-index: 20;
  pointer-events: none;
  overflow: hidden;
}
.glass-shine {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 100%;
  background: linear-gradient(180deg,
    rgba(255, 255, 255, 0.12) 0%,
    rgba(255, 255, 255, 0.06) 20%,
    rgba(255, 255, 255, 0.02) 50%,
    transparent 100%);
}
.glass-ripple {
  position: absolute;
  top: 8px;
  left: -10%;
  width: 30%;
  height: 60%;
  background: linear-gradient(105deg,
    transparent 30%,
    rgba(255, 255, 255, 0.15) 45%,
    rgba(255, 255, 255, 0.08) 50%,
    transparent 55%);
  animation: glass-shimmer 8s ease-in-out infinite;
  transform: skewX(-15deg);
}
@keyframes glass-shimmer {
  0%, 100% { left: -15%; opacity: 0.6; }
  50% { left: 85%; opacity: 0.3; }
}

/* ===== Fish ===== */
.fish-sprite {
  z-index: 10;
}
.fish-sprite:hover {
  z-index: 30;
}
.fish-sprite:hover .fish-mover {
  filter: brightness(1.2);
}

/* Mover: handles position animation (translate only, no scaleX) */
.fish-mover {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

/* Emoji flip layer */
.fish-flip {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Name label — never flips */
.fish-name-label {
  display: block;
  font-size: 9px;
  font-weight: 600;
  text-align: center;
  max-width: 64px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-shadow: 0 1px 2px rgba(0,0,0,0.4);
  line-height: 1.2;
}

/* ===== Icon fallback ===== */
.fish-icon-wrap {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.fish-icon-wrap::before {
  content: '🐟';
  position: absolute;
  font-size: 1.5rem;
  z-index: 0;
}
.fish-icon-svg {
  position: relative;
  z-index: 1;
}

/* ===== Fish mini bars (HP + Energy) — hidden by default, show on hover ===== */
.fish-bars {
  display: none;
  flex-direction: column;
  gap: 2px;
  width: 36px;
}
.fish-sprite:hover .fish-bars {
  display: flex;
}
.fish-bar {
  height: 3px;
  border-radius: 2px;
  overflow: hidden;
  background: rgba(0,0,0,0.35);
}
.fish-bar-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.5s ease;
}
.hp-fill { background: #ef4444; }
.energy-fill { background: #22c55e; }

/* ===== Swim animations — position only (translate) ===== */
.swim1-pos { animation: swim1-pos 11s ease-in-out infinite; }
.swim2-pos { animation: swim2-pos 13s ease-in-out infinite; }
.swim3-pos { animation: swim3-pos 10s ease-in-out infinite; }

@keyframes swim1-pos {
  0%, 100% { transform: translate(0, 0); }
  25% { transform: translate(50px, -16px); }
  50% { transform: translate(-25px, 8px); }
  75% { transform: translate(-45px, -12px); }
}
@keyframes swim2-pos {
  0%, 100% { transform: translate(0, 0); }
  25% { transform: translate(35px, -28px); }
  50% { transform: translate(-18px, 12px); }
  75% { transform: translate(-55px, -20px); }
}
@keyframes swim3-pos {
  0%, 100% { transform: translate(0, 0); }
  25% { transform: translate(25px, -32px); }
  50% { transform: translate(-35px, 4px); }
  75% { transform: translate(-18px, -24px); }
}

/* ===== Swim animations — flip only (scaleX) ===== */
.swim1-flip { animation: swim1-flip 11s ease-in-out infinite; }
.swim2-flip { animation: swim2-flip 13s ease-in-out infinite; }
.swim3-flip { animation: swim3-flip 10s ease-in-out infinite; }

@keyframes swim1-flip {
  0%, 24.9% { transform: scaleX(1); }
  25%, 74.9% { transform: scaleX(-1); }
  75%, 100% { transform: scaleX(1); }
}
@keyframes swim2-flip {
  0%, 24.9% { transform: scaleX(1); }
  25%, 74.9% { transform: scaleX(-1); }
  75%, 100% { transform: scaleX(1); }
}
@keyframes swim3-flip {
  0%, 24.9% { transform: scaleX(1); }
  25%, 74.9% { transform: scaleX(-1); }
  75%, 100% { transform: scaleX(1); }
}

/* ===== Memorial strip ===== */
.memorial-strip {
  background: linear-gradient(135deg, #1a2634 0%, #1e2d3d 50%, #1a2634 100%);
  border-top: 1px solid rgba(255,255,255,0.06);
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
  font-size: 11px;
}
.memorial-icon { opacity: 0.5; }
.memorial-label { color: rgba(255,255,255,0.3); margin-right: 2px; }
.memorial-fish {
  color: rgba(255,255,255,0.45);
  cursor: help;
  transition: color 0.2s;
}
.memorial-fish:hover { color: rgba(255,255,255,0.7); }
.memorial-tooltip {
  display: none;
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  margin-bottom: 6px;
  background: rgba(15, 23, 42, 0.95);
  color: #cbd5e1;
  font-size: 11px;
  border-radius: 8px;
  padding: 6px 10px;
  white-space: nowrap;
  max-width: 220px;
  text-align: center;
  z-index: 50;
  box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  border: 1px solid rgba(255,255,255,0.08);
}
.memorial-fish:hover .memorial-tooltip { display: block; }
</style>
