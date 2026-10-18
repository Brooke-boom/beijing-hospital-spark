<template>
  <div v-if="store.drawer.open" class="scrim" @click.self="store.closeDrawer()">
    <div class="drawer">
      <button class="btn ghost sm close" type="button" @click="store.closeDrawer()">关闭</button>

      <div v-if="store.drawer.loading" class="center">加载机构详情…</div>
      <div v-else-if="!d" class="center">未取到详情</div>

      <template v-else-if="d.error">
        <h2>详情加载失败</h2>
        <div class="notice">{{ d.error }}</div>
      </template>

      <!-- 响应结构（web/app.py /api/inst/<id>/detail）：
           base = 主档字段 · contact = 联系与坐标 · specialty = 重点专科分级
           networks / depts / links / around* = 协作网络、科室明细、就诊入口、周边配套。
           分区顺序：① 名称/类别/等级/办别 → ② 地址/联系/距离 → ③ 科室/来源/备注 → ④ 对标（折叠） -->
      <template v-else-if="base && contact">
        <!-- ① 名称 / 类别 / 等级 / 办别 -->
        <h2>{{ base.name }}</h2>
        <div class="muted">
          {{ base.district }}
          <template v-if="base.category"> · {{ base.category }}</template>
          <template v-if="base.category_sub"> · {{ base.category_sub }}</template>
        </div>
        <div class="row" style="margin:12px 0;gap:7px">
          <span class="badge" :class="lvClass(base.level)">{{ base.level || '—' }}</span>
          <span v-if="base.level_sub" class="badge l0">{{ base.level_sub }}</span>
          <span class="badge" :class="ownClass(base.ownership)">{{ base.ownership || '未标注' }}</span>
          <span v-if="base.grade_scope === 'not_applicable'" class="badge na">不适用医院分级</span>
          <span v-if="contact.coord_precision" class="badge l0" :title="coordTip">坐标：{{ coordLabel }}</span>
        </div>

        <!-- ② 地址 / 联系 / 距离 -->
        <div class="distbox">
          <div class="dv">{{ distText }}</div>
          <div class="dn">
            距 {{ baseName }} 的球面直线距离（Haversine 公式），不代表路程{{ precisionNote }}
          </div>
        </div>
        <div class="kv">
          <div class="k">地址</div><div>{{ contact.addr || '—' }}</div>
          <div class="k">电话</div><div>{{ contact.phone || '—' }}</div>
          <div v-if="contact.website" class="k">网址</div>
          <div v-if="contact.website"><a :href="contact.website" target="_blank" rel="noopener">{{ contact.website }}</a></div>
          <div v-if="contact.traffic" class="k">交通</div>
          <div v-if="contact.traffic">{{ contact.traffic }}</div>
        </div>

        <!-- ③ 科室 / 来源 / 备注 -->
        <h3 class="dsec">科室与资源</h3>
        <div class="kv">
          <div class="k">科室数量</div>
          <div>
            {{ deptText(base) }}
            <div class="muted" style="font-size:11px;margin-top:3px">{{ deptExplain(base) }}</div>
          </div>
          <div class="k">重点专科</div>
          <div>
            <template v-if="keyCount">国家级 {{ natCount }} 项 · 市级 {{ munCount }} 项</template>
            <!-- 未收录不写成「0 项」：0 既有"真实未入选"也有"数据源未覆盖"，
                 统一口径为「本数据集未收录」，与列表徽标的显隐规则一致 -->
            <span v-else class="muted">本数据集未收录</span>
            <div v-if="!keyCount" class="muted" style="font-size:11px;margin-top:3px">
              国家 / 市级临床重点专科名单未收录该机构（如军队医院不在地方公开名单内），故不展示项数
            </div>
          </div>
          <div class="k">协作网络</div>
          <div>{{ (d.networks && d.networks.length) ? d.networks.join('、') : '未纳入' }}</div>
          <div v-if="base.ownership_basis" class="k">办别依据</div>
          <div v-if="base.ownership_basis">{{ base.ownership_basis }}</div>
        </div>

        <template v-if="nat.length || mun.length || feat.length">
          <h3 class="dsec">重点专科 / 特色</h3>
          <div v-if="nat.length" class="notice" style="margin-bottom:8px">
            <b>国家级：</b>{{ nat.join('、') }}
          </div>
          <div v-if="mun.length" class="notice" style="margin-bottom:8px">
            <b>市级：</b>{{ mun.join('、') }}
          </div>
          <div v-if="feat.length" class="notice" style="margin-bottom:8px">
            <b>擅长科室：</b>{{ feat.join('、') }}
          </div>
        </template>

        <h3 class="dsec">
          科室清单（最多 60 条）
          <span v-if="deptListKind(base) === 'derived'" class="tag">推导清单</span>
          <span v-else-if="deptListKind(base) === 'nodept'" class="tag">诊疗科目</span>
        </h3>
        <div v-if="deptListKind(base) === 'derived'" class="notice" style="margin-bottom:8px">
          该机构应当收录科室设置，但源数据与在线核实均未取得，以下名录系按「机构名称 / 机构类型职能」
          推导，仅用于科室维度检索，<b>不代表该院真实科室构成</b>。
        </div>
        <div v-else-if="deptListKind(base) === 'nodept'" class="notice" style="margin-bottom:8px">
          该类机构（{{ base.category_fine || base.category }}）{{ deptExplain(base) }}
          以下为按机构类型归入的<b>诊疗科目</b>，仅用于科室维度检索。
        </div>
        <div class="chips">
          <span v-for="x in (d.depts || [])" :key="x.dept_name" class="chip"
                :style="x.is_key_specialty ? 'border-color:rgba(var(--acc-rgb),.5)' : ''">
            {{ x.dept_name }}<template v-if="x.is_key_specialty"> · 重点</template>
            <span v-if="x.source" class="muted" style="font-size:10.5px">{{ x.source }}</span>
          </span>
          <span v-if="!(d.depts || []).length" class="muted">暂无科室明细</span>
        </div>

        <!-- ④ 同区同类距离对标：默认折叠，按需展开（图表让位给文字信息，避免抽屉过长） -->
        <details class="morefold" style="margin-top:16px">
          <summary>同区同类距离对标<span class="morefold-hint">同一行政区 · 同一机构类型 · 按距参考点由近到远</span></summary>
          <div class="peers" v-if="peers.length">
            <div v-for="p in peers" :key="p.id" class="p" @click="store.openDrawer(p.id)">
              <span class="pn">{{ p.name }}</span>
              <span class="pl">{{ p.level || '—' }}</span>
              <span class="pd">{{ p.distance_km == null ? '—' : (p.coord_precision === 'high' ? '' : '约 ') + p.distance_km + ' km' }}</span>
            </div>
          </div>
          <div v-else class="muted" style="padding:8px 0">{{ peersNote }}</div>
        </details>

        <h3 class="dsec">就诊入口</h3>
        <div class="chips">
          <a v-for="l in (d.links || [])" :key="l.url || l.name" class="chip" :href="l.url"
             target="_blank" rel="noopener">{{ l.name }}</a>
          <span v-if="!(d.links || []).length" class="muted">暂无</span>
        </div>

        <h3 class="dsec">周边配套</h3>
        <div v-if="d.around_enabled">
          <div v-for="(v, k) in (d.around || {})" :key="k" class="kv" style="margin:0 0 4px">
            <div class="k">{{ { metro: '地铁站', parking: '停车场', bus: '公交站' }[k] || k }}</div>
            <div>
              <template v-if="v && v.length">
                {{ v.map((x) => x.name + (x.distance ? '（' + x.distance + '）' : '')).join('、') }}
              </template>
              <span v-else class="muted">—</span>
            </div>
          </div>
          <div v-if="!d.around_online" class="muted">（周边数据未取到在线结果，显示为空属正常）</div>
        </div>
        <!-- 离线部署没有高德密钥，这里必须明说"不可用"，不能让读者以为是真的没有配套 -->
        <div v-else class="muted">
          周边配套（地铁 / 公交 / 停车场）需要在线地图服务：当前离线部署未配置密钥，该模块不可用；
          机构主档信息不受影响。
        </div>
      </template>

      <div v-else class="center">详情数据结构不完整</div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useDataStore, DEFAULT_BASE } from '../store'
