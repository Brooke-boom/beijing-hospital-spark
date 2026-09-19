import { defineStore } from 'pinia'
import api from './api'

// 默认基准点：天安门（后端未收到 lng/lat 时也用这个，前后端口径一致）
export const DEFAULT_BASE = { name: '天安门', lng: 116.397428, lat: 39.90923 }

const EMPTY_QUERY = {
  q: '', district: '', level: '', category: '', dept: '', net: '',
  sort: 'score', page: 1, pageSize: 20
}

// 就医决策表单初值。planReset() 用它做「回到起始页」的原地还原：
// 必须 Object.assign 到同一个对象上，不能整体替换 —— PlanView 里 `const f = store.plan.form`
// 持有的是引用，换对象会让已挂载页面的 v-model 全部失联。
function blankPlanForm() {
  return {
    q: '', dept: '', extra: '', prefer: 'specialty',
    max_km: 0, public_only: false, level: '', district: ''
  }
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
    toast: '',
    // ---- 就医决策主线：一条从需求到方案的任务流，不是展示页 ----
    plan: {
      step: 1,                 // 1 说需求 → 2 看候选 → 3 做比较 → 4 拿方案
      form: blankPlanForm(),
      result: null,            // /api/plan 返回的完整数据（分诊结论 + 候选 + 依据）
      loading: false,
      error: '',
      primaryId: null,         // 用户标记的主选机构
      keptIds: [],             // 圈定的备选（做比较用）
      history: [],             // 历史方案（留痕，可回溯）
      historyLoaded: false,
      savedId: null            // 本次已保存的方案 id
    }
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

    totalPages: (s) => Math.max(1, Math.ceil(s.total / s.query.pageSize)),

    // ---- 就医决策派生数据 ----
    planCandidates: (s) => (s.plan.result && s.plan.result.candidates) || [],
    planPrimary(s) {
      const cs = (s.plan.result && s.plan.result.candidates) || []
      return cs.find((c) => String(c.id) === String(s.plan.primaryId)) || cs[0] || null
    },
    planKept(s) {
      const cs = (s.plan.result && s.plan.result.candidates) || []
      return s.plan.keptIds
        .map((id) => cs.find((c) => String(c.id) === String(id)))
        .filter(Boolean)
    },
    planTriage: (s) => (s.plan.result && s.plan.result.triage) || null,
    planReady: (s) => !!(s.plan.result && s.plan.result.ok)
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

    // ================= 就医决策：一条从需求到方案的任务流 =================
    // 与「查询」的区别在于有任务态：草稿 → 候选 → 定稿 → 产出物，可回退、可留痕。
    planSetForm(patch) {
      Object.assign(this.plan.form, patch)
    },

    async planRun() {
      const f = this.plan.form
      if (!f.q && !f.dept) { this.notify('请先描述症状或选择科室'); return }
      this.plan.loading = true
      this.plan.error = ''
      const b = this.base || DEFAULT_BASE
      try {
        const r = await api.plan({
          q: f.q || undefined,
          dept: f.dept || undefined,
          extra: f.extra || undefined,
          district: f.district || undefined,
          prefer: f.prefer,
          max_km: Number(f.max_km) || 0,
          public_only: !!f.public_only,
          level: f.level || undefined,
          top_n: 12,
          lng: b.lng, lat: b.lat, base_name: b.name
        })
        this.plan.result = r
        this.plan.savedId = null
        if (r.ok) {
          this.plan.step = 2
          const cs = r.candidates || []
          this.plan.primaryId = cs.length ? cs[0].id : null
          this.plan.keptIds = cs.slice(0, 3).map((c) => c.id)
          const d0 = ((r.triage || {}).target_depts || [])[0]
          api.track('plan', f.q || f.dept || '', (d0 && d0.name) || '', cs.length)
        } else {
          this.plan.step = 1
        }
      } catch (e) {
        this.plan.error = e.message
      } finally {
        this.plan.loading = false
      }
    },

    planGoto(step) {
      if (step >= 1 && step <= 4) this.plan.step = step
    },

    planToggleKeep(id) {
      id = String(id)
      const i = this.plan.keptIds.indexOf(id)
      if (i >= 0) this.plan.keptIds.splice(i, 1)
      else if (this.plan.keptIds.length < 4) this.plan.keptIds.push(id)
      else this.notify('最多同时比较 4 家机构')
    },

    planSetPrimary(id) {
      this.plan.primaryId = String(id)
      const i = this.plan.keptIds.indexOf(String(id))
      if (i >= 0) this.plan.keptIds.splice(i, 1)
      if (this.plan.keptIds.length >= 4) this.plan.keptIds.pop()
      this.plan.keptIds.unshift(String(id))
    },

    planReset() {
      this.plan.step = 1
      this.plan.result = null
      this.plan.error = ''
      this.plan.primaryId = null
      this.plan.keptIds = []
      this.plan.savedId = null
      // 起始页 = 干净的输入区。原地还原，保住 PlanView 里对 form 的引用。
      Object.assign(this.plan.form, blankPlanForm())
    },

    // 是否有"进行中的决策"（用于决定要不要显示"重新开始"入口 / 是否提示）
    planBusy() {
      const p = this.plan
      return p.step > 1 || !!p.result || !!p.error
    },

    // 回到起始页：侧栏「就医决策」与页内「重新开始」共用同一个入口语义。
    // 已经在起始页时静默跳过，不弹提示、不抖动。
    planHome() {
      if (!this.planBusy()) return
      this.planReset()
      this.notify('已回到起始页')
    },

    async planSave() {
      if (!this.planReady) { this.notify('请先生成方案'); return }
      try {
        const r = await api.planSave({
          payload: this.plan.result,
          primary_id: this.plan.primaryId
        })
        if (r.ok) {
          this.plan.savedId = r.id
          this.notify('已保存到「我的方案」')
          await this.planLoadHistory(true)
        } else {
          this.notify(r.hint || '保存失败')
        }
      } catch (e) {
        this.notify('保存失败：' + e.message)
      }
    },

    async planLoadHistory(force = false) {
      if (this.plan.historyLoaded && !force) return
      try {
        const r = await api.planList()
        this.plan.history = r.items || []
        this.plan.historyLoaded = true
      } catch (e) { /* 历史是次要信息，失败不影响主流程 */ }
    },

    async planOpenSaved(id) {
      try {
        const r = await api.planGet(id)
        const pl = r.plan && r.plan.payload
        if (r.ok && pl && pl.ok) {
          this.plan.result = pl
          this.plan.savedId = r.plan.id
          const cs = pl.candidates || []
          this.plan.primaryId = r.plan.chosen_id || (cs.length ? cs[0].id : null)
          this.plan.keptIds = cs.slice(0, 3).map((c) => c.id)
          this.plan.step = 4
        } else {
          this.notify('该方案数据已失效')
        }
      } catch (e) {
        this.notify('打开失败：' + e.message)
      }
    },

    async planDeleteSaved(id) {
      try {
        await api.planDelete(id)
        this.plan.history = this.plan.history.filter((x) => x.id !== id)
        if (this.plan.savedId === id) this.plan.savedId = null
        this.notify('已删除')
      } catch (e) {
        this.notify('删除失败：' + e.message)
      }
    },

    notify(msg) {
      this.toast = msg
      setTimeout(() => { if (this.toast === msg) this.toast = '' }, 2600)
    }
  }
})
