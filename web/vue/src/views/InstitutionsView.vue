<template>
  <div class="page">
    <FilterBar />

    <div class="panel">
      <h3>
        机构列表 <span class="tag">共 {{ fmt(store.total) }} 家</span>
        <span class="muted" style="margin-left:auto">
          距离基准：{{ store.base ? store.base.name : '天安门（市中心）' }} · 球面直线距离（不代表路程）
        </span>
      </h3>

      <div class="railhead">
        <span class="muted" style="font-size:12px">点行看详情 · 勾选左侧方块加入对比 · 严格匹配（结果均满足全部条件）</span>
        <select class="ctl sortctl" :value="store.query.sort"
                title="排序方式只改变结果顺序，不改变筛选条件"
                @change="applySort($event.target.value)">
          <option value="score">默认排序</option>
          <option value="distance">距离（近 → 远）</option>
          <option value="level">医院等级</option>
          <option value="depts">科室收录量</option>
          <option value="name">机构名称</option>
        </select>
      </div>

      <div v-if="store.items.length" class="listwrap">
        <table class="tbl">
          <thead>
            <tr>
              <th style="width:34px"></th>
              <th>机构名称 / 地址</th>
              <th style="width:76px">等级</th>
              <th style="width:76px">办别</th>
              <th style="width:82px">类型</th>
              <th style="width:104px">科室</th>
              <th style="width:96px">距参考点</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in store.items" :key="r.id"
                :class="{ sel: store.picks.includes(String(r.id)) }"
                @click="store.openDrawer(r.id)">
              <td @click.stop>
                <input type="checkbox" :checked="store.picks.includes(String(r.id))"
                       title="加入对比" @change="store.togglePick(r.id)" />
              </td>
              <td>
                <div class="name">{{ r.name }}
                  <!-- 重点专科短徽标：有收录才显示；未收录的说明放详情抽屉，不逐行挂「0 项」 -->
                  <span v-if="(r.key_specialty_count || 0) > 0" class="ksc"
                        title="数据集收录的重点专科数（国家 / 市级临床重点专科名单）">{{ r.key_specialty_count }} 重点专科</span>
                </div>
                <div class="sub">
                  {{ r.district }}<template v-if="r.addr"> · {{ r.addr }}</template>
                  <template v-if="r.feature"> · 特色：{{ r.feature }}</template>
                </div>
              </td>
              <td><span class="badge" :class="lvClass(r.level)">{{ r.level || '—' }}</span></td>
              <td><span class="badge" :class="ownClass(r.ownership)">{{ r.ownership || '未标注' }}</span></td>
              <td>{{ r.category || '—' }}</td>
              <td :title="deptTip(r)">{{ deptText(r)
                }}<span v-if="deptSuffix(r)" class="muted" style="font-size:10px">·{{ deptSuffix(r) }}</span></td>
              <td :title="distTip(r)">{{ distText(r) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty">
        {{ store.loading ? '加载中…' : '没有符合条件的机构，试试放宽筛选条件' }}
      </div>

      <div class="pager">
        <span class="info">
          第 {{ store.query.page }} / {{ store.totalPages }} 页 · 每页
          <select class="ctl" style="min-height:26px;padding:2px 6px;display:inline-block;width:auto"
                  :value="store.query.pageSize" @change="store.setPageSize($event.target.value)">
            <option :value="20">20</option>
            <option :value="50">50</option>
            <option :value="100">100</option>
          </select>
          条
        </span>
        <button class="btn sm" type="button" :disabled="store.query.page <= 1" @click="store.gotoPage(1)">首页</button>
        <button class="btn sm" type="button" :disabled="store.query.page <= 1" @click="store.gotoPage(store.query.page - 1)">上一页</button>
        <button class="btn sm" type="button" :disabled="store.query.page >= store.totalPages" @click="store.gotoPage(store.query.page + 1)">下一页</button>
        <button class="btn sm" type="button" :disabled="store.query.page >= store.totalPages" @click="store.gotoPage(store.totalPages)">末页</button>
      </div>
    </div>

    <div v-if="store.picks.length" class="pickbar">
      <span>已选 <b>{{ store.picks.length }}</b> 家（最多 4 家）</span>
      <button class="btn sm primary" type="button" @click="store.openCompare()">横向对比</button>
      <button class="btn sm ghost" type="button" @click="store.clearPicks()">清空</button>
    </div>
  </div>
</template>

<script setup>
import FilterBar from '../components/FilterBar.vue'
import { useDataStore } from '../store'
import { deptText, deptTip, deptSuffix } from '../deptLabel'

const store = useDataStore()
const fmt = (n) => (n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString())

// 等级配色沿用项目语义色：三级=主色、二级=青、一级=橙、其他=中性
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
// 排序：改排序回到第 1 页再查（与改条件同一套语义）
function applySort(v) { store.setQuery({ sort: v }) }
// 距离列：坐标精度标识与单文件形态一致——high 直显，其余加「约」；
// title 里写清参考点与「直线距离，不代表路程」。
function distText(r) {
  if (r.distance_km === null || r.distance_km === undefined) return '—'
  return (r.coord_precision === 'high' ? '' : '约 ') + r.distance_km + ' km'
}
function distTip(r) {
  const base = store.base ? store.base.name : '天安门（市中心）'
  if (r.distance_km === null || r.distance_km === undefined) return '该机构无坐标，暂不参与距离排序'
  return '距' + base + '的球面直线距离' + (r.coord_precision === 'high' ? '' : '（坐标为粗精度，值为估算）') + '，不代表路程'
}
</script>
