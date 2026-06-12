/**
 * API 封装层
 * 统一请求处理 + 错误兜底
 */
const BASE = '/api'

export async function apiGet(url) {
  const res = await fetch(`${BASE}${url}`)
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data
}

async function request(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const data = await res.json()
  if (!res.ok || data.code !== 200) {
    throw new Error(data.detail || data.message || '请求失败')
  }
  return data.data
}

// --- 群管理 ---
export const listGroups = () => request('/groups')
export const renameGroup = (id, name) =>
  request(`/groups/${id}?name=${encodeURIComponent(name)}`, { method: 'PUT' })
export const deleteGroup = (id) => request(`/groups/${id}`, { method: 'DELETE' })

export async function uploadGroup(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/groups/upload`, { method: 'POST', body: form })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || '上传失败')
  return data.data
}

// --- 群成员 ---
export const getMembers = (gid) => request(`/groups/${gid}/members`)

// --- 日期 ---
export const getDates = (gid) => request(`/groups/${gid}/dates`)
export const getAnalyzedDates = (gid) => request(`/groups/${gid}/dates/analyzed`)

// --- 每日报告 ---
export const analyzeDate = (gid, date) =>
  request(`/groups/${gid}/analyze/${date}`, { method: 'POST' })
// 异步分析：返回 task_id。v0.12.0: 支持 modelId 参数
export const analyzeDateAsync = async (gid, date, modelId = null) => {
  const params = new URLSearchParams()
  if (modelId) params.set('model_id', modelId)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${BASE}/groups/${gid}/analyze/${date}${qs}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data // { task_id, status } or { cached, report, ... }
}
export const getReport = (gid, date) => request(`/groups/${gid}/report/${date}`)
export const deleteReport = (gid, date) =>
  request(`/groups/${gid}/report/${date}`, { method: 'DELETE' })
export const getRecentReports = (gid, limit = 7) =>
  request(`/groups/${gid}/reports/recent?limit=${limit}`)
export const getTrending = (gid, days = 7) =>
  request(`/groups/${gid}/trending?days=${days}`)

// --- 画像 ---
export const getRelations = (gid) => request(`/groups/${gid}/relations`)
export const getPortraits = (gid) => request(`/groups/${gid}/portraits`)
export const getPortrait = (gid, mid) => request(`/groups/${gid}/portrait/${mid}`)
export const refreshPortrait = (gid, mid) =>
  request(`/groups/${gid}/portrait/${mid}/refresh`, { method: 'POST' })
// 异步刷新画像
export const refreshPortraitAsync = async (gid, mid) => {
  const res = await fetch(`${BASE}/groups/${gid}/portrait/${mid}/refresh`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data
}
export const refreshAllPortraits = (gid) =>
  request(`/groups/${gid}/portraits/refresh-all`, { method: 'POST' })

// --- 深度画像 ---
export const getPortraitStats = (gid, mid) =>
  request(`/groups/${gid}/portrait/${mid}/stats`)
export const getPortraitHistory = (gid, mid) =>
  request(`/groups/${gid}/portrait/${mid}/history`)
export const getArchaeology = (gid, mid) =>
  request(`/groups/${gid}/portrait/${mid}/archaeology`)
export const generateDeepPortrait = async (gid, mid) => {
  const res = await fetch(`${BASE}/groups/${gid}/portrait/${mid}/deep`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data
}
// 统一画像分析（v0.5.1 合并：基础+深度一步完成）
// max_days: 0=全量, 10=最近10天增量刷新
// v0.12.2: 支持 modelId 参数
export const analyzePortrait = async (gid, mid, modelId = null) => {
  const params = new URLSearchParams()
  if (modelId) params.set('model_id', modelId)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${BASE}/groups/${gid}/portrait/${mid}/analyze${qs}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data
}
// 一键分析全群画像
export const analyzeAllPortraits = async (gid, modelId = null) => {
  const params = new URLSearchParams()
  if (modelId) params.set('model_id', modelId)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${BASE}/groups/${gid}/portraits/analyze-all${qs}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data
}

// --- 任务 ---
export const getActiveTasks = () => request('/tasks/active')

// --- 统计 ---
export const getGroupStats = (gid) => request(`/groups/${gid}/stats`)
export const getGlobalStats = () => request('/stats/global')
export const getHealth = () => request('/health')
export const getTaskHistory = (gid, limit = 10) => request(`/tasks/history?group_id=${gid}&limit=${limit}`)

// --- 批量分析 ---
export const analyzeAll = async (gid, modelId = null) => {
  const params = new URLSearchParams()
  if (modelId) params.set('model_id', modelId)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${BASE}/groups/${gid}/analyze-all${qs}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data
}

// --- 群鱼塘 v0.9 ---
export const getFishPond = (gid) => request(`/groups/${gid}/fishpond/`)
export const getFishDetail = (gid, wxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}`)
export const deleteFish = (gid, wxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/delete`, { method: 'POST' })
export const adoptFish = (gid, wxid, displayName = '') =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/adopt`, {
    method: 'POST', body: JSON.stringify({ display_name: displayName })
  })
