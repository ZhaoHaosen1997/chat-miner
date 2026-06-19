/**
 * API 封装层
 * 统一请求处理 + 错误兜底
 */
const BASE = '/api'

export async function apiGet(url) {
  const res = await fetch(`${BASE}${url}`)
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data  // v0.13.2: 统一返回 data.data，与 request() 一致
}

export async function request(url, options = {}) {
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
export const analyzeDateAsync = async (gid, date, modelId = null, force = false) => {
  const params = new URLSearchParams()
  if (modelId) params.set('model_id', modelId)
  if (force) params.set('force', 'true')
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
export const getTaskHistoryAll = ({ groupId, taskType, status, limit = 50, offset = 0 } = {}) => {
  const params = new URLSearchParams()
  if (groupId) params.set('group_id', groupId)
  if (taskType) params.set('task_type', taskType)
  if (status) params.set('status', status)
  params.set('limit', limit)
  params.set('offset', offset)
  return request(`/tasks/history?${params.toString()}`)
}

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
export const restFish = (gid, wxid) =>                          // v1.16.0
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/rest`, { method: 'POST' })
export const getPondLog = (gid, limit = 30) =>                  // v1.16.1
  request(`/groups/${gid}/fishpond/pond-log?limit=${limit}`)
export const triggerPondEvent = (gid) =>                        // v1.16.1
  request(`/groups/${gid}/fishpond/trigger-event`, { method: 'POST' })
export const getPondTreasury = (gid) =>                         // v1.16.1
  request(`/groups/${gid}/fishpond/treasury`)
export const getTreasuryLog = (gid, limit = 20) =>             // v1.16.2
  request(`/groups/${gid}/fishpond/treasury?limit=${limit}`)
export const getUpgrades = (gid) =>                            // v1.16.2
  request(`/groups/${gid}/fishpond/upgrades`)
export const upgradePond = (gid, upgradeKey) =>                // v1.16.2
  request(`/groups/${gid}/fishpond/upgrade`, { method:'POST', body:JSON.stringify({upgrade_key:upgradeKey}) })
export const executeDecree = (gid, decreeKey, targetWxid) =>   // v1.16.2
  request(`/groups/${gid}/fishpond/decree`, { method:'POST', body:JSON.stringify({decree:decreeKey, target_wxid:targetWxid}) })
export const getDecreeLimits = (gid) =>                        // v1.16.2
  request(`/groups/${gid}/fishpond/decree-limits`)
export const batchAdopt = (gid) =>                             // v1.16.2
  request(`/groups/${gid}/fishpond/batch-adopt`, { method:'POST' })
export const getHotSearch = (gid, days = 7) =>                 // v1.16.2
  request(`/groups/${gid}/fishpond/hot-search?days=${days}`)
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

// v1.16.4: 鱼际关系 + 传奇任务 + 公告牌
export const getFishRelationships = (gid, wxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/relationships`)
export const getLegendaryQuestStatus = (gid, wxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/legendary-quest-status`)
export const doLegendaryQuest = (gid, wxid) =>
  request(`/groups/${gid}/fishpond/fish/${encodeURIComponent(wxid)}/legendary-quest`, { method: 'POST' })
export const getBulletin = (gid) =>
  request(`/groups/${gid}/fishpond/bulletin`)
export const setBulletin = (gid, content) =>
  request(`/groups/${gid}/fishpond/bulletin`, { method: 'POST', body: JSON.stringify({ content }) })

// --- 周报/月报 ---
export const getPeriods = (gid, type = 'weekly') =>
  request(`/groups/${gid}/periods?type=${type}`)
export const getWeeklyReport = (gid, periodKey) =>
  request(`/groups/${gid}/weekly/${periodKey}`)
export const getMonthlyReport = (gid, periodKey) =>
  request(`/groups/${gid}/monthly/${periodKey}`)
export const generateAllWeekly = async (gid, modelId = null) => {
  const params = new URLSearchParams()
  if (modelId) params.set('model_id', modelId)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${BASE}/groups/${gid}/weekly/generate-all${qs}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data
}
export const generateAllMonthly = async (gid, modelId = null) => {
  const params = new URLSearchParams()
  if (modelId) params.set('model_id', modelId)
  const qs = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(`${BASE}/groups/${gid}/monthly/generate-all${qs}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data
}
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
  request(`/settings/models/${id}/set-default`, { method: 'POST', body: '{}' })
export const checkModelHealth = (id) =>
  request(`/settings/models/${id}/health`)
export const getModelDefaults = () => request('/settings/defaults')

// ==================== 应用设置 v1.0.2 ====================
export const getAppSettings = () => request('/settings/app-settings')
export const updateAppSetting = (key, value) =>
  request('/settings/app-settings', {
    method: 'PUT', body: JSON.stringify({ key, value })
  })

// v1.16.5: 共享作弊模式检查
export async function isCheatModeEnabled() {
  try {
    const settings = await getAppSettings()
    if (!Array.isArray(settings)) return false
    const s = settings.find(s => s.key === 'pond_cheat_mode')
    return s ? s.value === 'true' : false
  } catch { return false }
}
export const updateAppSettingsBatch = (updates) =>
  request('/settings/app-settings/batch', {
    method: 'PUT', body: JSON.stringify({ updates })
  })

// ==================== 停用词 v1.0.2 ====================
export const getStopwords = () => apiGet('/settings/stopwords')
export const updateStopwords = (text) =>
  request('/settings/stopwords', {
    method: 'PUT', body: JSON.stringify({ text })
  })

// ==================== WeFlow 同步 ====================
export const getWeFlowSessions = (keyword = '') =>
  request(`/weflow/sessions?keyword=${encodeURIComponent(keyword)}&limit=200`)
export async function triggerWeFlowSync(group_id) {
  const res = await fetch(`${BASE}/weflow/sync/${group_id}`, { method: 'POST' })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '同步失败')
  return data.data
}
export const linkWeFlowGroup = (group_id, chatroom_id) =>
  request('/weflow/link', {
    method: 'POST', body: JSON.stringify({ group_id, chatroom_id })
  })
