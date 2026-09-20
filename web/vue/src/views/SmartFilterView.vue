<template>
  <div class="page">
    <!-- ===================== ① 输入区：两个通道，一份条件 schema ===================== -->
    <div class="panel">
      <h3>
        智能筛选 <span class="tag">自然语言 → 结构化条件 → 真实数据</span>
        <button v-if="hasResult" class="btn ghost sm" style="margin-left:auto" type="button"
                @click="store.nlqReset()">重新开始</button>
      </h3>
      <div class="muted">
        用中文描述你想找的机构，系统把这句话翻译成结构化条件，再按条件去数据库查真实数据。
        解析出的条件可以逐条删除后重查——<b>看到的就是实际执行的</b>。
      </div>

      <div class="nlqtabs">
        <button type="button" :class="{ on: mode === 'nl' }" @click="store.nlqSetMode('nl')">
          用一句话描述
        </button>
        <button type="button" :class="{ on: mode === 'cond' }" @click="store.nlqSetMode('cond')">
          逐项设置条件
        </button>
        <span class="nlqscope">不提供诊断 / 用药建议 / 挂号推荐</span>
      </div>

      <!-- 通道一：自然语言 -->
      <template v-if="mode === 'nl'">
        <div class="nlqask">
          <div class="field">
            <label>机构筛选需求（Ctrl / ⌘ + Enter 直接提交）</label>
            <textarea v-model="q" rows="2"
                      placeholder="例如：朝阳区和海淀区的三级公立医院，按距离从近到远"
                      @keydown.ctrl.enter="submit" @keydown.meta.enter="submit"></textarea>
          </div>
          <button class="btn primary" type="button" :disabled="store.nlq.loading" @click="submit()">
            {{ store.nlq.loading ? '查询中…' : '开始筛选' }}
          </button>
        </div>
        <div class="nlqex">
          <span class="muted">试试这些：</span>
          <button v-for="e in EXAMPLES" :key="e" class="ex" type="button" @click="submit(e)">{{ e }}</button>
        </div>
      </template>

      <!-- 通道二：手填条件（与自然语言解析出的条件同源，可互相回填） -->
      <template v-else>
        <div class="row" style="margin-top:14px">
          <div class="field" style="flex:1 1 150px">
            <label>行政区</label>
            <select class="ctl" v-model="form.district">
              <option value="">全部 16 区</option>
              <option v-for="d in districts" :key="d" :value="d">{{ d }}</option>
            </select>
          </div>
          <div class="field" style="flex:0 1 120px">
            <label>医院等级</label>
            <select class="ctl" v-model="form.level">
              <option value="">全部等级</option>
              <option v-for="l in levels" :key="l" :value="l">{{ l }}</option>
            </select>
          </div>
          <div class="field" style="flex:1 1 150px">
            <label>机构类型</label>
            <select class="ctl" v-model="form.category">
              <option value="">全部类型</option>
              <option v-for="c in categories" :key="c" :value="c">{{ c }}</option>
            </select>
          </div>
          <div class="field" style="flex:0 1 130px">
            <label>所有制</label>
            <select class="ctl" v-model="form.ownership">
              <option value="">全部</option>
              <option v-for="o in ownerships" :key="o" :value="o">{{ o }}</option>
            </select>
          </div>
          <div class="field" style="flex:1 1 170px">
            <label>数据来源</label>
            <select class="ctl" v-model="form.source">
              <option value="">全部来源</option>
              <option v-for="r in sourceRules" :key="r.key" :value="r.key">{{ r.label }}</option>
            </select>
          </div>
        </div>

        <div class="row" style="margin-top:12px">
          <div class="field" style="flex:1 1 200px">
            <label>科室（取自机构实际开展科室）</label>
            <select class="ctl" v-model="form.dept">
              <option value="">全部科室</option>
              <option v-for="d in depts" :key="d.dept_name" :value="d.dept_name">
                {{ d.dept_name }}（{{ d.hospital_count }}）
              </option>
            </select>
          </div>
          <div class="field" style="flex:1 1 160px">
            <label>机构名称关键词</label>
            <input class="ctl" type="text" v-model.trim="form.kw" placeholder="如：协和 / 儿童" />
          </div>
          <div class="field" style="flex:1 1 170px">
            <label>统计维度（选了就是统计，不是清单）</label>
            <select class="ctl" v-model="store.nlq.dimension">
              <option value="">不统计（出机构清单）</option>
              <option v-for="(v, k) in dimLabel" :key="k" :value="k">按{{ v }}统计</option>
            </select>
          </div>
          <div class="field" style="flex:0 1 160px">
            <label>排序</label>
            <select class="ctl" v-model="store.nlq.sort">
              <option v-for="(v, k) in sortLabel" :key="k" :value="k">{{ v }}</option>
            </select>
          </div>
        </div>

        <div class="row" style="margin-top:14px">
          <button class="btn primary" type="button" :disabled="store.nlq.loading" @click="submitCond">
            {{ store.nlq.loading ? '查询中…' : '按条件查询' }}
          </button>
          <button class="btn ghost" type="button" @click="clearCond">清空条件</button>
          <button class="btn ghost" type="button" @click="store.nlqSetMode('nl')">改用一句话</button>
        </div>
      </template>

      <!-- 边界声明：写死在页面上，不靠 AI 自律 -->
      <div class="nlqmsg info" style="margin-top:14px">
        <strong>边界：</strong>系统只处理<b>机构资源数据</b>，不回答疾病、症状、用药、挂号之类的问题——
        数据集里没有患者诊疗数据。所有机构名称与统计数字都来自数据库查询，不生成、不补造。
      </div>

      <div v-if="store.nlq.error" class="nlqmsg refuse">
        <strong>请求失败：</strong>{{ store.nlq.error }}
      </div>
    </div>

    <!-- ===================== ② 系统理解到的条件（可增删） ===================== -->
    <div v-if="res" class="panel">
      <h3>
        系统理解到的条件 <span class="tag">{{ chips.length }} 条</span>
        <span class="muted" style="margin-left:auto">
          解析引擎：{{ engineLabel }} · 结果类型：{{ intentLabel }}
        </span>
      </h3>
      <div class="chips">
        <span v-if="!chips.length" class="muted">未识别出明确的筛选条件（下方为系统说明）</span>
        <span v-for="c in chips" :key="c.key" class="chip">
          {{ c.label }}：{{ c.text }}
          <button type="button" title="移除该条件并重新查询" @click="store.nlqDropChip(c.key)">×</button>
        </span>
      </div>
      <div v-if="unmatched.length" class="nlqmsg info">
        <strong>未识别的片段：</strong>{{ unmatched.join('、') }}。
        系统不会猜这些词的含义——请改用条件式表达（行政区 / 类型 / 等级 / 所有制 / 来源 / 科室）。
      </div>
      <div v-if="notice" class="nlqmsg info">{{ notice }}</div>
      <div v-if="res.summary" class="nlqmsg info">{{ res.summary }}</div>
    </div>

    <!-- ===================== ③ 拒答：医疗类输入 ===================== -->
    <div v-if="refusal" class="panel">
      <h3>这类问题本系统不回答 <span class="tag">能力边界</span></h3>
      <div class="nlqmsg refuse" style="white-space:pre-line">{{ refusal }}</div>
      <div class="muted" style="margin-top:10px">
        可以改成描述机构条件，例如：朝阳区三级公立医院 · 开设骨科的机构 · 医保定点名单中的社区卫生服务中心。
      </div>
    </div>

    <!-- ===================== ④ 统计意图：图表 + 明细 ===================== -->
    <template v-if="isStats">
      <div class="kpis k4">
        <div class="card hero">
          <div class="l">统计机构总数</div>
          <div class="v">{{ fmt(res.total) }}</div>
          <div class="s">{{ res.summary ? '本次统计口径下的机构合计' : '' }}</div>
        </div>
        <div class="card k2">
          <div class="l">覆盖维度值</div>
          <div class="v">{{ res.rows.length }}</div>
          <div class="s">按「{{ res.dimension_label }}」分组的组数</div>
        </div>
        <div class="card k2">
          <div class="l">最多的一组</div>
          <div class="v">{{ topGroup.n }}<span class="muted" style="font-size:12px"> 家</span></div>
          <div class="s">{{ topGroup.name || '—' }}</div>
        </div>
        <div class="card k2">
          <div class="l">最少的一组</div>
          <div class="v">{{ bottomGroup.n }}<span class="muted" style="font-size:12px"> 家</span></div>
          <div class="s">{{ bottomGroup.name || '—' }}</div>
        </div>
      </div>

      <div class="split">
        <div class="panel">
          <h3>按「{{ res.dimension_label }}」分布 <span class="tag">{{ chartLabel }}</span></h3>
          <div class="chartbox tall" ref="elStat"></div>
        </div>
        <div class="panel">
          <h3>统计明细 <span class="tag">数字来自 SQL 分组计数</span></h3>
          <div class="listwrap" style="max-height:420px">
            <table class="tbl">
              <thead>
                <tr>
                  <th>{{ res.dimension_label }}</th>
                  <th style="width:88px">机构数</th>
                  <th style="width:110px">占比</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="r in res.rows" :key="r.name">
                  <td>{{ r.name || '未标注' }}</td>
                  <td>{{ fmt(r.cnt) }}</td>
                  <td class="muted">{{ pct(r.cnt, res.total) }}%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </template>

    <!-- ===================== ⑤ 清单意图：概览 + 列表 + 地图 ===================== -->
    <template v-else-if="isFilter">
      <div class="kpis">
        <div class="card hero">
          <div class="l">命中机构</div>
          <div class="v">{{ fmt(res.total) }}</div>
          <div class="s">全部来自 MySQL 查询结果</div>
        </div>
        <div class="card k2"><div class="l">三级</div>
          <div class="v">{{ fmt(res.stats.level3) }}</div><div class="s">应参评口径</div></div>
        <div class="card k2"><div class="l">二级</div>
          <div class="v">{{ fmt(res.stats.level2) }}</div><div class="s">应参评口径</div></div>
        <div class="card k2"><div class="l">公立</div>
          <div class="v">{{ fmt(res.stats.public_cnt) }}</div><div class="s">办别判定为公立</div></div>
        <div class="card k2"><div class="l">民营</div>
          <div class="v">{{ fmt(res.stats.private_cnt) }}</div><div class="s">办别判定为民营</div></div>
        <div class="card k2"><div class="l">含坐标</div>
          <div class="v">{{ fmt(res.stats.coord_ok) }}</div>
          <div class="s">可在地图上定位</div></div>
      </div>

      <div class="split" style="grid-template-columns:minmax(0,1fr) minmax(360px,460px)">
        <div class="panel">
          <h3>
            筛选结果 <span class="tag">按「{{ sortLabelText }}」排序</span>
            <span class="muted" style="margin-left:auto">第 {{ res.page }} 页 · 共 {{ fmt(res.total) }} 家</span>
          </h3>
          <div v-if="items.length" class="listwrap" style="max-height:560px">
            <table class="tbl">
              <thead>
                <tr>
                  <th style="width:46px">序号</th>
                  <th>机构名称</th>
                  <th style="width:74px">等级</th>
                  <th style="width:74px">办别</th>
                  <th style="width:78px">距离</th>
                  <th style="width:70px">匹配度</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(r, i) in items" :key="r.id"
                    @mouseenter="focusPoint(r.id)" @click="store.openDrawer(r.id)">
                  <td class="muted">{{ (res.page - 1) * res.page_size + i + 1 }}</td>
                  <td>
                    <div class="name">{{ r.name }}</div>
                    <div class="sub">
                      {{ r.district }}
                      <template v-if="r.category"> · {{ r.category }}</template>
                      <template v-if="r.addr"> · {{ r.addr }}</template>
                    </div>
                  </td>
                  <td><span class="badge" :class="lvClass(r.level)">{{ r.level || '—' }}</span></td>
                  <td><span class="badge" :class="ownClass(r.ownership)">{{ r.ownership || '未标注' }}</span></td>
                  <td>{{ r.distance_km === null || r.distance_km === undefined ? '—' : r.distance_km + ' km' }}</td>
                  <td>{{ r.score === null || r.score === undefined ? '—' : Number(r.score).toFixed(3) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div v-else class="empty">无命中结果</div>

          <div class="pager">
            <span class="info">第 {{ res.page }} / {{ totalPages }} 页</span>
            <button class="btn sm" type="button" :disabled="res.page <= 1"
                    @click="store.nlqPage(res.page - 1)">上一页</button>
            <button class="btn sm" type="button" :disabled="res.page >= totalPages"
                    @click="store.nlqPage(res.page + 1)">下一页</button>
          </div>
        </div>

        <div class="panel">
          <h3>结果分布 <span class="tag">点击点位看机构档案</span></h3>
          <div class="chartbox tall" ref="elMap" style="height:560px"></div>
          <div class="muted" style="margin-top:8px;font-size:11.5px">
            仅展示本页含坐标的 {{ withCoord }} 家机构；距离按当前基准点用 Haversine 公式计算。
          </div>
        </div>
      </div>
    </template>

    <!-- ===================== ⑥ 会话留痕 + 数据来源 ===================== -->
    <div v-if="res" class="split">
      <div class="panel">
        <h3>数据来源 <span class="tag">所有数字可复算</span></h3>
        <div class="nlqsrc">
          <div class="sline"><b>查询库表</b><span>{{ src.database || '—' }}</span></div>
          <div class="sline"><b>机构总数</b><span>{{ fmt(src.institutions) }} 家（全库口径）</span></div>
          <div class="sline"><b>数据批次</b><span>{{ src.batch_date || '—' }}　·　源文件 {{ fmt(src.source_files) }} 个</span></div>
          <div class="sline"><b>数据链路</b><span>{{ src.detail || '—' }}</span></div>
          <div class="sline"><b>AI 边界</b><span>{{ src.note || scopeNote }}</span></div>
        </div>
      </div>

      <div class="panel">
        <h3>本次会话的查询 <span class="tag">{{ store.nlq.history.length }}</span></h3>
        <div v-if="store.nlq.history.length" class="nlqhist">
          <button v-for="(h, i) in store.nlq.history" :key="i" class="h" type="button"
                  :title="'重新执行：' + h.title" @click="store.nlqReplay(h)">
            <b>{{ h.title }}</b>
            <span class="muted">{{ fmt(h.n) }} 家</span>
            <i>{{ h.at }}</i>
          </button>
        </div>
        <div v-else class="muted">本次会话还没有查询记录。</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch, nextTick } from 'vue'
import { useDataStore } from '../store'
import { tokens, tip, echarts } from '../charts'
// 北京 16 区边界：权威副本在 web/vendor/beijing_geo.json，
// web/vue/build.sh 每次构建会同步覆盖 geo/ 下的这一份，避免两处边界漂移。
import beijingGeo from '../../geo/beijing_geo.json'

const store = useDataStore()

const EXAMPLES = [
  '朝阳区和海淀区的三级公立医院',
  '按行政区统计三级医院的数量',
  '开设有骨科的机构，按距离从近到远',
  '医保定点名单里的社区卫生服务中心有多少家',
  '查看各区机构数量分布'
]

const q = ref(store.nlq.q)
const elStat = ref(null)
const elMap = ref(null)

const mode = computed(() => store.nlq.mode)
const form = computed(() => store.nlq.form)
const res = computed(() => store.nlq.result)
const isStats = computed(() => store.nlqIsStats)
const isFilter = computed(() => store.nlqIsFilter)
const hasResult = computed(() => !!store.nlq.result)
const chips = computed(() => store.nlqChips)
const items = computed(() => store.nlqItems)
const unmatched = computed(() => (res.value && res.value.parsed && res.value.parsed.unmatched) || [])
const notice = computed(() => (res.value && res.value.parsed && res.value.parsed.notice) || '')
// 拒答：后端用 intent=unsupported 明确表达"这类问题不归我管"，前端据此换一套文案
const refusal = computed(() => {
  const r = res.value
  if (r && r.intent === 'unsupported') return r.message || '这类问题不在本系统的能力范围内。'
  if (r && !r.ok && r.message && r.intent !== 'error') return r.message
  return ''
})
const src = computed(() => (res.value && res.value.data_source) || {})
const scopeNote = computed(() => (store.nlq.lex && store.nlq.lex.scope_note) || '')

const districts = computed(() => store.meta.districts || [])
const levels = computed(() => (store.nlq.lex && store.nlq.lex.levels) || store.meta.levels || [])
const categories = computed(() =>
  (store.meta.categories || []).map((c) => c.category).filter(Boolean))
const ownerships = computed(() => (store.nlq.lex && store.nlq.lex.ownerships) || ['公立', '民营', '未标注'])
const sourceRules = computed(() => (store.nlq.lex && store.nlq.lex.source_rules) || [])
const dimLabel = computed(() => (store.nlq.lex && store.nlq.lex.dim_label) || { district: '行政区' })
const sortLabel = computed(() => (store.nlq.lex && store.nlq.lex.sort_label) || { score: '条件匹配度' })
const sortLabelText = computed(() => sortLabel.value[(res.value && res.value.sort) || 'score'] || '条件匹配度')

const engineLabel = computed(() => {
  const e = res.value && res.value.parsed && res.value.parsed.engine
  return e === 'llm' ? '规则 + 大模型兜底' : '离线规则引擎（词表 + 正则）'
})
const intentLabel = computed(() => {
  const r = res.value
  if (!r) return '—'
  if (r.intent === 'stats') return '维度统计'
  if (r.intent === 'filter') return '机构清单'
  if (r.intent === 'unsupported') return '超出能力范围'
  return '错误'
})
const chartLabel = computed(() => ((res.value && res.value.chart) === 'pie' ? '饼图' : '条形图'))

const totalPages = computed(() => {
  const r = res.value
  if (!r || !r.page_size) return 1
  return Math.max(1, Math.ceil((r.total || 0) / r.page_size))
})
const topGroup = computed(() => {
  const rows = (res.value && res.value.rows) || []
  return rows.length ? { name: rows[0].name, n: rows[0].cnt } : { name: '', n: '—' }
})
const bottomGroup = computed(() => {
  const rows = (res.value && res.value.rows) || []
  return rows.length ? { name: rows[rows.length - 1].name, n: rows[rows.length - 1].cnt } : { name: '', n: '—' }
})
const withCoord = computed(() => items.value.filter((r) => r.lng != null && r.lat != null).length)

const fmt = (n) => (n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString())
const pct = (a, b) => (b ? ((a / b) * 100).toFixed(2) : '0.00')
function lvClass(lv) {
  return { 三级: 'l3', 二级: 'l2', 一级: 'l1' }[lv] || 'l0'
}
function ownClass(o) {
  if (o === '公立') return 'pub'
  if (o === '民营') return 'pri'
  return 'na'
}

// ---------------- 提交 ----------------
// 输入框绑的是组件内的 q，所以提交时要把它的值显式传下去：
// 不传的话 store 会去读自己那份 q（没有人写过），表现为"点了按钮没反应"。
// 示例词按钮传的是字符串，主按钮不传 → 统一在这里归一。
function submit(text) {
  store.nlqRun(typeof text === 'string' ? text : q.value)
}
function submitCond() {
  store.nlqRunConditions()
}
function clearCond() {
  store.nlq.form.district = ''
  store.nlq.form.level = ''
  store.nlq.form.category = ''
  store.nlq.form.ownership = ''
  store.nlq.form.source = ''
  store.nlq.form.dept = ''
  store.nlq.form.kw = ''
  store.nlq.dimension = ''
}

// ---------------- 统计图 ----------------
let statInst = null
function drawStat() {
  const r = res.value
  if (!elStat.value || !r || r.intent !== 'stats') return
  const t = tokens()
  if (!statInst) statInst = echarts.init(elStat.value)
  const rows = r.rows || []
  if (!rows.length) {
    statInst.clear()
    // 空结果也要给一句人话，避免出现"图表区域一片空白但没人解释"
    statInst.setOption({
      title: {
        text: '该维度下没有可统计的记录', left: 'center', top: 'middle',
        textStyle: { color: t.axis, fontSize: 12, fontWeight: 400 }
      }
    }, true)
    return
  }
  // 条形图按数值升序排列（横向柱状图从下往上画，升序才符合"多的在上"的阅读习惯）
  const sorted = [...rows].sort((a, b) => (a.cnt || 0) - (b.cnt || 0))
  if (r.chart === 'pie') {
    const pal = [t.acc, t.vio, t.teal, t.warn, t.pink, t.crit, t.ink3]
    statInst.setOption({
      tooltip: { trigger: 'item', ...tip(t), formatter: '{b}：{c} 家（{d}%）' },
      legend: {
        bottom: 0, textStyle: { color: t.ink2, fontSize: 11 }, itemWidth: 9, itemHeight: 9,
        formatter: (name) => {
          const x = rows.find((v) => v.name === name)
          return x ? name + ' ' + x.cnt : name
        }
      },
      series: [{
        type: 'pie', radius: ['46%', '68%'], center: ['50%', '44%'],
        avoidLabelOverlap: true, minAngle: 5,
        itemStyle: { borderColor: t.panel, borderWidth: 2 },
        labelLine: { length: 8, length2: 8, lineStyle: { color: t.split } },
        // formatter 传函数时 ECharts 不会做 {b}/{c} 模板替换，必须自己拼字符串
        label: { color: t.ink2, fontSize: 11, lineHeight: 14,
          formatter: (p) => (p.percent >= 5 ? p.name + '\n' + p.value : '') },
        data: sorted.map((x, i) => ({
          name: x.name || '未标注', value: x.cnt,
          itemStyle: { color: pal[i % pal.length] }
        }))
      }]
    }, true)
    return
  }
  statInst.setOption({
    grid: { left: 6, right: 46, top: 12, bottom: 6, containLabel: true },
    tooltip: { trigger: 'axis', ...tip(t) },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: t.split } }, axisLabel: { color: t.axis } },
    yAxis: {
      type: 'category', data: sorted.map((x) => x.name || '未标注'),
      axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false },
      axisLabel: { color: t.axis, fontSize: 11 }
    },
    series: [{
      type: 'bar', data: sorted.map((x) => x.cnt), barMaxWidth: 16,
      itemStyle: { color: t.acc, borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: t.ink2, fontSize: 10.5 }
    }]
  }, true)
}

