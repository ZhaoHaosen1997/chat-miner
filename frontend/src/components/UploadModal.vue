<script setup>
import { ref } from 'vue'
import { Upload, FileJson, X, CheckCircle, Loader2 } from 'lucide-vue-next'

const props = defineProps({ group: Object })
const emit = defineEmits(['close', 'uploaded'])

const file = ref(null)
const uploading = ref(false)
const error = ref('')
const preview = ref(null)

const isGroupImport = !!props.group

function onFileChange(e) {
  const f = e.target.files?.[0]
  if (!f) return
  if (!f.name.endsWith('.json')) {
    error.value = '请选择 .json 格式的聊天记录文件'
    return
  }
  file.value = f
  error.value = ''
  preview.value = { name: f.name, size: (f.size / 1024 / 1024).toFixed(1) + ' MB' }
}

async function handleUpload() {
  if (!file.value) return
  uploading.value = true
  error.value = ''
  try {
    const form = new FormData()
    form.append('file', file.value)

    let url, method
    if (isGroupImport) {
      url = `/api/groups/${props.group.id}/import`
      method = 'POST'
    } else {
      url = '/api/groups/upload'
      method = 'POST'
    }

    const res = await fetch(url, { method, body: form })
    const data = await res.json()
    if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '上传失败')
    emit('uploaded', data.data)
  } catch (e) {
    error.value = e.message || '上传失败'
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
       @click.self="emit('close')">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md mx-4 overflow-hidden">
      <!-- Header -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-slate-100">
        <h3 class="text-lg font-semibold text-slate-800 flex items-center gap-2">
          <Upload class="w-5 h-5 text-indigo-500" />
          {{ isGroupImport ? `导入数据到「${props.group.display_name || props.group.name}」` : '导入群聊数据' }}
        </h3>
        <button @click="emit('close')" class="p-1 rounded-lg hover:bg-slate-100 text-slate-400">
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Body -->
      <div class="px-6 py-5">
        <!-- 提示文字 -->
        <p v-if="isGroupImport" class="text-xs text-slate-400 mb-3">
          💡 追加导入会自动去重，已有消息不会重复。群名如果变了也不影响。
        </p>

        <!-- 文件拖拽区 -->
        <label
          :class="[
            'flex flex-col items-center justify-center gap-3 p-8 border-2 border-dashed rounded-xl cursor-pointer transition-colors',
            file.value ? 'border-indigo-300 bg-indigo-50/50' : 'border-slate-200 hover:border-indigo-300 hover:bg-slate-50',
          ]"
        >
          <input type="file" accept=".json" class="hidden" @change="onFileChange" />
          <template v-if="!file.value">
            <FileJson class="w-10 h-10 text-slate-300" />
            <div class="text-center">
              <p class="text-sm text-slate-500">点击或拖拽上传 .json 文件</p>
              <p class="text-xs text-slate-400 mt-1">微信聊天记录导出格式</p>
            </div>
          </template>
          <template v-else>
            <CheckCircle class="w-10 h-10 text-green-500" />
            <div class="text-center">
              <p class="text-sm font-medium text-slate-700">{{ preview.name }}</p>
              <p class="text-xs text-slate-400">{{ preview.size }}</p>
            </div>
          </template>
        </label>

        <!-- 错误提示 -->
        <div v-if="error" class="mt-3 text-sm text-red-500 bg-red-50 px-3 py-2 rounded-lg">
          {{ error }}
        </div>
      </div>

      <!-- Footer -->
      <div class="px-6 py-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-3">
        <button @click="emit('close')"
                class="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 transition-colors">
          取消
        </button>
        <button
          @click="handleUpload"
          :disabled="!file.value || uploading"
          :class="[
            'px-5 py-2 text-sm font-medium rounded-xl transition-all flex items-center gap-2',
            file.value && !uploading
              ? 'bg-indigo-600 text-white hover:bg-indigo-700 shadow-lg shadow-indigo-200'
              : 'bg-slate-200 text-slate-400 cursor-not-allowed',
          ]"
        >
          <Loader2 v-if="uploading" class="w-4 h-4 animate-spin" />
          {{ uploading ? '导入中...' : isGroupImport ? '追加导入' : '确认导入' }}
        </button>
      </div>
    </div>
  </div>
</template>
