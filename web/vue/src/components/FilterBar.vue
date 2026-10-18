<template>
  <div class="panel">
    <h3>条件筛选 <span class="tag">多维</span>
      <button class="btn ghost sm" style="margin-left:auto" type="button"
              :disabled="!store.hasConditions" @click="resetAll">恢复默认视图</button>
    </h3>

    <!-- 常用筛选：默认展示，覆盖最高频的五个维度（关键词 / 区域 / 类型 / 等级 / 科室） -->
    <div class="filters">
      <div class="field wide2">
        <label>关键词（机构名 / 地址）</label>
        <input class="ctl" type="text" v-model.trim="kw" placeholder="如：协和 / 儿童医院"
               @keyup.enter="applyKw" />
      </div>
      <div class="field">
        <label>区域</label>
        <select class="ctl" v-model="store.query.district" @change="apply('district')">
          <option value="">全部 16 区</option>
          <option v-for="d in store.meta.districts" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>
      <div class="field">
        <label>类型</label>
        <select class="ctl" v-model="store.query.category" @change="apply('category')">
          <option value="">全部类型</option>
          <option v-for="c in store.meta.categories" :key="c.category" :value="c.category">
            {{ c.category }}（{{ c.inst_count }}）
          </option>
        </select>
      </div>
      <div class="field">
        <label>等级</label>
        <select class="ctl" v-model="store.query.level" @change="apply('level')">
          <option value="">全部等级</option>
          <option v-for="l in store.meta.levels" :key="l" :value="l">{{ l }}</option>
        </select>
      </div>
      <!-- 科室是本系统的核心筛选项（科室证据 / 科室收录量），从二级折叠提到常用行：
           第二行正好三个字段填满整行，右下角不再空出 1/3 行宽。 -->
      <div class="field">
        <label>科室</label>
        <select class="ctl" v-model="store.query.dept" @change="apply('dept')">
          <option value="">全部科室</option>
          <option v-for="d in store.meta.depts" :key="d.dept_name" :value="d.dept_name">
            {{ d.dept_name }}（{{ d.hospital_count }}）
          </option>
        </select>
      </div>
    </div>

    <!-- 更多筛选：默认折叠，只留低频三项（等级等次 / 来源证据 / 协作网络） -->
    <details class="morefold">
      <summary>更多筛选<span class="morefold-hint">等级等次 · 来源证据 · 协作网络</span></summary>
      <div class="filters">
        <div class="field">
          <label>等级等次</label>
          <select class="ctl" v-model="store.query.level_sub" @change="apply('level_sub')"
                  title="医院等级等次（甲等 / 乙等 / 丙等）。三甲 = 三级且甲等的组合条件">
            <option value="">不限等次</option>
            <option value="甲等">甲等</option>
            <option value="乙等">乙等</option>
            <option value="丙等">丙等</option>
          </select>
        </div>
        <div class="field">
          <label>科室来源证据</label>
          <select class="ctl" v-model="store.query.dept_evidence" @change="apply('dept_evidence')"
                  title="名称与规则推断的科室映射不计入证据；本项只保留有来源记录（官方名单 / 在线核实 / 重点专科）的机构">
            <option value="">全部映射（含推断）</option>
            <option value="recorded">仅有来源记录</option>
          </select>
        </div>
        <div class="field">
          <label>协作网络</label>
          <select class="ctl" v-model="store.query.net" @change="apply('net')">
            <option value="">全部网络</option>
            <option v-for="n in store.meta.nets" :key="n.value" :value="n.value">{{ n.label }}</option>
          </select>
        </div>
      </div>
    </details>

    <!-- 距离区：参考点、定位与半径集中在一处 -->
    <div class="filters distgroup" style="margin-top:12px">
      <div class="field distfield">
        <label>距离参考点（默认按天安门（市中心）计算直线距离）</label>
        <div class="rangebox">
          <input class="ctl" type="text" v-model.trim="baseQ" placeholder="输入地址，如：中关村 / 回龙观"
                 title="支持 地址 / 区名 / 机构名；解析后成为距离计算起点" @keyup.enter="doGeocode" />
          <button class="btn" type="button" :disabled="geocoding" @click="doGeocode">
            {{ geocoding ? '解析中…' : '设置参考点' }}
          </button>
          <button class="btn" type="button" title="调用浏览器定位，把「我的位置」作为参考点（需授权）"
                  @click="store.locateMe()">使用我的位置</button>
          <button v-if="store.base" class="btn ghost" type="button"
                  title="清除参考点，距离恢复按天安门（市中心）计算" @click="store.setBase(null)">恢复天安门</button>
        </div>
      </div>
      <div class="field">
        <label>直线半径（km，仅高精度坐标）</label>
        <input class="ctl" type="number" min="0.01" max="200" step="0.1" v-model="store.query.radius"
               @change="apply('radius')" placeholder="不限"
               title="距参考点的球面直线距离半径（0 – 200 km）。仅使用 high 精度坐标的机构" />
      </div>
    </div>

    <!-- 快捷入口：一键套用高频条件组合 -->
    <div class="presetbar">
      <span class="plabel">快捷入口</span>
      <button class="preset" type="button" title="筛选医院等级 = 三级" @click="preset({ level: '三级' })">三级医院</button>
      <button class="preset" type="button" title="筛选医院等级 = 二级" @click="preset({ level: '二级' })">二级医院</button>
      <!-- 「基层」≠「一级医院」：一级是医院层级，基层还包括诊所 / 村卫生室 /
           社区卫生服务站等类型（按机构类型筛）。这里只写准确的那个。 -->
      <button class="preset" type="button"
              title="一级医院（医院层级）；诊所 / 村卫生室 / 社区卫生服务站等基层机构请按「机构类型」筛选"
              @click="preset({ level: '一级' })">一级医院</button>
      <button class="preset" type="button" title="三级医院 + 按距参考点由近到远排序"
              @click="preset({ level: '三级', sort: 'distance' })">离参考点最近的三级</button>
      <button class="preset" type="button" title="纳入卒中中心协作网络" @click="preset({ net: 'stroke' })">卒中中心</button>
      <button class="preset" type="button"
              title="按科室收录量排序：数值是数据集收录到的科室明细条数，不代表医疗能力或真实科室完整程度"
              @click="preset({ sort: 'depts' })">科室收录量排序</button>
      <span class="preset-sp"></span>
    </div>

    <div class="chips" style="margin-top:12px">
      <span v-if="!store.chips.length" class="muted">未设置筛选条件（显示全部机构，按默认排序）</span>
      <span v-for="c in store.chips" :key="c.key" class="chip">
        {{ c.label }}：{{ c.value }}
        <button type="button" :title="'移除该条件：' + c.label" @click="store.setQuery({ [c.key]: '' })">×</button>
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useDataStore } from '../store'
import api from '../api'

