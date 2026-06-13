<script setup>
import { ref, inject, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import GroupSelector from './GroupSelector.vue'
import UploadModal from './UploadModal.vue'
import { MessageCircle, Users, LayoutDashboard, Loader2, Fish, Settings } from 'lucide-vue-next'
import { listGroups, apiGet } from '../api/index.js'

const props = defineProps({ currentGroup: Object })
const emit = defineEmits(['group-change'])

const router = useRouter()
const route = useRoute()
const showUpload = ref(false)
const importLoading = ref(false)

// ---- Keyboard: W/S or Up/Down to switch report type ----
function getISOWeekNumber(d) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  date.setUTCDate(date.getUTCDate() + 4 - (date.getUTCDay() || 7))
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1))
  const weekNo = Math.ceil(((date - yearStart) / 86400000 + 1) / 7)
  return weekNo
}

function dateToWeek(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  const week = getISOWeekNumber(d)
  const year = d.getFullYear()
  return `${year}-W${String(week).padStart(2, '0')}`
}

function weekToMonth(weekStr) {
  // Parse "2026-W24" → first day of that week → month
  const [y, w] = weekStr.split('-W')
  const jan4 = new Date(Date.UTC(+y, 0, 4))
  const firstMonday = new Date(jan4)
  firstMonday.setUTCDate(jan4.getUTCDate() - (jan4.getUTCDay() || 7) + 1)
  const monday = new Date(firstMonday)
  monday.setUTCDate(firstMonday.getUTCDate() + (+w - 1) * 7)
  return `${monday.getUTCFullYear()}-${String(monday.getUTCMonth() + 1).padStart(2, '0')}`
}

function monthToYear(monthStr) {
  return monthStr.split('-')[0]
}

function reportTypeSwitch(direction) {
  const p = route.path
  const up = direction === 'up'

  // Daily → Weekly
  const dailyMatch = p.match(/^\/report\/(\d{4}-\d{2}-\d{2})$/)
  if (dailyMatch) {
    if (up) { router.push(`/weekly/${dateToWeek(dailyMatch[1])}`); return }
    return // daily is lowest, can't go down
  }

  // Weekly → Monthly (up) or Daily (down)
  const weeklyMatch = p.match(/^\/weekly\/(\d{4}-W\d{2})$/)
  if (weeklyMatch) {
    if (up) { router.push(`/monthly/${weekToMonth(weeklyMatch[1])}`); return }
    // Down: go to the Monday of this week
    const [y, w] = weeklyMatch[1].split('-W')
    const jan4 = new Date(Date.UTC(+y, 0, 4))
    const firstMonday = new Date(jan4)
    firstMonday.setUTCDate(jan4.getUTCDate() - (jan4.getUTCDay() || 7) + 1)
    const monday = new Date(firstMonday)
    monday.setUTCDate(firstMonday.getUTCDate() + (+w - 1) * 7)
    router.push(`/report/${monday.toISOString().slice(0, 10)}`)
    return
  }

  // Monthly → Annual (up) or Weekly (down)
  const monthlyMatch = p.match(/^\/monthly\/(\d{4}-\d{2})$/)
  if (monthlyMatch) {
    if (up) { router.push(`/annual/${monthToYear(monthlyMatch[1])}`); return }
    // Down: go to first week of this month
    const [y, m] = monthlyMatch[1].split('-')
    const firstDay = new Date(+y, +m - 1, 1)
    router.push(`/weekly/${dateToWeek(firstDay.toISOString().slice(0, 10))}`)
    return
  }

  // Annual → Monthly (down only)
  const annualMatch = p.match(/^\/annual\/(\d{4})$/)
  if (annualMatch) {
    if (!up) { router.push(`/monthly/${annualMatch[1]}-01`); return }
    return // annual is highest, can't go up
  }
}

function onReportTypeKey(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return
  if (e.key === 'ArrowUp' || e.key === 'w' || e.key === 'W') {
    e.preventDefault()
    reportTypeSwitch('up')
  } else if (e.key === 'ArrowDown' || e.key === 's' || e.key === 'S') {
    e.preventDefault()
    reportTypeSwitch('down')
  }
}

onMounted(() => window.addEventListener('keydown', onReportTypeKey))
onUnmounted(() => window.removeEventListener('keydown', onReportTypeKey))
const activeTaskId = inject('activeTaskId', ref(''))
const groupSelectorRef = ref(null)
const appVersion = ref('')

// 浏览器标题
	document.title = 'Chat-Miner'

	// 获取版本号
onMounted(async () => {
  try {
    const health = await apiGet('/health')
    appVersion.value = health?.version || ''
  } catch (e) { /* ignore */ }
})

const navItems = [
  { path: '/', label: '仪表盘', icon: LayoutDashboard },
  { path: '/portraits', label: '群友画像', icon: Users },
  { path: '/fishpond', label: '群鱼塘', icon: Fish },
  { path: '/settings', label: '设置', icon: Settings },
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
  <div class="min-h-screen" style="background: var(--color-page)">
    <!-- 顶部导航 -->
    <header class="bg-white/80 backdrop-blur-md border-b border-slate-200/60 sticky top-0 z-30">
      <div class="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        <div class="flex items-center gap-6">
          <!-- Logo -->
          <div class="flex items-center gap-2">
            <span class="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
              <MessageCircle class="w-4 h-4 text-white" />
            </span>
            <span class="hidden sm:inline text-slate-800 font-bold text-lg">Chat-Miner</span>
            <span v-if="appVersion" class="text-[10px] text-slate-400 font-medium">{{ appVersion }}</span>
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
