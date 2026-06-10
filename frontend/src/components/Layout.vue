<script setup>
import { ref, inject, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import GroupSelector from './GroupSelector.vue'
import UploadModal from './UploadModal.vue'
import { MessageCircle, Users, LayoutDashboard, Loader2, Fish } from 'lucide-vue-next'
import { listGroups } from '../api/index.js'

const props = defineProps({ currentGroup: Object })
const emit = defineEmits(['group-change'])

const router = useRouter()
const route = useRoute()
const showUpload = ref(false)
const importLoading = ref(false)
const activeTaskId = inject('activeTaskId', ref(''))
const groupSelectorRef = ref(null)

const navItems = [
  { path: '/', label: '仪表盘', icon: LayoutDashboard },
  { path: '/portraits', label: '群友画像', icon: Users },
  { path: '/fishpond', label: '群鱼塘', icon: Fish },
]

function navTo(path) {
  router.push(path)
}

async function onUploaded(data) {
  showUpload.value = false
  // 导入新群：刷新群列表下拉菜单，选中新导入的群并跳转
  importLoading.value = true
  try {
    // 先刷新 GroupSelector 的群列表
    if (groupSelectorRef.value) {
      await groupSelectorRef.value.reload()
    }
    const groups = await listGroups()
    const newGroup = groups.find(g => g.id === data.group_id)
    if (newGroup) {
      emit('group-change', newGroup)
      router.push('/')
    } else {
      // 找回 first group
      if (groups.length > 0) {
        emit('group-change', groups[0])
        router.push('/')
      }
    }
  } catch (e) { console.error(e) }
  finally { importLoading.value = false }
}
</script>

<template>
  <div class="min-h-screen bg-slate-100">
    <!-- 顶部导航 -->
    <header class="bg-white border-b border-slate-200 sticky top-0 z-30">
      <div class="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        <div class="flex items-center gap-6">
          <!-- Logo -->
          <div class="flex items-center gap-2 text-indigo-600 font-bold text-lg">
            <MessageCircle class="w-5 h-5" />
            <span class="hidden sm:inline">Chat-Miner</span>
          </div>
          <!-- 群选择器 -->
          <GroupSelector
            ref="groupSelectorRef"
            :current="currentGroup"
            @select="emit('group-change', $event)"
            @upload-click="showUpload = true"
          />
        </div>
        <!-- 导航 -->
        <nav v-if="currentGroup" class="flex items-center gap-1">
          <button
            v-for="item in navItems"
            :key="item.path"
            @click="navTo(item.path)"
            :class="[
              'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors',
              route.path === item.path
                ? 'bg-indigo-50 text-indigo-700 font-medium'
                : 'text-slate-500 hover:text-slate-800 hover:bg-slate-100',
            ]"
          >
            <component :is="item.icon" class="w-4 h-4" />
            {{ item.label }}
          </button>
          <!-- 任务进行中指示灯 -->
          <div v-if="activeTaskId" class="flex items-center gap-1.5 px-2 py-1 text-xs text-indigo-500">
            <Loader2 class="w-3.5 h-3.5 animate-spin" />
            <span class="hidden sm:inline">分析中</span>
          </div>
        </nav>
      </div>
    </header>

    <!-- 主内容 -->
    <main class="max-w-6xl mx-auto px-4 py-6">
      <!-- 未选群 -->
      <div v-if="!currentGroup" class="flex flex-col items-center justify-center py-32">
        <MessageCircle class="w-16 h-16 text-slate-300 mb-4" />
        <h2 class="text-xl font-semibold text-slate-600 mb-2">欢迎使用 Chat-Miner</h2>
        <p class="text-slate-400 mb-6">导入微信群聊记录，用 AI 生成有趣的每日报告和群友画像</p>
        <button
          @click="showUpload = true"
          class="px-6 py-3 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-200"
        >
          导入群聊数据
        </button>
      </div>
      <!-- 已选群 -->
      <slot v-else />
    </main>

    <!-- 导入中遮罩 -->
    <div v-if="importLoading" class="fixed inset-0 z-50 flex items-center justify-center bg-black/20">
      <div class="bg-white rounded-xl shadow-xl px-8 py-6 text-center">
        <Loader2 class="w-8 h-8 animate-spin text-indigo-400 mx-auto mb-3" />
        <p class="text-sm text-slate-600">导入完成，加载中...</p>
      </div>
    </div>

    <!-- 上传弹窗 -->
    <UploadModal
      v-if="showUpload"
      @close="showUpload = false"
      @uploaded="onUploaded"
    />
  </div>
</template>
