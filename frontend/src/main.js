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

const routes = [
  { path: '/', component: Dashboard },
  { path: '/report/:date', component: DailyReport, props: true },
  { path: '/portraits', component: Portraits },
  { path: '/portrait/:memberId', component: PortraitDetail, props: true },
  { path: '/weekly/:weekId', component: WeeklyReport, props: true },
  { path: '/monthly/:monthId', component: MonthlyReport, props: true },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

createApp(App).use(router).mount('#app')
