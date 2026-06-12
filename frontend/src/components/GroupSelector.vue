<script setup>
import { ref, onMounted } from 'vue'
import { listGroups, renameGroup, deleteGroup, request } from '../api/index.js'
import { ChevronDown, Upload, Plus, Loader2, Pencil, Trash2, Check, X } from 'lucide-vue-next'

const props = defineProps({ current: Object })
const emit = defineEmits(['select', 'upload-click'])

const groups = ref([])
const menuOpen = ref(false)
const showCreate = ref(false)
const newName = ref('')
const creating = ref(false)
const createError = ref('')

// 编辑/删除
const editingId = ref(null)
const editName = ref('')
const editLoading = ref(false)
const deletingId = ref(null)

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
    const data = await request('/groups', {
      method: 'POST',
      body: JSON.stringify({ name }),
    })
    await loadGroups()
    emit('select', { id: data.group_id, name: data.name, display_name: data.name })
    showCreate.value = false
    newName.value = ''
    menuOpen.value = false
  } catch (e) {
    createError.value = e.message || '请求失败'
  } finally {
    creating.value = false
  }
}

function startEdit(g) {
  editingId.value = g.id
  editName.value = g.display_name || g.name
}

function cancelEdit() {
  editingId.value = null
  editName.value = ''
}

async function saveEdit(g) {
  const name = editName.value.trim()
  if (!name || name === (g.display_name || g.name)) {
    cancelEdit()
    return
  }
  editLoading.value = true
  try {
    await renameGroup(g.id, name)
    await loadGroups()
    if (props.current?.id === g.id) {
      const updated = groups.value.find(gr => gr.id === g.id)
      if (updated) emit('select', updated)
    }
  } catch (e) { console.error(e) }
  finally { editLoading.value = false; editingId.value = null }
}

async function handleDelete(g) {
  if (!confirm(`确定要删除「${g.display_name || g.name}」吗？\n\n此操作会删除该群的所有数据和分析结果，不可恢复。`)) return
  deletingId.value = g.id
  try {
    await deleteGroup(g.id)
    await loadGroups()
    if (props.current?.id === g.id) {
      emit('select', groups.value[0] || null)
    }
  } catch (e) { console.error(e) }
  finally { deletingId.value = null }
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
        <div
          v-for="g in groups"
          :key="g.id"
          :class="[
            'px-3 py-2.5 flex items-center justify-between hover:bg-slate-50 transition-colors',
            current?.id === g.id && 'bg-indigo-50',
          ]"
        >
          <!-- 编辑模式 -->
          <div v-if="editingId === g.id" class="flex-1 flex items-center gap-1">
            <input
              v-model="editName"
              @keyup.enter="saveEdit(g)"
              @keyup.escape="cancelEdit"
              class="flex-1 px-2 py-1 text-sm border border-indigo-300 rounded-lg focus:outline-none"
              autofocus
            />
            <button @click="saveEdit(g)" :disabled="editLoading"
                    class="p-1 text-emerald-500 hover:bg-emerald-50 rounded">
              <Check class="w-3.5 h-3.5" />
            </button>
            <button @click="cancelEdit" class="p-1 text-slate-400 hover:bg-slate-100 rounded">
              <X class="w-3.5 h-3.5" />
            </button>
          </div>
          <!-- 普通模式 -->
          <template v-else>
            <div class="flex-1 min-w-0 cursor-pointer" @click="select(g)">
              <div class="text-sm font-medium text-slate-700 truncate">{{ g.display_name || g.name }}</div>
              <div class="text-xs text-slate-400">{{ g.message_count }} 条消息 · {{ g.sender_count }} 人</div>
            </div>
            <div class="flex items-center gap-0.5 ml-1">
              <div v-if="current?.id === g.id" class="w-2 h-2 bg-indigo-500 rounded-full mr-1" />
              <button @click.stop="startEdit(g)"
                      class="p-1 text-slate-300 hover:text-indigo-500 hover:bg-indigo-50 rounded transition-colors"
                      title="重命名">
                <Pencil class="w-3 h-3" />
              </button>
              <button @click.stop="handleDelete(g)"
                      :disabled="deletingId === g.id"
                      class="p-1 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded transition-colors disabled:opacity-50"
                      title="删除">
                <Loader2 v-if="deletingId === g.id" class="w-3 h-3 animate-spin" />
                <Trash2 v-else class="w-3 h-3" />
              </button>
            </div>
          </template>
        </div>
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
