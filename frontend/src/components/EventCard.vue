<script setup>
import { ref, computed } from 'vue'
import {
  MessageCircle, Users, Quote, ChevronDown, ChevronUp, Loader2,
  Target, MessageSquareText, PartyPopper, Megaphone, Laugh,
} from 'lucide-vue-next'
import { getEventDetail } from '../api/index.js'

const props = defineProps({
  event: { type: Object, required: true },
  groupId: { type: [Number, String], default: null },
})

const expanded = ref(false)
const contextLoading = ref(false)
const contextMessages = ref([])

const typeConfig = {
  decision: { icon: Target, label: '决策', color: 'text-amber-600', bg: 'bg-amber-50' },
  discussion: { icon: MessageSquareText, label: '讨论', color: 'text-blue-600', bg: 'bg-blue-50' },
  social: { icon: PartyPopper, label: '社交', color: 'text-pink-600', bg: 'bg-pink-50' },
  announcement: { icon: Megaphone, label: '公告', color: 'text-purple-600', bg: 'bg-purple-50' },
  meme: { icon: Laugh, label: '梗', color: 'text-green-600', bg: 'bg-green-50' },
}

const cfg = typeConfig[props.event.event_type] || typeConfig.discussion

const participantNames = computed(() => {
  const names = props.event.participant_names || {}
  return Object.values(names).slice(0, 5)
})

function formatTimeSpan() {
  const start = props.event.start_time || ''
  const end = props.event.end_time || ''
  const s = start.length >= 16 ? start.slice(11, 16) : start
  const e = end.length >= 16 ? end.slice(11, 16) : end
  if (s && e) return `${s} ~ ${e}`
  if (start.length >= 10) return start.slice(0, 10)
  return ''
}

async function toggleContext() {
  if (expanded.value) {
    expanded.value = false
    return
  }
  if (contextMessages.value.length > 0) {
    expanded.value = true
    return
  }
  contextLoading.value = true
  try {
    const detail = await getEventDetail(props.groupId, props.event.id)
    contextMessages.value = detail.context_messages || []
    expanded.value = true
  } catch (e) {
    console.error('加载对话上下文失败:', e)
  } finally {
    contextLoading.value = false
  }
}
</script>

<template>
  <div class="bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md transition-shadow">
    <!-- 事件卡片主体 -->
    <div class="p-4">
      <div class="flex items-start gap-3">
        <!-- 类型图标 -->
        <div :class="[cfg.bg, 'w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0']">
          <component :is="cfg.icon" :class="[cfg.color, 'w-4.5 h-4.5']" />
        </div>

        <div class="flex-1 min-w-0">
          <!-- 标题 + 时间 -->
          <div class="flex items-start justify-between gap-2 mb-1">
            <h3 class="font-semibold text-slate-800 leading-snug">{{ event.title }}</h3>
            <span class="text-xs text-slate-400 whitespace-nowrap flex-shrink-0 mt-0.5">
              {{ formatTimeSpan() }}
            </span>
          </div>

          <!-- 描述 -->
          <p v-if="event.description" class="text-sm text-slate-600 leading-relaxed mb-2">
            {{ event.description }}
          </p>

          <!-- 关键金句 -->
          <div v-if="event.key_quotes && event.key_quotes.length > 0" class="mb-2 space-y-1">
            <div
              v-for="(q, i) in event.key_quotes"
              :key="i"
              class="flex items-start gap-1.5 text-sm text-slate-500 italic"
            >
              <Quote class="w-3.5 h-3.5 text-slate-300 flex-shrink-0 mt-0.5" />
              <span>"{{ q }}"</span>
            </div>
          </div>

          <!-- 参与成员 + 消息数 -->
          <div class="flex items-center gap-4 text-xs text-slate-400 mt-2">
            <div v-if="participantNames.length > 0" class="flex items-center gap-1">
              <Users class="w-3.5 h-3.5" />
              <span>{{ participantNames.join('、') }}</span>
            </div>
            <div v-if="event.message_count" class="flex items-center gap-1">
              <MessageCircle class="w-3.5 h-3.5" />
              <span>{{ event.message_count }} 条消息</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 查看对话上下文按钮 -->
    <button
      @click="toggleContext"
      class="w-full flex items-center justify-center gap-1.5 py-2 text-xs text-slate-400 hover:text-indigo-500 hover:bg-slate-50 rounded-b-xl border-t border-slate-100 transition-colors"
    >
      <Loader2 v-if="contextLoading" class="w-3.5 h-3.5 animate-spin" />
      <ChevronDown v-else-if="!expanded" class="w-3.5 h-3.5" />
      <ChevronUp v-else class="w-3.5 h-3.5" />
      {{ contextLoading ? '加载对话...' : expanded ? '收起对话' : '查看完整对话' }}
    </button>

    <!-- 对话上下文展开区 -->
    <div v-if="expanded && contextMessages.length > 0"
         class="border-t border-slate-100 bg-slate-50 rounded-b-xl p-4 max-h-80 overflow-y-auto">
      <div class="space-y-1.5">
        <div
          v-for="(msg, i) in contextMessages"
          :key="i"
          class="text-sm leading-relaxed"
        >
          <span class="text-slate-400 text-xs mr-1.5">{{ msg.time }}</span>
          <span class="font-medium text-slate-600 mr-1.5">{{ msg.sender }}:</span>
          <span class="text-slate-700">{{ msg.content }}</span>
        </div>
      </div>
    </div>
    <div v-else-if="expanded && contextMessages.length === 0"
         class="border-t border-slate-100 bg-slate-50 rounded-b-xl p-4 text-center text-sm text-slate-400">
      暂无原始对话上下文
    </div>
  </div>
</template>
