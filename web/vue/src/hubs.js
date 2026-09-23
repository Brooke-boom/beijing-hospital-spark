import { defineAsyncComponent } from 'vue'

// ============================================================================
// 查阅区（支撑页）定义
// ----------------------------------------------------------------------------
// 原来 7 个平级入口会把"这套系统 = 一堆图表页"的印象放大；改成 4 个支撑页后，
// 每个页面回答一个完整的问题，页内再用子标签切换看法：
//   找机构    → 有哪些机构 / 怎么筛出来
//   资源画像  → 全市资源怎么分布 / 结构如何
//   数据治理  → 数据从哪来 / 质量如何
//   系统说明  → 系统是什么、边界在哪
// 主线（智能筛选）不在这里，它是独立的任务流：一句话进，一份结果出。
// ============================================================================

const InstitutionsView = defineAsyncComponent(() => import('./views/InstitutionsView.vue'))
const FilterView = defineAsyncComponent(() => import('./views/FilterView.vue'))
const OverviewView = defineAsyncComponent(() => import('./views/OverviewView.vue'))
const AnalyticsView = defineAsyncComponent(() => import('./views/AnalyticsView.vue'))
const IntegrationView = defineAsyncComponent(() => import('./views/IntegrationView.vue'))
const QualityView = defineAsyncComponent(() => import('./views/QualityView.vue'))

export const HUBS = {
  find: {
    title: '找机构',
    desc: '查北京任意一家医疗机构：按区、等级、类型、科室逐步收窄，点开看档案，可勾选 2–4 家横向对比。',
    tabs: [
      { k: 'institutions', t: '机构列表', c: InstitutionsView },
      { k: 'filter', t: '条件筛选', c: FilterView }
    ]
  },
  profile: {
    title: '资源画像',
    desc: '把 9,684 家机构当成一个整体来看：数量、等级、办别、区域与科室覆盖的结构是什么样的。',
    tabs: [
      { k: 'overview', t: '总览', c: OverviewView },
      { k: 'analytics', t: '结构分析', c: AnalyticsView }
    ]
  },
  govern: {
    title: '数据治理',
    desc: '这套数据的来路与成色：70 个源文件怎么整合成一张主表、哪些字段可信、哪些是真实数据边界。',
    tabs: [
      { k: 'integration', t: '整合过程', c: IntegrationView },
      { k: 'quality', t: '质量核验', c: QualityView }
    ]
  }
}

// 旧路径 → 新地址的映射，保证之前分享过的深链接仍然能打开。
// 注意：'/filter' 从"找机构·条件筛选子标签"升级成了任务主线本身，
// 因此它不再出现在映射表里——它已经是一个真实路由了。
export const LEGACY_REDIRECT = {
  '/plan': { name: 'filter' },
  '/institutions': { name: 'find', query: { t: 'institutions' } },
  '/overview': { name: 'profile', query: { t: 'overview' } },
  '/analytics': { name: 'profile', query: { t: 'analytics' } },
  '/integration': { name: 'govern', query: { t: 'integration' } },
  '/quality': { name: 'govern', query: { t: 'quality' } }
}
