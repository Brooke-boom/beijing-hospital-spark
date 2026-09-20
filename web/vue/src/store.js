import { defineStore } from 'pinia'
import api from './api'

// 默认基准点：天安门（后端未收到 lng/lat 时也用这个，前后端口径一致）
export const DEFAULT_BASE = { name: '天安门', lng: 116.397428, lat: 39.90923 }

const EMPTY_QUERY = {
  q: '', district: '', level: '', category: '', dept: '', net: '',
  sort: 'score', page: 1, pageSize: 20
}

// 智能筛选页的初始条件。所有字段与后端 web/nlq.py 的条件 schema 一一对应，
// 前端不发明自己的字段名——否则"自然语言解析出来的条件"与"条件筛选 Tab 填的条件"
// 会变成两套东西，也就无法互相回填。
function blankNlqForm() {
  return { district: '', level: '', category: '', ownership: '', source: '', dept: '', kw: '' }
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
    // ---- 智能筛选主线：自然语言 → 条件 → 真实数据，一条链路走完 ----
    // 与「机构查询」的区别：那里是人逐项填条件；这里是规则引擎先读懂中文，
    // 再把解析结果作为**可删除、可重填的条件**交给用户确认，确认后才查数据。
    nlq: {
      mode: 'nl',              // nl = 自然语言通道，cond = 条件筛选通道
      q: '',                   // 用户输入的原句
      form: blankNlqForm(),    // 条件筛选通道的控件状态
      dimension: '',           // 非空 = 要"按某维度统计"而不是机构清单
      loading: false,
      error: '',
      result: null,            // /api/nlq/query 的完整返回（含 applied / summary / rows）
      page: 1,
      pageSize: 20,
      sort: 'score',
      lex: null,               // 词表（/api/nlq/lexicon）：维度标签、来源规则、边界文案
      lexLoaded: false,
      history: []              // 本次会话的查询留痕：演示时可回看
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

    // ---- 智能筛选派生数据 ----
    // 判定"这次结果是清单还是统计"只看后端返回的 intent，
    // 前端不根据用户输入的措辞去猜——口径必须与后端一致。
    nlqResult: (s) => s.nlq.result,
    nlqIsStats: (s) => !!(s.nlq.result && s.nlq.result.ok && s.nlq.result.intent === 'stats'),
    nlqIsFilter: (s) => !!(s.nlq.result && s.nlq.result.ok && s.nlq.result.intent === 'filter'),
    // 解析出的条件卡片：直接采用后端的 describe() 结果，前端不自己拼标签
    nlqChips: (s) => (s.nlq.result && s.nlq.result.applied) || [],
    // 命中的机构清单（仅清单意图有）
    nlqItems: (s) => (s.nlq.result && s.nlq.result.items) || [],
    // 统计结果行（仅统计意图有）
    nlqRows: (s) => (s.nlq.result && s.nlq.result.rows) || [],
    nlqTotal: (s) => (s.nlq.result && s.nlq.result.total) || 0
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

    // ================= 智能筛选：自然语言 → 条件 → 真实数据 =================
    // 与「机构查询」的动作区分开：这里的查询由"一句话"驱动，条件由后端解析产出，
    // 用户可以对解析结果做减法（删掉某个条件卡）或改写后重查。
    nlqSetForm(patch) {
      Object.assign(this.nlq.form, patch)
    },

    nlqSetMode(mode) {
      this.nlq.mode = mode === 'cond' ? 'cond' : 'nl'
    },

    // 词表：维度标签、来源规则、边界文案都来自后端，前端不复制一份。
    // 已经取到就不再请求（切页不会重复打接口）。
    async nlqLoadLex() {
      if (this.nlq.lexLoaded) return this.nlq.lex
      try {
        this.nlq.lex = await api.nlqLexicon()
        this.nlq.lexLoaded = true
      } catch (e) { /* 词表只影响文案与下拉项，失败时页面仍可用 */ }
      return this.nlq.lex
    },

    // 自然语言通道：原句交给 /api/nlq/query，后端一步完成"解析 + 查数据"。
    // text 只接受字符串：写成 @click="nlqRun" 时 Vue 会把点击事件传进来，
    // 那样 `event.trim()` 会直接抛错——所以这里显式判类型，而不是信任调用方。
    async nlqRun(text) {
      const q = (typeof text === 'string' ? text : (this.nlq.q || '')).trim()
      this.nlq.q = q
      if (!q) { this.notify('请先描述您想查找的机构条件'); return }
      await this._nlqExec({ q })
    },

    // 条件通道：把控件值整理成后端条件 schema 后提交。
    // dimension 非空 → 要统计；否则 → 要清单。两者走同一个接口，口径统一。
    async nlqRunConditions() {
      const f = this.nlq.form
      const conditions = {}
      if (f.district) conditions.district = [f.district]
      if (f.level) conditions.level = [f.level]
      if (f.category) conditions.category = [f.category]
      if (f.ownership) conditions.ownership = [f.ownership]
      if (f.source) conditions.source = [f.source]
      if (f.dept) conditions.dept = f.dept
      if (f.kw) conditions.kw = f.kw
      if (this.nlq.dimension) conditions.dimension = this.nlq.dimension
      conditions._sort = this.nlq.sort
      if (!Object.keys(conditions).filter((k) => k !== '_sort').length) {
        this.notify('请至少设置一个筛选条件，或选择统计维度')
        return
      }
      await this._nlqExec({ conditions })
    },

    // 删掉一个条件卡后重查：以后端返回的 conditions 为准做减法，
    // 不用前端的表单反推——避免"界面显示的条件"和"实际查询的条件"两套口径。
    async nlqDropChip(key) {
      const cur = (this.nlq.result && this.nlq.result.conditions) || {}
      const next = { ...cur }
      delete next[key]
      const rest = Object.keys(next).filter((k) => k !== '_sort' && k !== 'dimension')
      if (!rest.length) { this.nlqReset(); return }
      await this._nlqExec({ conditions: next })
    },

    // 翻页：后端把分页参数定义在**条件对象内**（conditions._page / _page_size），
    // 所以这里以后端回传的 conditions 为准再查一次，而不是把页码塞在请求体顶层。
    // 一句话查询的首次结果同样带 conditions，因此清单页翻页无需重复解析中文。
    async nlqPage(page) {
      const r = this.nlq.result
      if (!r || !r.ok || r.intent !== 'filter') return
      const total = Math.max(1, Math.ceil((r.total || 0) / this.nlq.pageSize))
      const p = Math.min(Math.max(1, page), total)
      const cond = { ...(r.conditions || {}), _page: p, _page_size: this.nlq.pageSize }
      await this._nlqExec({ conditions: cond })
    },

    // 一次查询的公共出口：负责 loading / error / 留痕 与结果落库。
    // 两条通道在这里合流，保证"自然语言"与"手填条件"拿到的是同一种数据结构。
    async _nlqExec({ q, conditions }) {
      this.nlq.loading = true
      this.nlq.error = ''
      try {
        const body = {}
        if (q) {
          body.q = q
        } else {
          const c = { ...conditions }
          if (!c._page) c._page = 1
          c._page_size = this.nlq.pageSize
          body.conditions = c
        }
        const r = await api.nlqQuery(body)
        this.nlq.result = r
        this.nlq.page = r.page || 1
        if (r.ok) {
          const title = r.intent === 'stats'
            ? '按' + (r.dimension_label || '维度') + '统计'
            : ((r.applied || []).map((c) => c.text).join(' · ') || '全部机构')
          this.nlq.history.unshift({
            title, at: new Date().toLocaleTimeString('zh-CN'), n: r.total || 0,
            q, conditions: q ? null : body.conditions
          })
          this.nlq.history = this.nlq.history.slice(0, 8)
          api.track('nlq', q || title, r.intent, r.total || 0)
        }
      } catch (e) {
        this.nlq.error = e.message
        this.nlq.result = null
      } finally {
        this.nlq.loading = false
      }
    },

    // 查过的句子可以一键重放：演示时不必重新敲一遍，也保证演示条件与记录一致
    async nlqReplay(h) {
      if (h.q) await this._nlqExec({ q: h.q })
      else if (h.conditions) { this.nlq.dimension = h.conditions.dimension || ''; await this._nlqExec({ conditions: h.conditions }) }
    },

    // 回到起始页：清空结果与输入，保留词表（省一次请求）
    nlqReset() {
      this.nlq.result = null
      this.nlq.q = ''
      this.nlq.error = ''
      this.nlq.page = 1
      this.nlq.dimension = ''
      Object.assign(this.nlq.form, blankNlqForm())
    },

    notify(msg) {
      this.toast = msg
      setTimeout(() => { if (this.toast === msg) this.toast = '' }, 2600)
    }
  }
})
