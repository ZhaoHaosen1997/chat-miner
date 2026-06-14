<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  events: { type: Array, default: () => [] },
})

const PAGE_SIZE = 10
const showCount = ref(PAGE_SIZE)

const visibleEvents = computed(() => props.events.slice(0, showCount.value))
const hasMore = computed(() => showCount.value < props.events.length)
function showMore() { showCount.value += PAGE_SIZE }

const eventLabels = {
  shark_attack: '🦈 鲨鱼来袭', treasure: '💎 沉船宝藏', mystic_kelp: '🍄 神秘海藻',
  fish_flu: '🤒 鱼流感', siren: '🧜 人鱼诱惑', fishhook: '🎣 鱼钩陷阱',
  wishing_star: '🌟 流星许愿', race: '🏁 洋流竞速', storm: '🌊 暴风雨',
  warm_current: '🌈 洋流送暖', beauty_contest: '👑 鳞光选美', acid_rain: '⚡ 酸雨',
  food_ship: '🍞 投食船经过', mutation: '🧬 基因突变', ghost_tide: '👻 幽灵鱼潮',
  carnival: '🎪 鱼群嘉年华', flavor: '📜 日常', death: '🪦 永别',
  born: '🐣 诞生', evolve: '🦋 进化', feed: '🍽️ 喂食', battle: '⚔️ 斗鱼',
  explore: '🔍 探索', showoff: '💃 晒鱼', touch: '🤝 摸鱼', rename: '✏️ 改名',
  revived: '✨ 复活', daily_status: '💬 今日状态',
}

const flavorBg = 'bg-amber-50/70 border-amber-100'
const deathBg = 'bg-slate-100/80 border-slate-200'
const normalBg = 'bg-white/80 border-slate-100'

function eventName(evt) {
  const type = evt.event_type || evt.type || ''
  const data = parseData(evt)
  const label = eventLabels[type] || type || '未知事件'

  if (type === 'death' || type === 'shark_attack') {
    const name = data.fish_name || data.victim || ''
    if (name) return `🪦 ${name} 永别`
    return label
  }
  // 风味文本不显示名字
  if (type === 'flavor') return label
  // 有 fish_name 的个体事件带上鱼名
  if (data.fish_name) return `${label} · ${data.fish_name}`
  return label
}

function isFlavor(evt) { return (evt.event_type || evt.type) === 'flavor' }
function isDeath(evt) {
  const t = evt.event_type || evt.type || ''
  return t === 'death' || t === 'shark_attack'
}
function eventTime(evt) {
  const t = evt.created_at || ''
  if (!t) return ''
  // SQLite CURRENT_TIMESTAMP 存的是 UTC，转为北京时间显示
  const d = new Date(t.replace(' ', 'T') + 'Z')
  if (isNaN(d.getTime())) return t.slice(11, 16) || t.slice(0, 10) || ''
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' })
}

// ===== 核心：叙事化事件详情 =====
function eventDetail(evt) {
  const type = evt.event_type || evt.type || ''
  const data = parseData(evt)
  const name = data.fish_name || ''

  // 风味文本直接返回原文
  if (type === 'flavor') return data.text || ''

  // 死亡事件
  if (type === 'death') {
    const parts = []
    if (data.cause) parts.push(data.cause)
    if (data.last_words) parts.push(`临终遗言："${data.last_words}"`)
    return parts.join('。')
  }
  if (type === 'shark_attack') {
    const parts = []
    parts.push(data.cause || '被鲨鱼袭击致死')
    if (data.last_words) parts.push(`遗言："${data.last_words}"`)
    return parts.join('。')
  }

  // 带检定的个体事件 → 叙事化
  if (data.check) {
    return narrateCheck(type, data, name)
  }

  // 群体事件：竞速
  if (type === 'race' && data.race_results) {
    return narrateRace(data.race_results)
  }
  // 群体事件：选美
  if (type === 'beauty_contest' && data.beauty_results) {
    return narrateBeauty(data.beauty_results)
  }

  // 其他特定类型
  if (type === 'evolve') return `${name}从 ${data.old_stage || '?'} 蜕变为 ${data.new_stage || '?'}！`
  if (type === 'born') return `${data.species || ''}（${data.rarity || ''}）`
  if (type === 'mutation') {
    if (data.success) return `${name}基因突变，觉醒了新潜能！`
    return data.desc || '基因突变未成功'
  }
  if (type === 'revived') return `${data.fish_name || ''}被幽灵潮汐冲回了鱼塘，奇迹生还！`
  if (type === 'daily_status') return data.status || ''
  if (type === 'carnival') return data.desc || '鱼群狂欢，全体精力回满！'

  // 通用：如果有效果数据就展示
  const effects = formatEffects(data)
  if (effects) return effects
  if (data.success !== undefined) return data.success ? '成功' : '失败'
  return data.desc || data.name || ''
}

