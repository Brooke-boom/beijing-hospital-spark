import { defineStore } from 'pinia'
import api from './api'

// 默认基准点：天安门（后端未收到 lng/lat 时也用这个，前后端口径一致）
export const DEFAULT_BASE = { name: '天安门', lng: 116.397428, lat: 39.90923 }

const EMPTY_QUERY = {
  q: '', district: '', level: '', category: '', dept: '', net: '',
  sort: 'score', page: 1, pageSize: 20
}

export const useDataStore = defineStore('data', {
  state: () => ({
    loaded: false,
    loading: false,
    error: '',
    health: null,
    items: [],
    total: 0,
    query: { ...EMPTY_QUERY },
    meta: { districts: [], levels: [], categories: [], depts: [], nets: [] },
    // 总览/分析页数据（来自 /api/overview/*、/api/specialty/groups、/api/about）
    overview: {
      districts: [],     // [{district, inst_count, level_3_count, ...}]
      levels: [],        // 仅应参评机构（不含"不适用医院分级"）
      levelsAll: [],     // 全量口径（含"不适用"桶）
      depts: [],         // [{dept_name, hospital_count, key_specialty_count}]
      specialtyGroups: [],
      about: null
    },
    netSize: {},           // { net 值: 命中机构数 }，用于协作网络规模图
    netSizeLoaded: false,
    base: null,              // 已设定的基准点（null = 未定位，距离按天安门算并标注）
    picks: [],               // 对比选择（机构 id）
    theme: 'dark',
    drawer: { open: false, id: null, data: null, loading: false },
    compare: { open: false, data: null, loading: false },
    toast: ''
  }),

  getters: {
    // 当前生效的排序方向（后端已内建方向，这里仅用于 UI 提示）
    sortDir: (s) => (['distance', 'score', 'name'].includes(s.query.sort) ? 'asc' : 'desc'),

    // 条件 chips：UI 只展示"用户真的设了条件"的那些
    chips(s) {
      const m = s.meta
      const nameOf = (list, key, val) => (list.find((x) => String(x[key]) === String(val)) || {})[key] || val
      const out = []
      if (s.query.district) out.push({ key: 'district', label: '区域', value: s.query.district })
      if (s.query.level) out.push({ key: 'level', label: '等级', value: s.query.level })
      if (s.query.category) out.push({ key: 'category', label: '类型', value: s.query.category })
      if (s.query.dept) out.push({ key: 'dept', label: '科室', value: s.query.dept })
      if (s.query.net) out.push({ key: 'net', label: '协作网络', value: nameOf(m.nets, 'value', s.query.net) })
      if (s.query.q) out.push({ key: 'q', label: '关键词', value: s.query.q })
      return out
    },

    hasConditions: (s) => !!(s.query.q || s.query.district || s.query.level ||
      s.query.category || s.query.dept || s.query.net),

    totalPages: (s) => Math.max(1, Math.ceil(s.total / s.query.pageSize))
  },

  actions: {
    async boot() {
      if (this.loaded) return
      this.loading = true
      this.error = ''
      try {
        const [health, filters, districts, levels] = await Promise.all([
          api.health(), api.filters(), api.districts(), api.levels()
        ])
        this.health = health
        this.meta.categories = filters.categories || []
        this.meta.depts = filters.depts || []
        this.meta.nets = filters.nets || [
          { value: 'ped_core', label: '儿科医联体·核心' },
          { value: 'ped_member', label: '儿科医联体·成员' },
          { value: 'stroke', label: '卒中中心' },
          { value: 'neonatal', label: '危重新生儿救治中心' },
          { value: 'maternal', label: '危重孕产妇救治中心' }
        ]
        this.meta.districts = (districts.items || districts.districts || districts || [])
          .map((d) => d.district).filter(Boolean)
        this.meta.levels = (levels.items || levels.levels || levels || [])
          .map((l) => l.level || l.level_norm).filter(Boolean)
        this.loaded = true
        await this.fetchList()
        // 总览/分析页数据跟着启动一起拉，切页不白屏
        this.loadOverview()
      } catch (e) {
        this.error = e.message
      } finally {
        this.loading = false
      }
    },

    async fetchList() {
      this.loading = true
      this.error = ''
      try {
        const p = {
          q: this.query.q || undefined,
          district: this.query.district || undefined,
          level: this.query.level || undefined,
          category: this.query.category || undefined,
          dept: this.query.dept || undefined,
          net: this.query.net || undefined,
          sort: this.query.sort,
          page: this.query.page,
          page_size: this.query.pageSize
        }
        const b = this.base || DEFAULT_BASE
        p.lng = b.lng
        p.lat = b.lat
        const r = await api.institutions(p)
        this.items = r.items || []
        this.total = r.total || 0
      } catch (e) {
        this.error = e.message
        this.items = []
        this.total = 0
      } finally {
        this.loading = false
      }
    },

    // 总览/分析页数据：一次性拉齐，页面切换不再重复请求
    async loadOverview(force = false) {
      if (this.overview.about && !force) return
      try {
        const [districts, levels, levelsAll, depts, groups, about] = await Promise.all([
          api.districts(), api.levels('graded'), api.levels('all'),
          api.depts(30), api.specialtyGroups(), api.about()
        ])
        this.overview.districts = districts || []
        this.overview.levels = levels || []
        this.overview.levelsAll = levelsAll || []
        this.overview.depts = depts || []
        this.overview.specialtyGroups = groups || []
        this.overview.about = about || null
      } catch (e) {
        this.error = e.message
      }
      // 协作网络规模：复用筛选接口的 total，只取 1 条记录，代价极小且口径与列表一致
      try {
        const nets = this.meta.nets || []
        const rs = await Promise.all(nets.map((n) =>
          api.institutions({ net: n.value, sort: 'score', page: 1, page_size: 1 })))
        const map = {}
        nets.forEach((n, i) => { map[n.value] = (rs[i] && rs[i].total) || 0 })
        this.netSize = map
        this.netSizeLoaded = true
      } catch (e) { /* 网络规模是次要信息，失败不打断页面 */ }
    },

    // 改条件 → 回到第 1 页再查（与后端分页语义一致）
    async setQuery(patch, { keepPage = false } = {}) {
      Object.assign(this.query, patch)
      if (!keepPage) this.query.page = 1
      await this.fetchList()
    },

    async resetQuery() {
      this.query = { ...EMPTY_QUERY }
      this.picks = []
      await this.fetchList()
    },

    async clearCondition(key) {
      await this.setQuery({ [key]: '' })
    },

    async setBase(point) {
      this.base = point ? { name: point.name, lng: point.lng, lat: point.lat } : null
      await this.fetchList()
    },

    async gotoPage(page) {
      const p = Math.min(Math.max(1, page), this.totalPages)
      this.query.page = p
      await this.fetchList()
    },

    async setPageSize(n) {
      await this.setQuery({ pageSize: Number(n) })
    },

    // ---- 对比选择（2–4 家）----
    togglePick(id) {
      id = String(id)
      const i = this.picks.indexOf(id)
      if (i >= 0) this.picks.splice(i, 1)
      else if (this.picks.length < 4) this.picks.push(id)
      else this.notify('最多同时对比 4 家机构')
    },
    clearPicks() { this.picks = [] },

    async openCompare() {
      if (this.picks.length < 2) { this.notify('请先勾选 2 家以上机构'); return }
      this.compare.open = true
      this.compare.loading = true
      this.compare.data = null
      try {
        this.compare.data = await api.compare(this.picks)
      } catch (e) {
        this.compare.data = { error: e.message }
      } finally {
        this.compare.loading = false
      }
      api.track('compare', this.picks.join(','), '', this.picks.length)
    },
    closeCompare() { this.compare.open = false },

    // ---- 详情抽屉 ----
    async openDrawer(id) {
      this.drawer.open = true
      this.drawer.id = id
      this.drawer.data = null
      this.drawer.loading = true
      try {
        this.drawer.data = await api.detail(id)
      } catch (e) {
        this.drawer.data = { error: e.message }
      } finally {
        this.drawer.loading = false
      }
      api.track('detail', String(id), '', 0)
    },
    closeDrawer() { this.drawer.open = false },

    // ---- 主题 ----
    applyTheme(theme) {
      this.theme = theme
      document.documentElement.setAttribute('data-theme', theme)
      try { localStorage.setItem('spa_theme', theme) } catch (e) { /* 隐私模式下忽略 */ }
    },
    initTheme() {
      let t = 'dark'
      try { t = localStorage.getItem('spa_theme') || 'dark' } catch (e) { /* ignore */ }
      this.applyTheme(t)
    },
    toggleTheme() { this.applyTheme(this.theme === 'dark' ? 'light' : 'dark') },

    notify(msg) {
      this.toast = msg
      setTimeout(() => { if (this.toast === msg) this.toast = '' }, 2600)
    }
  }
})
