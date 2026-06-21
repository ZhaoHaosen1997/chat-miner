<script setup>
import { ref, inject, onMounted, watch, computed } from 'vue'
import {
  getGroupMemes, addGroupMeme, updateGroupMeme, deleteGroupMeme,
  rejectGroupMeme, scanGroupMemes,
} from '../api/index.js'
import {
  Sparkles, Plus, Pencil, Trash2, Check, X, Loader2,
  BookOpen, CheckCircle2, XCircle, AlertCircle,
} from 'lucide-vue-next'

const currentGroup = inject('currentGroup')
const memes = ref([])
const loading = ref(false)
const scanning = ref(false)
const scanMsg = ref('')
const scanTime = ref('')
const aiRaw = ref('')  // AI 原始返回（空结果时展示，便于排查）
const editingId = ref(null)
const editDesc = ref('')
const approvingId = ref(null)  // 正在审核编辑中的梗 id（与普通编辑区分）
const showAdd = ref(false)
const newTerm = ref('')
const newDesc = ref('')
const highlightIds = ref(new Set()) // 新扫描到的梗 id，临时高亮

// 按状态分组
const pendingMemes = computed(() => memes.value.filter(m => m.status === 'pending'))
const approvedMemes = computed(() => memes.value.filter(m => m.status === 'approved'))

async function load() {
  if (!currentGroup.value?.id) return
  loading.value = true
  try { memes.value = await getGroupMemes(currentGroup.value.id) } catch { memes.value = [] }
  finally { loading.value = false }
}

async function doScan() {
  scanning.value = true; scanMsg.value = ''; scanTime.value = ''; aiRaw.value = ''
  try {
    const r = await scanGroupMemes(currentGroup.value.id)
    scanMsg.value = `发现 ${r.memes?.length || 0} 个，新增 ${r.new_count || 0} 个（待审核）`
    scanTime.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    aiRaw.value = r.ai_raw || ''
    await load()
    highlightIds.value = new Set(pendingMemes.value.map(m => m.id))
    setTimeout(() => { highlightIds.value = new Set() }, 4000)
  } catch (e) { scanMsg.value = '扫描失败: ' + e.message }
  finally { scanning.value = false }
}

// 点击"通过"→ 打开编辑面板，让用户确认/修改描述后再通过
function startApprove(m) {
  approvingId.value = m.id
  editingId.value = m.id
  editDesc.value = m.description
}

// 确认通过：保存描述（DB 层 update_group_meme 自动 pending→approved）
async function confirmApprove() {
  const mid = approvingId.value
  if (!mid) return
  try {
    await updateGroupMeme(currentGroup.value.id, mid, editDesc.value)
    editingId.value = null
    approvingId.value = null
    await load()
  } catch (e) { alert(e.message) }
}

function cancelApprove() {
  editingId.value = null
  approvingId.value = null
}

async function doReject(mid) {
  await rejectGroupMeme(currentGroup.value.id, mid)
  await load()
}

async function doAdd() {
  if (!newTerm.value.trim() || !newDesc.value.trim()) return
  try {
    await addGroupMeme(currentGroup.value.id, newTerm.value.trim(), newDesc.value.trim())
    newTerm.value = ''; newDesc.value = ''; showAdd.value = false
    await load()
  } catch (e) { alert(e.message) }
}

function startEdit(m) { editingId.value = m.id; editDesc.value = m.description }
async function doSave(mid) {
  try {
    await updateGroupMeme(currentGroup.value.id, mid, editDesc.value)
    editingId.value = null
    await load()
  } catch (e) { alert(e.message) }
}
async function doDelete(m) {
  if (confirm(`删除"${m.term}"？`)) {
    await deleteGroupMeme(currentGroup.value.id, m.id)
    await load()
  }
}

// 判断描述是否为疑问句（AI 不确定的表达）
function isUncertain(desc) {
  return /[？?]/.test(desc) || /^似乎|可能|好像|不确定|推测|大概/.test(desc)
}

onMounted(load)
watch(currentGroup, () => {
  scanMsg.value = ''; scanTime.value = ''; aiRaw.value = ''
  editingId.value = null; approvingId.value = null; showAdd.value = false
  load()
})
</script>