// ---------------- 结果地图 ----------------
let mapInst = null
let mapRegistered = false
let pointIndex = {}

function drawMap() {
  if (!elMap.value || !res.value || res.value.intent !== 'filter') return
  const t = tokens()
  if (!mapRegistered) {
    echarts.registerMap('beijing', beijingGeo)
    mapRegistered = true
  }
  if (!mapInst) {
    mapInst = echarts.init(elMap.value)
    // 地图上的点位可点：直接打开机构档案抽屉，与列表点击同一条路径
    mapInst.on('click', (p) => {
      const id = p && p.data && p.data.id
      if (id) store.openDrawer(id)
    })
  }
  const pts = items.value
    .filter((r) => r.lng != null && r.lat != null)
    .map((r) => ({ id: r.id, name: r.name, value: [r.lng, r.lat], km: r.distance_km }))
  pointIndex = {}
  pts.forEach((p, i) => { pointIndex[String(p.id)] = i })
  mapInst.setOption({
    tooltip: {
      trigger: 'item', ...tip(t),
      formatter: (p) => (p.data && p.data.km != null
        ? p.name + '<br />约 ' + p.data.km + ' km'
        : p.name)
    },
    geo: {
      map: 'beijing', roam: true, zoom: 1.02,
      scaleLimit: { min: 0.8, max: 6 },
      itemStyle: { areaColor: t.mapArea, borderColor: t.mapBd, borderWidth: 1 },
      emphasis: { itemStyle: { areaColor: t.mapHi }, label: { show: false } },
      label: { show: false }
    },
    series: [{
      type: 'effectScatter', coordinateSystem: 'geo', data: pts,
      symbolSize: 7, rippleEffect: { scale: 2.6, brushType: 'stroke' },
      itemStyle: { color: t.acc, shadowBlur: 6, shadowColor: t.acc },
      emphasis: {
        label: { show: true, formatter: (p) => p.name, color: t.ink, fontSize: 11, position: 'right' }
      }
    }]
  }, true)
}

