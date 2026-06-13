<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { X, Search, Link2, RefreshCw, Loader2, CheckCircle, AlertCircle, Sparkles } from 'lucide-vue-next'
import { getWeFlowSessions, triggerWeFlowSync, linkWeFlowGroup } from '../api'

const props = defineProps({
  group: { type: Object, default: null },  // currentGroup from Dashboard
})
const emit = defineEmits(['close'])

const activeTaskId = inject('activeTaskId')
const showError = inject('showError')

const sessions = ref([])
const loading = ref(true)
const searchKeyword = ref('')
const errorMsg = ref('')
const syncing = ref({})   // { sessionId: 'loading' | 'done' | 'error' }
const linking = ref(false)

// 自动匹配结果
const autoMatch = ref(null)  // null=还未检查, {session}=匹配成功, false=无匹配

const filteredSessions = computed(() => {
  if (!searchKeyword.value) return sessions.value
  const kw = searchKeyword.value.toLowerCase()
  return sessions.value.filter(s =>
    (s.name || '').toLowerCase().includes(kw) ||
    (s.id || '').toLowerCase().includes(kw)
  )
})

onMounted(async () => {
  try {
    const data = await getWeFlowSessions()
    sessions.value = (data.sessions || [])
      .filter(s => s.type === 'group')
      .sort((a, b) => {
        if (a.linked && !b.linked) return -1
        if (!a.linked && b.linked) return 1
        return (b.messageCount || 0) - (a.messageCount || 0)
      })

    // 自动匹配：当前群名 vs WeFlow 会话名
    if (props.group) {
      tryAutoMatch()
    }
  } catch (e) {
    errorMsg.value = e.message || '获取 WeFlow 会话列表失败'
  } finally {
    loading.value = false
  }
})

function tryAutoMatch() {
  const groupName = props.group?.display_name || props.group?.name || ''
  if (!groupName) { autoMatch.value = false; return }

  // 1. wxid 精确匹配（已关联）→ 直接跳过匹配阶段
  const byWxid = sessions.value.find(s => s.linked && s.group_id === props.group.id)
  if (byWxid) {
    autoMatch.value = { session: byWxid, reason: 'linked' }
    return
  }

  // 2. 群名唯一匹配
  const byName = sessions.value.filter(s => !s.linked && s.name === groupName)
  if (byName.length === 1) {
    autoMatch.value = { session: byName[0], reason: 'name_match' }
    return
  }

  // 3. 群名包含匹配（唯一结果）
  const byFuzzy = sessions.value.filter(s =>
    !s.linked &&
    s.name && groupName &&
    (s.name.includes(groupName) || groupName.includes(s.name))
  )
  if (byFuzzy.length === 1) {
    autoMatch.value = { session: byFuzzy[0], reason: 'fuzzy_match' }
    return
  }

  autoMatch.value = false
}

async function doSync(session) {
  if (syncing.value[session.id]) return
  syncing.value = { ...syncing.value, [session.id]: 'loading' }

  try {
    const result = await triggerWeFlowSync(session.group_id)
    syncing.value = { ...syncing.value, [session.id]: 'done' }
    if (result.task_id) {
      activeTaskId.value = result.task_id
    }
    emit('close')
  } catch (e) {
    syncing.value = { ...syncing.value, [session.id]: 'error' }
    showError?.('同步失败', e.message || '未知错误')
  }
}

async function doLinkAndSync() {
  if (linking.value) return
  const session = autoMatch.value?.session
  if (!session) return

  linking.value = true
  try {
    // 先关联
    await linkWeFlowGroup(props.group.id, session.id)
    // 立即同步
    const result = await triggerWeFlowSync(props.group.id)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    }
    emit('close')
  } catch (e) {
    showError?.('操作失败', e.message || '未知错误')
  } finally {
    linking.value = false
  }
}

function cancelAutoMatch() {
  autoMatch.value = false  // 回退到列表视图
}

