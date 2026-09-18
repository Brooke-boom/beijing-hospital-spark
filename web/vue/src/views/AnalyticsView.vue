<template>
  <div class="page">
    <div class="panel">
      <h3>医疗资源多维分析 <span class="tag">空间 / 等级 / 科室 / 协作网络</span>
        <button class="btn ghost sm" style="margin-left:auto" type="button" @click="store.loadOverview(true)">
          刷新数据
        </button>
      </h3>
      <div class="muted">
        本页所有图表均由 <code>/api/overview/*</code> 与 <code>/api/specialty/groups</code> 实时返回，
        数据源为 MySQL 服务层（ADS/DWS），非前端静态造数。
      </div>
    </div>

    <div class="split">
      <div class="panel">
        <h3>区域资源分布 <span class="tag">机构数 / 三级机构数 双系列</span></h3>
        <div class="chartbox tall" ref="elRegion"></div>
      </div>
      <div class="panel">
        <h3>等级结构 <span class="tag">district_count / category_count</span></h3>
        <div class="chartbox tall" ref="elLevel"></div>
      </div>
    </div>

    <div class="split">
      <div class="panel">
        <h3>重点专科分布 TOP 14 <span class="tag">按挂牌该专科的机构数</span></h3>
        <div class="chartbox tall" ref="elSpecialty"></div>
      </div>
      <div class="panel">
        <h3>协作网络规模 <span class="tag">成员机构数</span></h3>
        <div class="chartbox tall" ref="elNet"></div>
        <div class="muted" style="margin-top:8px">
          协作网络（儿科医联体／卒中中心／危重新生儿与孕产妇救治中心）
          是跨机构的资源协同维度，用于回答"某类急重症能去哪几家"。
        </div>
      </div>
    </div>

    <div class="panel">
      <h3>科室覆盖明细 <span class="tag">共 {{ ov.depts.length }} 个科室口径</span></h3>
      <div class="listwrap" style="max-height:360px">
        <table class="tbl">
          <thead>
            <tr>
              <th style="width:56px">#</th>
              <th>科室名称</th>
              <th style="width:150px">开展机构数</th>
              <th style="width:150px">其中重点专科</th>
              <th style="width:200px">占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(d, i) in ov.depts" :key="d.dept_name">
              <td class="muted">{{ i + 1 }}</td>
              <td><span class="name">{{ d.dept_name }}</span></td>
              <td>{{ fmt(d.hospital_count) }}</td>
              <td>
                <span v-if="d.key_specialty_count" class="badge l3">{{ d.key_specialty_count }}</span>
                <span v-else class="muted">—</span>
              </td>
              <td>
                <div class="bar"><i :style="{ width: barW(d.hospital_count) }"></i></div>
                <span class="muted" style="font-size:11px">{{ share(d.hospital_count) }}%</span>
              </td>
            </tr>
          </tbody>
        </table>
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

const elRegion = ref(null)
const elLevel = ref(null)
const elSpecialty = ref(null)
const elNet = ref(null)

const maxDept = computed(() => Math.max(1, ...ov.value.depts.map((d) => d.hospital_count || 0)))
const fmt = (n) => (n === null || n === undefined ? '—' : Number(n).toLocaleString())
const barW = (n) => ((n || 0) / maxDept.value) * 100 + '%'
const share = (n) => {
  const t = ov.value.depts.reduce((a, r) => a + (r.hospital_count || 0), 0)
  return t ? ((n / t) * 100).toFixed(1) : '0.0'
}

const { render: renderRegion } = useChart(elRegion, (t) => {
  const rows = [...ov.value.districts].sort((a, b) => b.inst_count - a.inst_count)
  if (!rows.length) return null
  return {
    grid: { left: 6, right: 10, top: 34, bottom: 40, containLabel: true },
    tooltip: { trigger: 'axis', ...tip(t) },
    legend: {
      top: 0, textStyle: { color: t.ink2, fontSize: 11 }, itemWidth: 10, itemHeight: 8,
      data: ['机构总数', '三级机构']
    },
    xAxis: {
      type: 'category', data: rows.map((r) => r.district),
      axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false },
      axisLabel: { color: t.axis, fontSize: 10.5, rotate: 38 }
    },
    yAxis: {
      type: 'value', splitLine: { lineStyle: { color: t.split } }, axisLabel: { color: t.axis }
    },
    series: [
      {
        name: '机构总数', type: 'bar', barMaxWidth: 14,
        itemStyle: { color: t.acc, borderRadius: [3, 3, 0, 0] },
        data: rows.map((r) => r.inst_count)
      },
      {
        name: '三级机构', type: 'bar', barMaxWidth: 14,
        itemStyle: { color: t.warn, borderRadius: [3, 3, 0, 0] },
        data: rows.map((r) => r.level_3_count)
      }
    ]
  }
})

const { render: renderLevel } = useChart(elLevel, (t) => {
  const rows = ov.value.levels.filter((r) => r.inst_count > 0)
  if (!rows.length) return null
  const pal = { 三级: t.acc, 二级: t.teal, 一级: t.warn, 未定级: t.ink3 }
  return {
    grid: { left: 6, right: 10, top: 34, bottom: 30, containLabel: true },
    tooltip: { trigger: 'axis', ...tip(t) },
    legend: { top: 0, textStyle: { color: t.ink2, fontSize: 11 }, itemWidth: 10, itemHeight: 8 },
    xAxis: {
      type: 'category', data: rows.map((r) => r.level_norm),
      axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false },
      axisLabel: { color: t.axis, fontSize: 11 }
    },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: t.split } }, axisLabel: { color: t.axis } },
    series: [
      {
        name: '机构数', type: 'bar', barMaxWidth: 34,
        data: rows.map((r) => ({ value: r.inst_count, itemStyle: { color: pal[r.level_norm] || t.vio, borderRadius: [4, 4, 0, 0] } })),
        label: { show: true, position: 'top', color: t.ink2, fontSize: 10.5 }
      },
      {
        name: '覆盖区县数', type: 'line', smooth: true, symbolSize: 6,
        lineStyle: { color: t.pink, width: 2 }, itemStyle: { color: t.pink },
        data: rows.map((r) => r.district_count)
      }
    ]
  }
})

const { render: renderSpecialty } = useChart(elSpecialty, (t) => {
  const rows = [...ov.value.specialtyGroups].sort((a, b) => b.hospital_count - a.hospital_count).slice(0, 14)
  if (!rows.length) return null
  return {
    grid: { left: 6, right: 46, top: 10, bottom: 6, containLabel: true },
    tooltip: { trigger: 'axis', ...tip(t) },
    xAxis: { type: 'value', splitLine: { lineStyle: { color: t.split } }, axisLabel: { color: t.axis } },
    yAxis: {
      type: 'category', data: rows.map((r) => r.dept_name).reverse(),
      axisLine: { lineStyle: { color: t.split } }, axisTick: { show: false },
      axisLabel: { color: t.axis, fontSize: 11 }
    },
    series: [{
      type: 'bar', barMaxWidth: 15,
      data: rows.map((r) => r.hospital_count).reverse(),
      // 不用地图色带（其低饱和暗色在深色底上对比度不足），改走主色→紫的横向渐变
      itemStyle: {
        borderRadius: [0, 4, 4, 0],
        color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0,
          colorStops: [{ offset: 0, color: t.vio }, { offset: 1, color: t.acc }] }
      },
      label: { show: true, position: 'right', color: t.ink2, fontSize: 10.5 }
    }]
  }
})

const { render: renderNet } = useChart(elNet, (t) => {
  const nets = store.meta.nets || []
  if (!nets.length) return null
  // 协作网络规模取自后端筛选命中数（net 维度），逐项请求保证口径一致
  const data = nets.map((n) => ({ name: n.label, value: store.netSize[n.value] || 0 }))
  if (!data.some((d) => d.value > 0)) return null
  const colors = [t.acc, t.teal, t.vio, t.warn, t.pink]
  return {
    tooltip: { trigger: 'item', ...tip(t), formatter: '{b}：{c} 家' },
    legend: {
      bottom: 0, textStyle: { color: t.ink2, fontSize: 11 }, itemWidth: 9, itemHeight: 9,
      formatter: (name) => {
        const d = data.find((x) => x.name === name)
        return d ? name + ' ' + d.value : name
      }
    },
    series: [{
      type: 'pie', radius: ['46%', '68%'], center: ['50%', '44%'],
      avoidLabelOverlap: true, minAngle: 8,
      itemStyle: { borderColor: t.panel, borderWidth: 2 },
      labelLine: { length: 8, length2: 8, lineStyle: { color: t.split } },
      label: { color: t.ink2, fontSize: 11, lineHeight: 14, formatter: (p) => (p.percent >= 9 ? (p.name + '\n' + p.value + ' 家') : '') },
      data: data.map((d, i) => ({ ...d, itemStyle: { color: colors[i % colors.length] } }))
    }]
  }
})

watch([() => ov.value.about, () => store.netSizeLoaded, () => store.theme], () => {
  renderRegion(); renderLevel(); renderSpecialty(); renderNet()
})
</script>
