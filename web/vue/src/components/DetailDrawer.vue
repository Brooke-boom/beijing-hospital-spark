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

      <template v-else>
        <h2>{{ inst.name }}</h2>
        <div class="muted">
          {{ inst.district }}
          <template v-if="inst.category_norm"> · {{ inst.category_norm }}</template>
          <template v-if="inst.category_sub"> · {{ inst.category_sub }}</template>
        </div>

        <div class="row" style="margin:12px 0;gap:7px">
          <span class="badge" :class="lvClass(inst.level_norm)">{{ inst.level_norm || '—' }}</span>
          <span class="badge" :class="ownClass(inst.ownership)">{{ inst.ownership || '未标注' }}</span>
          <span v-if="inst.grade_scope === 'not_applicable'" class="badge na">不适用医院分级</span>
          <span v-if="inst.coord_precision" class="badge l0">坐标：{{ inst.coord_precision }}</span>
        </div>

        <div class="kv">
          <div class="k">地址</div><div>{{ inst.addr || '—' }}</div>
          <div class="k">电话</div><div>{{ inst.phone || '—' }}</div>
          <div class="k">科室数量</div>
          <div>
            {{ deptText(inst) }}
            <div class="muted" style="font-size:11px;margin-top:3px">{{ deptExplain(inst) }}</div>
          </div>
          <div class="k">重点专科</div>
          <div>
            国家级 {{ inst.national_specialty_count || 0 }} 项 ·
            市级 {{ inst.municipal_specialty_count || 0 }} 项
          </div>
          <div class="k">协作网络</div>
          <div>{{ (d.networks && d.networks.length) ? d.networks.join('、') : '未纳入' }}</div>
          <div v-if="inst.ownership_basis" class="k">办别依据</div>
          <div v-if="inst.ownership_basis">{{ inst.ownership_basis }}</div>
        </div>

        <h3 style="font-size:13px;margin:16px 0 8px">重点专科 / 特色</h3>
        <div v-if="nat" class="notice" style="margin-bottom:8px">
          <b>国家级：</b>{{ nat }}
        </div>
        <div v-if="mun" class="notice" style="margin-bottom:8px">
          <b>市级：</b>{{ mun }}
        </div>
        <div v-if="inst.feature" class="notice" style="margin-bottom:8px">
          <b>擅长科室：</b>{{ inst.feature }}
        </div>
        <div v-if="!nat && !mun && !inst.feature" class="muted">暂无专科标注</div>

        <h3 style="font-size:13px;margin:16px 0 8px">
          科室清单（最多 60 条）
          <span v-if="deptListKind(inst) === 'derived'" class="tag">推导清单</span>
          <span v-else-if="deptListKind(inst) === 'nodept'" class="tag">诊疗科目</span>
        </h3>
        <div v-if="deptListKind(inst) === 'derived'" class="notice" style="margin-bottom:8px">
          该机构应当收录科室设置，但源数据与在线核实均未取得，以下名录系按「机构等级 × 类型」
          或机构名称推导，仅用于科室维度检索，<b>不代表该院真实科室构成</b>。
        </div>
        <div v-else-if="deptListKind(inst) === 'nodept'" class="notice" style="margin-bottom:8px">
          该类机构（{{ inst.category_fine || inst.category }}）{{ deptExplain(inst) }}
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

        <h3 style="font-size:13px;margin:16px 0 8px">周边配套</h3>
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
        <div v-else class="muted">未配置高德密钥，周边配套不可用（不影响主流程）</div>

        <h3 style="font-size:13px;margin:16px 0 8px">就诊入口</h3>
        <div class="chips">
          <a v-for="l in (d.links || [])" :key="l.url || l.name" class="chip" :href="l.url"
             target="_blank" rel="noopener">{{ l.name }}</a>
          <span v-if="!(d.links || []).length" class="muted">暂无</span>
        </div>

        <div v-if="d.status" class="notice" style="margin-top:16px">
          <b>实时状态（模拟）：</b>
          <span v-if="d.status.level">人流 {{ d.status.level }}</span>
          <span v-if="d.status.wait_minutes !== undefined"> · 预计等待 {{ d.status.wait_minutes }} 分钟</span>
          <span v-if="d.status.note"> · {{ d.status.note }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useDataStore } from '../store'
import { deptText, deptExplain, deptListKind } from '../deptLabel'

const store = useDataStore()
const d = computed(() => store.drawer.data)
const inst = computed(() => (d.value && (d.value.inst || d.value.item || d.value)) || {})
const nat = computed(() => (inst.value.national_specialty || '').trim())
const mun = computed(() => (inst.value.municipal_specialty || '').trim())

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
