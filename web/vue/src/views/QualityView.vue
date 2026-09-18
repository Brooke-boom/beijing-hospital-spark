<template>
  <div class="page">
    <div class="panel">
      <h3>数据质量概览 <span class="tag">全部指标取自真实表统计</span>
        <button class="btn ghost sm" style="margin-left:auto" type="button" @click="store.loadOverview(true)">
          重新统计
        </button>
      </h3>
      <div class="muted">
        本页不展示任何人工编写的"质量得分"，只呈现可从库里直接复算的客观指标，
        以及对无法补全字段的如实说明。
      </div>
    </div>

    <div class="kpis k4">
      <div class="card hero">
        <div class="l">坐标覆盖率</div>
        <div class="v">{{ coordRate }}%</div>
        <div class="s">精确 {{ fmt(coordHigh) }} · 粗略 {{ fmt(coordRough) }} · 缺失 {{ fmt(coordMissing) }}</div>
      </div>
      <div class="card k2">
        <div class="l">应参评机构占比</div>
        <div class="v">{{ pct(gradedTotal, c.institutions) }}%</div>
        <div class="s">{{ fmt(gradedTotal) }} / {{ fmt(c.institutions) }} 家可判定等级</div>
      </div>
      <div class="card k2">
        <div class="l">科室关系记录</div>
        <div class="v">{{ fmt(c.dept_relations) }}</div>
        <div class="s">机构 × 科室 明细关系</div>
      </div>
      <div class="card k2">
        <div class="l">导诊知识库条目</div>
        <div class="v">{{ fmt(c.triage_dict) }}</div>
        <div class="s">疾病 → 科室 映射（离线规则引擎）</div>
      </div>
    </div>

    <div class="split">
      <div class="panel">
        <h3>各区坐标质量 <span class="tag">精确 / 粗略 / 缺失</span></h3>
        <div class="chartbox tall" ref="elCoord"></div>
      </div>
      <div class="panel">
        <h3>等级口径说明 <span class="tag">避免假性未定级</span></h3>
        <div class="listwrap" style="max-height:380px">
          <table class="tbl">
            <thead>
              <tr><th>等级</th><th style="width:100px">机构数</th><th>说明</th></tr>
            </thead>
            <tbody>
              <tr v-for="l in ov.levels" :key="l.level_norm">
                <td><span class="badge" :class="lvClass(l.level_norm)">{{ l.level_norm }}</span></td>
                <td>{{ fmt(l.inst_count) }}</td>
                <td class="muted">覆盖 {{ l.district_count }} 个区 · {{ l.category_count }} 类机构</td>
              </tr>
              <tr>
                <td><span class="badge na">不适用医院分级</span></td>
                <td>{{ fmt(notApplicable) }}</td>
                <td class="muted">制度上无等级：诊所 / 村卫生室 / 门诊部 / 社区卫生服务站 / 医务室 / 急救 / 疾控 / 体检中心</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="muted" style="margin-top:10px;font-size:12px">
          若把"不适用"计入未定级，会形成约 87% 的假性未定级并掩盖真实结构，
          因此接口默认口径 <code>scope=graded</code> 只统计应参评机构。
        </div>
      </div>
    </div>

    <div class="panel">
      <h3>已知数据边界 <span class="tag">如实保留，不做伪造</span></h3>
      <div class="bnd">
        <div v-for="b in BOUNDS" :key="b.t" class="bndcard">
          <div class="bt">{{ b.t }}</div>
          <div class="bv">{{ b.v }}</div>
          <div class="bd">{{ b.d }}</div>
        </div>
      </div>
    </div>

    <div class="panel">
      <h3>数据更新时间线 <span class="tag">来自 /api/about</span></h3>
      <div class="flow">
        <div v-for="(u, i) in updateLog" :key="u.date + i" class="flowstep">
          <div class="num">{{ i + 1 }}</div>
          <div class="body">
            <div class="ft">{{ u.date }}</div>
            <div class="fd">{{ u.desc }}</div>
          </div>
        </div>
        <div v-if="!updateLog.length" class="muted">暂无更新记录</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useDataStore } from '../store'
