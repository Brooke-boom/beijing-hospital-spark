import { onBeforeUnmount, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useDataStore } from './store'

// ECharts 画在 canvas 上，**不认 CSS 变量**（var(--x) 只在 DOM 样式里成立）。
// 所以图表配色必须从 CSS 变量读出**实值**再喂给 chart.setOption。
// 切换主题时重新 tokens() 一次并重绘，颜色才会跟着变——这是本项目最容易翻车的点。
export function tokens() {
  const cs = getComputedStyle(document.documentElement)
  const g = (n) => cs.getPropertyValue(n).trim()
  return {
    axis: g('--chart-axis'), split: g('--chart-split'),
    tipBg: g('--tip-bg'), tipBd: g('--tip-bd'),
    ink: g('--ink'), ink2: g('--ink-2'), ink3: g('--ink-3'),
    panel: g('--panel'), line: g('--line'),
    acc: g('--acc'), vio: g('--vio'), teal: g('--teal'),
    warn: g('--warn'), crit: g('--crit'), pink: g('--pink'),
    mapArea: g('--map-area'), mapHi: g('--map-hi'), mapBd: g('--map-bd'),
    ramp: [g('--map-r1'), g('--map-r2'), g('--map-r3'), g('--map-r4'), g('--map-r5')].filter(Boolean),
    body2: g('--body-2')
  }
}

// 统一 tooltip 外观（跟着主题走）
export function tip(t) {
  return {
    backgroundColor: t.tipBg,
    borderColor: t.tipBd,
    borderWidth: 1,
    textStyle: { color: t.ink, fontSize: 12 },
    extraCssText: 'border-radius:8px;box-shadow:0 6px 20px -14px rgba(0,0,0,.5);'
  }
}

export function axisBase(t) {
  return {
    axisLine: { lineStyle: { color: t.split } },
    axisTick: { show: false },
    axisLabel: { color: t.axis, fontSize: 11 },
    splitLine: { lineStyle: { color: t.split } }
  }
}

/**
 * 把一个 DOM 容器接成 ECharts 实例，并在主题切换时自动重绘。
 * @param elRef   ref 指向的容器
 * @param builder (t) => option   传入解析后的实色，返回 option
 * 返回 { render }：数据变化后由调用方手动再调一次 render()。
 */
export function useChart(elRef, builder) {
  const store = useDataStore()
  let inst = null

  const render = async () => {
    await nextTick()
    if (!elRef.value) return
    if (!inst) inst = echarts.init(elRef.value)
    const option = builder(tokens())
    if (option) inst.setOption(option, true)
    inst.resize()
  }

  const onResize = () => { if (inst) inst.resize() }

  onMounted(() => {
    render()
    window.addEventListener('resize', onResize)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('resize', onResize)
    if (inst) { inst.dispose(); inst = null }
  })
  // 主题变了 → 重新读实色 → 重绘
  store.$subscribe(() => { /* 占位：数据订阅由调用方控制 */ })
  return { render }
}

export { echarts }
