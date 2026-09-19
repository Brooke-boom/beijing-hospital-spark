<template>
  <div class="page">
    <!-- 任务步骤条：这条主线有明确的任务态，可回退、可重来 -->
    <div class="stepper">
      <button v-for="(s, i) in STEPS" :key="s.k" type="button"
              class="step" :class="{ on: store.plan.step === i + 1, done: store.plan.step > i + 1 }"
              :disabled="i + 1 > maxReached" @click="store.planGoto(i + 1)">
        <span class="n">{{ i + 1 }}</span>
        <span class="tx">
          <b>{{ s.t }}</b>
          <i>{{ s.d }}</i>
        </span>
      </button>
    </div>

    <!-- ============ 步骤 1：说清需求 ============ -->
    <template v-if="store.plan.step === 1">
      <div class="panel">
        <h3>说清你的就医需求 <span class="tag">自然语言</span></h3>
        <textarea class="ctl ask" rows="3" v-model="f.q"
                  placeholder="用大白话说就行，例如：孩子发烧两天了 / 老人最近总心慌胸闷 / 腰疼想做检查 / 睡不着觉"
                  @keydown.ctrl.enter="store.planRun()" @keydown.meta.enter="store.planRun()"></textarea>
        <div class="exchips">
          <span class="muted">试试这些：</span>
          <button v-for="e in EXAMPLES" :key="e" class="chip tap" type="button" @click="f.q = e">{{ e }}</button>
        </div>

        <div class="row" style="margin-top:16px;align-items:flex-start">
          <div class="field" style="flex:1 1 260px">
            <label>你的位置（用来算距离与可达性）</label>
            <div class="row" style="gap:7px;flex-wrap:nowrap">
              <input class="ctl" type="text" v-model.trim="baseQ" placeholder="输入地址，如：中关村 / 天安门"
                     @keyup.enter="doGeocode" />
              <button class="btn" type="button" :disabled="geocoding" @click="doGeocode">
                {{ geocoding ? '解析中…' : '设定' }}
              </button>
            </div>
            <div class="hintline">
              当前基准：<b>{{ baseName }}</b>
              <span v-if="!store.base" class="muted">（未设定，按天安门计算并标注"距市中心"）</span>
            </div>
          </div>

          <div class="field" style="flex:1 1 300px">
            <label>决策偏好</label>
            <div class="prefergrp">
              <button v-for="p in PREFERS" :key="p.v" type="button" class="prefer"
                      :class="{ on: f.prefer === p.v }" @click="f.prefer = p.v">
                <b>{{ p.t }}</b><i>{{ p.d }}</i>
              </button>
            </div>
          </div>
        </div>

        <div class="row" style="margin-top:14px;align-items:flex-end">
          <div class="field" style="flex:0 1 130px">
            <label>限定区域</label>
            <select class="ctl" v-model="f.district">
              <option value="">不限</option>
              <option v-for="d in store.meta.districts" :key="d" :value="d">{{ d }}</option>
            </select>
          </div>
          <div class="field" style="flex:0 1 120px">
            <label>限定等级</label>
            <select class="ctl" v-model="f.level">
              <option value="">不限</option>
              <option v-for="l in LEVELS" :key="l" :value="l">{{ l }}</option>
            </select>
          </div>
          <div class="field" style="flex:0 1 150px">
            <label>最大距离（km，0 = 不限）</label>
            <input class="ctl" type="number" min="0" step="1" v-model="f.max_km" />
          </div>
          <div class="field" style="flex:0 0 auto">
            <label>办别</label>
            <label class="switch">
              <input type="checkbox" v-model="f.public_only" />
              <span>只要公立</span>
            </label>
          </div>
        </div>

        <div class="actbar">
          <button class="btn primary lg" type="button" :disabled="store.plan.loading" @click="store.planRun()">
            {{ store.plan.loading ? '正在匹配机构…' : '生成就医方案' }}
          </button>
          <span class="muted">先判断应就诊科室 → 再按偏好排序机构 → 最后给出可带走的方案</span>
        </div>

        <div v-if="store.plan.error" class="errbox">请求失败：{{ store.plan.error }}</div>
        <div v-else-if="failure" class="errbox">
          {{ failure.hint }}
          <div class="exchips" v-if="(failure.examples || []).length">
            <span class="muted">换个说法：</span>
            <button v-for="e in failure.examples" :key="e" class="chip tap" type="button"
                    @click="f.q = e; store.planRun()">{{ e }}</button>
          </div>
        </div>
      </div>

      <div v-if="store.plan.history.length" class="panel">
        <h3>我的方案 <span class="tag">{{ store.plan.history.length }}</span></h3>
        <div class="histlist">
          <div v-for="h in store.plan.history" :key="h.id" class="hist">
            <button class="hmain tap" type="button" @click="store.planOpenSaved(h.id)">
              <b>{{ h.title }}</b>
              <i>{{ h.created_at }} · {{ h.depts || '—' }} · {{ h.candidate_cnt }} 个候选</i>
            </button>
            <button class="btn ghost sm" type="button" @click="store.planDeleteSaved(h.id)">删除</button>
          </div>
        </div>
      </div>
    </template>

    <!-- ============ 步骤 2：看候选 ============ -->
    <template v-else-if="store.plan.step === 2">
      <div class="panel">
        <h3>候选机构
          <span class="tag">{{ cands.length }} 家</span>
          <button class="btn ghost sm" type="button" style="margin-left:auto" @click="store.planGoto(1)">
            ← 改条件
          </button>
        </h3>

        <div class="triagecard" v-if="triage">
          <div class="tl">判断应就诊科室</div>
          <div class="td">
            <span v-for="d in triage.target_depts" :key="d.name" class="deptpill">
              {{ d.name }}<em>{{ d.category }}</em>
              <i v-if="d.is_emergency" class="emg">急诊</i>
            </span>
          </div>
          <div class="tn">
            命中依据：{{ triage.target_depts.map((d) => d.matched_by).join('、') }}
            <template v-if="triage.corrected_district">
              ｜已纠正区名「{{ triage.corrected_district.from }}」→「{{ triage.corrected_district.to }}」
            </template>
          </div>
        </div>

        <div class="chips">
          <span class="chip">{{ store.plan.result.input.prefer_label }}</span>
          <span class="chip" v-if="store.plan.result.input.district">
            区域：{{ store.plan.result.input.district }}</span>
          <span class="chip" v-if="store.plan.result.input.level">
            等级：{{ store.plan.result.input.level }}</span>
          <span class="chip" v-if="store.plan.result.input.public_only">仅公立</span>
          <span class="chip" v-if="store.plan.result.input.max_km">
            ≤ {{ store.plan.result.input.max_km }} km</span>
          <span class="chip" v-if="store.plan.result.input.located">
            基准：{{ store.plan.result.input.base_name || '已定位' }}</span>
        </div>

        <div class="candlist">
          <PlanCandidateCard v-for="c in cands" :key="c.id" :c="c" />
        </div>

        <div class="actbar">
          <button class="btn primary" type="button" :disabled="!store.plan.keptIds.length"
                  @click="store.planGoto(3)">
            下一步 · 对比选中的 {{ store.plan.keptIds.length }} 家
          </button>
          <button class="btn ghost" type="button" :disabled="!store.plan.primaryId" @click="store.planGoto(4)">
            直接用当前主选生成方案
          </button>
        </div>
      </div>
    </template>

    <!-- ============ 步骤 3：做比较 ============ -->
    <template v-else-if="store.plan.step === 3">
      <div class="panel">
        <h3>横向对比 <span class="tag">{{ kept.length }} 家</span>
          <button class="btn ghost sm" type="button" style="margin-left:auto" @click="store.planGoto(2)">
            ← 回候选
          </button>
        </h3>
        <div v-if="!kept.length" class="muted" style="padding:20px 0">
          还没有勾选机构，回到上一步勾选 2–4 家后再来对比。
        </div>
        <div v-else class="cmpwrap">
          <table class="tbl cmp">
            <thead>
              <tr>
                <th class="rowh">对比项</th>
                <th v-for="c in kept" :key="c.id">
                  <div class="cmpname">{{ c.name }}</div>
                  <button class="btn sm" type="button"
                          :class="{ primary: String(store.plan.primaryId) === String(c.id) }"
                          @click="store.planSetPrimary(c.id)">
                    {{ String(store.plan.primaryId) === String(c.id) ? '★ 主选' : '设为主选' }}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              <tr><td class="rowh">应就诊科室</td>
                <td v-for="c in kept" :key="c.id">{{ c.dept_name }}</td></tr>
              <tr><td class="rowh">专科实力</td>
                <td v-for="c in kept" :key="c.id">
                  {{ c.tier_label }}
                  <span class="muted">（{{ c.strength }} 分）</span>
                </td></tr>
              <tr><td class="rowh">机构等级</td>
                <td v-for="c in kept" :key="c.id">{{ c.level || c.level_norm || '—' }}</td></tr>
              <tr><td class="rowh">办别</td>
                <td v-for="c in kept" :key="c.id">{{ c.ownership || '未标注' }}</td></tr>
              <tr><td class="rowh">所在区</td>
                <td v-for="c in kept" :key="c.id">{{ c.district || '—' }}</td></tr>
              <tr><td class="rowh">距离</td>
                <td v-for="c in kept" :key="c.id">
                  {{ c.distance_km != null ? c.distance_km + ' km' : '—' }}</td></tr>
              <tr><td class="rowh">协作网络</td>
                <td v-for="c in kept" :key="c.id">{{ c.is_network ? '成员' : '—' }}</td></tr>
              <tr><td class="rowh">开设科室数</td>
                <td v-for="c in kept" :key="c.id">{{ c.dept_count || '—' }}</td></tr>
              <tr><td class="rowh">匹配度</td>
                <td v-for="c in kept" :key="c.id">
                  <b>{{ c.match_score.toFixed(3) }}</b>
                  <div class="minibar"><i :style="{ width: Math.round(c.match_score * 100) + '%' }"></i></div>
                </td></tr>
              <tr><td class="rowh">推荐依据</td>
                <td v-for="c in kept" :key="c.id">
                  <div class="reasons">
                    <span v-for="(rs, i) in c.reasons" :key="i">{{ rs }}</span>
                  </div>
                </td></tr>
              <tr><td class="rowh">地址</td>
                <td v-for="c in kept" :key="c.id" class="addr">{{ c.addr || '—' }}</td></tr>
            </tbody>
          </table>
        </div>
        <div class="actbar">
          <button class="btn primary" type="button" :disabled="!store.plan.primaryId" @click="store.planGoto(4)">
            生成就医方案 →
          </button>
        </div>
      </div>
    </template>

    <!-- ============ 步骤 4：拿方案 ============ -->
    <template v-else>
      <div class="panel">
        <h3>就医决策方案
          <span class="tag">可带走</span>
          <span class="btnrow">
            <button class="btn sm" type="button" @click="copyPlan">复制</button>
            <button class="btn sm" type="button" @click="downloadPlan">下载</button>
            <button class="btn sm" type="button" @click="printPlan">打印</button>
            <button class="btn sm" type="button" :disabled="store.plan.step === 1"
                    @click="store.planSave()">
              {{ store.plan.savedId ? '已保存' : '保存到我的方案' }}
            </button>
          </span>
        </h3>

        <div v-if="!primary" class="muted" style="padding:20px 0">还没有选定主选机构。</div>

        <div v-else class="plancard" id="plan-print">
          <div class="ph">
            <div>
              <div class="ptitle">{{ primary.name }}</div>
              <div class="pmeta">
                {{ primary.dept_name }} · {{ primary.level || primary.level_norm || '等级未标注' }}
                · {{ primary.ownership || '办别未标注' }}
              </div>
            </div>
            <div class="ptag">{{ primary.tier_label }}</div>
          </div>

          <div class="ps">
            <div class="prow">
              <label>地址</label>
              <div>{{ primary.addr || '—' }}</div>
            </div>
            <div class="prow">
              <label>电话</label>
              <div>{{ primary.phone || '—' }}</div>
            </div>
            <div class="prow">
              <label>距离</label>
              <div>
                <template v-if="primary.distance_km != null">
                  {{ primary.distance_km }} 公里（距{{ store.plan.result.input.base_name || '基准点' }}）
                </template>
                <template v-else>未设置位置基准，无法计算</template>
              </div>
            </div>
            <div class="prow">
              <label>需求</label>
              <div>{{ store.plan.result.input.q || store.plan.result.input.forced_dept }}</div>
            </div>
          </div>

          <div class="psec">
            <h4>为什么推荐这家</h4>
            <ul>
              <li v-for="(rs, i) in primary.reasons" :key="i">{{ rs }}</li>
            </ul>
          </div>

          <div class="psec" v-if="alternatives.length">
            <h4>备选机构（{{ alternatives.length }}）</h4>
            <ol>
              <li v-for="a in alternatives" :key="a.id">
                <b>{{ a.name }}</b> · {{ a.dept_name }}
                <span class="muted">
                  {{ a.tier_label }}<template v-if="a.distance_km != null"> · {{ a.distance_km }} km</template>
                </span>
              </li>
            </ol>
          </div>

          <div class="psec">
            <h4>就诊前准备</h4>
            <ul>
              <li v-for="(x, i) in PREP" :key="i">{{ x }}</li>
            </ul>
          </div>

          <div class="psec">
            <h4>预约挂号</h4>
            <ul>
              <li>北京市预约挂号统一平台：<b>https://www.114yygh.com/</b></li>
              <li>也可通过医院官方微信公众号、官方 App 预约，或拨打 114</li>
            </ul>
          </div>

          <div class="pfoot">
            生成时间 {{ store.plan.result.generated_at }}　|　数据来源：北京市卫健委公开名录 + 在线核实口径
            <br />
            本方案由系统基于公开数据生成，仅作就诊决策参考，不构成诊断意见；急危重症请直接拨打 120。
          </div>
        </div>

        <div class="actbar">
          <button class="btn ghost" type="button" @click="store.planGoto(3)">← 回对比</button>
          <button class="btn ghost" type="button" @click="store.planReset()">重新开始一次决策</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useDataStore } from '../store'
