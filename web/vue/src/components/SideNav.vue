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

    <!-- 查阅页：一个页面回答一个问题，页内用子标签切换看法。
         智能筛选不在这里——它已改为常驻右下角的悬浮球，任何页都能呼出。 -->
    <router-link v-for="n in NAV" :key="n.name" :to="{ name: n.name }" class="navtab"
                 :class="{ active: route.name === n.name }" :title="n.title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round" v-html="n.icon" />
      <span class="lbl">{{ n.title }}</span>
    </router-link>

    <div class="sidefoot">
      右下角悬浮球 = 智能筛选<br>一句话筛选，任何页可呼出
    </div>
  </aside>
</template>

<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()

// 侧栏只留查阅页；智能筛选改为悬浮球（SmartFilterDock），不再占导航位。
const NAV = [
  { name: 'find', title: '找机构', icon: '<circle cx="11" cy="11" r="7"/><path d="M16.4 16.4L21 21"/>' },
  { name: 'profile', title: '资源画像', icon: '<path d="M4 20V10M9 20V4M14 20v-7M19 20v-12"/>' },
  { name: 'govern', title: '数据治理', icon: '<path d="M12 2l9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 17l9 5 9-5"/>' },
  { name: 'about', title: '系统说明', icon: '<path d="M12 3a9 9 0 100 18 9 9 0 000-18zM12 10v6M12 7.5h.01"/>' }
]
</script>
