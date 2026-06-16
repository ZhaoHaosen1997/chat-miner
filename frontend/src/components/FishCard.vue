<script setup>
import { ref, computed, onMounted } from 'vue'
import { X, Dices, Trash2, TrendingUp, Shield, Pencil, Sword, Users } from 'lucide-vue-next'
import FishStatusBubble from './FishStatusBubble.vue'
import { getFishRelationships, getLegendaryQuestStatus, doLegendaryQuest, renameFish } from '../api/index.js'

const props = defineProps({
  fish: Object,
  loading: String,
  groupId: Number,
})

const emit = defineEmits(['close', 'action', 'refresh'])

const showDeleteConfirm = ref(false)

// --- v1.16.4: 改名 ---
const showRenameInput = ref(false)
const renameText = ref('')
const renameSaving = ref(false)
async function saveRename() {
  const name = renameText.value.trim()
  if (!name || name.length > 20) return
  renameSaving.value = true
  try {
    await renameFish(props.groupId, props.fish.wxid, name)
    showRenameInput.value = false
    emit('refresh')
  } catch (e) { /* ignore */ }
  finally { renameSaving.value = false }
}

// --- v1.16.4: 传奇试炼 ---
const questStatus = ref(null)
const questLoading = ref(false)
const questResult = ref(null)
async function loadQuestStatus() {
  if (!props.groupId || !props.fish?.wxid) return
  try {
    const res = await getLegendaryQuestStatus(props.groupId, props.fish.wxid)
    questStatus.value = res
  } catch (e) { /* ignore */ }
}
async function startLegendaryQuest() {
  questLoading.value = true
  questResult.value = null
  try {
    const res = await doLegendaryQuest(props.groupId, props.fish.wxid)
    questResult.value = res
    await loadQuestStatus()
    emit('refresh')
  } catch (e) { /* ignore */ }
  finally { questLoading.value = false }
}
const canQuest = computed(() => {
  if (!questStatus.value) return false
  return questStatus.value.can_challenge
})

// --- v1.16.4: 朋友圈 ---
const relationships = ref([])
async function loadRelationships() {
  if (!props.groupId || !props.fish?.wxid) return
  try {
    const res = await getFishRelationships(props.groupId, props.fish.wxid)
    relationships.value = res?.relationships || []
  } catch (e) { /* ignore */ }
}
onMounted(() => {
  loadQuestStatus()
  loadRelationships()
})

const speciesEmoji = {
  goldfish: '🐟', koi: '🎏', clownfish: '🤡', betta: '🐠', arowana: '🐉',
  angelfish: '👼', pufferfish: '🐡', shark: '🦈', crocodile: '🐊', orca: '🐳',
  octopus: '🐙', squid: '🦑', crab: '🦀', lobster: '🦞', jellyfish: '🪼',
  shrimp: '🦐', mantis_shrimp: '🦐', conch: '🐚', nautilus: '🌀',
  oyster: '🦪', whale: '🐋', dolphin: '🐬', seal: '🦭', otter: '🦦',
  otter2: '🦦', walrus: '🦭', turtle: '🐢', frog: '🐸', axolotl: '🦎',
  mermaid: '🧜‍♀️', plesiosaur: '🦕', sea_snake: '🐍', sea_slug: '🐌',
  sturgeon: '🐟', eel: '⚡',
}

const speciesInfo = computed(() => props.fish?.species_info || {})

const displayEmoji = computed(() => {
  return props.fish?.emoji_variant || speciesEmoji[props.fish?.species] || '🐟'
})

const personalityTraits = computed(() => {
  const raw = props.fish?.personality_traits
  if (!raw) return []
  if (typeof raw === 'string') {
    try { return JSON.parse(raw) } catch { return [] }
  }
  return Array.isArray(raw) ? raw : []
})

const traitIcons = {
  '勇敢': '🦁', '好奇': '🔍', '活泼': '🤸', '勤奋': '💪', '谨慎': '🛡️',
  '乐天': '😊', '傲娇': '💅', '贪吃': '🍔', '社牛': '🎤', '胆小': '😨',
  '懒惰': '😴', '暴躁': '💢', '沉稳': '🧘', '机灵': '🧠', '粘人': '🥰',
  '孤僻': '🏚️', '贪睡': '😴', '迷糊': '😵', '浪漫': '💕',
  '倔强': '🤨', '戏精': '🎪', '冒险家': '🧭',
}
function traitIcon(name) { return traitIcons[name] || '🎭' }

