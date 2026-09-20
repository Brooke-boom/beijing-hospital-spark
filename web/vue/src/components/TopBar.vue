<template>
  <header class="topbar">
    <div>
      <h1>北京市医疗机构资源整合与多维筛选可视化系统</h1>
      <div class="sub">Beijing Medical Institutions · Spark · HDFS · MySQL · Flask · Vue</div>
    </div>
    <div class="topmeta">
      <span class="chipmeta">机构总数 <b>{{ fmt(store.total || store.health?.institutions) }}</b></span>
      <span class="chipmeta">最近一次筛选 <b>{{ hitText }}</b></span>
      <span class="chipmeta">基准点 <b>{{ store.base ? store.base.name : '未设定' }}</b></span>
      <!-- 从工作台回查阅形态（单文件大屏）的入口：进来之后得能回去，不能是单向门 -->
      <a v-if="!isFile" class="lookbtn" href="/"
         title="返回单文件查阅形态：不依赖后端的离线数据大屏（系统起始页）">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor"
             stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <path d="M19 12H5M11 18l-6-6 6-6" />
        </svg>
        <span>查阅形态</span>
      </a>
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
import { computed } from 'vue'
import { useDataStore } from '../store'
const store = useDataStore()
const fmt = (n) => (n === null || n === undefined || n === '' ? '—' : Number(n).toLocaleString())
// 顶栏展示"最近一次筛选"，而不是机构查询页的命中数：
// 前者是主线动作的结果，后者只是某个支撑页的分页总数，两者口径不同不能混用。
const hitText = computed(() => {
  const r = store.nlq.result
  if (!r || !r.ok) return '—'
  return fmt(r.total)
})
// 直接用 dist/index.html 双击打开（file://）时 "/" 指向文件系统根，链接无意义 → 隐藏
const isFile = typeof location !== 'undefined' && location.protocol === 'file:'
</script>