const store = useDataStore()
const kw = ref(store.query.q)
const baseQ = ref('')
const geocoding = ref(false)

watch(() => store.query.q, (v) => { if (v !== kw.value) kw.value = v })

function applyKw() { store.setQuery({ q: kw.value }) }
function apply() { /* v-model 已改 query，这里只触发查询 */ store.setQuery({}) }

// 快捷入口与「恢复默认视图」：改条件后统一回到第 1 页再查
function preset(patch) { store.setQuery(patch) }
function resetAll() {
  store.resetQuery()
  store.setBase(null)
}

async function doGeocode() {
  if (!baseQ.value) { store.notify('请输入地址'); return }
  geocoding.value = true
  try {
    const r = await api.geocode(baseQ.value)
    // 后端 /api/geocode 返回 {ok, lng, lat, name} 或 {ok:false, error}
    if (r && (r.ok === false || r.lng === undefined || r.lng === null)) {
      store.notify(r.message || r.error || '未解析到该地址')
    } else {
      await store.setBase({ name: r.name || baseQ.value, lng: r.lng, lat: r.lat })
      store.notify('基准点已设为：' + (r.name || baseQ.value))
    }
  } catch (e) {
    store.notify('地址解析失败：' + e.message)
  } finally {
    geocoding.value = false
  }
}
</script>
