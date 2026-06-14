<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: '' },
})

const show = computed(() => !!props.status)
</script>

<template>
  <div v-if="show" class="relative group inline-block">
    <span class="text-xs text-slate-400 cursor-help">💬</span>
    <div class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 hidden group-hover:block
                bg-slate-800 text-white text-xs rounded-lg px-2 py-1 shadow-lg
                whitespace-nowrap max-w-48 text-center z-50">
      {{ status }}
    </div>
  </div>
</template>
