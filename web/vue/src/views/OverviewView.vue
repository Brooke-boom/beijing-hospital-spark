<template>
  <div class="page">
    <div class="kpis">
      <div class="card hero">
        <div class="l">机构总数</div>
        <div class="v">{{ fmt(totalInst) }}</div>
        <div class="s">覆盖 {{ districtCount }} 个行政区 · 快照 {{ snapshot }}</div>
      </div>
      <div class="card k2">
        <div class="l">三级机构</div>
        <div class="v">{{ fmt(level3) }}</div>
        <div class="s">占应参评机构 {{ pct(level3, gradedTotal) }}%</div>
      </div>
      <div class="card k2">
        <div class="l">应参评机构</div>
        <div class="v">{{ fmt(gradedTotal) }}</div>
        <div class="s">其余 {{ fmt(notApplicable) }} 家按类型归"不适用分级"</div>
      </div>
      <div class="card k2">
        <div class="l">坐标覆盖率</div>
        <div class="v">{{ coordRate }}%</div>
        <div class="s">精确 {{ fmt(coordHigh) }} · 粗略 {{ fmt(coordRough) }}</div>
      </div>
      <div class="card k2">
        <div class="l">重点专科机构</div>
        <div class="v">{{ specialtyHosp }}</div>
        <div class="s">挂牌记录 {{ fmt(specialtyRows) }} 条 · {{ specialtyKinds }} 类专科</div>
      </div>
      <div class="card k2">
        <div class="l">协作网络成员</div>
        <div class="v">{{ fmt(networkMembers) }}</div>
        <div class="s">跨 {{ networkCount }} 类协作网络（成员可重复计入）</div>
      </div>
    </div>

    <div class="split" style="margin-top:14px">
      <div class="panel">
        <h3>各行政区机构数量 <span class="tag">TOP 16</span></h3>
        <div class="chartbox" ref="elDistrict"></div>
      </div>
      <div class="panel">
        <h3>等级分布 <span class="tag">应参评机构口径</span></h3>
        <div class="chartbox" ref="elLevel"></div>
        <div class="muted" style="margin-top:8px">
          制度上不具备医院等级的机构（诊所／村卫生室／门诊部等 {{ fmt(notApplicable) }} 家）
          已从本口径剔除，避免形成 87% 的假性未定级。
        </div>
      </div>
    </div>

    <div class="split" style="margin-top:14px">
      <div class="panel">
        <h3>科室覆盖 TOP 12 <span class="tag">按开展该科室的机构数</span></h3>
        <div class="chartbox" ref="elDept"></div>
      </div>
      <div class="panel">
        <h3>机构类型构成 <span class="tag">按机构类别聚合</span></h3>
        <div class="chartbox" ref="elCategory"></div>
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

const elDistrict = ref(null)
const elLevel = ref(null)
const elDept = ref(null)
const elCategory = ref(null)

const totalInst = computed(() => store.health?.institutions || store.total || 0)
const districtCount = computed(() => ov.value.districts.length)
const level3 = computed(() => pick(ov.value.levels, '三级'))
const gradedTotal = computed(() => ov.value.levels.reduce((a, r) => a + (r.inst_count || 0), 0))
const levelsAllTotal = computed(() => ov.value.levelsAll.reduce((a, r) => a + (r.inst_count || 0), 0))
const notApplicable = computed(() => Math.max(0, levelsAllTotal.value - gradedTotal.value))
const coordHigh = computed(() => fold(ov.value.districts, 'coord_high_count'))
const coordRough = computed(() => fold(ov.value.districts, 'coord_rough_count'))
const coordMissing = computed(() => fold(ov.value.districts, 'coord_missing_count'))
const coordRate = computed(() => {
  const t = coordHigh.value + coordRough.value + coordMissing.value
  return t ? (((t - coordMissing.value) / t) * 100).toFixed(2) : '—'
})
const keySpecialtyCount = computed(() => fold(ov.value.depts, 'key_specialty_count'))
// 重点专科口径：ads_specialty_hospital 是「机构 × 专科」的挂牌记录表
const specialtyRows = computed(() =>
  ov.value.specialtyGroups.reduce((a, g) => a + (g.hospital_count || 0), 0))
const specialtyHosp = computed(() => {
  const ids = new Set()
  ov.value.specialtyGroups.forEach((g) => (g.hospitals || []).forEach((h) => ids.add(h.id)))
  return ids.size
})
const specialtyKinds = computed(() => ov.value.specialtyGroups.length)
const networkCount = computed(() => store.meta.nets.length)
const networkMembers = computed(() =>
  Object.values(store.netSize || {}).reduce((a, n) => a + (n || 0), 0))
// 快照日期统一取后端 /api/about 的 updated_at，与「系统说明」页口径一致
const snapshot = computed(() => (ov.value.about && ov.value.about.updated_at) || '—')

function pick(list, name) {
  return (list || []).filter((r) => String(r.level_norm) === name)
    .reduce((a, r) => a + (r.inst_count || 0), 0)
}
function fold(list, field) {
  return (list || []).reduce((a, r) => a + (r[field] || 0), 0)
}
const fmt = (n) => (n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString())
const pct = (a, b) => (b ? ((a / b) * 100).toFixed(1) : '0.0')

