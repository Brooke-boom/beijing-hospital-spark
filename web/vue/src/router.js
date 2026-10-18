import { createRouter, createWebHashHistory } from 'vue-router'
import { LEGACY_REDIRECT } from './hubs'

// 用 hash 模式：Flask 把构建产物挂在 /spa/ 子路径下，hash 模式无需服务端回退规则，
// 直接双击 dist/index.html 也能跑（离线兜底）。
const routes = [
  // 默认入口 = 机构查询。智能筛选已改为常驻悬浮球（SmartFilterDock），不再占独立路由——
  // 查询是动作不是地点，任何查阅页都能呼出。
  { path: '/', redirect: '/find' },
  // 旧深链接兜底：/filter 曾是智能筛选独立页，统一落到机构查询
  { path: '/filter', redirect: '/find' },

  // 查阅支撑页：一个页面回答一个问题，页内用子标签切换看法
  { path: '/find', name: 'find', component: () => import('./views/HubView.vue'),
    meta: { hub: 'find', title: '找机构' } },
  { path: '/profile', name: 'profile', component: () => import('./views/HubView.vue'),
    meta: { hub: 'profile', title: '资源画像' } },
  { path: '/govern', name: 'govern', component: () => import('./views/HubView.vue'),
    meta: { hub: 'govern', title: '数据治理' } },
  { path: '/about', name: 'about', component: () => import('./views/AboutView.vue'),
    meta: { title: '系统说明' } }
]

// 旧路径永久跳转到新的支撑页，之前分享过的深链接不会失效
for (const [old, target] of Object.entries(LEGACY_REDIRECT)) {
  routes.push({ path: old, redirect: target })
}

// 未匹配的地址回主线，避免出现空白页
routes.push({ path: '/:pathMatch(.*)*', redirect: '/filter' })

export default createRouter({
  history: createWebHashHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})
