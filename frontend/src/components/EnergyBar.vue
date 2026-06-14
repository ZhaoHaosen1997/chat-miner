<script setup>
defineProps({
  current: { type: Number, default: 100 },
  max: { type: Number, default: 100 },
  label: { type: String, default: '精力' },
  color: { type: String, default: '#22C55E' },
})
</script>

<template>
  <div>
    <div class="flex justify-between text-xs text-slate-500 mb-1">
      <span>{{ label }}</span>
      <span>{{ current }}/{{ max }}</span>
    </div>
    <div class="h-2 bg-slate-100 rounded-full overflow-hidden">
      <div class="h-full rounded-full transition-all duration-500"
        :style="{ width: `${Math.min(100, (current / max) * 100)}%`, backgroundColor: color }">
      </div>
    </div>
  </div>
</template>