function abilityMod(score) {
  const m = Math.floor((score - 10) / 2)
  return m >= 0 ? `+${m}` : `${m}`
}

const attrConfig = [
  { key: 'strength',     label: '力量', abbr: 'STR', icon: '💪', color: '#EF4444', bg: 'rgba(239,68,68,0.06)', border: 'rgba(239,68,68,0.2)' },
  { key: 'dexterity',    label: '敏捷', abbr: 'DEX', icon: '🏃', color: '#22C55E', bg: 'rgba(34,197,94,0.06)', border: 'rgba(34,197,94,0.2)' },
  { key: 'constitution', label: '体质', abbr: 'CON', icon: '❤️', color: '#3B82F6', bg: 'rgba(59,130,246,0.06)', border: 'rgba(59,130,246,0.2)' },
  { key: 'intelligence', label: '智力', abbr: 'INT', icon: '🧠', color: '#A855F7', bg: 'rgba(168,85,247,0.06)', border: 'rgba(168,85,247,0.2)' },
  { key: 'wisdom',       label: '感知', abbr: 'WIS', icon: '👁️', color: '#EAB308', bg: 'rgba(234,179,8,0.06)',  border: 'rgba(234,179,8,0.2)' },
  { key: 'charisma',     label: '魅力', abbr: 'CHA', icon: '💋', color: '#EC4899', bg: 'rgba(236,72,153,0.06)', border: 'rgba(236,72,153,0.2)' },
]

