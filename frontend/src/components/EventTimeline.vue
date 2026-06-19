<script setup>
import { computed } from 'vue'
import EventCard from './EventCard.vue'

const props = defineProps({
  events: { type: Array, required: true },
  groupId: { type: [Number, String], default: null },
})

// 按月份分组，倒序（最新月份在前）
const groupedEvents = computed(() => {
  const groups = {}
  for (const e of props.events) {
    const month = (e.start_time || '').slice(0, 7)  // "2025-06"
    if (!month) continue
    if (!groups[month]) groups[month] = []
    groups[month].push(e)
  }
  return Object.entries(groups).sort((a, b) => b[0].localeCompare(a[0]))
})

function formatMonthLabel(month) {
  const [y, m] = month.split('-')
  return `${y}年${parseInt(m)}月`
}
</script>

<template>
  <div class="relative">
    <!-- 时间轴线 -->
    <div class="absolute left-4 top-0 bottom-0 w-px bg-slate-200" />

    <div v-for="[month, monthEvents] in groupedEvents" :key="month" class="mb-8">
      <!-- 月份标签 -->
      <div class="flex items-center gap-3 mb-4 relative">
        <div class="w-3 h-3 rounded-full bg-indigo-400 border-2 border-white shadow-sm z-10 flex-shrink-0" />
        <span class="text-sm font-semibold text-slate-500">{{ formatMonthLabel(month) }}</span>
      </div>

      <!-- 事件卡片列表 -->
      <div class="ml-7 space-y-3">
        <EventCard
          v-for="event in monthEvents"
          :key="event.id"
          :event="event"
          :group-id="groupId"
        />
      </div>
    </div>
  </div>
</template>
