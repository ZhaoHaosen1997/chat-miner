<script setup>
import { ref, provide, onMounted } from 'vue'
import Layout from './components/Layout.vue'
import ProgressPanel from './components/ProgressPanel.vue'
import ErrorModal from './components/ErrorModal.vue'
import { getActiveTasks, listGroups } from './api/index.js'

const currentGroup = ref(null)
const refreshKey = ref(0)

// 全局任务管理
const activeTaskId = ref('')
const taskHistory = ref([])  // [{taskId, groupName, type, status, finishedAt}]

// v0.12.5: 全局错误弹窗
const errorModalRef = ref(null)
function showError(title, message, detail = '', context = '') {
  errorModalRef.value?.show({ title, message, detail, context })
}
provide('showError', showError)

// 页面刷新后恢复进行中任务 + 自动选择默认群
onMounted(async () => {
  try {
    const active = await getActiveTasks()
    if (active.length > 0) {
      activeTaskId.value = active[0].task_id
    }
  } catch (e) { /* ignore */ }

  // v0.12.0: 自动选择默认群
  try {
    const defaultGid = localStorage.getItem('defaultGroupId')
    if (defaultGid && !currentGroup.value) {
      const groups = await listGroups()
      const target = groups.find(g => String(g.id) === String(defaultGid))
      if (target) {
        currentGroup.value = target
      }
    }
  } catch (e) { /* ignore */ }
})

provide('currentGroup', currentGroup)
provide('triggerRefresh', () => refreshKey.value++)
provide('activeTaskId', activeTaskId)
provide('addTaskHistory', (entry) => {
  // 去重
  const idx = taskHistory.value.findIndex(t => t.taskId === entry.taskId)
  if (idx >= 0) {
    taskHistory.value[idx] = entry
  } else {
    taskHistory.value.unshift(entry)
  }
  // 只保留最近 20 条
  if (taskHistory.value.length > 20) taskHistory.value.pop()
})

function onGroupChange(group) {
  currentGroup.value = group
  // v0.13.3: 切换群组时清理上一个群的活动任务 ID
  activeTaskId.value = ''
}

function onTaskDone(data) {
  if (data.status === 'done' || data.status === 'failed' || data.status === 'cancelled') {
    // 记录到历史
    addTaskHistoryEntry(activeTaskId.value, data)
    activeTaskId.value = ''
  }
}

function addTaskHistoryEntry(taskId, data) {
  const entry = {
    taskId,
    groupName: currentGroup.value?.display_name || currentGroup.value?.name || '',
    type: data.type || 'analyze_day',
    status: data.status,
    step: data.step,
    error: data.error,
    finishedAt: new Date().toLocaleString('zh'),
  }
  const idx = taskHistory.value.findIndex(t => t.taskId === taskId)
  if (idx >= 0) {
    taskHistory.value[idx] = entry
  } else {
    taskHistory.value.unshift(entry)
  }
  if (taskHistory.value.length > 20) taskHistory.value.pop()
}
</script>

<template>
  <div>
    <Layout :current-group="currentGroup" @group-change="onGroupChange">
      <router-view :key="refreshKey" />
    </Layout>

    <!-- 全局任务进度面板 -->
    <ProgressPanel
      v-if="activeTaskId"
      :task-id="activeTaskId"
      @done="onTaskDone"
      @close="activeTaskId = ''"
    />

    <!-- 全局错误弹窗 -->
    <ErrorModal ref="errorModalRef" />
  </div>
</template>
