import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

import Dashboard from './views/Dashboard.vue'
import DailyReport from './views/DailyReport.vue'
import Portraits from './views/Portraits.vue'
import PortraitDetail from './views/PortraitDetail.vue'
import WeeklyReport from './views/WeeklyReport.vue'
import MonthlyReport from './views/MonthlyReport.vue'
import FishPond from './views/FishPond.vue'
import FishDailyReport from './views/FishDailyReport.vue'
import AnnualReport from './views/AnnualReport.vue'
import Settings from './views/Settings.vue'
import TaskHistory from './views/TaskHistory.vue'
import ComprehensivePortrait from './views/ComprehensivePortrait.vue'
import EventDetail from './views/EventDetail.vue'
import MemeEncyclopedia from './views/MemeEncyclopedia.vue'
import AiCallLogs from './views/AiCallLogs.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/report/:date', component: DailyReport, props: true },
  { path: '/portraits', component: Portraits },
  { path: '/portrait/:memberId', component: PortraitDetail, props: true },
  { path: '/weekly/:weekId', component: WeeklyReport, props: true },
  { path: '/monthly/:monthId', component: MonthlyReport, props: true },
  { path: '/fishpond', component: FishPond },
  { path: '/fish-report/:date', component: FishDailyReport, props: true },
  { path: '/annual/:yearId', component: AnnualReport, props: true },
  { path: '/settings', component: Settings },
  { path: '/tasks', component: TaskHistory },
  { path: '/event/:eventId', component: EventDetail, props: true },
  { path: '/events', redirect: '/' },
  { path: '/memes', component: MemeEncyclopedia },
  { path: '/ai-logs', component: AiCallLogs },
  { path: '/comprehensive/:personaId', component: ComprehensivePortrait, props: true },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

const app = createApp(App)
app.use(router)

// v0.13.3: 全局 Vue 错误处理，桥接到 ErrorModal
app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue Error]', err, info)
  // 尝试通过 DOM 查找 ErrorModal 实例触发显示
  const detail = err instanceof Error ? (err.stack || '').split('\n').slice(0, 3).join('\n') : ''
  window.dispatchEvent(new CustomEvent('app-error', {
    detail: { title: '前端异常', message: err.message || String(err), detail, context: info }
  }))
}

app.mount('#app')
