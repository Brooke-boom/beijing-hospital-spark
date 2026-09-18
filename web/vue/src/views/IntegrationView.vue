<template>
  <div class="page">
    <div class="kpis k4">
      <div class="card hero">
        <div class="l">整合后机构总数</div>
        <div class="v">{{ fmt(c.institutions) }}</div>
        <div class="s">去重合并后的干净机构主表</div>
      </div>
      <div class="card k2">
        <div class="l">科室关系记录</div>
        <div class="v">{{ fmt(c.dept_relations) }}</div>
        <div class="s">机构 × 科室 明细关系</div>
      </div>
      <div class="card k2">
        <div class="l">专科名单记录</div>
        <div class="v">{{ fmt(c.specialty_rows) }}</div>
        <div class="s">国家 / 市 / 区级专科公示明细</div>
      </div>
      <div class="card k2">
        <div class="l">落库表数量</div>
        <div class="v">{{ fmt(c.tables) }}</div>
        <div class="s">MySQL hospital 库（ODS 已上移 HDFS）</div>
      </div>
    </div>

    <div class="panel">
      <h3>数据整合流水线 <span class="tag">8 个阶段 · 真实执行</span>
        <button class="btn ghost sm" style="margin-left:auto" type="button" @click="store.loadOverview(true)">
          刷新
        </button>
      </h3>
      <div class="flow">
        <div v-for="(s, i) in pipeline" :key="s.step" class="flowstep">
          <div class="num">{{ s.step }}</div>
          <div class="body">
            <div class="ft">{{ s.name }}<span class="tool">{{ s.tool }}</span></div>
            <div class="fd">{{ s.desc }}</div>
          </div>
          <div v-if="i < pipeline.length - 1" class="arrow">→</div>
        </div>
      </div>
    </div>

    <div class="split">
      <div class="panel">
        <h3>数仓分层 <span class="tag">HDFS Parquet + MySQL 服务层</span></h3>
        <div class="layers">
          <div v-for="L in LAYERS" :key="L.code" class="layer" :class="L.cls">
            <div class="lc">{{ L.code }}</div>
            <div>
              <div class="ln">{{ L.name }}</div>
              <div class="ld">{{ L.desc }}</div>
            </div>
            <div class="lstore">{{ L.store }}</div>
          </div>
        </div>
        <div class="muted" style="margin-top:10px;font-size:12px">
          只有 ADS 服务层结果落 MySQL 供 Flask 查询；ODS/DWD/DWS 均以 Parquet 存于 HDFS，
          避免把明细数据搬进关系库。
        </div>
      </div>

      <div class="panel">
        <h3>数据来源 <span class="tag">公开渠道</span></h3>
        <div class="srclist">
          <a v-for="s in sources" :key="s.name" class="srccard" :href="s.url" target="_blank" rel="noopener">
            <div class="sn">{{ s.name }}</div>
            <div class="sd">{{ s.desc }}</div>
          </a>
        </div>
        <div class="muted" style="margin-top:10px;font-size:12px">
          源文件去重后 70 个（CSV / XLSX）。预约挂号平台仅做链接跳转，不抓取号源数据。
        </div>
      </div>
    </div>

    <div class="panel">
      <h3>MySQL 服务层表清单 <span class="tag">共 {{ warehouse.length }} 张</span></h3>
      <div class="listwrap" style="max-height:380px">
        <table class="tbl">
          <thead>
            <tr>
              <th style="width:70px">层</th>
              <th style="width:270px">表名</th>
              <th style="width:110px">表内行数</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="w in warehouse" :key="w.name">
              <td>
                <span class="badge" :class="layerClass(w.name)">{{ layerOf(w.name) }}</span>
              </td>
              <td><span class="name" style="font-family:ui-monospace,Menlo,monospace;font-size:12.5px">{{ w.name }}</span></td>
              <td>{{ fmt(w.rows_) }}</td>
              <td class="muted">{{ w.comment || '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useDataStore } from '../store'

const store = useDataStore()
const about = computed(() => store.overview.about || {})
const c = computed(() => about.value.counts || {})
const pipeline = computed(() => about.value.pipeline || [])
const sources = computed(() => about.value.sources || [])
const warehouse = computed(() => about.value.warehouse || [])

const LAYERS = [
  { code: 'ODS', name: '原始层', desc: '治理后 CSV 原样入湖，不做任何加工，保证可回溯', store: 'HDFS Parquet', cls: 'l-ods' },
  { code: 'DWD', name: '明细清洗层', desc: '字段标准化、等级/办别归一（COALESCE 在线核实值）、坐标校验', store: 'HDFS Parquet', cls: 'l-dwd' },
  { code: 'DWS', name: '五维汇总层', desc: '空间 / 类型等级 / 科室 / 协作网络 / 时间 五个维度的宽表汇总', store: 'HDFS Parquet', cls: 'l-dws' },
  { code: 'ADS', name: '服务层', desc: '面向接口的检索主表与各类概览表，建复合索引后由 Flask 直查', store: 'MySQL', cls: 'l-ads' }
]

const LAYER_BADGE = { ads: 'l3', dws: 'l2', dwd: 'l1', dim: 'l0', fact: 'pub' }
function layerOf(name) {
  if (/^ads_/.test(name)) return 'ADS'
  if (/^dws_/.test(name)) return 'DWS'
  if (/^dwd_/.test(name)) return 'DWD'
  if (/^dim_/.test(name)) return 'DIM'
  if (/^fact_/.test(name)) return 'FACT'
  if (/^ods_/.test(name)) return 'ODS'
  return '其他'
}
function layerClass(name) {
  const k = layerOf(name).toLowerCase()
  return LAYER_BADGE[k] || 'na'
}
const fmt = (n) => (n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString())
</script>
