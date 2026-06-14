<script setup>
import { ref, inject, computed, onMounted } from 'vue'
import { getPondTreasury, getUpgrades, upgradePond,
         executeDecree, getDecreeLimits, batchAdopt, getHotSearch, getFishPond }
  from '../api/index.js'
import { TrendingUp, Crown, Shield } from 'lucide-vue-next'

const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')
const gid = computed(() => currentGroup.value?.id)
const emit = defineEmits(['pond-refresh'])

const treasury = ref({ balance: 0, total_earned: 0, total_spent: 0 })
const upgrades = ref([])
const decreeLimits = ref({})
const hotSearch = ref({})
const actionLoading = ref('')
const titles = ref([])

// 一键领养确认
const showBatchConfirm = ref(false)

const upgradeDefs = {
  purifier: { icon: '💧', name: '净水器', desc: '疾病概率 -15%/级' },
  shark_net: { icon: '🛡️', name: '防鲨网', desc: '掠食者伤害 -2/级' },
  nutrient: { icon: '🌿', name: '营养剂', desc: '全体日成长 +1/级' },
  radar: { icon: '📡', name: '探测器', desc: '宝藏概率×1.2/级' },
  medbay: { icon: '🏥', name: '医疗站', desc: '日自动回血 +1HP/级' },
}

const ALL_TITLES = {
  newbie: { label: '🌱 新手塘主', desc: '首次开启自动事件' },
  builder: { label: '🏗️ 基建狂魔', desc: '任意升级达到 Lv5' },
  gambler: { label: '🎰 赌怪', desc: '手动触发事件 50 次' },
  capitalist: { label: '💰 资本家', desc: '金库余额突破 5000' },
  necromancer: { label: '👻 亡灵法师', desc: '幽灵鱼复活 3 条鱼' },
  dragon_lord: { label: '🐉 龙骑士', desc: '拥有 5 条传说级鱼' },
  sweeper: { label: '🧹 勤劳清洁工', desc: '清理鱼塘 30 次' },
  philanthropist: { label: '🎁 大慈善家', desc: '全员投喂 50 次' },
}

const DECREE_DEFS = {
  feed_all: { icon:'🍞', name:'全员投喂', cost:50, desc:'全体鱼获得喂食效果' },
  energy_boost: { icon:'⚡', name:'精力补给', cost:80, desc:'全体鱼恢复30精力' },
  heal: { icon:'💊', name:'急救包', cost:30, desc:'选一只鱼，HP回满' },
  clean: { icon:'🪣', name:'清理鱼塘', cost:20, desc:'全体happiness+5，精力+10' },
  rain: { icon:'🌧️', name:'人工降雨', cost:100, desc:'触发有益群体事件' },
  elite_train: { icon:'🎓', name:'精英培训', cost:200, desc:'选一只鱼，随机属性+2' },
  force_event: { icon:'🎪', name:'举办活动', cost:300, desc:'强制触发一次稀有事件' },
  title_award: { icon:'🏆', name:'命名表彰', cost:50, desc:'给鱼授予特殊称号' },
}

const canAfford = (cost) => treasury.value.balance >= cost

async function load() {
  if (!gid.value) return
  try {
    const [t, u, d, h] = await Promise.all([
      getPondTreasury(gid.value), getUpgrades(gid.value),
      getDecreeLimits(gid.value), getHotSearch(gid.value),
    ])
    treasury.value = t.treasury || t
    upgrades.value = u || []
    decreeLimits.value = d || {}
    hotSearch.value = h || {}
    loadTitles()
  } catch (e) { console.error('加载管理面板失败:', e) }
}

async function loadTitles() {
  try {
    const { apiGet } = await import('../api/index.js')
    const settings = await apiGet('/api/settings/app-settings')
    for (const s of settings) {
      if (s.key === 'pond_keeper_titles') {
        try { titles.value = JSON.parse(s.value) || [] } catch { titles.value = [] }
      }
    }
  } catch { titles.value = [] }
}

async function handleUpgrade(key) {
  actionLoading.value = key
  try {
    await upgradePond(gid.value, key)
    await load()
    emit('pond-refresh')
  } catch (e) { alert(e.message || '升级失败') }
  finally { actionLoading.value = '' }
}

async function handleDecree(key) {
  actionLoading.value = key
  try {
    await executeDecree(gid.value, key, undefined)
    await load()
    emit('pond-refresh')
  } catch (e) { alert(e.message || '决议执行失败') }
  finally { actionLoading.value = '' }
}

async function handleBatchAdopt() {
  showBatchConfirm.value = false
  actionLoading.value = 'batch'
  try {
    const result = await batchAdopt(gid.value)
    await load()
    emit('pond-refresh')
  } catch (e) { alert(e.message || '领养失败') }
  finally { actionLoading.value = '' }
}

onMounted(load)
</script>

