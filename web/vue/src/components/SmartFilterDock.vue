<template>
  <div>
    <!-- ===================== 悬浮球：常驻右下角，任何页面都能一键呼出 ===================== -->
    <button class="fab" type="button" :class="{ on: open, pulse: !used }" :title="open ? '收起智能筛选' : '智能筛选：用一句话找机构'"
            aria-label="智能筛选" @click="toggle">
      <template v-if="!open">
        <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor"
             stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
          <path d="M8 7h8a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z"/>
          <path d="M12 7V4"/>
          <circle cx="12" cy="4" r="1"/>
          <circle cx="10" cy="11" r="1.1"/>
          <circle cx="14" cy="11" r="1.1"/>
          <path d="M10 15h4"/>
        </svg>
        <span v-if="hitCount !== null" class="fabbadge">{{ hitCount }}</span>
      </template>
      <template v-else>
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round">
          <path d="M6 6l12 12M18 6L6 18" />
        </svg>
      </template>
    </button>

    <!-- ===================== 展开面板 ===================== -->
    <transition name="dock">
      <div v-if="open" class="dockpanel" role="dialog" aria-label="智能筛选面板">
        <div class="dockhead">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
               stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 5h16l-6.2 7.2V19l-3.6 1.8v-8.6L4 5z" />
          </svg>
          <b>智能筛选</b>
          <span class="muted docksub">一句话 → 结构化条件 → 真实结果</span>
          <button class="btn ghost sm" type="button" @click="close">收起</button>
        </div>
        <div class="dockbody">
          <SmartFilterView />
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
// 悬浮球形态的智能筛选：不再占一个独立页面（那是"报表站"的布局），
// 常驻球让它在任何查阅页都能被呼出——查询是动作，不是地点。
// 面板里渲染的就是原 SmartFilterView 全部内容，条件/结果/抽屉逻辑零复制。
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useDataStore } from '../store'
import SmartFilterView from '../views/SmartFilterView.vue'

const store = useDataStore()
const open = ref(false)
const used = ref(false)

try { used.value = !!localStorage.getItem('__nlq_dock_used__') } catch (e) {}

function toggle() { open.value ? close() : show() }
function show() {
  open.value = true
  window.__NLQ_DOCK__ = true
  try { localStorage.setItem('__nlq_dock_used__', '1'); used.value = true; } catch (e) {}
}
function close() { open.value = false }
function onKey(e) { if (e.key === 'Escape' && open.value) close() }
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))

// 球上的小徽标：有结果时直接显示命中数，扫一眼就知道上次查了多少
const hitCount = computed(() => {
  const r = store.nlq.result
  return r && r.ok ? (r.total ?? null) : null
})
</script>
