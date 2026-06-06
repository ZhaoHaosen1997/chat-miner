<script setup>
import { ref, inject, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getReport, analyzeDateAsync, deleteReport } from '../api/index.js'
import { ArrowLeft, Sparkles, Loader2, Clock, MessageSquare, Users, Hash, RefreshCw } from 'lucide-vue-next'

const props = defineProps({ date: String })
const router = useRouter()
const currentGroup = inject('currentGroup')
const activeTaskId = inject('activeTaskId')

const reanalyzing = ref(false)

async function reanalyze() {
  if (reanalyzing.value || activeTaskId.value) return
  reanalyzing.value = true
  try {
    // 删除旧报告
    try { await deleteReport(currentGroup.value.id, props.date) } catch(e) {}
    // 触发重分析
    const result = await analyzeDateAsync(currentGroup.value.id, props.date)
    if (result.task_id) {
      activeTaskId.value = result.task_id
    } else {
      // 立即完成（消息太少等）
      await load()
    }
  } catch (e) { console.error(e) }
  finally { reanalyzing.value = false }
}

const report = ref(null)
const stats = ref(null)
const loading = ref(true)
const analyzing = ref(false)
const error = ref('')

async function load() {
  if (!currentGroup.value || !props.date) return
  loading.value = true
  error.value = ''
  try {
    const data = await getReport(currentGroup.value.id, props.date)
    report.value = data.report
    stats.value = data.stats
  } catch (e) {
    // 未分析，尝试触发分析
    if (e.message?.includes('404') || e.message?.includes('尚未分析')) {
      error.value = 'not_analyzed'
    } else {
      error.value = e.message
    }
  } finally {
    loading.value = false
  }
}

async function startAnalyze() {
  if (analyzing.value) return
  analyzing.value = true
  error.value = ''
  try {
    const data = await analyzeDate(currentGroup.value.id, props.date)
    report.value = data.report
    stats.value = data.stats
    error.value = ''
  } catch (e) {
    error.value = e.message
  } finally {
    analyzing.value = false
  }
}

watch([currentGroup, () => props.date], load, { immediate: true })

// 重分析完成后刷新
watch(activeTaskId, (newVal, oldVal) => {
  if (oldVal && !newVal) {
    load()
  }
})

function goBack() { router.push('/') }

// 活跃时段
const hourLabels = Array.from({ length: 24 }, (_, i) => `${String(i).padStart(2, '0')}:00`)
const maxHourCount = ref(0)
watch(stats, (s) => {
  if (s?.hourly_distribution) {
    maxHourCount.value = Math.max(1, ...Object.values(s.hourly_distribution))
  }
})
</script>

