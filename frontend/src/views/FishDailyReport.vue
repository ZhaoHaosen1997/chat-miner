<script setup>
import { ref, inject, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { getFishReport, generateFishReport } from '../api/index.js'
import { ArrowLeft, Sparkles, Loader2, ShoppingBag, Zap } from 'lucide-vue-next'

const props = defineProps({ date: String })
const router = useRouter()
const currentGroup = inject('currentGroup')

const report = ref(null)
const loading = ref(true)
const generating = ref(false)
const error = ref('')
const gid = ref(null)

onMounted(async () => {
  gid.value = currentGroup.value?.id
  await loadReport()
})

watch(() => currentGroup.value?.id, async () => {
  gid.value = currentGroup.value?.id
  await loadReport()
})

async function loadReport() {
  if (!gid.value || !props.date) return
  loading.value = true
  error.value = ''
  try {
    const r = await getFishReport(gid.value, props.date)
    report.value = r
  } catch (e) {
    if (e.message.includes('404')) {
      report.value = null
    } else {
      error.value = e.message
    }
  } finally { loading.value = false }
}

async function handleGenerate() {
  generating.value = true
  try {
    await generateFishReport(gid.value, props.date)
    await loadReport()
  } catch (e) { error.value = e.message }
  finally { generating.value = false }
}

const reportData = () => {
  if (!report.value?.report_json) return {}
  const rj = report.value.report_json
  if (typeof rj === 'string') {
    try { return JSON.parse(rj) } catch { return {} }
  }
  return rj
}

const rarityColor = {
  '普通': 'text-slate-500 bg-slate-100',
  '稀有': 'text-blue-600 bg-blue-50',
  '史诗': 'text-purple-600 bg-purple-50',
  '传说': 'text-orange-500 bg-orange-50',
}
</script>

<template>
  <div class="max-w-2xl mx-auto px-4 py-6 space-y-6">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <button @click="router.back()"
        class="flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 transition">
        <ArrowLeft :size="16" /> 返回
      </button>
      <button v-if="!report && !loading"
        @click="handleGenerate" :disabled="generating"
        class="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium
               hover:bg-indigo-700 disabled:opacity-50 transition shadow-sm">
        <Sparkles :size="16" :class="{ 'animate-spin': generating }" />
        {{ generating ? 'AI 写日报中...' : '生成鱼塘日报' }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="text-center py-20">
      <Loader2 :size="32" class="mx-auto mb-3 animate-spin text-slate-400" />
      <p class="text-slate-400 text-sm">加载日报...</p>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="text-center py-20">
      <p class="text-red-500">{{ error }}</p>
    </div>

    <!-- No Report -->
    <div v-else-if="!report" class="text-center py-20">
      <span class="text-5xl">📰</span>
      <h2 class="text-xl font-semibold text-slate-600 mt-4">{{ props.date }} 鱼塘日报</h2>
      <p class="text-slate-400 mt-2 text-sm">还没有生成今日日报</p>
      <p class="text-slate-300 text-xs mt-1">点击上方"生成鱼塘日报"让 AI 来写</p>
    </div>

    <!-- Report -->
    <div v-else>
      <!-- Date & Title -->
      <div class="text-center mb-6">
        <h1 class="text-2xl font-bold text-slate-800">🐟 群鱼塘日报</h1>
        <p class="text-sm text-slate-400 mt-1">{{ props.date }}</p>
        <p v-if="report.model_used" class="text-xs text-slate-300 mt-0.5">🤖 {{ report.model_used }}</p>
      </div>

      <!-- Weather -->
      <div v-if="reportData().weather?.emoji"
        class="flex items-center gap-3 bg-gradient-to-r from-sky-50 to-amber-50 rounded-xl px-4 py-3 border border-sky-100">
        <span class="text-3xl">{{ reportData().weather.emoji }}</span>
        <div>
          <div class="font-semibold text-slate-700">{{ reportData().weather.name }}</div>
          <div class="text-xs text-slate-500">{{ reportData().weather.effect }}</div>
        </div>
      </div>

      <!-- AI Report Text -->
      <div class="bg-white rounded-xl border border-slate-200 p-6">
        <div class="prose prose-sm max-w-none text-slate-700 leading-relaxed whitespace-pre-line">
          {{ reportData().text || '（日报内容为空）' }}
        </div>
      </div>

      <!-- Black Market -->
      <div v-if="reportData().black_market?.length" class="bg-gradient-to-br from-slate-800 to-slate-900 rounded-xl p-5 text-white">
        <div class="flex items-center gap-2 mb-3">
          <ShoppingBag :size="18" class="text-amber-400" />
          <h3 class="font-bold text-amber-400">🛒 今日黑市</h3>
        </div>
        <div class="grid gap-2">
          <div v-for="item in reportData().black_market" :key="item.key"
            class="flex items-center justify-between bg-white/10 rounded-lg px-3 py-2">
            <div>
              <span class="font-medium text-white text-sm">{{ item.name }}</span>
              <span class="ml-2 px-1.5 py-0.5 rounded text-[10px]" :class="rarityColor[item.rarity] || 'text-slate-300 bg-slate-700'">
                {{ item.rarity }}
              </span>
            </div>
            <div class="text-right text-xs">
              <div class="text-amber-400 font-bold">{{ item.price }} 鳞币</div>
              <div class="text-slate-400">库存 {{ item.stock }}</div>
            </div>
          </div>
        </div>
        <p class="text-xs text-slate-400 mt-3">群友发送 /购买 商品名 即可抢购，先到先得！</p>
      </div>
    </div>
  </div>
</template>
