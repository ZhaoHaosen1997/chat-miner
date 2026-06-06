import { createApp } from 'vue'
import { createRouter, createWebHashHistory } from 'vue-router'
import App from './App.vue'
import './style.css'

import Dashboard from './views/Dashboard.vue'
import DailyReport from './views/DailyReport.vue'
import Portraits from './views/Portraits.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/report/:date', component: DailyReport, props: true },
  { path: '/portraits', component: Portraits },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

createApp(App).use(router).mount('#app')
