<script setup>
import { ref, inject, onMounted } from 'vue'
import { getGroupMemes, addGroupMeme, updateGroupMeme, deleteGroupMeme, scanGroupMemes } from '../api/index.js'
import { Sparkles, Plus, Pencil, Trash2, Check, X, Loader2, BookOpen } from 'lucide-vue-next'

const currentGroup = inject('currentGroup')
const memes = ref([])
const loading = ref(false)
const scanning = ref(false)
const scanMsg = ref('')
const editingId = ref(null)
const editDesc = ref('')
const showAdd = ref(false)
const newTerm = ref('')
const newDesc = ref('')

async function load() {
  if (!currentGroup.value?.id) return
  loading.value = true
  try { memes.value = await getGroupMemes(currentGroup.value.id) } catch { memes.value = [] }
  finally { loading.value = false }
}

async function doScan() {
  scanning.value = true; scanMsg.value = ''
  try { const r = await scanGroupMemes(currentGroup.value.id); scanMsg.value = `发现 ${r.memes?.length||0} 个，新增 ${r.new_count||0} 个`; await load() }
  catch (e) { scanMsg.value = '扫描失败: ' + e.message }
  finally { scanning.value = false }
}

async function doAdd() {
  if (!newTerm.value.trim() || !newDesc.value.trim()) return
  try { await addGroupMeme(currentGroup.value.id, newTerm.value.trim(), newDesc.value.trim()); newTerm.value=''; newDesc.value=''; showAdd.value=false; await load() }
  catch (e) { alert(e.message) }
}

function startEdit(m) { editingId.value = m.id; editDesc.value = m.description }
async function doSave(mid) {
  try { await updateGroupMeme(currentGroup.value.id, mid, editDesc.value); editingId.value = null; await load() }
  catch (e) { alert(e.message) }
}
async function doDelete(m) { if (confirm(`删除"${m.term}"？`)) { await deleteGroupMeme(currentGroup.value.id, m.id); await load() } }

onMounted(load)
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-2">
        <BookOpen class="w-5 h-5 text-violet-500" />
        <h3 class="text-lg font-semibold text-slate-700">群梗百科</h3>
      </div>
      <div class="flex items-center gap-2">
        <button @click="doScan" :disabled="scanning" class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-violet-50 text-violet-600 hover:bg-violet-100 disabled:opacity-50">
          <Sparkles v-if="!scanning" class="w-3.5 h-3.5" /><Loader2 v-else class="w-3.5 h-3.5 animate-spin" />{{ scanning?'扫描中...':'AI 扫描' }}
        </button>
        <button @click="showAdd=!showAdd" class="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-slate-100 text-slate-600 hover:bg-slate-200"><Plus class="w-3.5 h-3.5" />添加</button>
      </div>
    </div>
    <div v-if="scanMsg" class="p-3 rounded-lg text-sm" :class="scanMsg.includes('失败')?'bg-red-50 text-red-600':'bg-green-50 text-green-700'">{{ scanMsg }}</div>
    <div v-if="showAdd" class="p-4 rounded-xl bg-slate-50 border space-y-3">
      <input v-model="newTerm" class="w-full px-3 py-2 text-sm border rounded-lg" placeholder="梗(词或短语)" maxlength="20" />
      <input v-model="newDesc" class="w-full px-3 py-2 text-sm border rounded-lg" placeholder="群内含义" maxlength="100" />
      <div class="flex gap-2"><button @click="doAdd" :disabled="!newTerm.trim()||!newDesc.trim()" class="px-3 py-1.5 text-sm rounded-lg bg-violet-500 text-white hover:bg-violet-600 disabled:opacity-50">添加</button><button @click="showAdd=false" class="px-3 py-1.5 text-sm rounded-lg bg-slate-200 text-slate-600">取消</button></div>
    </div>
    <div v-if="loading" class="flex justify-center py-8"><Loader2 class="w-5 h-5 animate-spin text-slate-300" /></div>
    <div v-else-if="!memes.length" class="py-8 text-center text-sm text-slate-400">暂无梗百科条目<br><span class="text-xs">点"AI 扫描"自动识别群内自有梗</span></div>
    <div v-else class="space-y-1.5">
      <div v-for="m in memes" :key="m.id" class="flex items-start gap-3 px-3 py-2.5 rounded-lg hover:bg-slate-50 group">
        <span class="shrink-0 px-2 py-0.5 rounded-md text-sm font-mono font-bold bg-violet-50 text-violet-700 border border-violet-200 min-w-[40px] text-center">{{ m.term }}</span>
        <div class="flex-1 min-w-0">
          <template v-if="editingId===m.id">
            <div class="flex items-center gap-2"><input v-model="editDesc" class="flex-1 px-2 py-1 text-sm border border-violet-300 rounded" maxlength="100" /><button @click="doSave(m.id)" class="p-1 text-green-500"><Check class="w-4 h-4" /></button><button @click="editingId=null" class="p-1 text-slate-400"><X class="w-4 h-4" /></button></div>
          </template>
          <template v-else><span class="text-sm text-slate-600">{{ m.description }}</span><span v-if="m.source==='ai'" class="ml-1.5 text-[10px] text-slate-400 bg-slate-100 px-1 py-0.5 rounded">AI</span></template>
        </div>
        <div class="shrink-0 flex gap-0.5 opacity-0 group-hover:opacity-100"><button @click="startEdit(m)" class="p-1 text-slate-400 hover:text-slate-600"><Pencil class="w-3.5 h-3.5" /></button><button @click="doDelete(m)" class="p-1 text-slate-400 hover:text-red-500"><Trash2 class="w-3.5 h-3.5" /></button></div>
      </div>
    </div>
  </div>
</template>
