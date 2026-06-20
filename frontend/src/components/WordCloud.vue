<script setup>
import { ref, watch, onMounted, nextTick } from 'vue'

const props = defineProps({
  words: { type: Array, default: () => [] },  // [{text, weight}]
  width: { type: Number, default: 0 },        // 0 = auto from container
  height: { type: Number, default: 280 },
})

const canvasRef = ref(null)
const hoveredWord = ref(null)

const colors = [
  '#F59E0B', '#D97706', '#B45309',  // amber
  '#EF4444', '#DC2626',             // red
  '#8B5CF6', '#7C3AED',             // violet
  '#EC4899', '#DB2777',             // pink
  '#6366F1', '#4F46E5',             // indigo
  '#10B981', '#059669',             // emerald
  '#F97316', '#EA580C',             // orange
  '#06B6D4', '#0891B2',             // cyan
]

function draw() {
  const canvas = canvasRef.value
  if (!canvas || !props.words.length) return
  const ctx = canvas.getContext('2d')
  const w = props.width || canvas.parentElement?.clientWidth || 500
  const h = props.height
  canvas.width = w
  canvas.height = h

  ctx.clearRect(0, 0, w, h)

  // v1.18.3: 过滤纯数字和单字符
  const filtered = props.words.filter(w => {
    const t = (w.text || '').trim()
    return t.length >= 2 && !/^\d+$/.test(t)
  })
  // Sort by weight descending
  const sorted = [...filtered].sort((a, b) => b.weight - a.weight)
  const maxWeight = Math.max(...sorted.map(s => s.weight), 1)

  // Simple spiral layout
  const placed = []
  const cx = w / 2, cy = h / 2
  let angle = 0, radius = 5

  for (const word of sorted) {
    const fontSize = 12 + (word.weight / maxWeight) * 28
    ctx.font = `bold ${fontSize}px "PingFang SC", "Microsoft YaHei", sans-serif`
    const metrics = ctx.measureText(word.text)
    const tw = metrics.width + 6, th = fontSize + 4

    // Spiral outward to find position
    let placed_ok = false
    for (let attempt = 0; attempt < 360; attempt++) {
      const x = cx + radius * Math.cos(angle)
      const y = cy + radius * Math.sin(angle)
      const bx = x - tw / 2, by = y - th / 2

      // Check collision
      let collides = false
      for (const p of placed) {
        if (bx < p.x + p.w && bx + tw > p.x && by < p.y + p.h && by + th > p.y) {
          collides = true
          break
        }
      }

      if (!collides && bx > 0 && bx + tw < w && by > 0 && by + th < h) {
        placed.push({ x: bx, y: by, w: tw, h: th, word })
        // Draw
        const color = colors[Math.floor((angle * 180 / Math.PI) / 30) % colors.length]
        ctx.fillStyle = color
        ctx.fillText(word.text, x - tw / 2 + 3, y + fontSize / 3)
        placed_ok = true
        break
      }

      angle += 0.3
      radius += 0.8
    }

    if (!placed_ok) {
      // Fallback: place at end with smaller font
      const fallSize = Math.max(10, fontSize * 0.6)
      ctx.font = `bold ${fallSize}px "PingFang SC", "Microsoft YaHei", sans-serif`
      // Just skip if still doesn't fit
    }

    angle += 2.2
    radius += 12 + (word.weight / maxWeight) * 15
  }
}

watch(() => props.words, () => nextTick(draw), { deep: true })
onMounted(() => nextTick(draw))
</script>

<template>
  <div class="relative">
    <canvas ref="canvasRef" class="w-full rounded-xl" :style="{ minHeight: height + 'px' }"></canvas>
    <div v-if="!words.length" class="absolute inset-0 flex items-center justify-center text-sm text-slate-300">
      暂无词云数据
    </div>
  </div>
</template>