export const feedFish = (gid, wxid, fromWxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/feed`, {
    method: 'POST', body: JSON.stringify({ from_wxid: fromWxid })
  })
export const touchFish = (gid, wxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/touch`, { method: 'POST' })
export const exploreFish = (gid, wxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/explore`, { method: 'POST' })
export const showoffFish = (gid, wxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/showoff`, { method: 'POST' })
export const trainFish = (gid, wxid, attrName) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/train`, {
    method: 'POST', body: JSON.stringify({ attr_name: attrName })
  })
export const fishItems = (gid, wxid, action, itemKey = '', qty = 1) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/items`, {
    method: 'POST', body: JSON.stringify({ action, item_key: itemKey, qty })
  })
export const buyFromMarket = (gid, wxid, itemKey) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/buy`, {
    method: 'POST', body: JSON.stringify({ item_key: itemKey })
  })
export const giftItem = (gid, wxid, targetName, itemKey) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/gift`, {
    method: 'POST', body: JSON.stringify({ target_name: targetName, item_key: itemKey })
  })
export const logSimCommand = (gid, entry) =>
  request(`/groups/${gid}/fishpond/log-sim-command`, {
    method: 'POST', body: JSON.stringify(entry)
  })
export const getBlackMarket = (gid, date = '') =>
  request(`/groups/${gid}/fishpond/black-market?date=${encodeURIComponent(date)}`)
export const generateFishReport = (gid, date = '') =>
  request(`/groups/${gid}/fishpond/generate-report?date=${encodeURIComponent(date)}`, { method: 'POST' })
export const getFishReport = (gid, date) =>
  request(`/groups/${gid}/fishpond/report/${encodeURIComponent(date)}`)
export const listFishReports = (gid) =>
  request(`/groups/${gid}/fishpond/reports`)
export const battleFish = (gid, wxid, targetWxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/battle`, {
    method: 'POST', body: JSON.stringify({ target_wxid: targetWxid })
  })
export const renameFish = (gid, wxid, name) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/rename`, {
    method: 'POST', body: JSON.stringify({ name })
  })
export const settleFishPond = (gid) =>
  request(`/groups/${gid}/fishpond/settle`, { method: 'POST' })
export const resettleFishPond = (gid, date) =>
  request(`/groups/${gid}/fishpond/resettle?date=${encodeURIComponent(date)}`, { method: 'POST' })
export const getFishLeaderboard = (gid, sort = 'growth') =>
  request(`/groups/${gid}/fishpond/leaderboard?sort=${sort}`)
export const getFishEvents = (gid, wxid = '', limit = 20) =>
  request(`/groups/${gid}/fishpond/events?wxid=${encodeURIComponent(wxid)}&limit=${limit}`)
export const parseFishCommands = (gid) =>
  request(`/groups/${gid}/fishpond/parse-commands`, { method: 'POST' })
export const getCoinBalance = (gid, wxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/coins`)
export const spendCoins = (gid, wxid, item, amount) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/coins/spend`, {
    method: 'POST', body: JSON.stringify({ item, amount })
  })
export const getShopItems = (gid) => request(`/groups/${gid}/fishpond/shop`)

// --- 周报/月报 ---
export const getPeriods = (gid, type = 'weekly') =>
  request(`/groups/${gid}/periods?type=${type}`)
export const getWeeklyReport = (gid, periodKey) =>
  request(`/groups/${gid}/weekly/${periodKey}`)
export const getMonthlyReport = (gid, periodKey) =>
  request(`/groups/${gid}/monthly/${periodKey}`)
export const generateWeekly = async (gid, periodKey = '', force = false, modelId = null) => {
  const params = new URLSearchParams()
  if (periodKey) params.set('period_key', periodKey)
  if (force) params.set('force', 'true')
  if (modelId) params.set('model_id', modelId)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${BASE}/groups/${gid}/weekly/generate${qs}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data
}
export const generateMonthly = async (gid, periodKey = '', force = false, modelId = null) => {
  const params = new URLSearchParams()
  if (periodKey) params.set('period_key', periodKey)
  if (force) params.set('force', 'true')
  if (modelId) params.set('model_id', modelId)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${BASE}/groups/${gid}/monthly/generate${qs}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data
}

// --- 年度报告 v0.11 ---
export const getAnnualReport = (gid, year) =>
  request(`/groups/${gid}/annual/${year}`)
export const getAnnualAwards = (gid, year) =>
  request(`/groups/${gid}/annual-awards/${year}`)
export const getMemberAwards = (gid, memberId) =>
  request(`/groups/${gid}/member/${memberId}/awards`)
export async function generateAnnual(gid, year = 0, force = false, modelId = null) {
  const params = new URLSearchParams()
  if (year) params.set('year', year)
  if (force) params.set('force', 'true')
  if (modelId) params.set('model_id', modelId)
  const qs = params.toString()
  const res = await fetch(`${BASE}/groups/${gid}/annual/generate${qs ? '?' + qs : ''}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data
}

// ==================== 模型配置 v0.12.0 ====================

export const getModelConfigs = () => request('/settings/models')
export const getModelConfig = (id) => request(`/settings/models/${id}`)
export const createModelConfig = (data) =>
  request('/settings/models', { method: 'POST', body: JSON.stringify(data) })
export const updateModelConfig = (id, data) =>
  request(`/settings/models/${id}`, { method: 'PUT', body: JSON.stringify(data) })
export const deleteModelConfig = (id) =>
  request(`/settings/models/${id}`, { method: 'DELETE' })
export const setDefaultModel = (id) =>
  request(`/settings/models/${id}/set-default`, { method: 'POST' })
export const checkModelHealth = (id) =>
  request(`/settings/models/${id}/health`)
export const getModelDefaults = () => request('/settings/defaults')