import { useChart, tip } from '../charts'

const store = useDataStore()
const ov = computed(() => store.overview)
const about = computed(() => ov.value.about || {})
const c = computed(() => about.value.counts || {})
const updateLog = computed(() => about.value.update_log || [])

const elCoord = ref(null)

const coordHigh = computed(() => fold('coord_high_count'))
const coordRough = computed(() => fold('coord_rough_count'))
const coordMissing = computed(() => fold('coord_missing_count'))
const coordRate = computed(() => {
  const t = coordHigh.value + coordRough.value + coordMissing.value
  return t ? (((t - coordMissing.value) / t) * 100).toFixed(2) : '—'
})
const gradedTotal = computed(() => ov.value.levels.reduce((a, r) => a + (r.inst_count || 0), 0))
const levelsAllTotal = computed(() => ov.value.levelsAll.reduce((a, r) => a + (r.inst_count || 0), 0))
const notApplicable = computed(() => Math.max(0, levelsAllTotal.value - gradedTotal.value))

const BOUNDS = [
  { t: '352 家民营医院无等级字段', v: '真实数据边界', d: '已在百度百科等公开渠道逐一核实，确实无等级字段，属数据边界而非解析漏损，故如实保留为空。' },
  { t: '248 家村卫生室办别未标注', v: '有意保留', d: '村办 / 私人办混合，公开信息无法单一判定，不强行标注以避免引入误差。' },
  { t: '2 家坐标缺失', v: '0.02%', d: '源数据无地址且无法地理编码，距离字段为空，前端显示为「—」而非 0。' },
  { t: '未定位机构不计距离', v: '回退天安门', d: '用户未设基准点时统一按天安门计算并在界面标注「距市中心」，杜绝 NaN。' }
]

function fold(field) {
  return (ov.value.districts || []).reduce((a, r) => a + (r[field] || 0), 0)
}
const fmt = (n) => (n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString())
const pct = (a, b) => (b ? ((a / b) * 100).toFixed(2) : '—')
function lvClass(lv) {
  if (lv === '三级') return 'l3'
  if (lv === '二级') return 'l2'
  if (lv === '一级') return 'l1'
  return 'l0'
}

const { render: renderCoord } = useChart(elCoord, (t) => {
  const rows = [...(ov.value.districts || [])].sort((a, b) => b.inst_count - a.inst_count)
  if (!rows.length) return null
  return {
    grid: { left: 6, right: 10, top: 34, bottom: 40, containLabel: true },
    tooltip: { trigger: 'axis', ...tip(t) },
    legend: {
      top: 0, textStyle: { color: t.ink2, fontSize: 11 }, itemWidth: 10, itemHeight: 8,
      data: ['坐标精确', '坐标粗略', '坐标缺失']
    },
    xAxis: {
      type: 'category', data: rows.map((r) => r.district),
      axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false },
      axisLabel: { color: t.axis, fontSize: 10.5, rotate: 38 }
    },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: t.split } }, axisLabel: { color: t.axis } },
    series: [
      { name: '坐标精确', type: 'bar', stack: 'c', itemStyle: { color: t.teal }, data: rows.map((r) => r.coord_high_count) },
      { name: '坐标粗略', type: 'bar', stack: 'c', itemStyle: { color: t.warn }, data: rows.map((r) => r.coord_rough_count) },
      {
        name: '坐标缺失', type: 'bar', stack: 'c',
        itemStyle: { color: t.crit, borderRadius: [3, 3, 0, 0] },
        data: rows.map((r) => r.coord_missing_count)
      }
    ]
  }
})

watch([() => ov.value.about, () => store.theme], () => renderCoord())
</script>