import api from '../api'
import PlanCandidateCard from '../components/PlanCandidateCard.vue'

const store = useDataStore()
const f = store.plan.form

const STEPS = [
  { k: 'ask', t: '说需求', d: '症状与偏好' },
  { k: 'cand', t: '看候选', d: '分诊与匹配' },
  { k: 'cmp', t: '做比较', d: '横向对比' },
  { k: 'plan', t: '拿方案', d: '带走的结论' }
]
const EXAMPLES = ['孩子发烧', '心慌胸闷', '腰疼', '睡不着', '牙疼', '孕检', '骨折', '咳嗽两周']
const LEVELS = ['三级', '二级', '一级', '未定级']
const PREFERS = [
  { v: 'specialty', t: '专科实力优先', d: '看科室是不是重点专科' },
  { v: 'distance', t: '就近优先', d: '少跑路，离家近' },
  { v: 'level', t: '等级优先', d: '优先高级别机构' },
  { v: 'balanced', t: '综合平衡', d: '各方面都不偏废' }
]
const PREP = [
  '携带本人身份证与医保卡；儿童就诊建议带出生证明或户口本',
  '带上既往病历、检查报告与正在服用的药物清单',
  '需要空腹的项目（抽血、腹部超声）请提前 8 小时禁食',
  '建议提前线上预约挂号，避开周一与上午早高峰',
  '发热患者先测量并记录体温变化，到院后主动告知分诊台'
]