export const getWeFlowStatus = () => request('/weflow/status')
export const toggleWeFlowAutoSync = (group_id, enabled) =>
  request(`/weflow/auto-sync/${group_id}`, {
    method: 'PUT', body: JSON.stringify({ enabled })
  })
export const unlinkWeFlowGroup = (group_id) =>
  request(`/weflow/unlink/${group_id}`, { method: 'POST' })

// ==================== Personas v1.5.0 ====================
export const getPersonas = () => request('/personas')
export const getPersona = (id) => request(`/personas/${id}`)
export const createPersona = (name, member_ids) =>
  request('/personas', { method: 'POST', body: JSON.stringify({ name, member_ids }) })
export const deletePersona = (id) =>
  request(`/personas/${id}`, { method: 'DELETE' })
export const linkMembersToPersona = (persona_id, member_id) =>
  request(`/personas/${persona_id}/members`, { method: 'POST', body: JSON.stringify({ member_id }) })
export const unlinkMemberFromPersona = (persona_id, member_id) =>
  request(`/personas/${persona_id}/members/${member_id}`, { method: 'DELETE' })
export const manualLinkMembers = (member_id_a, member_id_b) =>
  request('/personas/link', { method: 'POST', body: JSON.stringify({ member_id_a, member_id_b }) })
export const autoLinkPersonas = () =>
  request('/personas/auto-link', { method: 'POST' })
export const getCrossGroupWxids = () => request('/personas/cross-group/wxids')
export const getCrossGroupDetail = (wxid) => request(`/personas/cross-group/${wxid}`)
// v1.5.2: 全面画像
export const analyzeComprehensivePortrait = async (personaId, modelId = null) => {
  const params = new URLSearchParams()
  const body = modelId ? { model_id: modelId } : {}
  const res = await fetch(`${BASE}/personas/${personaId}/comprehensive`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '生成失败')
  return data.data  // { task_id, status }
}

// ==================== Prompts v1.5.4 ====================
export const getPrompts = (analysisType = '') =>
  request(`/settings/prompts${analysisType ? `?analysis_type=${encodeURIComponent(analysisType)}` : ''}`)
export const createPrompt = (name, analysis_type, system_prompt, is_default = false) =>
  request('/settings/prompts', { method: 'POST', body: JSON.stringify({ name, analysis_type, system_prompt, is_default }) })
export const updatePrompt = (id, updates) =>
  request(`/settings/prompts/${id}`, { method: 'PUT', body: JSON.stringify(updates) })
export const deletePrompt = (id) =>
  request(`/settings/prompts/${id}`, { method: 'DELETE' })
export const setDefaultPrompt = (id) =>
  request(`/settings/prompts/${id}/default`, { method: 'PUT', body: '{}' })
export const getDefaultPrompt = (analysisType) =>
  request(`/settings/prompts/default?analysis_type=${encodeURIComponent(analysisType)}`)

// ==================== 事件探测 v1.18.0 ====================

export async function detectEvents(gid, dateStart, dateEnd) {
  const res = await fetch(`${BASE}/groups/${gid}/events/detect`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date_start: dateStart, date_end: dateEnd }),
  })
  const data = await res.json()
  if (!res.ok || data.code !== 200) throw new Error(data.detail || data.message || '请求失败')
  return data.data  // { task_id, status, date_start, date_end }
}

export function getEvents(gid, params = {}) {
  const qs = new URLSearchParams()
  if (params.type) qs.set('type', params.type)
  if (params.date_from) qs.set('date_from', params.date_from)
  if (params.date_to) qs.set('date_to', params.date_to)
  const query = qs.toString() ? `?${qs.toString()}` : ''
  return request(`/groups/${gid}/events${query}`)
}

export function getEventDetail(gid, eventId) {
  return request(`/groups/${gid}/events/${eventId}`)
}
