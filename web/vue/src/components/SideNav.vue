<template>
  <aside class="sidebar">
    <div class="brandmark">
      <div class="mark">
        <svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M4 21V6l8-3 8 3v15M9 21v-4h6v4M12 8v5M9.5 10.5h5" />
        </svg>
      </div>
      <div>
        <div class="bt">医疗机构资源整合</div>
        <div class="bs">Spark · Flask · Vue</div>
      </div>
    </div>

    <router-link v-for="n in NAV" :key="n.name" :to="{ name: n.name }" class="navtab"
                 :class="{ active: route.name === n.name }" :title="n.title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round" v-html="n.icon" />
      <span class="lbl">{{ n.title }}</span>
    </router-link>

    <div class="sidefoot">
      7 维筛选 · 地图与列表联动<br>勾选 2–4 家横向对比
    </div>
  </aside>
</template>

<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()

const NAV = [
  { name: 'overview', title: '数据总览', icon: '<path d="M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10"/>' },
  { name: 'analytics', title: '医疗资源分析', icon: '<path d="M4 20V10M9 20V4M14 20v-7M19 20v-12"/>' },
  { name: 'institutions', title: '机构查询', icon: '<circle cx="11" cy="11" r="7"/><path d="M16.4 16.4L21 21"/>' },
  { name: 'filter', title: '智能筛选', icon: '<path d="M12 3l1.9 4.6L18.5 9l-4.6 1.4L12 15l-1.9-4.6L5.5 9l4.6-1.4zM18 15.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z"/>' },
  { name: 'integration', title: '数据整合', icon: '<path d="M12 2l9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 17l9 5 9-5"/>' },
  { name: 'quality', title: '数据质量', icon: '<path d="M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>' },
  { name: 'about', title: '系统说明', icon: '<path d="M12 3a9 9 0 100 18 9 9 0 000-18zM12 10v6M12 7.5h.01"/>' }
]
</script>
