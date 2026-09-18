import { createRouter, createWebHashHistory } from 'vue-router'

// 用 hash 模式：Flask 把构建产物挂在 /spa/ 子路径下，hash 模式无需服务端回退规则，
// 直接双击 dist/index.html 也能跑（离线兜底）。
const routes = [
  { path: '/', redirect: '/overview' },
  { path: '/overview', name: 'overview', component: () => import('./views/OverviewView.vue'), meta: { title: '数据总览' } },
  { path: '/analytics', name: 'analytics', component: () => import('./views/AnalyticsView.vue'), meta: { title: '医疗资源分析' } },
  { path: '/institutions', name: 'institutions', component: () => import('./views/InstitutionsView.vue'), meta: { title: '机构查询' } },
  { path: '/filter', name: 'filter', component: () => import('./views/FilterView.vue'), meta: { title: '智能筛选' } },
  { path: '/integration', name: 'integration', component: () => import('./views/IntegrationView.vue'), meta: { title: '数据整合' } },
  { path: '/quality', name: 'quality', component: () => import('./views/QualityView.vue'), meta: { title: '数据质量' } },
  { path: '/about', name: 'about', component: () => import('./views/AboutView.vue'), meta: { title: '系统说明' } }
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})
