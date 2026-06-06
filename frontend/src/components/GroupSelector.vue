<script setup>
import { ref, onMounted, watch } from 'vue'
import { listGroups } from '../api/index.js'
import { ChevronDown, Upload, Trash2 } from 'lucide-vue-next'

const props = defineProps({ current: Object })
const emit = defineEmits(['select', 'upload-click'])

const groups = ref([])
const loading = ref(false)
const menuOpen = ref(false)

async function loadGroups() {
  loading.value = true
  try { groups.value = await listGroups() } catch (e) { console.error(e) }
  finally { loading.value = false }
}

function select(g) {
  emit('select', g)
  menuOpen.value = false
}

onMounted(loadGroups)

// 重新加载（暴露给父组件调用）
defineExpose({ reload: loadGroups })
</script>

<template>
  <div class="relative">
    <button
      @click="menuOpen = !menuOpen"
      class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 hover:bg-slate-100 text-sm transition-colors"
    >
      <span v-if="current" class="font-medium text-slate-700 max-w-[140px] truncate">
        {{ current.display_name || current.name }}
      </span>
      <span v-else class="text-slate-400">选择群聊</span>
      <ChevronDown :class="['w-4 h-4 text-slate-400 transition-transform', menuOpen && 'rotate-180']" />
    </button>

    <!-- 下拉菜单 -->
    <div
      v-if="menuOpen"
      class="absolute top-full mt-1 left-0 w-64 bg-white rounded-xl border border-slate-200 shadow-xl z-40 overflow-hidden"
      @click.self="menuOpen = false"
    >
      <div class="max-h-64 overflow-y-auto py-1">
        <button
          v-for="g in groups"
          :key="g.id"
          @click="select(g)"
          :class="[
            'w-full text-left px-3 py-2.5 flex items-center justify-between hover:bg-slate-50 transition-colors',
            current?.id === g.id && 'bg-indigo-50',
          ]"
        >
          <div>
            <div class="text-sm font-medium text-slate-700">{{ g.display_name || g.name }}</div>
            <div class="text-xs text-slate-400">{{ g.message_count }} 条消息 · {{ g.sender_count }} 人</div>
          </div>
          <div v-if="current?.id === g.id" class="w-2 h-2 bg-indigo-500 rounded-full" />
        </button>
        <div v-if="groups.length === 0" class="px-3 py-4 text-sm text-slate-400 text-center">
          暂无群聊，请先导入
        </div>
      </div>
      <div class="border-t border-slate-100 p-1.5 flex gap-1">
        <button
          @click="emit('upload-click'); menuOpen = false"
          class="flex-1 flex items-center justify-center gap-1.5 py-2 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
        >
          <Upload class="w-4 h-4" /> 导入新群
        </button>
      </div>
    </div>

    <!-- 遮罩 -->
    <div v-if="menuOpen" class="fixed inset-0 z-30" @click="menuOpen = false" />
  </div>
</template>