const rarityConfig = computed(() => {
  const map = {
    '普通': { gradient: 'from-slate-400 to-slate-500', bg: 'bg-slate-100', text: 'text-slate-600', border: 'border-slate-200', glow: '' },
    '稀有': { gradient: 'from-sky-400 to-blue-500', bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200', glow: '0 0 20px rgba(56,189,248,0.25)' },
    '史诗': { gradient: 'from-purple-400 to-purple-600', bg: 'bg-purple-50', text: 'text-purple-700', border: 'border-purple-200', glow: '0 0 24px rgba(168,85,247,0.25)' },
    '传说': { gradient: 'from-amber-400 to-orange-500', bg: 'bg-amber-50', text: 'text-amber-700', border: 'border-amber-200', glow: '0 0 28px rgba(251,191,36,0.3)' },
  }
  return map[props.fish?.rarity] || map['普通']
})

const xpProgress = computed(() => {
  const xp = props.fish?.experience || 0
  const lv = props.fish?.level || 1
  const xpTable = [0, 100, 300, 600, 1000, 1500, 2100, 2800, 3600, 4500]
  const currentLevelXp = xpTable[lv - 1] || 0
  const nextLevelXp = xpTable[lv] || xpTable[xpTable.length - 1] + 1500
  const pct = Math.min(100, Math.round(((xp - currentLevelXp) / (nextLevelXp - currentLevelXp)) * 100))
  return { pct, next: nextLevelXp, current: xp }
})

const stageProgress = computed(() => {
  const g = props.fish?.growth || 0
  const stages = [
    { name: '鱼苗', max: 0 },
    { name: '幼鱼', max: 100 },
    { name: '成鱼', max: 500 },
    { name: '大鱼', max: 2000 },
    { name: '传说', max: 5000 },
  ]
  const currentIdx = stages.findIndex(s => s.name === props.fish?.stage) || 0
  const nextStage = stages[currentIdx + 1]
  if (!nextStage) return { pct: 100, next: null, label: 'MAX' }
  const prevMax = stages[currentIdx].max
  const needed = nextStage.max - prevMax
  const progress = g - prevMax
  return { pct: Math.min(100, Math.round((progress / needed) * 100)), next: nextStage.name, label: `${progress.toFixed(0)}/${needed}` }
})

function confirmDelete() {
  emit('action', 'delete', props.fish.wxid)
  showDeleteConfirm.value = false
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-sm"
    @click.self="$emit('close')">
    <div class="fishcard-shell">
      <!-- ===== Decorative top bar ===== -->
      <div class="fishcard-topbar" :class="rarityConfig.gradient"></div>

      <!-- ===== Header ===== -->
      <div class="fishcard-header">
        <button @click="$emit('close')" class="fishcard-close">
          <X :size="18" />
        </button>

        <!-- Emoji with rarity glow -->
        <div class="fishcard-emoji" :style="{ boxShadow: rarityConfig.glow }">
          <span class="text-5xl">{{ displayEmoji }}</span>
        </div>

        <!-- Name & meta -->
        <div class="fishcard-meta">
          <div class="flex items-center gap-2 flex-wrap">
            <h2 class="fishcard-name">
              <template v-if="!showRenameInput">{{ fish.fish_name }}
                <button @click="showRenameInput = true; renameText = fish.fish_name" class="rename-icon-btn">
                  <Pencil :size="13" />
                </button>
              </template>
              <span v-else class="flex items-center gap-1">
                <input v-model="renameText" @keyup.enter="saveRename" @keyup.escape="showRenameInput = false"
                  class="rename-input" maxlength="20" autofocus />
                <button @click="saveRename" :disabled="renameSaving" class="rename-save-btn">✓</button>
                <button @click="showRenameInput = false" class="rename-cancel-btn">✕</button>
              </span>
            </h2>
            <FishStatusBubble :status="fish.daily_status || ''" />
          </div>
          <div class="fishcard-subtitle">
            <span>{{ speciesInfo.name || fish.species }}</span>
            <span class="mx-1.5 text-slate-300">·</span>
            <span :class="['fishcard-rarity', rarityConfig.bg, rarityConfig.text, rarityConfig.border]">
              {{ fish.rarity }}
            </span>
            <span class="mx-1.5 text-slate-300">·</span>
            <span class="fishcard-level">Lv {{ fish.level }}</span>
            <span v-if="fish.level === 10" class="text-[10px] text-amber-500 font-bold ml-0.5">MAX</span>
          </div>

          <!-- Personality traits -->
          <div v-if="personalityTraits?.length" class="fishcard-traits">
            <span v-for="trait in personalityTraits" :key="(typeof trait === 'string' ? trait : trait.key)"
              class="fishcard-trait">
              {{ typeof trait === 'string' ? traitIcon(trait) + ' ' + trait : (trait.icon || '🎭') + ' ' + trait.key }}
            </span>
          </div>
        </div>
      </div>

      <!-- ===== Attribute Grid ===== -->
      <div class="fishcard-section">
        <h3 class="fishcard-section-title">
          <Shield :size="13" /> 属性面板
        </h3>
        <div class="attr-grid">
          <div v-for="attr in attrConfig" :key="attr.key"
            class="attr-card"
            :style="{ background: attr.bg, borderColor: attr.border }">
            <div class="attr-header">
              <span class="attr-icon">{{ attr.icon }}</span>
              <span class="attr-abbr" :style="{ color: attr.color }">{{ attr.abbr }}</span>
            </div>
            <div class="attr-score">{{ fish[attr.key] || 0 }}</div>
            <div class="attr-mod" :style="{ color: attr.color }">
              {{ abilityMod(fish[attr.key] || 0) }}
            </div>
            <div class="attr-label" :style="{ color: attr.color }">{{ attr.label }}</div>
          </div>
        </div>
      </div>

      <!-- ===== Proficiencies ===== -->
      <div v-if="fish.proficiencies?.length" class="fishcard-section">
        <div class="flex items-center gap-2 text-xs text-slate-400 mb-1.5">
          <Dices :size="13" /> 熟练项
        </div>
        <div class="flex flex-wrap gap-1">
          <span v-for="p in fish.proficiencies" :key="p"
            class="prof-tag">
            {{ {athletics:'运动', acrobatics:'特技', endurance:'坚韧', investigation:'调查',
               nature:'自然', performance:'表演', stealth:'隐匿', insight:'洞悉',
               intimidation:'威吓'}[p] || p }}
          </span>
        </div>
      </div>

      <!-- ===== Stat Bars ===== -->
      <div class="fishcard-section">
        <h3 class="fishcard-section-title">
          <TrendingUp :size="13" /> 成长状态
        </h3>
        <div class="stat-bars">
          <!-- Growth -->
          <div class="stat-row">
            <div class="stat-label">🌱 成长</div>
            <div class="stat-bar-wrap">
              <div class="stat-bar">
                <div class="stat-fill growth-fill" :style="{ width: `${Math.min(100, (fish.growth || 0) / 50)}%` }"></div>
              </div>
              <span class="stat-val">{{ fish.growth?.toFixed(0) || 0 }}</span>
            </div>
            <span class="stat-hint">→ {{ stageProgress.next || 'MAX' }}</span>
          </div>

          <!-- Happiness -->
          <div class="stat-row">
            <div class="stat-label">💕 幸福</div>
            <div class="stat-bar-wrap">
              <div class="stat-bar">
                <div class="stat-fill happy-fill" :style="{ width: `${fish.happiness || 0}%` }"></div>
              </div>
              <span class="stat-val">{{ fish.happiness?.toFixed(0) || 0 }}</span>
            </div>
            <span class="stat-hint">/100</span>
          </div>

          <!-- XP -->
          <div class="stat-row">
            <div class="stat-label">⭐ 经验</div>
            <div class="stat-bar-wrap">
              <div class="stat-bar">
                <div class="stat-fill xp-fill" :style="{ width: `${xpProgress.pct}%` }"></div>
              </div>
              <span class="stat-val">{{ fish.experience || 0 }}</span>
            </div>
            <span class="stat-hint" v-if="fish.level < 10">/{{ xpProgress.next }}</span>
          </div>

          <!-- HP -->
          <div class="stat-row">
            <div class="stat-label">❤️ 生命</div>
            <div class="stat-bar-wrap">
              <div class="stat-bar">
                <div class="stat-fill hp-fill" :style="{ width: `${Math.max(0, Math.min(100, ((fish.hp || 0) / (fish.max_hp || 20)) * 100))}%` }"></div>
              </div>
              <span class="stat-val">{{ fish.hp || 0 }}</span>
            </div>
            <span class="stat-hint">/{{ fish.max_hp || 20 }}</span>
          </div>

          <!-- Energy -->
          <div class="stat-row">
            <div class="stat-label">⚡ 精力</div>
            <div class="stat-bar-wrap">
              <div class="stat-bar">
                <div class="stat-fill energy-fill-pond" :style="{ width: `${Math.max(0, Math.min(100, ((fish.energy || 0) / (fish.max_energy || 100)) * 100))}%` }"></div>
              </div>
              <span class="stat-val">{{ fish.energy || 0 }}</span>
            </div>
            <span class="stat-hint">/{{ fish.max_energy || 100 }}</span>
          </div>
        </div>
      </div>

      <!-- ===== Footer info ===== -->
      <div class="fishcard-footer-info">
        <div class="footer-stat">
          <span class="footer-stat-icon">🐚</span>
          <span>阶段 <b>{{ fish.stage }}</b></span>
        </div>
        <div class="footer-stat">
          <span class="footer-stat-icon">🔥</span>
          <span>连活 <b>{{ fish.consecutive_days || 0 }} 天</b></span>
        </div>
      </div>

      <!-- ===== v1.16.4: Legendary Quest ===== -->
      <div v-if="fish.stage === '传说' && fish.level >= 8 && questStatus" class="fishcard-section">
        <h3 class="fishcard-section-title">
          <Sword :size="13" /> 传奇试炼
        </h3>
        <div v-if="questStatus.step === 4" class="legendary-done">
          ⚔️ 已通关传奇试炼 — 永久全检定优势
        </div>
        <div v-else class="legendary-progress">
          <div class="quest-steps">
            <span v-for="(name, idx) in questStatus.step_names.slice(1, 4)" :key="idx"
              :class="['quest-step', { done: questStatus.step > idx, current: questStatus.step === idx }]">
              {{ idx === 1 ? '💪' : idx === 2 ? '🧠' : '💋' }} {{ name }}
            </span>
          </div>
          <button v-if="canQuest" @click="startLegendaryQuest" :disabled="questLoading"
            class="quest-btn">
            <Sword :size="14" /> {{ questLoading ? '检定中...' : '挑战下一步' }}
          </button>
          <div v-else-if="questStatus.today_attempted && questStatus.step < 4" class="quest-hint">
            今日已挑战，明天再来
          </div>
          <div v-if="questResult" class="quest-result" :class="{ success: questResult.success }">
            {{ questResult.message }}
          </div>
        </div>
      </div>

      <!-- ===== v1.16.4: Relationships ===== -->
      <div v-if="relationships.length" class="fishcard-section">
        <h3 class="fishcard-section-title">
          <Users :size="13" /> 朋友圈
        </h3>
        <div class="rel-list">
          <div v-for="rel in relationships" :key="rel.other_wxid" class="rel-item">
            <span class="rel-emoji">{{ rel.other_emoji || '🐟' }}</span>
            <span class="rel-name">{{ rel.other_name }}</span>
            <span :class="['rel-tag', rel.relation_type === 'friendship' ? 'rel-friend' : 'rel-rival']">
              {{ rel.relation_type === 'friendship' ? '🤝 友谊' : '⚔️ 劲敌' }}
            </span>
            <span class="rel-strength">Lv.{{ rel.strength }}</span>
          </div>
        </div>
      </div>

      <!-- ===== Delete ===== -->
      <div class="fishcard-delete">
        <template v-if="!showDeleteConfirm">
          <button @click="showDeleteConfirm = true" class="delete-btn">
            <Trash2 :size="14" /> 删除此鱼
          </button>
        </template>
        <template v-else>
          <div class="flex gap-2">
            <button @click="confirmDelete" class="delete-confirm-btn">确认删除</button>
            <button @click="showDeleteConfirm = false" class="delete-cancel-btn">取消</button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ===== Shell ===== */
.fishcard-shell {
  width: 440px;
  max-height: 92vh;
  overflow-y: auto;
  background: linear-gradient(175deg, #fafdfe 0%, #f5f9fb 40%, #f0f5f8 100%);
  border-radius: 20px;
  box-shadow:
    0 0 0 1px rgba(0,0,0,0.06),
    0 20px 60px -12px rgba(0,0,0,0.2),
    0 8px 24px -8px rgba(0,0,0,0.12);
  animation: card-in 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}
@keyframes card-in {
  from { opacity: 0; transform: scale(0.92) translateY(16px); }
  to   { opacity: 1; transform: scale(1) translateY(0); }
}

/* ===== Top bar ===== */
.fishcard-topbar {
  height: 3px;
  border-radius: 20px 20px 0 0;
}

/* ===== Header ===== */
.fishcard-header {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 20px 20px 0;
  position: relative;
}
.fishcard-close {
  position: absolute;
  top: 14px;
  right: 14px;
  padding: 6px;
  border-radius: 8px;
  color: #94a3b8;
  transition: all 0.15s;
  background: none;
  border: none;
  cursor: pointer;
}
.fishcard-close:hover {
  background: rgba(0,0,0,0.04);
  color: #475569;
}

.fishcard-emoji {
  width: 80px;
  height: 80px;
  border-radius: 18px;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid rgba(0,0,0,0.04);
  transition: box-shadow 0.3s;
}

.fishcard-meta { flex: 1; min-width: 0; }
.fishcard-name {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.01em;
  line-height: 1.3;
}
.fishcard-subtitle {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  margin-top: 4px;
  font-size: 13px;
  color: #64748b;
}
.fishcard-rarity {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid;
}
.fishcard-level {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
}

/* Traits */
.fishcard-traits {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 8px;
}
.fishcard-trait {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 20px;
  font-size: 10px;
  font-weight: 500;
  background: linear-gradient(135deg, #eef2ff, #f0e6ff);
  color: #6366f1;
  border: 1px solid rgba(99,102,241,0.1);
}

/* ===== Sections ===== */
.fishcard-section {
  padding: 16px 20px 0;
}
.fishcard-section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 10px;
}

/* ===== Attribute grid ===== */
.attr-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.attr-card {
  padding: 10px 6px;
  border-radius: 12px;
  border: 1px solid;
  text-align: center;
  transition: transform 0.15s;
}
.attr-card:hover {
  transform: translateY(-2px);
}
.attr-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin-bottom: 2px;
}
.attr-icon { font-size: 14px; }
.attr-abbr {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.attr-score {
  font-size: 22px;
  font-weight: 800;
  color: #0f172a;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}
.attr-mod {
  font-size: 14px;
  font-weight: 700;
  line-height: 1.2;
}
.attr-label {
  font-size: 9px;
  font-weight: 600;
  opacity: 0.7;
  margin-top: 1px;
}

/* ===== Proficiency tags ===== */
.prof-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 500;
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}

/* ===== Stat bars ===== */
.stat-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.stat-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.stat-label {
  width: 52px;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  text-align: right;
  flex-shrink: 0;
  white-space: nowrap;
}
.stat-bar-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}
.stat-bar {
  flex: 1;
  height: 7px;
  background: #e8ecf0;
  border-radius: 4px;
  overflow: hidden;
}
.stat-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s cubic-bezier(0.16, 1, 0.3, 1);
}
.growth-fill {
  background: linear-gradient(90deg, #0ea5e9, #38bdf8);
}
.happy-fill {
  background: linear-gradient(90deg, #f43f5e, #fb7185);
}
.xp-fill {
  background: linear-gradient(90deg, #06b6d4, #22d3ee);
}
.hp-fill { background: #ef4444; }
.energy-fill-pond { background: #22c55e; }
.stat-val {
  font-size: 11px;
  font-weight: 700;
  color: #334155;
  font-variant-numeric: tabular-nums;
  min-width: 28px;
  text-align: right;
}
.stat-hint {
  font-size: 10px;
  color: #94a3b8;
  min-width: 32px;
}

/* ===== Footer info ===== */
.fishcard-footer-info {
  display: flex;
  gap: 16px;
  padding: 12px 20px 0;
}
.footer-stat {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #94a3b8;
}
.footer-stat b {
  color: #475569;
  font-weight: 600;
}
.footer-stat-icon { font-size: 13px; }

/* ===== Delete ===== */
.fishcard-delete {
  padding: 16px 20px 20px;
}
.delete-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
  color: #94a3b8;
  background: transparent;
  border: 1px dashed #d1d5db;
  cursor: pointer;
  transition: all 0.2s;
}
.delete-btn:hover {
  color: #ef4444;
  border-color: #fca5a5;
  background: #fef2f2;
}
.delete-confirm-btn {
  flex: 1;
  padding: 9px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  background: #ef4444;
  color: white;
  border: none;
  cursor: pointer;
  transition: background 0.2s;
}
.delete-confirm-btn:hover { background: #dc2626; }
.delete-cancel-btn {
  flex: 1;
  padding: 9px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
  background: white;
  color: #64748b;
  border: 1px solid #e2e8f0;
  cursor: pointer;
  transition: background 0.2s;
}
.delete-cancel-btn:hover { background: #f8fafc; }

/* ===== v1.16.4: Rename ===== */
.rename-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px;
  margin-left: 4px;
  border-radius: 4px;
  color: #94a3b8;
  background: none;
  border: none;
  cursor: pointer;
  vertical-align: middle;
  opacity: 0;
  transition: opacity 0.15s, color 0.15s;
}
.fishcard-name:hover .rename-icon-btn { opacity: 1; }
.rename-icon-btn:hover { color: #6366f1; }
.rename-input {
  width: 130px;
  padding: 2px 6px;
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
  border: 1px solid #6366f1;
  border-radius: 6px;
  outline: none;
  background: white;
}
.rename-save-btn, .rename-cancel-btn {
  padding: 1px 6px;
  font-size: 12px;
  border-radius: 4px;
  border: none;
  cursor: pointer;
}
.rename-save-btn { background: #6366f1; color: white; }
.rename-cancel-btn { background: #f1f5f9; color: #94a3b8; }

/* ===== v1.16.4: Legendary Quest ===== */
.legendary-done {
  padding: 10px 12px;
  border-radius: 10px;
  background: linear-gradient(135deg, #fef3c7, #fde68a);
  color: #92400e;
  font-size: 12px;
  font-weight: 600;
  text-align: center;
}
.legendary-progress { display: flex; flex-direction: column; gap: 8px; }
.quest-steps { display: flex; gap: 6px; }
.quest-step {
  flex: 1;
  padding: 6px 4px;
  border-radius: 8px;
  font-size: 10px;
  text-align: center;
  background: #f1f5f9;
  color: #94a3b8;
  font-weight: 500;
}
.quest-step.done { background: #dcfce7; color: #16a34a; }
.quest-step.current { background: #ede9fe; color: #7c3aed; font-weight: 700; }
.quest-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  background: linear-gradient(135deg, #7c3aed, #a855f7);
  color: white;
  border: none;
  cursor: pointer;
  transition: all 0.2s;
}
.quest-btn:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(124,58,237,0.3); }
.quest-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
.quest-hint { font-size: 11px; color: #94a3b8; text-align: center; }
.quest-result {
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 600;
  background: #fef2f2;
  color: #dc2626;
}
.quest-result.success { background: #f0fdf4; color: #16a34a; }

/* ===== v1.16.4: Relationships ===== */
.rel-list { display: flex; flex-direction: column; gap: 6px; }
.rel-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #f1f5f9;
}
.rel-emoji { font-size: 18px; }
.rel-name { font-size: 13px; font-weight: 600; color: #334155; }
.rel-tag {
  padding: 1px 7px;
  border-radius: 12px;
  font-size: 10px;
  font-weight: 500;
}
.rel-friend { background: #dcfce7; color: #16a34a; }
.rel-rival { background: #fef2f2; color: #dc2626; }
.rel-strength { margin-left: auto; font-size: 10px; color: #94a3b8; font-weight: 600; }
</style>
