<script setup>
import { ref, onMounted } from 'vue'
import { listGroups } from '../api/index.js'
import { ChevronDown, Upload, Plus, Loader2 } from 'lucide-vue-next'

const props = defineProps({ current: Object })
const emit = defineEmits(['select', 'upload-click'])

const groups = ref([])
const menuOpen = ref(false)
const showCreate = ref(false)
const newName = ref('')
const creating = ref(false)
const createError = ref('')

async function loadGroups() {
  try { groups.value = await listGroups() } catch (e) { console.error(e) }
}

function select(g) {
  emit('select', g)
  menuOpen.value = false
}

async function handleCreate() {
  const name = newName.value.trim()
  if (!name) { createError.value = '请输入群名'; return }
  creating.value = true
  createError.value = ''
  try {
    const BASE = '/api'
    const res = await fetch(`${BASE}/groups`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    const data = await res.json()
    if (data.code === 200) {
      await loadGroups()
      emit('select', { id: data.data.group_id, name: data.data.name, display_name: data.data.name })
      showCreate.value = false
      newName.value = ''
      menuOpen.value = false
    } else {
      createError.value = data.message || '创建失败'
    }
  } catch (e) {
    createError.value = e.message || '请求失败'
  } finally {
    creating.value = false
  }
}

onMounted(loadGroups)
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
          暂无群聊
        </div>
      </div>

      <!-- 底部操作栏 -->
      <div class="border-t border-slate-100 p-1.5 space-y-1">
        <!-- 新建群表单 -->
        <div v-if="showCreate" class="px-2 py-1">
          <input
            v-model="newName"
            @keyup.enter="handleCreate"
            placeholder="输入群名"
            class="w-full px-2 py-1.5 text-sm border border-slate-200 rounded-lg focus:outline-none focus:border-indigo-300"
            autofocus
          />
          <div class="flex gap-1 mt-1.5">
            <button
              @click="handleCreate"
              :disabled="creating"
              class="flex-1 py-1.5 text-xs bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 flex items-center justify-center gap-1"
            >
              <Loader2 v-if="creating" class="w-3 h-3 animate-spin" />
              {{ creating ? '...' : '创建' }}
            </button>
            <button
              @click="showCreate = false; createError = ''"
              class="px-3 py-1.5 text-xs text-slate-500 hover:bg-slate-100 rounded-lg"
            >取消</button>
          </div>
          <div v-if="createError" class="text-xs text-red-400 mt-1">{{ createError }}</div>
        </div>

        <div v-else class="flex gap-1">
          <button
            @click="showCreate = true"
            class="flex-1 flex items-center justify-center gap-1.5 py-2 text-sm text-slate-600 hover:bg-slate-50 rounded-lg transition-colors"
          >
            <Plus class="w-4 h-4" /> 新建群
          </button>
          <button
            @click="emit('upload-click'); menuOpen = false"
            class="flex-1 flex items-center justify-center gap-1.5 py-2 text-sm text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors"
          >
            <Upload class="w-4 h-4" /> 导入群
          </button>
        </div>
      </div>
    </div>

    <!-- 遮罩 -->
    <div v-if="menuOpen" class="fixed inset-0 z-30" @click="menuOpen = false" />
  </div>
</template>
