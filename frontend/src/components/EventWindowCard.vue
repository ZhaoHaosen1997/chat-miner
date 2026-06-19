<script setup>
import { computed } from 'vue'
import { Loader2, Clock, Users, MessageCircle, Search, CheckCircle2, Circle } from 'lucide-vue-next'

const props = defineProps({
  window: { type: Object, required: true },
  groupId: { type: [Number, String], default: null },
})

const emit = defineEmits(['analyze'])

const summary = computed(() => props.window.summary || {})
const status = computed(() => props.window.status || 'pending')

const statusConfig = {
  pending: { icon: Circle, label: '待分析', class: 'bg-amber-50 text-amber-600 border-amber-200' },
  analyzing: { icon: Loader2, label: '分析中', class: 'bg-blue-50 text-blue-600 border-blue-200' },
  analyzed: { icon: CheckCircle2, label: '已分析', class: 'bg-green-50 text-green-600 border-green-200' },
  empty: { icon: Search, label: '无事件', class: 'bg-slate-50 text-slate-500 border-slate-200' },
}

const cfg = computed(() => statusConfig[status.value] || statusConfig.pending)
const eventTitle = computed(() => props.window.event?.title || '')

function formatTimeSpan() {
  const start = props.window.start_time || ''
  const end = props.window.end_time || ''
  if (start.length >= 16 && end.length >= 16) {
    const date = start.slice(0, 10)
    return `${date} ${start.slice(11, 16)} ~ ${end.slice(11, 16)}`
  }
  return start ? `${start.slice(0, 16)} ~ ${end.slice(0, 16)}` : ''
}

function topSpeakers() {
  const speakers = summary.value.top_speakers || []
  if (!speakers.length) return ''
  return speakers.slice(0, 3).map(s => s.name).join('、')
}

const previewMessages = computed(() => {
  const preview = summary.value.preview || []
  return Array.isArray(preview) ? preview : []
})
</script>

<template>
  <div
    :class="[
      'bg-white rounded-xl border shadow-sm transition-all',
      status === 'analyzed' ? 'border-green-200' :
      status === 'empty' ? 'border-slate-200 opacity-75' :
      'border-slate-200 hover:shadow-md',
    ]"
  >
    <div class="p-4">
      <div class="flex items-start justify-between gap-3 mb-2">
        <!-- 状态徽标 -->
        <div :class="[cfg.class, 'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border']">
          <component :is="cfg.icon" :class="['w-3 h-3', status === 'analyzing' ? 'animate-spin' : '']" />
          {{ cfg.label }}
        </div>

        <!-- 时间 -->
        <span class="text-xs text-slate-400 whitespace-nowrap flex-shrink-0">
          <Clock class="w-3 h-3 inline mr-0.5" />
          {{ formatTimeSpan() }}
        </span>
      </div>

      <!-- 已分析时显示事件标题 -->
      <div v-if="status === 'analyzed' && eventTitle" class="mb-2">
        <span class="text-sm font-semibold text-slate-800">{{ eventTitle }}</span>
      </div>

      <!-- 指标 -->
      <div class="flex items-center gap-4 text-xs text-slate-400 mb-2">
        <span class="flex items-center gap-1">
          <MessageCircle class="w-3 h-3" />
          {{ props.window.message_count || 0 }} 条消息
        </span>
        <span v-if="topSpeakers()" class="flex items-center gap-1 truncate max-w-[200px]">
          <Users class="w-3 h-3 flex-shrink-0" />
          {{ topSpeakers() }}
        </span>
      </div>

      <!-- 消息预览（仅待分析/分析中时显示） -->
      <div v-if="previewMessages.length > 0 && status === 'pending'" class="mb-3 space-y-0.5 bg-slate-50 rounded p-2">
        <div
          v-for="(msg, i) in previewMessages"
          :key="i"
          class="text-xs text-slate-500 truncate"
        >
          <span class="text-slate-400 mr-1">{{ msg.time }}</span>
          <span class="font-medium text-slate-600">{{ msg.sender }}:</span>
          {{ msg.content }}
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="flex items-center gap-2 mt-3">
        <button
          v-if="status === 'pending'"
          @click="emit('analyze', window.id)"
          class="flex items-center gap-1 px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 transition-colors"
        >
          <Search class="w-3 h-3" />
          分析
        </button>

        <button
          v-else-if="status === 'analyzing'"
          disabled
          class="flex items-center gap-1 px-3 py-1.5 bg-blue-100 text-blue-500 rounded-lg text-xs font-medium cursor-not-allowed"
        >
          <Loader2 class="w-3 h-3 animate-spin" />
          分析中...
        </button>

        <button
          v-else-if="status === 'empty'"
          @click="emit('analyze', window.id)"
          class="flex items-center gap-1 px-3 py-1.5 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg text-xs font-medium transition-colors"
        >
          重新分析
        </button>

        <button
          v-else-if="status === 'analyzed'"
          @click="emit('analyze', window.id)"
          class="flex items-center gap-1 px-3 py-1.5 text-slate-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg text-xs font-medium transition-colors"
        >
          重新分析
        </button>
      </div>
    </div>
  </div>
</template>