import api from '../api'
import { deptText, deptExplain, deptListKind } from '../deptLabel'

const store = useDataStore()
const d = computed(() => store.drawer.data)
const base = computed(() => (d.value && d.value.base) || null)
const contact = computed(() => (d.value && d.value.contact) || null)
const nat = computed(() => ((d.value && d.value.specialty && d.value.specialty.national) || []))
const mun = computed(() => ((d.value && d.value.specialty && d.value.specialty.municipal) || []))
const feat = computed(() => ((d.value && d.value.specialty && d.value.specialty.feature) || []))
const keyCount = computed(() => (d.value && d.value.specialty && d.value.specialty.key_count) || 0)
const natCount = computed(() => (d.value && d.value.specialty && d.value.specialty.national_count) || 0)
const munCount = computed(() => (d.value && d.value.specialty && d.value.specialty.municipal_count) || 0)

// ---- 距离：与列表同一口径（Haversine 球面直线，粗精度加「约」）----
function haversine(lng1, lat1, lng2, lat2) {
  const R = 6371.0088
  const rad = (x) => (x * Math.PI) / 180
  const dLat = rad(lat2 - lat1)
  const dLng = rad(lng2 - lng1)
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(a))
}
const baseName = computed(() => (store.base ? store.base.name : '天安门（市中心）'))
const distKm = computed(() => {
  const c = contact.value
  if (!c || c.lng == null || c.lat == null) return null
  const b = store.base || DEFAULT_BASE
  return haversine(b.lng, b.lat, c.lng, c.lat)
})
const distText = computed(() => {
  if (distKm.value == null) return '暂无坐标'
  const v = Math.round(distKm.value * 10) / 10
  return (contact.value.coord_precision === 'high' ? '' : '约 ') + v.toFixed(1) + ' km'
})
const precisionNote = computed(() => {
  const p = contact.value && contact.value.coord_precision
  if (p === 'high') return '（坐标为高精度）'
  if (p === 'rough') return '（坐标为粗精度，值为估算）'
  return ''
})
const COORD_LABEL = { high: '高精度', rough: '粗精度', missing: '缺失' }
const coordLabel = computed(() => COORD_LABEL[contact.value && contact.value.coord_precision] ||
  (contact.value && contact.value.coord_precision) || '—')
