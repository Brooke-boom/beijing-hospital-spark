<template>
  <div class="page">
    <div class="panel">
      <h3>智能筛选 <span class="tag">7 维条件组合</span>
        <span class="muted" style="margin-left:auto">
          命中 <b style="color:var(--ink-strong)">{{ fmt(store.total) }}</b> 家
        </span>
      </h3>
      <div class="muted">
        七个维度：关键词 / 区域 / 等级 / 类型 / 科室 / 协作网络 / 距离基准。
        条件通过 <code>GET /api/institutions</code> 提交，后端在 MySQL 上用复合索引执行，
        实测典型多维筛选扫描行数由 9,777 降至 33。
      </div>

      <div class="row" style="margin-top:12px;flex-wrap:wrap">
        <span class="muted" style="font-size:12px">常用预设：</span>
        <button v-for="p in PRESETS" :key="p.label" class="btn sm ghost" type="button"
                @click="applyPreset(p)">{{ p.label }}</button>
        <button class="btn sm" type="button" :disabled="!store.hasConditions" @click="store.resetQuery()">
          清空条件
        </button>
      </div>
    </div>

    <FilterBar />

    <div class="split">
      <div class="panel">
        <h3>筛选结果 <span class="tag">按「{{ sortLabel }}」排序</span></h3>
        <div v-if="store.items.length" class="listwrap" style="max-height:520px">
          <table class="tbl">
            <thead>
              <tr>
                <th style="width:46px">序号</th>
                <th>机构名称</th>
                <th style="width:78px">等级</th>
                <th style="width:78px">办别</th>
                <th style="width:78px">距离</th>
                <th style="width:70px">评分</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in store.items" :key="r.id" @click="store.openDrawer(r.id)">
                <td class="muted">{{ (store.query.page - 1) * store.query.pageSize + i + 1 }}</td>
                <td>
                  <div class="name">{{ r.name }}</div>
                  <div class="sub">{{ r.district }}<template v-if="r.addr"> · {{ r.addr }}</template></div>
                </td>
                <td><span class="badge" :class="lvClass(r.level)">{{ r.level || '—' }}</span></td>
                <td><span class="badge" :class="ownClass(r.ownership)">{{ r.ownership || '未标注' }}</span></td>
                <td>{{ r.distance_km === null || r.distance_km === undefined ? '—' : r.distance_km + ' km' }}</td>
                <td>{{ r.score === null || r.score === undefined ? '—' : r.score }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">{{ store.loading ? '加载中…' : '无命中结果' }}</div>

        <div class="pager">
          <span class="info">第 {{ store.query.page }} / {{ store.totalPages }} 页</span>
          <button class="btn sm" type="button" :disabled="store.query.page <= 1" @click="store.gotoPage(store.query.page - 1)">上一页</button>
          <button class="btn sm" type="button" :disabled="store.query.page >= store.totalPages" @click="store.gotoPage(store.query.page + 1)">下一页</button>
        </div>
      </div>

      <div class="panel">
        <h3>当前条件 <span class="tag">可复现的查询串</span></h3>
        <div class="kv">
          <div class="k">关键词</div><div>{{ store.query.q || '（未设）' }}</div>
          <div class="k">区域</div><div>{{ store.query.district || '（全部）' }}</div>
          <div class="k">等级</div><div>{{ store.query.level || '（全部）' }}</div>
          <div class="k">类型</div><div>{{ store.query.category || '（全部）' }}</div>
          <div class="k">科室</div><div>{{ store.query.dept || '（全部）' }}</div>
          <div class="k">协作网络</div><div>{{ netLabel || '（全部）' }}</div>
          <div class="k">排序</div><div>{{ sortLabel }}</div>
          <div class="k">距离基准</div>
          <div>{{ store.base ? (store.base.name + '（' + store.base.lng + ', ' + store.base.lat + '）') : '天安门（默认）' }}</div>
          <div class="k">命中</div><div>{{ fmt(store.total) }} 家</div>
        </div>

        <h3 style="font-size:13px;margin:16px 0 8px">API 请求</h3>
        <div class="notice" style="word-break:break-all;font-size:12px">GET {{ apiPath }}</div>
        <div class="muted" style="margin-top:8px;font-size:12px">
          同样的查询串在任何时刻都能复现同一结果集（数据快照固定）。
        </div>

        <h3 style="font-size:13px;margin:16px 0 8px">导出</h3>
        <div class="row">
          <button class="btn sm ghost" type="button" @click="copyCurl">复制请求地址</button>
          <button class="btn sm ghost" type="button" @click="copyJson">复制当前页 JSON</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import FilterBar from '../components/FilterBar.vue'
import { useDataStore } from '../store'

const store = useDataStore()

const PRESETS = [
  { label: '三级医院', patch: { level: '三级' } },
  { label: '二级医院', patch: { level: '二级' } },
  { label: '儿科医联体', patch: { net: 'ped_core' } },
  { label: '卒中中心', patch: { net: 'stroke' } },
  { label: '妇幼保健', patch: { category: '妇幼保健' } },
  { label: '急救中心', patch: { category: '急救中心' } }
]

const SORTS = {
  score: '条件匹配度', distance: '距离（近 → 远）', level: '医院等级',
  depts: '科室收录量', name: '机构名称'
}
const sortLabel = computed(() => SORTS[store.query.sort] || store.query.sort)
const netLabel = computed(() => {
  const n = (store.meta.nets || []).find((x) => x.value === store.query.net)
  return n ? n.label : store.query.net
})

const apiPath = computed(() => {
  const p = new URLSearchParams()
  Object.entries({
    q: store.query.q, district: store.query.district, level: store.query.level,
    category: store.query.category, dept: store.query.dept, net: store.query.net,
    sort: store.query.sort, page: store.query.page, page_size: store.query.pageSize
  }).forEach(([k, v]) => { if (v !== '' && v !== null && v !== undefined) p.set(k, v) })
  const b = store.base
  if (b) { p.set('lng', b.lng); p.set('lat', b.lat) }
  return '/api/institutions?' + p.toString()
})

function applyPreset(p) {
  store.resetQuery().then(() => store.setQuery(p.patch))
}
function copyCurl() {
  navigator.clipboard.writeText(location.origin + apiPath.value)
    .then(() => store.notify('请求地址已复制'))
    .catch(() => store.notify('当前环境不允许写剪贴板'))
}
function copyJson() {
  navigator.clipboard.writeText(JSON.stringify(store.items, null, 2))
    .then(() => store.notify('当前页 JSON 已复制'))
    .catch(() => store.notify('当前环境不允许写剪贴板'))
}
const fmt = (n) => (n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString())
function lvClass(lv) {
  if (lv === '三级') return 'l3'
  if (lv === '二级') return 'l2'
  if (lv === '一级') return 'l1'
  return 'l0'
}
function ownClass(o) {
  if (o === '公立') return 'pub'
  if (o === '民营') return 'pri'
  return 'na'
}
</script>