// ---- 图表 ----
const { render: renderDistrict } = useChart(elDistrict, (t) => {
  const rows = [...ov.value.districts].sort((a, b) => b.inst_count - a.inst_count).slice(0, 16)
  if (!rows.length) return null
  const data = rows.map((r) => r.inst_count)
  const ramp = t.ramp.length ? t.ramp : [t.acc]
  const max = Math.max(...data) || 1
  return {
    grid: { left: 6, right: 40, top: 12, bottom: 6, containLabel: true },
    tooltip: { trigger: 'axis', ...tip(t) },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: t.split } }, axisLabel: { color: t.axis } },
    yAxis: {
      type: 'category', data: rows.map((r) => r.district),
      axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false },
      axisLabel: { color: t.axis, fontSize: 11 }
    },
    series: [{
      type: 'bar', data, barMaxWidth: 15,
      itemStyle: {
        borderRadius: [0, 4, 4, 0],
        color: (p) => ramp[Math.min(ramp.length - 1, Math.floor((1 - p.value / max) * (ramp.length - 1)))]
      },
      label: { show: true, position: 'right', color: t.ink2, fontSize: 10.5 }
    }]
  }
})

const { render: renderLevel } = useChart(elLevel, (t) => {
  const rows = ov.value.levels.filter((r) => r.inst_count > 0)
  if (!rows.length) return null
  const pal = { 三级: t.acc, 二级: t.teal, 一级: t.warn, 未定级: t.ink3 }
  const legendFmt = (name) => {
    const r = rows.find((x) => x.level_norm === name)
    return r ? r.level_norm + ' ' + r.inst_count : name
  }
  return {
    tooltip: { trigger: 'item', ...tip(t), formatter: '{b}：{c} 家（{d}%）' },
    legend: {
      bottom: 0, textStyle: { color: t.ink2, fontSize: 11 }, itemWidth: 9, itemHeight: 9,
      formatter: legendFmt, data: rows.map((r) => r.level_norm)
    },
    series: [{
      type: 'pie', radius: ['48%', '70%'], center: ['50%', '45%'],
      avoidLabelOverlap: true, minAngle: 6,
      itemStyle: { borderColor: t.panel, borderWidth: 2 },
      labelLine: { length: 8, length2: 8, lineStyle: { color: t.split } },
      // 占比过小的分片不画标签，避免与相邻标签重叠（数值由图例给出）
      // 注意：formatter 传函数时 ECharts 不做 {b}/{c} 模板替换，必须自己拼好字符串
      label: {
        color: t.ink2, fontSize: 11, lineHeight: 14,
        formatter: (p) => (p.percent >= 5 ? p.name + '\n' + p.value : '')
      },
      data: rows.map((r) => ({
        name: r.level_norm, value: r.inst_count, itemStyle: { color: pal[r.level_norm] || t.vio }
      }))
    }]
  }
})

const { render: renderDept } = useChart(elDept, (t) => {
  const rows = [...ov.value.depts].sort((a, b) => b.hospital_count - a.hospital_count).slice(0, 12)
  if (!rows.length) return null
  return {
    grid: { left: 6, right: 40, top: 12, bottom: 6, containLabel: true },
    tooltip: { trigger: 'axis', ...tip(t) },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: t.split } }, axisLabel: { color: t.axis } },
    yAxis: {
      type: 'category', data: rows.map((r) => r.dept_name).reverse(),
      axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false },
      axisLabel: { color: t.axis, fontSize: 11 }
    },
    series: [{
      type: 'bar', data: rows.map((r) => r.hospital_count).reverse(), barMaxWidth: 14,
      itemStyle: { color: t.teal, borderRadius: [0, 4, 4, 0] },
      label: { show: true, position: 'right', color: t.ink2, fontSize: 10.5 }
    }]
  }
})

const { render: renderCategory } = useChart(elCategory, (t) => {
  const rows = [...(store.meta.categories || [])].sort((a, b) => b.inst_count - a.inst_count).slice(0, 9)
  if (!rows.length) return null
  const colors = [t.acc, t.vio, t.teal, t.warn, t.pink, t.crit, t.ink3, t.acc, t.vio]
  return {
    tooltip: { trigger: 'item', ...tip(t), formatter: '{b}：{c} 家（{d}%）' },
    // 类型条目多、名称长：图例竖排在右侧，饼图左移，避免横向挤压截断
    legend: {
      orient: 'vertical', right: 4, top: 'center',
      textStyle: { color: t.ink2, fontSize: 11 }, itemWidth: 9, itemHeight: 9,
      itemGap: 9, formatter: (name) => {
        const r = rows.find((x) => x.category === name)
        return r ? name + ' ' + r.inst_count : name
      }
    },
    series: [{
      type: 'pie', radius: ['44%', '68%'], center: ['34%', '50%'],
      avoidLabelOverlap: true, minAngle: 4,
      itemStyle: { borderColor: t.panel, borderWidth: 2 },
      labelLine: { show: false },
      label: {
        color: t.ink, fontSize: 11, fontWeight: 600,
        formatter: (p) => (p.percent >= 8 ? p.name + '\n' + p.value : '')
      },
      data: rows.map((r, i) => ({ name: r.category, value: r.inst_count, itemStyle: { color: colors[i % colors.length] } }))
    }]
  }
})

// 数据到位 / 主题切换 → 重绘全部图表
watch([() => ov.value.about, () => store.theme], () => {
  renderDistrict(); renderLevel(); renderDept(); renderCategory()
}, { immediate: false })
</script>
