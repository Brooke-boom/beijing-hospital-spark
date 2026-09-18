<template>
  <div class="layout">
    <SideNav />
    <div class="maincol">
      <TopBar />
      <div v-if="store.error" class="page">
        <div class="notice">
          <b>接口未连通：</b>{{ store.error }}<br>
          请确认后端已启动：<code>bash web/start.sh</code>（Flask 默认 5001 端口，数据来自 MySQL hospital 库）
        </div>
      </div>
      <router-view v-else />
    </div>

    <DetailDrawer />
    <CompareDialog />
    <div v-if="store.toast" class="toast">{{ store.toast }}</div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useDataStore } from './store'
import SideNav from './components/SideNav.vue'
import TopBar from './components/TopBar.vue'
import DetailDrawer from './components/DetailDrawer.vue'
import CompareDialog from './components/CompareDialog.vue'

const store = useDataStore()
onMounted(() => {
  store.initTheme()
  store.boot()
})
</script>