const baseQ = ref('')
const geocoding = ref(false)

const cands = computed(() => store.planCandidates)
const primary = computed(() => store.planPrimary)
const kept = computed(() => store.planKept)
const triage = computed(() => store.planTriage)
const baseName = computed(() => (store.base ? store.base.name : '天安门（默认）'))
// 只有生成过方案才允许跳到后面的步骤，避免空步骤
const maxReached = computed(() => (store.planReady ? 4 : 1))
const failure = computed(() => {
  const r = store.plan.result
  return r && !r.ok && store.plan.step === 1 ? r : null
})
const alternatives = computed(() => {
  const p = primary.value
  if (!p) return []
  return cands.value.filter((c) => String(c.id) !== String(p.id)).slice(0, 3)
})

async function doGeocode() {
  if (!baseQ.value) { store.notify('请输入地址'); return }
  geocoding.value = true
  try {
    const r = await api.geocode(baseQ.value)
    if (r && (r.ok === false || r.lng === undefined || r.lng === null)) {
      store.notify(r.message || r.error || '未解析到该地址')
    } else {
      await store.setBase({ name: r.name || baseQ.value, lng: r.lng, lat: r.lat })
      store.notify('位置已设为：' + (r.name || baseQ.value))
    }
  } catch (e) {
    store.notify('地址解析失败：' + e.message)
  } finally {
    geocoding.value = false
  }
}

