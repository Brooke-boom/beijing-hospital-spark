<template>
  <div class="page">
    <div class="panel">
      <h3>系统说明 <span class="tag">Spark + HDFS + MySQL + Flask + Vue</span></h3>
      <div class="muted">
        本页信息全部由 <code>GET /api/about</code> 返回，与后端真实运行状态一致。
      </div>
      <div class="hero2">
        <div class="h2t">
          <div class="h2title">北京市医疗机构资源整合与多维筛选可视化系统</div>
          <div class="h2sub">
            面向北京市 9,789 家医疗机构的多源数据整合、七个维度筛选、距离与等级排序、
            协作网络分析与机构详情展示。
          </div>
        </div>
        <div class="h2stat">
          <div><span>数据快照</span><b>{{ snapshot }}</b></div>
          <div><span>机构总数</span><b>{{ fmt(c.institutions) }}</b></div>
          <div><span>落库表</span><b>{{ fmt(c.tables) }}</b></div>
          <div><span>导诊知识库</span><b>{{ fmt(c.triage_dict) }}</b></div>
        </div>
      </div>
    </div>

    <div class="split">
      <div class="panel">
        <h3>技术栈与职责 <span class="tag">每一层都真实落地</span></h3>
        <div class="layers">
          <div v-for="t in STACK" :key="t.name" class="layer" :class="t.cls">
            <div class="lc">{{ t.short }}</div>
            <div>
              <div class="ln">{{ t.name }}</div>
              <div class="ld">{{ t.desc }}</div>
            </div>
            <div class="lstore">{{ t.ver }}</div>
          </div>
        </div>
      </div>

      <div class="panel">
        <h3>七维筛选与排序 <span class="tag">核心功能</span></h3>
        <div class="kv">
          <div class="k">① 关键词</div><div>机构名称模糊匹配</div>
          <div class="k">② 区域</div><div>16 个行政区</div>
          <div class="k">③ 等级</div><div>三级 / 二级 / 一级 / 未定级（应参评口径）</div>
          <div class="k">④ 类型</div><div>医院 / 诊所 / 门诊部 / 妇幼保健 / 急救中心 / 体检中心 / 其他</div>
          <div class="k">⑤ 科室</div><div>按机构实际开展的诊疗科室</div>
          <div class="k">⑥ 协作网络</div><div>儿科医联体 / 卒中中心 / 危重新生儿 / 危重孕产妇</div>
          <div class="k">⑦ 距离基准</div><div>自定义起始地址 → 地理编码 → Haversine 距离</div>
        </div>
        <h3 style="font-size:13px;margin:16px 0 8px">排序口径</h3>
        <div class="kv">
          <div class="k">条件匹配度</div><div>等级权重 0.5 + 距离权重 0.3 + 科室权重 0.2（归一化加权）</div>
          <div class="k">距离</div><div>基于设定基准点的 Haversine 球面距离，近 → 远</div>
          <div class="k">医院等级</div><div>三级 → 二级 → 一级 → 未定级，同级按距离升序</div>
          <div class="k">科室数量</div><div>按开展科室数降序（资源丰富度代理指标）</div>
          <div class="k">机构名称</div><div>按机构名称升序，便于按字面快速定位</div>
        </div>
      </div>
    </div>

    <div class="panel">
      <h3>数据来源与合规 <span class="tag">{{ sources.length }} 个渠道</span></h3>
      <div class="srclist">
        <a v-for="s in sources" :key="s.name" class="srccard" :href="s.url" target="_blank" rel="noopener">
          <div class="sn">{{ s.name }}</div>
          <div class="sd">{{ s.desc }}</div>
        </a>
      </div>
      <div class="muted" style="margin-top:10px;font-size:12px">
        系统仅使用公开渠道数据，不做医疗建议；机构信息可能存在变更，请以官方发布为准。
        预约挂号平台仅做入口链接跳转，不抓取任何号源数据。
      </div>
    </div>

    <div class="panel">
      <h3>前端双形态 <span class="tag">Vue 工程 + 零依赖离线单文件</span></h3>
      <div class="grid2" style="margin-top:10px">
        <div class="notice">
          <b>在线形态（Vue 3）：</b>本页即 Vue 单页应用，通过 <code>/api/*</code> 调 Flask，
          数据实时来自 MySQL。开发期用 Vite 代理，生产由 Flask 同源托管构建产物。
        </div>
        <div class="notice">
          <b>离线兜底（单文件）：</b><code>dashboard_offline.html</code> 把快照数据与 ECharts
          全部内联，双击即可打开，无需后端与网络，是答辩现场的兜底方案。
        </div>
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
const sources = computed(() => about.value.sources || [])
const snapshot = computed(() => about.value.updated_at || '—')

const STACK = [
  { short: 'HDFS', name: '分布式文件系统', ver: '3.3.6', cls: 'l-ods',
    desc: 'ODS 原始层 / DWD 明细层 / DWS 汇总层以 Parquet 存储，作为全链路唯一数据源' },
  { short: 'SPARK', name: '分布式计算引擎', ver: '3.5.3', cls: 'l-dwd',
    desc: '数仓分层作业与五个维度汇总，按维度拆分作业文件，支持 --only / --from 断点重跑' },
  { short: 'MYSQL', name: '关系型数据库', ver: '8.x', cls: 'l-dws',
    desc: '仅承载 ADS 服务层与维表（19 张表），建复合索引支撑 Flask 多维筛选' },
  { short: 'FLASK', name: '后端服务', ver: 'Python 3', cls: 'l-ads',
    desc: '22 个 REST 接口：筛选 / 排序 / 详情 / 概览 / 对比 / 地理编码 / 导诊 / 埋点' },
  { short: 'VUE', name: '前端框架', ver: 'Vue 3 + Vite', cls: 'l-dwd',
    desc: '单页应用，Pinia 状态管理、Vue Router 路由，ECharts 渲染地图与多维图表' },
  { short: 'DOCKER', name: '容器编排', ver: 'Compose', cls: 'l-ods',
    desc: '5 个容器：HDFS NameNode/DataNode、Spark Master/Worker、MySQL，一键拉起' }
]

const fmt = (n) => (n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString())
</script>
