<template>
  <header class="topbar">
    <div>
      <h1>北京市医疗机构资源整合与多维筛选可视化系统</h1>
      <div class="sub">Beijing Medical Institutions · Spark · HDFS · MySQL · Flask · Vue</div>
    </div>
    <div class="topmeta">
      <span class="chipmeta">机构总数 <b>{{ fmt(store.total || store.health?.institutions) }}</b></span>
      <span class="chipmeta">筛选命中 <b>{{ fmt(store.total) }}</b></span>
      <span class="chipmeta">基准点 <b>{{ store.base ? store.base.name : '未设定' }}</b></span>
      <button class="themebtn" type="button" :title="store.theme === 'dark' ? '切换到白天外观' : '切换到黑夜外观'"
              @click="store.toggleTheme()">
        <svg v-if="store.theme === 'dark'" viewBox="0 0 24 24" width="16" height="16" fill="none"
             stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
          <path d="M12 7.4a4.6 4.6 0 100 9.2 4.6 4.6 0 000-9.2zM12 2.4v2.1M12 19.5v2.1M4.3 4.3l1.5 1.5M18.2 18.2l1.5 1.5M2.4 12h2.1M19.5 12h2.1M4.3 19.7l1.5-1.5M18.2 5.8l1.5-1.5"/>
        </svg>
        <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round">
          <path d="M20.2 14.6A8.6 8.6 0 019.4 3.8a8.6 8.6 0 1010.8 10.8z"/>
        </svg>
      </button>
    </div>
  </header>
</template>

<script setup>
import { useDataStore } from '../store'
const store = useDataStore()
const fmt = (n) => (n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString())
</script>
