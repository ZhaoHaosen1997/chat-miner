<script setup>
import { ref, inject, watch, onMounted } from 'vue'
import { getPortraits, refreshPortrait, getMembers } from '../api/index.js'
import { Loader2, Sparkles, RefreshCw, X, User, MessageSquare, Clock, Tag } from 'lucide-vue-next'

const currentGroup = inject('currentGroup')
const triggerRefresh = inject('triggerRefresh')

const portraits = ref([])
const members = ref([])
const loading = ref(false)
const refreshing = ref(null)
const selected = ref(null)
const error = ref('')

async function load() {
  if (!currentGroup.value) return
  loading.value = true
  const gid = currentGroup.value.id
  try {
    const [p, m] = await Promise.all([getPortraits(gid), getMembers(gid)])
    portraits.value = p
    members.value = m
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

watch(currentGroup, load, { immediate: true })

async function refreshOne(memberId) {
  if (refreshing.value === memberId) return
  refreshing.value = memberId
  try {
    await refreshPortrait(currentGroup.value.id, memberId)
    await load()
    triggerRefresh?.()
  } catch (e) {
    console.error(e)
  } finally {
    refreshing.value = null
  }
}

function openDetail(portrait) {
  selected.value = portrait
}

// 将 portraits 和 members 合并
const mergedPortraits = ref([])
watch([portraits, members], ([p, m]) => {
  mergedPortraits.value = p.map(pt => {
    const member = m.find(mb => mb.id === pt.member_id) || {}
    return { ...pt, ...member }
  })
})
</script>

<template>
  <div>
    <!-- 头部 -->
    <div class="flex items-center justify-between mb-6">
      <div>
        <h2 class="text-xl font-bold text-slate-800">群友画像</h2>
        <p class="text-sm text-slate-400 mt-1">基于 AI 分析的成员性格、风格和角色</p>
      </div>
      <div class="text-xs text-slate-400">
        {{ portraits.length }} / {{ members.length }} 人已生成画像
      </div>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="flex items-center justify-center py-20">
      <Loader2 class="w-8 h-8 animate-spin text-indigo-400" />
    </div>

    <!-- 画像卡片网格 -->
    <div v-else class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      <div
        v-for="p in mergedPortraits"
        :key="p.member_id"
        @click="openDetail(p)"
        class="card p-4 cursor-pointer hover:border-indigo-200 transition-all group"
      >
        <!-- 头像 + name -->
        <div class="flex items-center gap-3 mb-3">
          <img
            v-if="p.avatar"
            :src="p.avatar"
            :alt="p.display_name"
            class="w-10 h-10 rounded-full bg-slate-100"
            referrerpolicy="no-referrer"
            @error="$event.target.style.display='none'"
          />
          <div v-else class="w-10 h-10 rounded-full bg-indigo-100 flex items-center justify-center">
            <User class="w-5 h-5 text-indigo-400" />
          </div>
          <div class="min-w-0">
            <div class="text-sm font-semibold text-slate-700 truncate">{{ p.display_name }}</div>
            <div v-if="p.remark && p.remark !== p.display_name" class="text-[11px] text-slate-400 truncate">{{ p.remark }}</div>
          </div>
        </div>

        <!-- 一句话人设 -->
        <p class="text-sm text-slate-600 leading-relaxed mb-3 group-hover:text-indigo-600 transition-colors">
          {{ p.portrait?.one_line || '点击生成画像' }}
        </p>

        <!-- 标签 -->
        <div v-if="p.portrait?.personality" class="flex flex-wrap gap-1 mb-2">
          <span
            v-for="tag in p.portrait.personality"
            :key="tag"
            class="px-2 py-0.5 bg-slate-100 text-slate-500 rounded-full text-[11px]"
          >{{ tag }}</span>
        </div>

        <!-- emoji -->
        <div class="flex items-center justify-between">
          <span class="text-lg">{{ p.portrait?.emoji_style || '👤' }}</span>
          <button
            @click.stop="refreshOne(p.member_id)"
            :disabled="refreshing === p.member_id"
            class="text-slate-300 hover:text-indigo-500 transition-colors"
            title="刷新画像"
          >
            <RefreshCw :class="['w-3.5 h-3.5', refreshing === p.member_id && 'animate-spin']" />
          </button>
        </div>
      </div>

      <!-- 未生成画像的成员 -->
      <div
        v-for="m in members.filter(mb => !portraits.find(p => p.member_id === mb.id))"
        :key="'nomem-' + m.id"
        class="card p-4 flex flex-col items-center justify-center text-center gap-2 min-h-[160px] opacity-60"
      >
        <User class="w-8 h-8 text-slate-300" />
        <div>
          <div class="text-sm font-medium text-slate-500">{{ m.display_name }}</div>
          <div class="text-xs text-slate-400">{{ m.message_count }} 条消息</div>
        </div>
        <button
          @click="refreshOne(m.id)"
          :disabled="refreshing === m.id"
          class="mt-1 px-3 py-1 text-xs text-indigo-500 hover:bg-indigo-50 rounded-lg transition-colors flex items-center gap-1"
        >
          <Sparkles class="w-3 h-3" /> 生成画像
        </button>
      </div>
    </div>

    <!-- 暂无数据 -->
    <div v-if="members.length === 0 && !loading" class="card p-12 text-center">
      <Sparkles class="w-12 h-12 text-slate-300 mx-auto mb-3" />
      <p class="text-slate-400">导入群聊并分析几天后，才能生成群友画像哦</p>
    </div>

    <!-- 详情弹窗 -->
    <Teleport to="body">
      <div
        v-if="selected"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
        @click.self="selected = null"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden max-h-[85vh] overflow-y-auto">
          <!-- Header -->
          <div class="sticky top-0 bg-white flex items-center justify-between px-5 py-3 border-b border-slate-100">
            <h3 class="font-semibold text-slate-800">成员画像</h3>
            <button @click="selected = null" class="p-1 rounded-lg hover:bg-slate-100 text-slate-400">
              <X class="w-5 h-5" />
            </button>
          </div>

          <!-- Body -->
          <div class="p-5 space-y-4">
            <!-- 基本信息 -->
            <div class="flex items-center gap-3">
              <img
                v-if="selected.avatar"
                :src="selected.avatar"
                :alt="selected.display_name"
                class="w-14 h-14 rounded-full bg-slate-100"
                referrerpolicy="no-referrer"
                @error="$event.target.style.display='none'"
              />
              <div v-else class="w-14 h-14 rounded-full bg-indigo-100 flex items-center justify-center">
                <User class="w-7 h-7 text-indigo-400" />
              </div>
              <div>
                <div class="text-lg font-bold text-slate-800">{{ selected.display_name }}</div>
                <div class="text-sm text-slate-400">{{ selected.one_line || selected.portrait?.one_line }}</div>
              </div>
              <div class="ml-auto text-3xl">{{ selected.portrait?.emoji_style || selected.emoji_style || '👤' }}</div>
            </div>

            <!-- 画像详情 -->
            <div class="space-y-3">
              <div class="bg-slate-50 rounded-xl p-3">
                <div class="text-xs text-slate-400 mb-1 flex items-center gap-1"><Tag class="w-3 h-3" /> 性格</div>
                <div class="flex gap-1.5 flex-wrap">
                  <span
                    v-for="t in selected.portrait?.personality || []"
                    :key="t"
                    class="px-2.5 py-1 bg-indigo-100 text-indigo-700 rounded-full text-sm font-medium"
                  >{{ t }}</span>
                </div>
              </div>

              <div class="grid grid-cols-2 gap-2">
                <div class="bg-slate-50 rounded-xl p-3">
                  <div class="text-xs text-slate-400 mb-1">说话风格</div>
                  <div class="text-sm font-medium text-slate-700">{{ selected.portrait?.speaking_style || '—' }}</div>
                </div>
                <div class="bg-slate-50 rounded-xl p-3">
                  <div class="text-xs text-slate-400 mb-1">群内角色</div>
                  <div class="text-sm font-medium text-slate-700">{{ selected.portrait?.role || '—' }}</div>
                </div>
              </div>

              <div class="bg-slate-50 rounded-xl p-3">
                <div class="text-xs text-slate-400 mb-1 flex items-center gap-1"><Clock class="w-3 h-3" /> 活跃时段</div>
                <div class="text-sm text-slate-700">{{ selected.portrait?.active_hours || '—' }}</div>
              </div>

              <div class="bg-slate-50 rounded-xl p-3">
                <div class="text-xs text-slate-400 mb-1">兴趣话题</div>
                <div class="flex gap-1.5 flex-wrap">
                  <span
                    v-for="t in selected.portrait?.interests || []"
                    :key="t"
                    class="px-2.5 py-1 bg-amber-50 text-amber-700 rounded-full text-sm"
                  >{{ t }}</span>
                </div>
              </div>

              <div v-if="selected.portrait?.signature_phrase" class="bg-slate-50 rounded-xl p-3">
                <div class="text-xs text-slate-400 mb-1">口头禅</div>
                <div class="text-sm text-slate-600 italic">"{{ selected.portrait.signature_phrase }}"</div>
              </div>
            </div>

            <!-- 刷新按钮 -->
            <button
              @click="refreshOne(selected.member_id)"
              :disabled="refreshing === selected.member_id"
              class="w-full py-2.5 flex items-center justify-center gap-2 text-sm text-indigo-500 hover:bg-indigo-50 rounded-xl transition-colors"
            >
              <RefreshCw :class="['w-4 h-4', refreshing === selected.member_id && 'animate-spin']" />
              刷新画像
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
