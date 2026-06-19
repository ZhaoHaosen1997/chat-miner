<script setup>
import { ref, onMounted, watch } from 'vue'
import { Calendar, ArrowRight, Clock, ChevronRight } from 'lucide-vue-next'
import { getEvents } from '../api/index.js'
import { useRouter } from 'vue-router'

const props = defineProps({
  groupId: { type: [Number, String], required: true },
  dateFrom: { type: String, default: '' },
  dateTo: { type: String, default: '' },
  memberId: { type: [Number, String], default: 0 },
  limit: { type: Number, default: 5 },
  label: { type: String, default: '相关事件' },
  sortBy: { type: String, default: 'time' }, // 'time' | 'msg_count'
})

const router = useRouter()
const events = ref([])
const loading = ref(false)

const typeIcons = {
  decision: '🎯',
  discussion: '💬',
  social: '🎉',
  announcement: '📢',
  meme: '🤣',
}

async function load() {
  if (!props.groupId || !props.dateFrom) return
  loading.value = true
  try {
    const params = { date_from: props.dateFrom, date_to: props.dateTo || props.dateFrom }
    if (props.memberId) params.member_id = props.memberId
    let result = await getEvents(props.groupId, params)
    // 排序
    if (props.sortBy === 'msg_count') {
      result.sort((a, b) => (b.message_count || 0) - (a.message_count || 0))
    }
    events.value = result.slice(0, props.limit)
  } catch (e) {
    console.error('加载相关事件失败:', e)
  } finally {
    loading.value = false
  }
}

function goToEvents() {
  router.push('/events')
}

function goToEvent(eventId) {
  router.push('/events')
  // 可以通过 URL hash 滚动，这里简化处理
}

watch(() => [props.dateFrom, props.dateTo], () => load())
onMounted(() => load())
</script>

<template>
  <div v-if="events.length > 0" class="mt-6 bg-white rounded-xl border border-slate-200 p-4">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-slate-600 flex items-center gap-1.5">
        <Clock class="w-4 h-4 text-indigo-400" />
        {{ label }}
        <span class="text-xs text-slate-400 font-normal">({{ events.length }})</span>
      </h3>
      <button
        @click="goToEvents"
        class="flex items-center gap-1 text-xs text-indigo-500 hover:text-indigo-700 transition-colors"
      >
        查看所有事件
        <ChevronRight class="w-3.5 h-3.5" />
      </button>
    </div>
    <div class="space-y-2">
      <div
        v-for="e in events"
        :key="e.id"
        @click="goToEvent(e.id)"
        class="flex items-start gap-2.5 p-2 rounded-lg hover:bg-slate-50 cursor-pointer transition-colors"
      >
        <span class="text-sm flex-shrink-0 mt-0.5">{{ typeIcons[e.event_type] || '📅' }}</span>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium text-slate-700 truncate">{{ e.title }}</p>
          <p v-if="e.message_count" class="text-xs text-slate-400 mt-0.5">
            {{ e.message_count }} 条消息 ·
            {{ (e.start_time || '').slice(0, 10) }}
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
