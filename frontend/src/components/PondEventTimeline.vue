<script setup>
defineProps({
  events: { type: Array, default: () => [] },
})

const eventLabels = {
  shark_attack: '🦈 鲨鱼来袭', treasure: '💎 沉船宝藏', mystic_kelp: '🍄 神秘海藻',
  fish_flu: '🤒 鱼流感', siren: '🧜 人鱼诱惑', fishhook: '🎣 鱼钩陷阱',
  wishing_star: '🌟 流星许愿', race: '🏁 洋流竞速', storm: '🌊 暴风雨',
  warm_current: '🌈 洋流送暖', beauty_contest: '👑 鳞光选美', acid_rain: '⚡ 酸雨',
  food_ship: '🍞 投食船经过', mutation: '🧬 基因突变', ghost_tide: '👻 幽灵鱼潮',
  carnival: '🎪 鱼群嘉年华', flavor: '📜 日常', death: '🪦 永别',
  born: '🐣 诞生', evolve: '🦋 进化', feed: '🍽️ 喂食', battle: '⚔️ 斗鱼',
  explore: '🔍 探索', showoff: '💃 晒鱼', touch: '🤝 摸鱼', rename: '✏️ 改名',
}

const flavorBg = 'bg-amber-50 border-amber-100'
const normalBg = 'bg-white border-slate-100'

function eventName(evt) {
  const type = evt.event_type || evt.type || ''
  return eventLabels[type] || type || '未知事件'
}

function isFlavor(evt) {
  return (evt.event_type || evt.type) === 'flavor'
}

function eventTime(evt) {
  const t = evt.created_at || ''
  return t.slice(11, 16) || t.slice(0, 10) || ''
}

function eventDetail(evt) {
  const type = evt.event_type || evt.type || ''
  const data = parseData(evt)
  if (type === 'shark_attack') return data.victim ? `${data.victim} 遭遇鲨鱼` : '鲨鱼袭击'
  if (type === 'treasure') return data.success ? '发现宝藏！' : '空手而归'
  if (type === 'race') return data.results ? `前3名已决出` : '竞速中'
  if (type === 'flavor') return evt.event_data?.text || data.text || ''
  if (type === 'death') return data.last_words || data.cause || ''
  if (type === 'born') return data.fish_name || '新鱼诞生'
  if (type === 'daily_status') return data.status || ''
  if (data.success !== undefined) return data.success ? '✅ 成功' : '❌ 失败'
  return data.desc || data.name || ''
}

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
    <div v-for="(evt, i) in events" :key="evt.id || i"
      :class="['rounded-lg p-3 text-sm border', isFlavor(evt) ? flavorBg : normalBg]">
      <div class="flex items-start gap-2">
        <span class="text-base shrink-0">{{ eventName(evt) }}</span>
        <span class="text-xs text-slate-400 shrink-0">{{ eventTime(evt) }}</span>
      </div>
      <div v-if="eventDetail(evt)" class="mt-1 text-xs text-slate-500 leading-relaxed"
        :class="{ 'italic': isFlavor(evt) }">
        {{ eventDetail(evt) }}
      </div>
    </div>
    <div v-if="!events?.length" class="text-center text-sm text-slate-400 py-6">
      今日暂无事件
    </div>
  </div>
</template>
