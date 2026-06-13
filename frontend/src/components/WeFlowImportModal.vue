<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { X, Search, Link2, RefreshCw, Loader2, CheckCircle, AlertCircle, Sparkles, Clock } from 'lucide-vue-next'
import { getWeFlowSessions, triggerWeFlowSync, linkWeFlowGroup, toggleWeFlowAutoSync, unlinkWeFlowGroup } from '../api'

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

// 判断群是否已有合法 WeFlow wxid（已关联）
function isAlreadyLinked(group) {
  const wxid = group?.wxid || ''
  return wxid.startsWith('wxid_') || wxid.includes('@chatroom')
}

onMounted(async () => {
  if (!props.group) {
    loading.value = false
    return
  }

  // 已关联：直接显示确认框，免去拉取会话列表
  if (isAlreadyLinked(props.group)) {
    autoMatch.value = {
      session: {
        id: props.group.wxid,
        name: props.group.display_name || props.group.name,
        linked: true,
        group_id: props.group.id,
        auto_sync: !!props.group.weflow_auto_sync,
        last_sync_at: props.group.weflow_last_sync_at || '',
        last_sync_result: props.group.weflow_last_sync_result || '',
      },
      reason: 'linked',
    }
    loading.value = false
    return
  }

  // 未关联：拉取会话列表做自动匹配
  try {
    const data = await getWeFlowSessions()
    sessions.value = (data.sessions || [])
      .filter(s => s.type === 'group' || s.type === 'private')
      .sort((a, b) => {
        if (a.linked && !b.linked) return -1
        if (!a.linked && b.linked) return 1
        return (b.messageCount || 0) - (a.messageCount || 0)
      })

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

  // 1. 群名唯一匹配
  const byName = sessions.value.filter(s => !s.linked && s.name === groupName)
  if (byName.length === 1) {
    autoMatch.value = { session: byName[0], reason: 'name_match' }
    return
  }

  // 2. 群名包含匹配（唯一结果）
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

async function toggleAutoSync(session) {
  try {
    const newVal = !session.auto_sync
    await toggleWeFlowAutoSync(session.group_id, newVal)
    session.auto_sync = newVal
  } catch (e) {
    showError?.('操作失败', e.message || '未知错误')
  }
}

async function doUnlink(session) {
  if (!confirm(`确定取消「${session.name || session.id}」与 WeFlow 的关联？\n不会删除已有数据，仅取消关联关系。`)) return
  try {
    await unlinkWeFlowGroup(session.group_id)
    session.linked = false
    session.auto_sync = false
    autoMatch.value = null  // 回退到列表视图
  } catch (e) {
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

            <!-- Auto-sync toggle (linked only) -->
            <div v-if="autoMatch.reason === 'linked'" class="flex items-center justify-between bg-slate-50 rounded-xl px-4 py-2.5">
              <div class="flex items-center gap-2">
                <Clock :size="14" class="text-slate-400" />
                <span class="text-sm text-slate-600">自动同步</span>
              </div>
              <button @click="toggleAutoSync(autoMatch.session)"
                      :class="['w-10 h-5 rounded-full transition-colors', autoMatch.session.auto_sync ? 'bg-emerald-400' : 'bg-gray-300']">
                <div :class="['w-4 h-4 rounded-full bg-white shadow transition-transform mt-0.5', autoMatch.session.auto_sync ? 'translate-x-5' : 'translate-x-0.5']" />
              </button>
            </div>
            <!-- Last sync info (linked only) -->
            <div v-if="autoMatch.reason === 'linked' && autoMatch.session.last_sync_at" class="text-center text-[10px] text-slate-400">
              上次同步：{{ autoMatch.session.last_sync_at }} &nbsp;{{ autoMatch.session.last_sync_result }}
            </div>

            <div class="flex gap-2">
              <button v-if="autoMatch.reason !== 'linked'"
                      @click="cancelAutoMatch"
                      class="flex-1 py-2.5 text-sm text-slate-500 border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors">
                从列表选择
              </button>
              <button v-if="autoMatch.reason === 'linked'"
                      @click="doUnlink(autoMatch.session)"
                      class="px-3 py-2.5 text-sm text-red-400 border border-red-200 rounded-xl hover:bg-red-50 transition-colors">
                取消关联
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
                   class="flex flex-col px-3 py-2.5 rounded-xl transition-colors"
                   :class="s.linked ? 'bg-emerald-50/50 border border-emerald-100/50' : 'hover:bg-slate-50 border border-transparent'">
                <div class="flex items-center gap-3">
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
                          @click="doUnlink(s)"
                          class="px-2 py-1 rounded-lg text-[10px] text-red-400 hover:text-red-600 hover:bg-red-50 transition-all flex-shrink-0"
                          title="取消关联">
                    <X :size="12" />
                  </button>
                  <button v-if="s.linked"
                          @click="doSync(s)"
                          :disabled="!!syncing[s.id] || !!activeTaskId"
                          class="px-2.5 py-1.5 rounded-lg text-[10px] font-medium bg-gradient-to-r from-emerald-500 to-teal-600 text-white hover:opacity-90 disabled:opacity-40 transition-all flex items-center gap-1 flex-shrink-0">
                    <Loader2 v-if="syncing[s.id] === 'loading'" :size="10" class="animate-spin" />
                    <RefreshCw v-else :size="10" />
                  </button>
                  <button v-else
                          @click="doLinkAndSyncForSession(s)"
                          :disabled="!!syncing[s.id]"
                          class="px-2.5 py-1.5 rounded-lg text-[10px] font-medium border border-slate-200 text-slate-500 hover:border-emerald-300 hover:text-emerald-600 transition-all flex items-center gap-1 flex-shrink-0">
                    <Link2 :size="10" />
                    关联
                  </button>
                </div>
                <!-- Auto-sync toggle + last sync status (linked only) -->
                <div v-if="s.linked" class="flex items-center gap-3 mt-1.5 ml-12 text-[10px]">
                  <button @click="toggleAutoSync(s)"
                          :class="['w-8 h-4 rounded-full transition-colors flex-shrink-0', s.auto_sync ? 'bg-emerald-400' : 'bg-gray-300']">
                    <div :class="['w-3 h-3 rounded-full bg-white shadow transition-transform mt-0.5', s.auto_sync ? 'translate-x-4' : 'translate-x-0.5']" />
                  </button>
                  <span class="text-slate-400">自动同步</span>
                  <span v-if="s.last_sync_at" class="text-slate-300 flex items-center gap-1">
                    <Clock :size="10" />
                    {{ s.last_sync_at.slice(5) }} &nbsp;{{ s.last_sync_result }}
                  </span>
                  <span v-else class="text-slate-300">尚未同步</span>
                </div>
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
