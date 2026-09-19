<template>
  <div class="page hubpage">
    <div class="hubhead">
      <div>
        <h2>{{ hub.title }}</h2>
        <p>{{ hub.desc }}</p>
      </div>
      <span class="hubkind">查阅支撑页</span>
    </div>

    <div class="subtabs" role="tablist">
      <button v-for="t in hub.tabs" :key="t.k" type="button" role="tab"
              :aria-selected="cur === t.k"
              class="subtab" :class="{ on: cur === t.k }" @click="pick(t.k)">
        {{ t.t }}
      </button>
    </div>

    <component :is="active.c" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { HUBS } from '../hubs'

const route = useRoute()
const router = useRouter()

const HUB_KEYS = computed(() => HUBS[route.meta.hub].tabs.map((x) => x.k))
const hub = computed(() => HUBS[route.meta.hub])
const cur = computed(() => {
  const q = route.query.t
  return HUB_KEYS.value.includes(q) ? q : HUB_KEYS.value[0]
})
const active = computed(() => hub.value.tabs.find((x) => x.k === cur.value))

// 子标签写进 URL（#/find?t=filter）：刷新、后退、分享都能还原到同一个看法
function pick(k) {
  if (k !== cur.value) router.replace({ query: { ...route.query, t: k } })
}

// 地址栏没带 t（或带了别的支撑页的 t）时补默认值，保证 URL 与页面一致。
// 必须等挂载后再改 URL，否则会在首次渲染期间触发一次多余导航。
const ready = ref(false)
function syncQuery() {
  if (!ready.value) return
  if (route.query.t !== cur.value) router.replace({ query: { ...route.query, t: cur.value } })
}
onMounted(() => { ready.value = true; syncQuery() })
watch(() => [route.meta.hub, route.query.t], syncQuery)
</script>
