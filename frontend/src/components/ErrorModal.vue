<script setup>
import { ref, computed } from 'vue'
import { X, AlertTriangle, ChevronDown, ChevronUp, Copy, Check } from 'lucide-vue-next'

const visible = ref(false)
const title = ref('')
const message = ref('')
const detail = ref('')
const context = ref('')
const timestamp = ref('')
const copied = ref(false)

function show(opts) {
  title.value = opts.title || '出错了'
  message.value = opts.message || '发生了一个意外错误'
  detail.value = opts.detail || ''
  context.value = opts.context || ''
  timestamp.value = new Date().toLocaleString('zh')
  visible.value = true
  copied.value = false
}

function close() {
  visible.value = false
}

const expanded = ref(false)
function toggleExpand() {
  expanded.value = !expanded.value
}

const fullLog = computed(() => {
  const parts = [
    `[${timestamp.value}] ${title.value}`,
    `消息: ${message.value}`,
  ]
  if (context.value) parts.push(`上下文: ${context.value}`)
  if (detail.value) parts.push(`详情:\n${detail.value}`)
  parts.push(`页面: ${location.href}`)
  parts.push(`UA: ${navigator.userAgent}`)
  return parts.join('\n')
})

async function copyLog() {
  try {
    await navigator.clipboard.writeText(fullLog.value)
    copied.value = true
    setTimeout(() => copied.value = false, 2000)
  } catch {
    // fallback
    const ta = document.createElement('textarea')
    ta.value = fullLog.value
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    copied.value = true
    setTimeout(() => copied.value = false, 2000)
  }
}

defineExpose({ show, close })
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm"
         @click.self="close">
      <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 bg-red-50 border-b border-red-100">
          <div class="flex items-center gap-2 text-red-700 font-semibold">
            <AlertTriangle :size="20" class="text-red-500" />
            {{ title }}
          </div>
          <button @click="close" class="p-1 rounded-lg hover:bg-red-100 text-red-400 hover:text-red-600 transition">
            <X :size="18" />
          </button>
        </div>

        <!-- Body -->
        <div class="px-5 py-4">
          <p class="text-sm text-gray-700">{{ message }}</p>
          <p v-if="context" class="text-xs text-gray-400 mt-2">发生位置：{{ context }}</p>

          <!-- 展开详情 -->
          <button @click="toggleExpand"
                  class="mt-3 flex items-center gap-1 text-xs text-gray-400 hover:text-gray-600 transition">
            <ChevronDown v-if="!expanded" :size="14" />
            <ChevronUp v-else :size="14" />
            技术详情（可复制给开发人员排查）
          </button>
          <div v-if="expanded" class="mt-2 p-3 bg-gray-50 rounded-lg text-xs font-mono text-gray-600 whitespace-pre-wrap max-h-48 overflow-auto">
            {{ fullLog }}
          </div>
        </div>

        <!-- Footer -->
        <div class="flex gap-2 px-5 py-3 bg-gray-50 border-t border-gray-100">
          <button @click="copyLog"
                  :class="['flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg transition',
                           copied ? 'bg-emerald-100 text-emerald-700' : 'bg-indigo-600 text-white hover:bg-indigo-700']">
            <Check v-if="copied" :size="14" />
            <Copy v-else :size="14" />
            {{ copied ? '已复制' : '复制错误日志' }}
          </button>
          <button @click="close"
                  class="flex-1 px-4 py-2 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-100 transition">
            关闭
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