<template>
  <div>
    <!-- 返回 -->
    <button @click="goBack" class="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 mb-4 transition-colors">
      <ArrowLeft class="w-4 h-4" /> 返回仪表盘
    </button>

    <!-- 加载 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <!-- 未分析 -->
    <div v-else-if="error === 'not_analyzed'" class="card p-12 text-center">
      <Sparkles class="w-12 h-12 text-slate-300 mx-auto mb-3" />
      <p class="text-slate-500 mb-4">{{ props.date }} 尚未分析</p>
      <button
        @click="startAnalyze"
        :disabled="analyzing"
        class="px-5 py-2.5 bg-indigo-600 text-white rounded-xl font-medium hover:bg-indigo-700 transition-all inline-flex items-center gap-2"
      >
        <Loader2 v-if="analyzing" class="w-4 h-4 animate-spin" />
        <Sparkles v-else class="w-4 h-4" />
        {{ analyzing ? 'AI 分析中...' : '开始 AI 分析' }}
      </button>
    </div>

    <!-- 错误 -->
    <div v-else-if="error" class="card p-8 text-center">
      <p class="text-red-400">加载失败：{{ error }}</p>
    </div>

    <!-- 报告内容 -->
    <template v-else-if="report">
      <!-- 头部 -->
      <div class="card p-6 mb-6 text-center">
        <div class="text-5xl mb-3">{{ report.mood_emoji }}</div>
        <h2 class="text-2xl font-bold text-slate-800 mb-1">{{ report.one_line }}</h2>
        <p v-if="report.headline && report.headline !== report.one_line" class="text-sm text-indigo-500 font-medium mb-1">📺 {{ report.headline }}</p>
        <div class="flex items-center justify-center gap-3">
          <p class="text-slate-400 text-sm">{{ props.date }} · {{ report.mood }}</p>
          <button
            @click="reanalyze"
            :disabled="reanalyzing"
            class="flex items-center gap-1 text-xs text-slate-400 hover:text-indigo-500 transition-colors disabled:opacity-50"
            title="重新分析（删除旧报告后调用 AI 重跑）"
          >
            <RefreshCw :class="['w-3 h-3', reanalyzing && 'animate-spin']" />
            {{ reanalyzing ? '分析中...' : '重新分析' }}
          </button>
        </div>
        <div class="flex justify-center gap-2 mt-3">
          <span
            v-for="kw in report.keywords"
            :key="kw"
            class="px-3 py-1 bg-indigo-50 text-indigo-600 rounded-full text-sm"
          >#{{ kw }}</span>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <!-- 主内容区 -->
        <div class="lg:col-span-2 space-y-6">
          <!-- 话题总结 -->
          <div class="card p-5">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <Hash class="w-4 h-4 text-indigo-400" /> 今日话题
            </h3>
            <div class="space-y-3">
              <div
                v-for="(topic, i) in report.topic_summary"
                :key="i"
                class="flex gap-3 p-3 bg-slate-50 rounded-xl"
              >
                <span class="flex-shrink-0 w-7 h-7 rounded-lg bg-indigo-100 text-indigo-600 font-bold text-sm flex items-center justify-center">
                  {{ i + 1 }}
                </span>
                <p class="text-sm text-slate-600 leading-relaxed">{{ topic }}</p>
              </div>
            </div>
          </div>

          <!-- 名场面 -->
          <div class="card p-5">
            <h3 class="font-semibold text-slate-700 mb-3 flex items-center gap-2">
              <Sparkles class="w-4 h-4 text-amber-400" /> 名场面
            </h3>
            <div v-if="report.scene_commentary" class="mb-3 px-3 py-2 bg-gradient-to-r from-amber-100 to-orange-100 rounded-lg text-sm text-amber-700 font-medium">
              🎬 {{ report.scene_commentary }}
            </div>
            <div class="space-y-3">
              <div
                v-for="(q, i) in report.funny_quotes"
                :key="i"
                class="p-3 bg-amber-50/50 rounded-xl border border-amber-100"
              >
                <div class="flex items-start gap-2 mb-1.5">
                  <span class="text-sm font-medium text-amber-700">{{ q.speaker }}</span>
                </div>
                <p class="text-slate-700 leading-relaxed mb-1.5">"{{ q.quote }}"</p>
                <p v-if="q.comment" class="text-xs text-amber-500 italic">— {{ q.comment }}</p>
              </div>
            </div>
          </div>

          <!-- 高光时刻 -->
          <div v-if="report.highlight" class="card p-5 bg-gradient-to-r from-indigo-50 to-purple-50 border-indigo-100">
            <p class="text-sm text-indigo-700 font-medium">📌 {{ report.highlight }}</p>
          </div>
        </div>

        <!-- 侧栏：统计 -->
        <div class="space-y-4">
          <!-- 当天数据 -->
          <div v-if="stats" class="card p-4 space-y-3">
            <div class="flex items-center gap-2 text-sm text-slate-500">
              <MessageSquare class="w-4 h-4" />
              <span>总消息 <strong class="text-slate-700">{{ stats.total_messages }}</strong></span>
            </div>
            <div class="flex items-center gap-2 text-sm text-slate-500">
              <Users class="w-4 h-4" />
              <span>活跃人数 <strong class="text-slate-700">{{ stats.active_members }}</strong></span>
            </div>
          </div>

          <!-- 24小时活跃分布 -->
          <div v-if="stats?.hourly_distribution" class="card p-4">
            <h4 class="text-sm font-medium text-slate-600 mb-2 flex items-center gap-1.5">
              <Clock class="w-3.5 h-3.5" /> 活跃时段
            </h4>
            <!-- AI 活跃规律描述 -->
            <div v-if="report.active_hours?.peak_desc || report.active_hours?.peak_label" class="mb-3 text-xs text-slate-500 bg-indigo-50 rounded-lg px-3 py-2">
              <span v-if="report.active_hours.peak_label" class="font-medium text-indigo-600">{{ report.active_hours.peak_label }}</span>
              <span v-if="report.active_hours.peak_desc"> · {{ report.active_hours.peak_desc }}</span>
              <span v-if="report.active_hours.quiet_note" class="block mt-0.5 text-slate-400">{{ report.active_hours.quiet_note }}</span>
            </div>
            <div class="flex items-end gap-[2px] h-16">
              <div
                v-for="h in hourLabels"
                :key="h"
                :title="`${h}: ${stats.hourly_distribution[h.slice(0,2)] || 0}条`"
                :style="{ height: `${((stats.hourly_distribution[h.slice(0,2)] || 0) / maxHourCount) * 100}%` }"
                :class="[
                  'flex-1 rounded-t-sm transition-colors',
                  (stats.hourly_distribution[h.slice(0,2)] || 0) > 0 ? 'bg-indigo-300 hover:bg-indigo-400' : 'bg-slate-100',
                ]"
              />
            </div>
            <div class="flex justify-between mt-1 text-[10px] text-slate-300">
              <span v-for="h in [0,6,12,18,23]" :key="h">{{ h }}h</span>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
