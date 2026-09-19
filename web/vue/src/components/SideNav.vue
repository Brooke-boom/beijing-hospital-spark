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

    <!-- 主任务：一条从需求到方案的就医决策主线 -->
    <router-link v-for="n in NAV_MAIN" :key="n.name" :to="{ name: n.name }" class="navtab main"
                 :class="{ active: route.name === n.name }" :title="n.title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round" v-html="n.icon" />
      <span class="lbl">{{ n.title }}</span>
    </router-link>

    <div class="navgroup">查阅</div>

    <router-link v-for="n in NAV_LOOK" :key="n.name" :to="{ name: n.name }" class="navtab"
                 :class="{ active: route.name === n.name }" :title="n.title">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
           stroke-linecap="round" stroke-linejoin="round" v-html="n.icon" />
      <span class="lbl">{{ n.title }}</span>
    </router-link>

    <div class="sidefoot">
      就医决策为任务主线<br>其余为数据查阅支撑
    </div>
  </aside>
</template>

<script setup>
import { useRoute } from 'vue-router'

const route = useRoute()

// 导航分两层：主线（办事）与查阅（看数据）。
// 平级的 7 个入口会让人以为这是个看板，分层之后主次关系才明确。
const NAV_MAIN = [
  { name: 'plan', title: '就医决策', icon: '<circle cx="6" cy="18" r="2.6"/><circle cx="18" cy="6" r="2.6"/><path d="M8.4 17.2h4.1a3.5 3.5 0 000-7H10a3.5 3.5 0 010-7h2"/>' }
]

const NAV_LOOK = [
  { name: 'find', title: '找机构', icon: '<circle cx="11" cy="11" r="7"/><path d="M16.4 16.4L21 21"/>' },
  { name: 'profile', title: '资源画像', icon: '<path d="M4 20V10M9 20V4M14 20v-7M19 20v-12"/>' },
  { name: 'govern', title: '数据治理', icon: '<path d="M12 2l9 5-9 5-9-5 9-5zM3 12l9 5 9-5M3 17l9 5 9-5"/>' },
  { name: 'about', title: '系统说明', icon: '<path d="M12 3a9 9 0 100 18 9 9 0 000-18zM12 10v6M12 7.5h.01"/>' }
]
</script>
