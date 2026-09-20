<template>
  <div class="panel">
    <h3>条件筛选 <span class="tag">7 维</span>
      <button class="btn ghost sm" style="margin-left:auto" type="button"
              :disabled="!store.hasConditions" @click="store.resetQuery()">重置</button>
    </h3>

    <div class="row" style="align-items:flex-end">
      <div class="field" style="flex:2 1 220px">
        <label>关键词（机构名）</label>
        <input class="ctl" type="text" v-model.trim="kw" placeholder="如：协和 / 儿童医院"
               @keyup.enter="applyKw" />
      </div>
      <div class="field" style="flex:1 1 130px">
        <label>区域</label>
        <select class="ctl" v-model="store.query.district" @change="apply('district')">
          <option value="">全部 16 区</option>
          <option v-for="d in store.meta.districts" :key="d" :value="d">{{ d }}</option>
        </select>
      </div>
      <div class="field" style="flex:1 1 110px">
        <label>等级</label>
        <select class="ctl" v-model="store.query.level" @change="apply('level')">
          <option value="">全部等级</option>
          <option v-for="l in store.meta.levels" :key="l" :value="l">{{ l }}</option>
        </select>
      </div>
      <div class="field" style="flex:1 1 120px">
        <label>类型</label>
        <select class="ctl" v-model="store.query.category" @change="apply('category')">
          <option value="">全部类型</option>
          <option v-for="c in store.meta.categories" :key="c.category" :value="c.category">
            {{ c.category }}（{{ c.inst_count }}）
          </option>
        </select>
      </div>
      <div class="field" style="flex:1 1 140px">
        <label>科室</label>
        <select class="ctl" v-model="store.query.dept" @change="apply('dept')">
          <option value="">全部科室</option>
          <option v-for="d in store.meta.depts" :key="d.dept_name" :value="d.dept_name">
            {{ d.dept_name }}（{{ d.hospital_count }}）
          </option>
        </select>
      </div>
      <div class="field" style="flex:1 1 150px">
        <label>协作网络</label>
        <select class="ctl" v-model="store.query.net" @change="apply('net')">
          <option value="">全部网络</option>
          <option v-for="n in store.meta.nets" :key="n.value" :value="n.value">{{ n.label }}</option>
        </select>
      </div>
    </div>

    <div class="row" style="margin-top:12px">
      <div class="field" style="flex:1 1 150px">
        <label>排序</label>
        <select class="ctl" v-model="store.query.sort" @change="apply('sort')">
          <option value="score">条件匹配度</option>
          <option value="distance">距离（近 → 远）</option>
          <option value="level">医院等级</option>
          <option value="depts">科室数量</option>
          <option value="name">机构名称</option>
        </select>
      </div>
      <div class="field" style="flex:2 1 240px">
        <label>距离基准点（留空则按天安门计算并标注为"距市中心"）</label>
        <div class="row" style="gap:7px;flex-wrap:nowrap">
          <input class="ctl" type="text" v-model.trim="baseQ" placeholder="输入地址，如：天安门 / 中关村"
                 @keyup.enter="doGeocode" style="flex:1" />
          <button class="btn" type="button" :disabled="geocoding" @click="doGeocode">
            {{ geocoding ? '解析中…' : '设定' }}
          </button>
          <button v-if="store.base" class="btn ghost" type="button" @click="store.setBase(null)">清除</button>
        </div>
      </div>
    </div>

    <div class="chips" style="margin-top:12px">
      <span v-if="!store.chips.length" class="muted">未设置筛选条件（显示全部机构，按条件匹配度排序）</span>
      <span v-for="c in store.chips" :key="c.key" class="chip">
        {{ c.label }}：{{ c.value }}
        <button type="button" @click="store.setQuery({ [c.key]: '' })" title="移除该条件">×</button>
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
