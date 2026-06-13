<script setup>
import { onMounted, onUnmounted } from 'vue'
import { ArrowLeft, ArrowRight } from 'lucide-vue-next'

const props = defineProps({
  prevLabel: { type: String, default: '' },
  nextLabel: { type: String, default: '' },
  showPrev: { type: Boolean, default: false },
  showNext: { type: Boolean, default: false },
})

const emit = defineEmits(['prev', 'next'])

function onKey(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return
  // ← A → 更早(prev)    → D → 更新(next)
  if (e.key === 'ArrowLeft' || e.key === 'a' || e.key === 'A') {
    if (props.showPrev) emit('prev')
  } else if (e.key === 'ArrowRight' || e.key === 'd' || e.key === 'D') {
    if (props.showNext) emit('next')
  }
}

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <!-- Left -->
  <div
    v-if="showPrev"
    class="fixed left-6 top-1/2 -translate-y-1/2 z-40 group"
  >
    <button
      @click="emit('prev')"
      class="w-14 h-14 rounded-full flex items-center justify-center
             bg-white/25 backdrop-blur-xl border border-white/20
             text-slate-300 hover:text-slate-600 hover:bg-white/60 hover:border-white/40
             hover:scale-110 hover:shadow-xl active:scale-95
             transition-all duration-300 ease-out
             shadow-[0_4px_24px_rgba(0,0,0,0.06)]"
      :title="prevLabel || '上一个 (A / ←)'"
    >
      <ArrowLeft class="w-6 h-6" />
    </button>
    <span
      v-if="prevLabel"
      class="absolute left-full ml-3 top-1/2 -translate-y-1/2
             px-2.5 py-1.5 bg-slate-800/80 backdrop-blur-sm text-white text-xs font-medium
             rounded-lg whitespace-nowrap
             opacity-0 group-hover:opacity-100 transition-all duration-200
             pointer-events-none"
    >
      {{ prevLabel }}
    </span>
  </div>

  <!-- Right -->
  <div
    v-if="showNext"
    class="fixed right-6 top-1/2 -translate-y-1/2 z-40 group"
  >
    <span
      v-if="nextLabel"
      class="absolute right-full mr-3 top-1/2 -translate-y-1/2
             px-2.5 py-1.5 bg-slate-800/80 backdrop-blur-sm text-white text-xs font-medium
             rounded-lg whitespace-nowrap
             opacity-0 group-hover:opacity-100 transition-all duration-200
             pointer-events-none"
    >
      {{ nextLabel }}
    </span>
    <button
      @click="emit('next')"
      class="w-14 h-14 rounded-full flex items-center justify-center
             bg-white/25 backdrop-blur-xl border border-white/20
             text-slate-300 hover:text-slate-600 hover:bg-white/60 hover:border-white/40
             hover:scale-110 hover:shadow-xl active:scale-95
             transition-all duration-300 ease-out
             shadow-[0_4px_24px_rgba(0,0,0,0.06)]"
      :title="nextLabel || '下一个 (D / →)'"
    >
      <ArrowRight class="w-6 h-6" />
    </button>
  </div>
</template>
