<template>
  <div v-if="store.compare.open" class="dlg" @click.self="store.closeCompare()">
    <div class="box">
      <div class="row" style="justify-content:space-between;align-items:center">
        <h2 style="margin:0;font-size:16px">机构横向对比</h2>
        <button class="btn ghost sm" type="button" @click="store.closeCompare()">关闭</button>
      </div>

      <div v-if="store.compare.loading" class="center">加载中…</div>
      <div v-else-if="!store.compare.data" class="center">无数据</div>
      <div v-else-if="store.compare.data.error" class="notice" style="margin-top:12px">
        {{ store.compare.data.error }}
      </div>
      <div v-else-if="store.compare.data.ok === false" class="notice" style="margin-top:12px">
        对比失败：需要 2–4 家机构（{{ store.compare.data.reason }}）
      </div>

      <template v-else>
        <div class="muted" style="margin-top:8px">
          共 {{ items.length }} 家 · 距离统一以天安门为基准，保证横向可比
        </div>
        <div style="overflow:auto;margin-top:12px">
          <table class="tbl">
            <thead>
              <tr>
                <th style="width:130px">字段</th>
                <th v-for="r in items" :key="r.id">{{ r.name }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in fields" :key="f[0]">
                <td class="muted">{{ f[1] }}</td>
                <td v-for="r in items" :key="r.id + f[0]">
                  {{ cell(r, f[0]) }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useDataStore } from '../store'

const store = useDataStore()
const items = computed(() => (store.compare.data && store.compare.data.items) || [])
const fields = computed(() => (store.compare.data && store.compare.data.fields) || [])

function cell(row, key) {
  const v = row[key]
  if (v === null || v === undefined || v === '') return '—'
  return String(v)
}
</script>
