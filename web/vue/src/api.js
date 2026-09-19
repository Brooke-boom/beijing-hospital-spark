import axios from 'axios'

// 前后端分离的唯一通道：前端不直连数据库，全部数据经 Flask 的 /api/* 获取。
// Flask 默认 5001 端口（macOS 5000 被 AirPlay 占用）；开发期由 Vite 代理，生产由 Flask 同源提供。
const http = axios.create({ baseURL: '/api', timeout: 30000 })

http.interceptors.response.use(
  (r) => r.data,
  (e) => {
    const msg = e?.response?.data?.error || e?.message || '请求失败'
    return Promise.reject(new Error(msg))
  }
)

export const api = {
  health: () => http.get('/health'),
  // 筛选主接口：q/district/level/category/dept/net/sort/page/page_size/lng/lat
  institutions: (params) => http.get('/institutions', { params }),
  filters: () => http.get('/meta/filters'),
  districts: () => http.get('/overview/districts'),
  // 等级分布：scope=graded 只统计应参评机构（默认），all 含"不适用医院分级"桶
  levels: (scope) => http.get('/overview/levels', { params: scope ? { scope } : {} }),
  depts: (limit) => http.get('/overview/depts', { params: limit ? { limit } : {} }),
  specialty: () => http.get('/specialty'),
  specialtyGroups: () => http.get('/specialty/groups'),
  detail: (id) => http.get(`/inst/${encodeURIComponent(id)}/detail`),
  compare: (ids) => http.get('/inst/compare', { params: { ids: ids.join(',') } }),
  triage: (payload) => http.post('/triage', payload),
  // ---- 就医决策主线：生成方案 + 方案留痕（系统区别于看板的关键能力）----
  plan: (payload) => http.post('/plan', payload),
  planSave: (payload) => http.post('/plans', payload),
  planList: () => http.get('/plans'),
  planGet: (id) => http.get(`/plans/${encodeURIComponent(id)}`),
  planDelete: (id) => http.delete(`/plans/${encodeURIComponent(id)}`),
  geocode: (address) => http.get('/geocode', { params: { address } }),
  about: () => http.get('/about'),
  adminStats: () => http.get('/admin/stats'),
  // 行为埋点：失败不影响主流程，静默吞掉
  track: (ev, k1, k2, n) => http.post('/track', { ev, k1, k2, n }).catch(() => {})
}

export default api
