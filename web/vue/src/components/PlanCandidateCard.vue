<template>
  <div class="cand" :class="{ main: isPrimary, picked: isKept }">
    <div class="chead">
      <div class="cname">
        <b>{{ c.name }}</b>
        <span v-if="c.alias_count" class="alias">
          （另有 {{ c.alias_count }} 个院区/名称已合并）
        </span>
      </div>
      <span class="tier" :class="{ top: c.tier >= 3 }">{{ c.tier_label }}</span>
    </div>

    <div class="cmeta">
      <span class="badge" :class="lvlClass">{{ c.level_norm || '未定级' }}</span>
      <span class="badge" :class="ownClass">{{ c.ownership || '未标注' }}</span>
      <span class="d">{{ c.district || '—' }}</span>
      <span class="sep">·</span>
      <span>应就诊 <b>{{ c.dept_name }}</b></span>
      <span class="sep" v-if="c.distance_km != null">·</span>
      <span v-if="c.distance_km != null">距 {{ baseLabel }} <b>{{ c.distance_km }}</b> km</span>
      <span class="sep" v-if="c.is_network">·</span>
      <span v-if="c.is_network" class="netbadge">协作网络成员</span>
    </div>

    <ul class="creasons">
      <li v-for="(r, i) in c.reasons" :key="i">{{ r }}</li>
    </ul>

    <div class="cfoot">
      <div class="cscore">
        <span class="sl">匹配度</span>
        <div class="minibar"><i :style="{ width: Math.round(c.match_score * 100) + '%' }"></i></div>
        <b>{{ c.match_score.toFixed(3) }}</b>
      </div>
      <div class="cact">
        <button class="btn sm" type="button" :class="{ primary: isPrimary }"
                @click="store.planSetPrimary(c.id)">
          {{ isPrimary ? '★ 主选' : '设为主选' }}
        </button>
        <button class="btn sm ghost" type="button" @click="store.planToggleKeep(c.id)">
          {{ isKept ? '✓ 已加入对比' : '加入对比' }}
        </button>
        <button class="btn sm ghost" type="button" @click="store.openDrawer(c.id)">详情</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useDataStore } from '../store'

const props = defineProps({ c: { type: Object, required: true } })
const store = useDataStore()

const isPrimary = computed(() => String(store.plan.primaryId) === String(props.c.id))
const isKept = computed(() => store.plan.keptIds.includes(String(props.c.id)))
const baseLabel = computed(() => (store.plan.result && store.plan.result.input.base_name) || '基准点')

const lvlClass = computed(() => {
  const m = { 三级: 'l3', 二级: 'l2', 一级: 'l1' }
  return m[props.c.level_norm] || 'l0'
})
const ownClass = computed(() => {
  const m = { 公立: 'pub', 民营: 'pri' }
  return m[props.c.ownership] || 'na'
})
</script>
