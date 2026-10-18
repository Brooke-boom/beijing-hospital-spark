<template>
  <div class="panel">
    <h3>
      机构列表 <span class="tag">共 {{ fmt(store.total) }} 家</span>
      <span class="muted" style="margin-left:auto">
        {{ store.base ? '距离基于「' + store.base.name + '」' : '距离基于天安门（市中心）' }}
      </span>
    </h3>

    <div class="listwrap" v-if="store.items.length">
      <table class="tbl">
        <thead>
          <tr>
            <th style="width:34px"></th>
            <th>机构名称 / 地址</th>
            <th style="width:74px">等级</th>
            <th style="width:74px">办别</th>
            <th style="width:80px">类型</th>
            <th style="width:104px">科室</th>
            <th style="width:96px">距参考点</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in store.items" :key="r.id" @click="store.openDrawer(r.id)"
              :class="{ sel: store.picks.includes(String(r.id)) }">
            <td @click.stop>
              <input type="checkbox" :checked="store.picks.includes(String(r.id))"
                     @change="store.togglePick(r.id)" title="加入对比" />
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
            <td :title="distTip(r)">{{ r.distance_km === null || r.distance_km === undefined ? '—' : (r.coord_precision === 'high' ? '' : '约 ') + r.distance_km + ' km' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else class="empty">
      {{ store.loading ? '加载中…' : '没有符合条件的机构，试试放宽筛选条件' }}
    </div>

    <div class="pager">
      <span class="info">
        第 {{ store.query.page }} / {{ store.totalPages }} 页 ·
        每页
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
</template>

<script setup>
import { useDataStore } from '../store'
import { deptText, deptTip, deptSuffix } from '../deptLabel'
const store = useDataStore()
const fmt = (n) => (n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString())

// 等级配色：三级=红、二级=橙、一级=绿、其他=中性（与项目整体语义色一致）
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
// 距离列：粗精度坐标加「约」，title 写清参考点（与 InstitutionsView 同一口径）
function distTip(r) {
  const base = store.base ? store.base.name : '天安门（市中心）'
  if (r.distance_km === null || r.distance_km === undefined) return '该机构无坐标，暂不参与距离排序'
  return '距' + base + '的球面直线距离' + (r.coord_precision === 'high' ? '' : '（坐标为粗精度，值为估算）') + '，不代表路程'
}
</script>
