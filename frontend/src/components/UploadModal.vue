<script setup>
import { ref } from 'vue'
import { uploadGroup } from '../api/index.js'
import { Upload, FileJson, X, CheckCircle, Loader2 } from 'lucide-vue-next'

const emit = defineEmits(['close', 'uploaded'])

const file = ref(null)
const uploading = ref(false)
const error = ref('')
const preview = ref(null)

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
    const data = await uploadGroup(file.value)
    emit('uploaded', {
      id: data.group_id,
      name: data.group_name,
      display_name: data.group_name,
      message_count: data.message_count,
      sender_count: data.sender_count,
    })
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
          <Upload class="w-5 h-5 text-indigo-500" /> 导入群聊数据
        </h3>
        <button @click="emit('close')" class="p-1 rounded-lg hover:bg-slate-100 text-slate-400">
          <X class="w-5 h-5" />
        </button>
      </div>

      <!-- Body -->
      <div class="px-6 py-5">
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
          {{ uploading ? '解析中...' : '确认导入' }}
        </button>
      </div>
    </div>
  </div>
</template>