<template>
  <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
    <!-- 左栏：称号+金库+热搜 -->
    <div class="space-y-4">
      <!-- 称号 -->
      <div class="card p-4">
        <h3 class="text-sm font-semibold text-slate-600 mb-2 flex items-center gap-1.5">
          <Crown :size="14" class="text-amber-500" /> 塘主称号
        </h3>
        <div class="flex flex-wrap gap-1.5">
          <span v-for="(info, key) in ALL_TITLES" :key="key"
            :class="['px-2 py-1 rounded-lg text-xs font-medium transition',
              titles.includes(key) ? 'bg-amber-50 text-amber-700 border border-amber-200' : 'bg-slate-50 text-slate-300 border border-slate-100']"
            :title="info.desc">
            {{ info.label }}
          </span>
        </div>
      </div>

      <!-- 金库 -->
      <div class="card p-4">
        <h3 class="text-sm font-semibold text-slate-600 mb-2">💰 鱼塘金库</h3>
        <div class="text-2xl font-bold text-amber-600">{{ treasury.balance?.toLocaleString() || 0 }} 🪙</div>
        <div class="text-[10px] text-slate-400 mt-1">累计收入 {{ treasury.total_earned?.toLocaleString() || 0 }} · 累计支出 {{ treasury.total_spent?.toLocaleString() || 0 }}</div>
      </div>

      <!-- 热搜 -->
      <div class="card p-4">
        <h3 class="text-sm font-semibold text-slate-600 mb-2">🏷️ 本周热搜</h3>
        <div class="space-y-1.5">
          <div v-for="(item, key) in hotSearch" :key="key"
            class="flex items-center justify-between text-xs text-slate-500">
            <span>{{ item.label }}</span>
            <span class="font-medium text-slate-700">{{ item.fish || '—' }} <span v-if="item.data" class="text-slate-400">×{{ item.data }}</span></span>
          </div>
        </div>
      </div>
    </div>

    <!-- 右栏：升级+决议+领养 -->
    <div class="lg:col-span-2 space-y-4">
      <!-- 升级 -->
      <div class="card p-4">
        <h3 class="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-1.5">
          <TrendingUp :size="14" class="text-emerald-500" /> 升级路线
        </h3>
        <div class="grid grid-cols-1 gap-2">
          <div v-for="(def, key) in upgradeDefs" :key="key"
            class="flex items-center justify-between p-3 rounded-xl border"
            :class="(upgrades.find(u=>u.key===key)?.level||0) >= 5 ? 'border-emerald-100 bg-emerald-50/30' : 'border-slate-100 bg-slate-50/50'">
            <div class="flex items-center gap-2">
              <span class="text-xl">{{ def.icon }}</span>
              <div>
                <div class="text-sm font-medium text-slate-700">{{ def.name }}</div>
                <div class="text-[10px] text-slate-400">{{ def.desc }}</div>
                <div class="flex gap-0.5 mt-1">
                  <span v-for="i in 5" :key="i"
                    :class="['w-3 h-1.5 rounded-full', i <= (upgrades.find(u=>u.key===key)?.level || 0) ? 'bg-emerald-400' : 'bg-slate-200']" />
                </div>
              </div>
            </div>
            <button v-if="(upgrades.find(u=>u.key===key)?.level||0) >= 5"
              class="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-100 text-slate-300 cursor-not-allowed">
              MAX
            </button>
            <button v-else-if="!canAfford(upgrades.find(u=>u.key===key)?.next_cost || 100)"
              class="px-3 py-1.5 text-xs font-medium rounded-lg bg-slate-100 text-slate-400 cursor-not-allowed flex items-center gap-1"
              :title="'需要 '+(upgrades.find(u=>u.key===key)?.next_cost||100)+' 🪙'">
              🚫 余额不足
            </button>
            <button v-else @click="handleUpgrade(key)" :disabled="actionLoading === key"
              class="px-3 py-1.5 text-xs font-medium rounded-lg bg-emerald-500 text-white hover:bg-emerald-600 transition">
              {{ actionLoading === key ? '...' : '↑ '+ (upgrades.find(u=>u.key===key)?.next_cost || '')+' 🪙' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 决议 -->
      <div class="card p-4">
        <h3 class="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-1.5">
          <Shield :size="14" class="text-indigo-500" /> 塘主决议
        </h3>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-2">
          <button v-for="(def, key) in DECREE_DEFS" :key="key"
            @click="handleDecree(key)"
            :disabled="actionLoading === key || (!canAfford(def.cost))"
            class="p-2.5 rounded-xl border text-left transition disabled:cursor-not-allowed"
            :class="canAfford(def.cost) ? 'border-slate-100 hover:border-indigo-200 hover:bg-indigo-50/30' : 'border-slate-50 bg-slate-50/50 opacity-50'"
            :title="canAfford(def.cost) ? def.desc : '金库余额不足'">
            <div class="text-lg">{{ def.icon }}</div>
            <div class="text-xs font-medium text-slate-700 mt-1">{{ def.name }}</div>
            <div class="text-[10px]" :class="canAfford(def.cost) ? 'text-slate-400' : 'text-red-400'">
              {{ def.cost }} 🪙
              <span v-if="!canAfford(def.cost)">🚫</span>
              <span v-else-if="decreeLimits[key]"> · {{ decreeLimits[key].used }}/{{ decreeLimits[key].max }}</span>
            </div>
          </button>
        </div>
      </div>

      <!-- 一键领养（内联确认） -->
      <div class="card p-4">
        <div v-if="!showBatchConfirm">
          <button @click="showBatchConfirm = true" :disabled="actionLoading === 'batch'"
            class="w-full py-3 rounded-xl text-sm font-medium bg-gradient-to-r from-indigo-500 to-purple-500 text-white hover:from-indigo-600 hover:to-purple-600 transition disabled:opacity-50">
            🎁 {{ actionLoading === 'batch' ? '领养中...' : '一键领养' }}
          </button>
          <p class="text-[10px] text-slate-400 text-center mt-1">为所有还没有鱼的群成员自动领养</p>
        </div>
        <div v-else class="flex flex-col items-center gap-2">
          <p class="text-sm text-slate-600">确定要为所有无鱼成员领养吗？</p>
          <div class="flex gap-2">
            <button @click="handleBatchAdopt"
              class="px-4 py-1.5 rounded-lg text-xs font-medium bg-indigo-500 text-white hover:bg-indigo-600 transition">
              确认领养
            </button>
            <button @click="showBatchConfirm = false"
              class="px-4 py-1.5 rounded-lg text-xs border border-slate-200 text-slate-500 hover:bg-slate-50 transition">
              取消
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