async function doLinkAndSyncForSession(session) {
  // 列表视图中对未关联群点击"关联"——需要当前群已在项目中
  if (!props.group) {
    showError?.('提示', '请先在首页选择一个群')
    return
  }
  if (syncing.value[session.id]) return
  syncing.value = { ...syncing.value, [session.id]: 'loading' }
  try {
    await linkWeFlowGroup(props.group.id, session.id)
    const result = await triggerWeFlowSync(props.group.id)
    if (result.task_id) activeTaskId.value = result.task_id
    emit('close')
  } catch (e) {
    syncing.value = { ...syncing.value, [session.id]: 'error' }
    showError?.('操作失败', e.message || '未知错误')
  }
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/30 backdrop-blur-sm" @click.self="emit('close')">
      <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[80vh] flex flex-col overflow-hidden">
        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-slate-100">
          <div class="flex items-center gap-2.5">
            <div class="w-8 h-8 rounded-lg bg-emerald-100 flex items-center justify-center">
              <RefreshCw :size="16" class="text-emerald-600" />
            </div>
            <div>
              <h2 class="text-sm font-semibold text-slate-800">WeFlow 同步</h2>
              <p class="text-[10px] text-slate-400">
                {{ autoMatch ? '已自动匹配群聊' : '选择要同步的群聊' }}
              </p>
            </div>
          </div>
          <button @click="emit('close')" class="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400">
            <X :size="18" />
          </button>
        </div>

        <!-- Auto-match Confirmation -->
        <template v-if="autoMatch">
          <div class="flex-1 p-5 space-y-4">
            <div class="text-center">
              <div class="w-14 h-14 rounded-2xl bg-emerald-100 flex items-center justify-center mx-auto mb-3">
                <Sparkles :size="24" class="text-emerald-600" />
              </div>
              <h3 class="text-sm font-semibold text-slate-800 mb-1">
                {{ autoMatch.reason === 'linked' ? '已关联到 WeFlow' : '自动匹配到 WeFlow 群聊' }}
              </h3>
              <p class="text-xs text-slate-400">
                {{ autoMatch.reason === 'name_match' ? '群名完全一致，确认后将自动关联并增量同步' :
                   autoMatch.reason === 'fuzzy_match' ? '群名相似，确认后将自动关联并增量同步' :
                   '点击同步拉取新消息' }}
              </p>
            </div>

            <div class="bg-slate-50 rounded-xl p-4 space-y-2 text-sm">
              <div class="flex justify-between">
                <span class="text-slate-400">本地群</span>
                <span class="font-medium text-slate-700">{{ props.group?.display_name || props.group?.name || '-' }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">WeFlow 群</span>
                <span class="font-medium text-slate-700">{{ autoMatch.session.name }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-slate-400">会话 ID</span>
                <span class="font-mono text-xs text-slate-500 truncate max-w-48">{{ autoMatch.session.id }}</span>
              </div>
            </div>

            <div class="flex gap-2">
              <button v-if="autoMatch.reason !== 'linked'"
                      @click="cancelAutoMatch"
                      class="flex-1 py-2.5 text-sm text-slate-500 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors">
                从列表选择
              </button>
              <button @click="autoMatch.reason === 'linked' ? doSync(autoMatch.session) : doLinkAndSync()"
                      :disabled="linking || !!activeTaskId"
                      class="flex-1 py-2.5 text-sm font-medium bg-gradient-to-r from-emerald-500 to-teal-600 text-white rounded-xl hover:opacity-90 disabled:opacity-40 transition-all flex items-center justify-center gap-1.5">
                <Loader2 v-if="linking" :size="14" class="animate-spin" />
                <RefreshCw v-else :size="14" />
                {{ linking ? '关联中...' : autoMatch.reason === 'linked' ? '开始同步' : '关联并同步' }}
              </button>
            </div>
          </div>
        </template>

        <!-- List View (no auto-match) -->
        <template v-else>
          <!-- Search -->
          <div class="px-5 py-3 border-b border-slate-50">
            <div class="relative">
              <Search :size="14" class="absolute left-3 top-1/2 -translate-y-1/2 text-slate-300" />
              <input v-model="searchKeyword" placeholder="搜索群名或 ID..." class="w-full pl-8 pr-3 py-2 text-xs rounded-lg border border-slate-200 focus:border-emerald-400 focus:ring-1 focus:ring-emerald-100 outline-none" />
            </div>
          </div>

          <!-- Session List -->
          <div class="flex-1 overflow-y-auto px-5 py-2">
            <div v-if="loading" class="text-center py-8 text-slate-400">
              <Loader2 :size="20" class="animate-spin inline" /> 加载中...
            </div>
            <div v-else-if="errorMsg" class="text-center py-8 text-red-400 text-xs">
              <AlertCircle :size="18" class="inline mb-1" /> {{ errorMsg }}
            </div>
            <div v-else-if="filteredSessions.length === 0" class="text-center py-8 text-slate-400 text-xs">
              没有匹配的群聊
            </div>
            <div v-else class="space-y-1 py-1">
              <div v-for="s in filteredSessions" :key="s.id"
                   class="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors"
                   :class="s.linked ? 'bg-emerald-50/50 border border-emerald-100/50' : 'hover:bg-slate-50 border border-transparent'">
                <div class="w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0"
                     :class="s.linked ? 'bg-emerald-100 text-emerald-600' : 'bg-slate-100 text-slate-400'">
                  <CheckCircle v-if="s.linked" :size="16" />
                  <Link2 v-else :size="16" />
                </div>
                <div class="flex-1 min-w-0">
                  <div class="text-xs font-medium text-slate-700 truncate">{{ s.name }}</div>
                  <div class="text-[10px] text-slate-400 truncate">{{ s.id }}</div>
                </div>
                <button v-if="s.linked"
                        @click="doSync(s)"
                        :disabled="!!syncing[s.id] || !!activeTaskId"
                        class="px-3 py-1.5 rounded-lg text-[10px] font-medium bg-gradient-to-r from-emerald-500 to-teal-600 text-white hover:opacity-90 disabled:opacity-40 transition-all flex items-center gap-1 flex-shrink-0">
                  <Loader2 v-if="syncing[s.id] === 'loading'" :size="10" class="animate-spin" />
                  <RefreshCw v-else :size="10" />
                  {{ syncing[s.id] === 'loading' ? '同步中' : '同步' }}
                </button>
                <button v-else
                        @click="doLinkAndSyncForSession(s)"
                        :disabled="!!syncing[s.id]"
                        class="px-3 py-1.5 rounded-lg text-[10px] font-medium border border-slate-200 text-slate-500 hover:border-emerald-300 hover:text-emerald-600 transition-all flex items-center gap-1 flex-shrink-0">
                  <Link2 :size="10" />
                  关联
                </button>
              </div>
            </div>
          </div>
        </template>

        <!-- Footer -->
        <div class="px-5 py-3 border-t border-slate-100 bg-slate-50/50">
          <p class="text-[10px] text-slate-400">已关联 {{ sessions.filter(s => s.linked).length }} / {{ sessions.length }} 个群 &nbsp;·&nbsp; 首次导入请用 ArkMe JSON</p>
        </div>
      </div>
    </div>
  </Teleport>
</template>