// 叙事化检定结果
function narrateCheck(type, data, name) {
  const c = data.check
  const ename = data.name || eventLabels[type] || type
  const actor = name || '某鱼'
  const fx = formatEffects(data)

  if (c.critical_hit) {
    const desc = data.desc && data.desc !== '成功' ? data.desc : ''
    let s = `${actor}在${ename}中运气爆棚！`
    if (desc) s += desc + '。'
    else s += '效果超乎预期。'
    if (fx) s += `（${fx}）`
    return s
  }
  if (c.critical_miss) {
    const desc = data.desc && data.desc !== '失败' ? data.desc : ''
    let s = `${actor}在${ename}中遭遇了重大失误...`
    if (desc) s += desc + '。'
    if (fx) s += `（${fx}）`
    return s
  }
  if (c.success) {
    let s = `${actor}顺利通过了${ename}的考验`
    if (fx) s += `，获得${fx}`
    return s
  }
  // 失败
  let s = `${actor}在${ename}中未能如愿`
  if (fx) s += `，${fx}`
  return s
}

// 叙事化竞速
function narrateRace(results) {
  if (!results || !results.length) return ''
  const medals = ['🥇', '🥈', '🥉']
  const parts = results.slice(0, 3).map((r, i) =>
    `${medals[i]}${r.fish_name}（${r.total}点）`
  )
  return `${parts.join('  ')}`
}

// 叙事化选美
function narrateBeauty(results) {
  if (!results || !results.length) return ''
  const r = results[0]
  let s = `${r.fish_name}以${r.total}点艳压群芳摘得桂冠`
  if (results.length >= 2) {
    s += `，${results[1].fish_name}（${results[1].total}点）获得亚军`
  }
  return s
}

// 效果列表 → 中文
function formatEffects(data) {
  const parts = []
  if (data.growth) parts.push(`成长${fmtNum(data.growth)}`)
  if (data.happiness) parts.push(`幸福${fmtNum(data.happiness)}`)
  if (data.hp_loss) parts.push(`损失${data.hp_loss}生命`)
  if (data.hp_heal) parts.push(`恢复${data.hp_heal}生命`)
  if (data.coin_amount) parts.push(`${data.coin_amount}鳞币`)
  if (data.energy_cost) parts.push(`消耗${data.energy_cost}精力`)
  if (data.energy_restore) parts.push(`恢复${data.energy_restore}精力`)
  if (data.xp_gain) parts.push(`${data.xp_gain}经验`)
  return parts.join('、')
}

function fmtNum(n) { return n > 0 ? `+${n}` : `${n}` }
function parseData(evt) {
  const d = evt.event_data
  if (!d) return {}
  if (typeof d === 'string') {
    try { return JSON.parse(d) } catch { return {} }
  }
  return d
}
</script>

<template>
  <div class="space-y-2">
    <div v-for="(evt, i) in visibleEvents" :key="evt.id || i"
      :class="['rounded-lg p-3 text-sm border transition-colors',
        isDeath(evt) ? deathBg : isFlavor(evt) ? flavorBg : normalBg]">
      <!-- Title -->
      <div class="flex items-start justify-between gap-2">
        <span class="text-sm font-semibold text-slate-700 leading-snug">{{ eventName(evt) }}</span>
        <span class="text-[11px] text-slate-400 shrink-0 mt-0.5">{{ eventTime(evt) }}</span>
      </div>
      <!-- Detail: narrative flavor text -->
      <div v-if="eventDetail(evt)" class="mt-1.5 text-xs leading-relaxed"
        :class="isFlavor(evt) ? 'italic text-slate-400' : 'text-slate-500'">
        {{ eventDetail(evt) }}
      </div>
    </div>
    <div v-if="!events?.length" class="text-center text-sm text-slate-400 py-8">
      今日暂无事件
    </div>
    <!-- Show more -->
    <div v-if="hasMore" class="text-center pt-1">
      <button @click="showMore"
        class="text-xs font-medium text-indigo-500 hover:text-indigo-600 hover:bg-indigo-50 px-4 py-1.5 rounded-lg transition">
        展开更多（{{ events.length - showCount }} 条剩余）
      </button>
    </div>
  </div>
</template>