<template>
  <div class="max-w-3xl mx-auto px-4 py-6 space-y-6">
    <!-- 页面头部 -->
    <div class="space-y-2">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-violet-100 flex items-center justify-center">
          <BookOpen class="w-5 h-5 text-violet-600" />
        </div>
        <div>
          <h2 class="text-xl font-bold text-slate-800">群梗百科</h2>
          <p class="text-sm text-slate-500">识别和记录群内约定俗成的"黑话"——外部人看不懂、群友心领神会的表达。AI 负责发现候选，你来确认含义。</p>
        </div>
      </div>
      <!-- 统计摘要 -->
      <div class="flex items-center gap-4 text-sm">
        <span class="text-slate-500">已收录 <strong class="text-violet-600">{{ approvedMemes.length }}</strong></span>
        <span v-if="pendingMemes.length > 0" class="text-amber-600">待审核 <strong>{{ pendingMemes.length }}</strong></span>
      </div>
    </div>

    <!-- 待审核区 -->
    <div v-if="pendingMemes.length > 0" class="rounded-2xl border border-amber-200 bg-amber-50/50 overflow-hidden">
      <div class="px-5 py-3 border-b border-amber-200 flex items-center gap-2">
        <AlertCircle class="w-4 h-4 text-amber-500" />
        <h3 class="font-semibold text-amber-800 text-sm">待审核（{{ pendingMemes.length }}）</h3>
        <span class="text-xs text-amber-500">AI 发现的候选梗，请确认或修改后收录</span>
      </div>
      <div class="divide-y divide-amber-100">
        <div v-for="m in pendingMemes" :key="m.id"
          class="px-5 py-3 flex items-start gap-3 hover:bg-amber-50/80 transition-colors"
          :class="highlightIds.has(m.id) ? 'animate-pulse bg-amber-100/50' : ''">
          <span class="shrink-0 px-2 py-0.5 rounded-md text-sm font-mono font-bold bg-amber-100 text-amber-700 border border-amber-200 min-w-[40px] text-center">{{ m.term }}</span>
          <div class="flex-1 min-w-0">
            <!-- 审核编辑模式（点击"通过"后） -->
            <template v-if="approvingId === m.id">
              <div class="space-y-2">
                <input v-model="editDesc" class="w-full px-2 py-1.5 text-sm border border-emerald-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-200" maxlength="100" placeholder="修改或确认梗的描述" />
                <div class="flex items-center gap-2 text-xs text-amber-500">
                  <AlertCircle class="w-3 h-3" />确认描述无误后点击"确认通过"
                </div>
              </div>
            </template>
            <!-- 普通编辑模式（点铅笔） -->
            <template v-else-if="editingId === m.id">
              <div class="flex items-center gap-2">
                <input v-model="editDesc" class="flex-1 px-2 py-1 text-sm border border-violet-300 rounded" maxlength="100" />
                <button @click="doSave(m.id)" class="p-1 text-green-500 hover:bg-green-50 rounded"><Check class="w-4 h-4" /></button>
                <button @click="editingId = null" class="p-1 text-slate-400 hover:bg-slate-100 rounded"><X class="w-4 h-4" /></button>
              </div>
            </template>
            <!-- 展示模式 -->
            <template v-else>
              <span class="text-sm" :class="isUncertain(m.description) ? 'italic text-amber-600' : 'text-slate-600'">{{ m.description }}</span>
              <span class="ml-1.5 text-[10px] text-slate-400 bg-slate-100 px-1 py-0.5 rounded">AI</span>
              <button @click="startEdit(m)" class="ml-1 p-0.5 text-slate-300 hover:text-slate-500 align-text-bottom"><Pencil class="w-3 h-3" /></button>
            </template>
          </div>
          <!-- 审核编辑模式下：确认通过 / 取消 -->
          <div v-if="approvingId === m.id" class="shrink-0 flex gap-1">
            <button @click="confirmApprove()" class="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-emerald-500 text-white hover:bg-emerald-600 transition-colors"><CheckCircle2 class="w-3.5 h-3.5" />确认通过</button>
            <button @click="cancelApprove()" class="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-slate-200 text-slate-500 hover:bg-slate-300 hover:text-slate-700 transition-colors">取消</button>
          </div>
          <!-- 普通模式：通过 / 驳回 -->
          <div v-else class="shrink-0 flex gap-1">
            <button @click="startApprove(m)" class="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-emerald-500 text-white hover:bg-emerald-600 transition-colors"><CheckCircle2 class="w-3.5 h-3.5" />通过</button>
            <button @click="doReject(m.id)" class="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-slate-200 text-slate-500 hover:bg-slate-300 hover:text-slate-700 transition-colors"><XCircle class="w-3.5 h-3.5" />驳回</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 扫描区 -->
    <div class="rounded-2xl border border-slate-200 bg-white p-5 space-y-3">
      <div class="flex items-center justify-between">
        <div>
          <h3 class="font-semibold text-slate-700 text-sm">AI 扫描发现</h3>
          <p class="text-xs text-slate-400 mt-0.5">
            扫描最近 <strong class="text-slate-500">2000 条</strong>消息（按发言人去重，最多采样 <strong class="text-slate-500">300 条</strong>），结合近期事件线索，识别群内自创梗。建议群聊活跃后使用，扫描结果需人工审核后生效。
          </p>
        </div>
        <button @click="doScan" :disabled="scanning"
          class="shrink-0 flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-xl bg-violet-500 text-white hover:bg-violet-600 disabled:opacity-50 transition-colors">
          <Sparkles v-if="!scanning" class="w-4 h-4" />
          <Loader2 v-else class="w-4 h-4 animate-spin" />
          {{ scanning ? '扫描中...' : 'AI 扫描' }}
        </button>
      </div>
      <!-- 扫描结果 -->
      <div v-if="scanMsg" class="space-y-2">
        <div class="flex items-center gap-2 p-3 rounded-lg text-sm"
          :class="scanMsg.includes('失败') ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-700'">
          <CheckCircle2 v-if="!scanMsg.includes('失败')" class="w-4 h-4 shrink-0" />
          <XCircle v-else class="w-4 h-4 shrink-0" />
          <span>{{ scanMsg }}</span>
          <span v-if="scanTime" class="text-xs opacity-60 ml-auto">{{ scanTime }}</span>
        </div>
        <!-- AI 原始返回（0 结果时展示，便于排查） -->
        <div v-if="aiRaw && !scanMsg.includes('失败')" class="p-3 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-500 font-mono break-all">
          <span class="text-slate-400">AI 原始返回：</span>{{ aiRaw }}
        </div>
      </div>
    </div>

    <!-- 已收录区 -->
    <div class="rounded-2xl border border-slate-200 bg-white overflow-hidden">
      <div class="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <BookOpen class="w-4 h-4 text-violet-500" />
          <h3 class="font-semibold text-slate-700 text-sm">已收录（{{ approvedMemes.length }}）</h3>
        </div>
        <button @click="showAdd = !showAdd"
          class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-violet-50 text-violet-600 hover:bg-violet-100 transition-colors">
          <Plus class="w-3.5 h-3.5" />添加
        </button>
      </div>

      <!-- 手动添加表单 -->
      <div v-if="showAdd" class="px-5 py-4 border-b border-slate-100 bg-slate-50/50 space-y-3">
        <div class="flex gap-3">
          <input v-model="newTerm" class="flex-1 px-3 py-2 text-sm border rounded-lg" placeholder="梗（词或短语）" maxlength="20" />
          <input v-model="newDesc" class="flex-[2] px-3 py-2 text-sm border rounded-lg" placeholder="群内含义" maxlength="100" />
        </div>
        <div class="flex gap-2">
          <button @click="doAdd" :disabled="!newTerm.trim() || !newDesc.trim()"
            class="px-4 py-1.5 text-sm font-medium rounded-lg bg-violet-500 text-white hover:bg-violet-600 disabled:opacity-50 transition-colors">确认添加</button>
          <button @click="showAdd = false; newTerm = ''; newDesc = ''"
            class="px-4 py-1.5 text-sm rounded-lg bg-slate-200 text-slate-600 hover:bg-slate-300 transition-colors">取消</button>
        </div>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="flex justify-center py-12">
        <Loader2 class="w-5 h-5 animate-spin text-slate-300" />
      </div>

      <!-- 空态 -->
      <div v-else-if="!approvedMemes.length" class="py-12 text-center">
        <BookOpen class="w-8 h-8 text-slate-200 mx-auto mb-2" />
        <p class="text-sm text-slate-400">暂无已收录的梗</p>
        <p class="text-xs text-slate-300 mt-1">使用 AI 扫描或手动添加</p>
      </div>

      <!-- 梗列表 -->
      <div v-else class="divide-y divide-slate-50">
        <div v-for="m in approvedMemes" :key="m.id"
          class="px-5 py-3 flex items-start gap-3 hover:bg-slate-50/50 transition-colors group">
          <span class="shrink-0 px-2 py-0.5 rounded-md text-sm font-mono font-bold bg-violet-50 text-violet-700 border border-violet-200 min-w-[40px] text-center">{{ m.term }}</span>
          <div class="flex-1 min-w-0">
            <template v-if="editingId === m.id">
              <div class="flex items-center gap-2">
                <input v-model="editDesc" class="flex-1 px-2 py-1 text-sm border border-violet-300 rounded" maxlength="100" />
                <button @click="doSave(m.id)" class="p-1 text-green-500 hover:bg-green-50 rounded"><Check class="w-4 h-4" /></button>
                <button @click="editingId = null" class="p-1 text-slate-400 hover:bg-slate-100 rounded"><X class="w-4 h-4" /></button>
              </div>
            </template>
            <template v-else>
              <span class="text-sm text-slate-600">{{ m.description }}</span>
              <span v-if="m.source === 'ai'" class="ml-1.5 text-[10px] text-slate-400 bg-slate-100 px-1 py-0.5 rounded">AI</span>
            </template>
          </div>
          <div class="shrink-0 flex gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <button @click="startEdit(m)" class="p-1 text-slate-400 hover:text-slate-600"><Pencil class="w-3.5 h-3.5" /></button>
            <button @click="doDelete(m)" class="p-1 text-slate-400 hover:text-red-500"><Trash2 class="w-3.5 h-3.5" /></button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
