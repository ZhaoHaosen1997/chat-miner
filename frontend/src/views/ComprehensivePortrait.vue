<script setup>
import { ref, inject, onMounted, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { getPersona, analyzeComprehensivePortrait } from '../api/index.js'
import {
  ArrowLeft, Sparkles, Loader2, RefreshCw, Users2,
  MessageSquare, Hash, Palette, Lightbulb, Target, Layers,
} from 'lucide-vue-next'

const props = defineProps({ personaId: String })
const router = useRouter()
const route = useRoute()
const activeTaskId = inject('activeTaskId')
const triggerRefresh = inject('triggerRefresh')

const persona = ref(null)
const loading = ref(true)
const generating = ref(false)
const error = ref('')

const groupId = computed(() => route.query.group_id)

function platformLabel(p, wxid) {
  if (p === 'wechat') return '微信'
  if (p === 'qq') return 'QQ'
  if (wxid?.startsWith('wxid_')) return '微信'
  if (wxid?.startsWith('u_') && !wxid?.includes('@chatroom')) return 'QQ'
  return ''
}

function parsePortrait(raw) {
  if (!raw) return null
  try { return typeof raw === 'string' ? JSON.parse(raw) : raw } catch { return null }
}

function firstEmoji(str) {
  if (!str) return '👤'
  // 匹配第一个 emoji 序列（含修饰符、ZWJ、肤色等）
  const m = str.match(/[\p{Emoji_Presentation}\p{Emoji}‍\u{fe0f}\u{1f3fb}-\u{1f3ff}]/u)
  return m ? m[0] : (str.slice(0, 2) || '👤')
}

async function load() {
  if (!props.personaId) return
  loading.value = true
  error.value = ''
  try {
    persona.value = await getPersona(props.personaId)
  } catch (e) {
    error.value = e.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function doGenerate() {
  if (generating.value || activeTaskId.value) return
  generating.value = true
  try {
    const result = await analyzeComprehensivePortrait(Number(props.personaId))
    if (result.task_id) {
      activeTaskId.value = result.task_id
    } else {
      generating.value = false  // v1.5.2: 无task_id时重置，防止按钮永久禁用
    }
  } catch (e) {
    console.error(e)
    generating.value = false
  }
}

// Watch for task completion to reload
import { watch } from 'vue'
watch(activeTaskId, (n, o) => {
  if (o && !n) {
    generating.value = false
    load()
    triggerRefresh?.()
  }
})

onMounted(load)

function goBack() {
  if (groupId.value) {
    router.push(`/?group_id=${groupId.value}`)
  } else {
    router.back()
  }
}
</script>

<template>
  <div class="min-h-screen" style="background: linear-gradient(180deg, #FAFAF8 0%, #F0EDF8 100%)">
    <!-- Loading -->
    <div v-if="loading" class="flex items-center justify-center py-32">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <!-- Error -->
    <div v-else-if="error" class="max-w-2xl mx-auto px-4 py-32 text-center">
      <p class="text-slate-500 mb-4">{{ error }}</p>
      <button @click="goBack" class="text-sm text-indigo-500 hover:text-indigo-600 font-medium">
        ← 返回
      </button>
    </div>

    <!-- Content -->
    <template v-else-if="persona">
      <!-- === Empty State: No comprehensive portrait yet === -->
      <div v-if="!persona.comprehensive_portrait" class="max-w-2xl mx-auto px-4 py-32 text-center">
        <div class="w-20 h-20 rounded-2xl bg-white shadow-sm border border-slate-100 flex items-center justify-center mx-auto mb-6">
          <Sparkles class="w-10 h-10 text-indigo-300" />
        </div>
        <h2 class="text-xl font-bold text-slate-800 mb-2">尚未生成全面画像</h2>
        <p class="text-sm text-slate-500 mb-2">
          聚合 {{ persona.name || 'Persona #' + persona.id }} 下
          {{ persona.members?.length || 0 }} 个身份的所有画像
        </p>
        <p class="text-xs text-slate-400 mb-8">用 AI 综合分析跨群人格特质</p>
        <button
          @click="doGenerate"
          :disabled="generating || !!activeTaskId"
          class="inline-flex items-center gap-2 px-6 py-3 bg-indigo-600 text-white text-sm font-medium rounded-xl hover:bg-indigo-700 transition-colors shadow-lg shadow-indigo-200 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Loader2 v-if="generating || activeTaskId" class="w-4 h-4 animate-spin" />
          <Sparkles v-else class="w-4 h-4" />
          {{ generating || activeTaskId ? '生成中...' : '生成全面画像' }}
        </button>
        <button @click="goBack" class="block mx-auto mt-4 text-sm text-slate-400 hover:text-slate-600 transition-colors">
          ← 返回
        </button>
      </div>

      <!-- === Generated Portrait === -->
      <div v-else class="max-w-3xl mx-auto px-4 py-8">
        <!-- Back link -->
        <button @click="goBack" class="flex items-center gap-1.5 text-sm text-slate-400 hover:text-slate-600 mb-8 transition-colors">
          <ArrowLeft class="w-4 h-4" /> 返回
        </button>

        <!-- === HERO === -->
        <section class="text-center mb-16">
          <div class="text-7xl mb-6">{{ firstEmoji(persona.comprehensive_portrait.unified_emoji) || '🎭' }}</div>
          <h1 class="text-3xl font-bold text-slate-800 tracking-tight mb-3">
            {{ persona.comprehensive_portrait.unified_oneline || '跨群人格画像' }}
          </h1>
          <div class="flex items-center justify-center gap-2 text-sm text-slate-400">
            <Users2 class="w-4 h-4" />
            <span>跨 {{ persona.members?.length || 0 }} 个群的身份</span>
            <span class="text-slate-300">·</span>
            <span v-if="persona.members?.some(m => platformLabel(m.platform, m.wxid) === '微信')" class="inline-flex items-center gap-1 px-2 py-0.5 bg-green-50 text-green-600 rounded-full text-xs font-medium">微信</span>
            <span v-if="persona.members?.some(m => platformLabel(m.platform, m.wxid) === 'QQ')" class="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-600 rounded-full text-xs font-medium">QQ</span>
          </div>
        </section>

        <!-- === CORE PERSONALITY === -->
        <section class="mb-16">
          <div class="flex items-center gap-2 mb-4">
            <div class="w-1 h-5 rounded-full bg-indigo-400"></div>
            <span class="text-xs font-semibold text-indigo-500 uppercase tracking-widest">核心人格</span>
          </div>
          <blockquote class="text-xl leading-relaxed text-slate-700 font-medium pl-5 border-l-2 border-indigo-200 italic">
            {{ persona.comprehensive_portrait.core_personality }}
          </blockquote>
        </section>

        <!-- === GROUP DIFFERENCES === -->
        <section v-if="persona.comprehensive_portrait.group_differences?.length" class="mb-16">
          <div class="flex items-center gap-2 mb-6">
            <div class="w-1 h-5 rounded-full bg-violet-400"></div>
            <span class="text-xs font-semibold text-violet-500 uppercase tracking-widest">群际差异</span>
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <div
              v-for="(gd, i) in persona.comprehensive_portrait.group_differences"
              :key="gd.group"
              class="group relative bg-white rounded-2xl p-5 border border-slate-100 shadow-sm hover:shadow-md transition-shadow border-l-2"
                   :class="i % 2 === 0 ? 'border-l-indigo-300' : 'border-l-violet-300'"
            >
              <h3 class="text-sm font-semibold text-slate-800 mb-2">{{ gd.group }}</h3>
              <div class="flex items-center gap-2 mb-2">
                <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium"
                      :class="i % 2 === 0 ? 'bg-indigo-50 text-indigo-600' : 'bg-violet-50 text-violet-600'">
                  {{ gd.role }}
                </span>
              </div>
              <p class="text-sm text-slate-500 leading-relaxed">{{ gd.difference }}</p>
            </div>
          </div>
        </section>

        <!-- === INSIGHT TRIPTYCH === -->
        <section class="mb-16">
          <div class="grid gap-6 md:grid-cols-3">
            <!-- Deep Insight -->
            <div v-if="persona.comprehensive_portrait.comprehensive_insight"
                 class="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
              <div class="flex items-center gap-2 mb-3">
                <Lightbulb class="w-4 h-4 text-amber-400" />
                <span class="text-xs font-semibold text-slate-500 uppercase tracking-wider">深度洞察</span>
              </div>
              <p class="text-sm text-slate-600 leading-relaxed">
                {{ persona.comprehensive_portrait.comprehensive_insight }}
              </p>
            </div>

            <!-- Interest Overlap -->
            <div v-if="persona.comprehensive_portrait.interest_overlap"
                 class="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
              <div class="flex items-center gap-2 mb-3">
                <Layers class="w-4 h-4 text-emerald-400" />
                <span class="text-xs font-semibold text-slate-500 uppercase tracking-wider">共同兴趣</span>
              </div>
              <p class="text-sm text-slate-600 leading-relaxed">
                {{ persona.comprehensive_portrait.interest_overlap }}
              </p>
            </div>

            <!-- Social Style -->
            <div v-if="persona.comprehensive_portrait.social_style"
                 class="bg-white rounded-2xl p-5 border border-slate-100 shadow-sm">
              <div class="flex items-center gap-2 mb-3">
                <MessageSquare class="w-4 h-4 text-rose-400" />
                <span class="text-xs font-semibold text-slate-500 uppercase tracking-wider">社交风格</span>
              </div>
              <p class="text-sm text-slate-600 leading-relaxed">
                {{ persona.comprehensive_portrait.social_style }}
              </p>
            </div>
          </div>
        </section>

        <!-- === MEMBER GALLERY === -->
        <section class="mb-16">
          <div class="flex items-center gap-2 mb-6">
            <div class="w-1 h-5 rounded-full bg-slate-300"></div>
            <span class="text-xs font-semibold text-slate-500 uppercase tracking-widest">各群画像</span>
          </div>
          <div class="grid gap-3 md:grid-cols-2">
            <div
              v-for="m in persona.members"
              :key="m.id"
              class="flex items-start gap-3 bg-white rounded-xl p-4 border border-slate-100 hover:border-indigo-200 transition-colors cursor-pointer"
              @click="router.push(`/portrait/${m.id}?group_id=${m.group_id}`)"
            >
              <div class="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center"
                   :class="platformLabel(m.platform, m.wxid) === '微信' ? 'bg-green-50 text-base' : platformLabel(m.platform, m.wxid) === 'QQ' ? 'bg-blue-50 text-base' : 'bg-slate-50 text-base'">
                {{ firstEmoji(parsePortrait(m.portrait_json)?.emoji_style) }}
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-1.5">
                  <span class="text-sm font-medium text-slate-700 truncate">{{ m.display_name || m.wxid }}</span>
                  <span class="text-[10px] px-1.5 py-0.5 rounded-full"
                        :class="platformLabel(m.platform, m.wxid) === '微信' ? 'bg-green-50 text-green-600' : platformLabel(m.platform, m.wxid) === 'QQ' ? 'bg-blue-50 text-blue-600' : 'bg-slate-100 text-slate-500'">
                    {{ platformLabel(m.platform, m.wxid) || '未知' }}
                  </span>
                </div>
                <div class="text-xs text-slate-400">{{ m.group_name }} · {{ m.message_count }} 条消息</div>
                <div v-if="parsePortrait(m.portrait_json)?.one_line" class="text-xs text-slate-500 mt-1 truncate">
                  {{ parsePortrait(m.portrait_json).one_line }}
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- === Footer: Regenerate === -->
        <div class="text-center pb-12">
          <button
            @click="doGenerate"
            :disabled="generating || !!activeTaskId"
            class="inline-flex items-center gap-1.5 text-sm text-slate-400 hover:text-indigo-500 transition-colors disabled:opacity-50"
          >
            <RefreshCw class="w-3.5 h-3.5" :class="{ 'animate-spin': generating || activeTaskId }" />
            重新生成全面画像
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