// 列表悬停 → 地图点位高亮：让"表里那一行"和"图上那个点"能对上
function focusPoint(id) {
  if (!mapInst) return
  const idx = pointIndex[String(id)]
  if (idx === undefined) return
  mapInst.dispatchAction({ type: 'downplay', seriesIndex: 0 })
  mapInst.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: idx })
}

// ---------------- 生命周期 ----------------
function disposeStat() {
  if (statInst) { statInst.dispose(); statInst = null }
}
function disposeMap() {
  if (mapInst) { mapInst.dispose(); mapInst = null }
  pointIndex = {}
}

// 统计与清单是两个互斥的模板分支，容器会被整块替换；
// 因此换结果类型时必须先销毁旧实例，否则 ECharts 会继续画在已经被移除的 DOM 上（表现为白屏）。
watch([() => store.nlq.result, () => store.theme], async () => {
  await nextTick()
  const r = res.value
  if (!r || !r.ok) { disposeStat(); disposeMap(); return }
  if (r.intent === 'stats') { disposeMap(); drawStat() }
  else if (r.intent === 'filter') { disposeStat(); drawMap() }
  else { disposeStat(); disposeMap() }
}, { deep: false })

// 「重新开始」会清空输入框，表单里的受控值要跟着回来（否则界面与 store 不一致）
watch(() => store.nlq.q, (v) => { if (v !== q.value) q.value = v })

onBeforeUnmount(() => {
  disposeStat()
  disposeMap()
})

// 词表只取一次：维度标签、来源规则、等级取值都以后端为准，前端不复制一份
store.nlqLoadLex()
</script>