const coordTip = computed(() => {
  const p = contact.value && contact.value.coord_precision
  if (p === 'high') return '坐标来自精确解析，可用于距离排序与半径筛选'
  if (p === 'rough') return '坐标为区域级估算，仅作参考，不参与半径筛选'
  return ''
})

// ---- 同区同类对标：真实接口数据（行政区 + 机构类型 + 距离排序），不造假样例 ----
const peers = ref([])
const peersNote = ref('')
watch(() => store.drawer.data, async (dv) => {
  peers.value = []
  peersNote.value = ''
  const b = dv && dv.base
  const c = dv && dv.contact
  if (!b || !c || c.lng == null || c.lat == null) {
    peersNote.value = '该机构暂无坐标，无法计算距离对标。'
    return
  }
  try {
    const basePt = store.base || DEFAULT_BASE
    const r = await api.institutions({
      district: b.district || undefined,
      category: b.category || undefined,
      sort: 'distance', page: 1, page_size: 8,
      lng: basePt.lng, lat: basePt.lat
    })
    peers.value = (r.items || [])
      .filter((x) => String(x.id) !== String(b.id))
      .slice(0, 6)
    if (!peers.value.length) peersNote.value = '同区同类型暂未检索到其他机构。'
  } catch (e) {
    peersNote.value = '对标数据加载失败：' + e.message
  }
})

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