function planText() {
  const p = primary.value
  const r = store.plan.result
  if (!p || !r) return ''
  const L = []
  L.push('《就医决策方案》')
  L.push('生成时间：' + (r.generated_at || ''))
  L.push('需求描述：' + (r.input.q || r.input.forced_dept || ''))
  if (r.input.base_name) L.push('位置基准：' + r.input.base_name)
  L.push('')
  L.push('【推荐就诊】')
  L.push(p.name + ' · ' + p.dept_name)
  L.push('地址：' + (p.addr || '—'))
  L.push('电话：' + (p.phone || '—'))
  if (p.distance_km != null) L.push('距离：' + p.distance_km + ' 公里')
  L.push('')
  L.push('【推荐依据】')
  ;(p.reasons || []).forEach((x) => L.push('· ' + x))
  if (alternatives.value.length) {
    L.push('')
    L.push('【备选机构】')
    alternatives.value.forEach((c, i) => {
      L.push((i + 2) + '. ' + c.name + ' · ' + c.dept_name +
        (c.distance_km != null ? '（' + c.distance_km + ' km）' : ''))
    })
  }
  L.push('')
  L.push('【就诊前准备】')
  PREP.forEach((x) => L.push('· ' + x))
  L.push('')
  L.push('【预约挂号】')
  L.push('北京市预约挂号统一平台：https://www.114yygh.com/')
  L.push('')
  L.push('（本方案由系统基于公开数据生成，仅作就诊决策参考，不构成诊断意见；急危重症请直接拨打 120）')
  return L.join('\n')
}

async function copyPlan() {
  const t = planText()
  try {
    await navigator.clipboard.writeText(t)
    store.notify('方案已复制到剪贴板')
  } catch (e) {
    store.notify('复制失败，请手动选择文本')
  }
}

function downloadPlan() {
  const p = primary.value
  const blob = new Blob([planText()], { type: 'text/plain;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = '就医方案_' + (p ? p.name : '') + '.txt'
  a.click()
  URL.revokeObjectURL(a.href)
  store.notify('已下载方案文件')
}

function printPlan() {
  window.print()
}

onMounted(() => {
  store.planLoadHistory()
})
</script>
