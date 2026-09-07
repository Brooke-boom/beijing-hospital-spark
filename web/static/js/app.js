/* 北京市医院医疗资源多维筛选系统 —— 前端逻辑 */
"use strict";

const $ = (id) => document.getElementById(id);
let mapChart, districtChart, levelChart;
let curPage = 1, totalPages = 1;
const PAGE_SIZE = 20;

/* ---------- 初始化 ---------- */
document.addEventListener("DOMContentLoaded", async () => {
  initCharts();
  await Promise.all([loadFilters(), loadStats()]);
  bindEvents();
  search(1);
});

function bindEvents() {
  $("btnSearch").addEventListener("click", () => search(1));
  $("btnReset").addEventListener("click", () => {
    ["fQ", "fDistrict", "fLevel", "fCategory", "fDept"].forEach((id) => ($(id).value = ""));
    $("fSort").value = "score";
    search(1);
  });
  $("fQ").addEventListener("keydown", (e) => e.key === "Enter" && search(1));
  ["fDistrict", "fLevel", "fCategory", "fDept", "fSort"].forEach((id) =>
    $(id).addEventListener("change", () => search(1))
  );
}

/* ---------- 顶部统计 ---------- */
async function loadStats() {
  const [districts, depts] = await Promise.all([
    fetch("/api/overview/districts").then((r) => r.json()),
    fetch("/api/overview/depts?limit=1").then((r) => r.json()),
  ]);
  const total = districts.reduce((s, d) => s + d.inst_count, 0);
  const l3 = districts.reduce((s, d) => s + d.level_3_count, 0);
  const l2 = districts.reduce((s, d) => s + d.level_2_count, 0);
  const coordOk = districts.reduce((s, d) => s + d.coord_high_count + d.coord_rough_count, 0);
  $("statTotal").textContent = total.toLocaleString();
  $("statL3").textContent = l3;
  $("statL2").textContent = l2;
  $("statCoord").textContent = ((coordOk / total) * 100).toFixed(1) + "%";
  $("statDept").textContent = depts.length ? 32 : "--";
}

/* ---------- 筛选下拉 ---------- */
async function loadFilters() {
  const meta = await fetch("/api/meta/filters").then((r) => r.json());
  fillSelect("fDistrict", meta.districts.map((d) => ({ v: d.district, t: `${d.district}（${d.inst_count}）` })));
  fillSelect("fLevel", meta.levels.map((d) => ({ v: d.level, t: `${d.level}（${d.inst_count}）` })));
  fillSelect("fCategory", meta.categories.map((d) => ({ v: d.category, t: `${d.category}（${d.inst_count}）` })));
  fillSelect("fDept", meta.depts.slice(0, 32).map((d) => ({ v: d.dept_name, t: `${d.dept_name}（${d.hospital_count}）` })));
}

function fillSelect(id, options) {
  const sel = $(id);
  const first = sel.options[0].outerHTML;
  sel.innerHTML = first + options.map((o) => `<option value="${o.v}">${o.t}</option>`).join("");
}

/* ---------- 查询与列表 ---------- */
async function search(page) {
  curPage = page || 1;
  const p = new URLSearchParams({
    q: $("fQ").value.trim(),
    district: $("fDistrict").value,
    level: $("fLevel").value,
    category: $("fCategory").value,
    dept: $("fDept").value,
    sort: $("fSort").value,
    page: curPage,
    page_size: PAGE_SIZE,
  });
  const data = await fetch("/api/institutions?" + p).then((r) => r.json());
  totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  $("resultCount").textContent = `共 ${data.total.toLocaleString()} 家`;
  renderList(data.items);
  renderPager();
  renderMapPoints(data.items);
}

function renderList(items) {
  const ul = $("instList");
  if (!items.length) {
    ul.innerHTML = '<li class="empty">没有符合条件的机构，试试放宽筛选～</li>';
    return;
  }
  ul.innerHTML = items
    .map((it) => {
      const lv = it.level || "未定级";
      const cls = lv === "三级" ? "l3" : lv === "二级" ? "l2" : lv === "一级" ? "l1" : "l0";
      const dist = it.distance_km != null ? `<span class="inst-dist">📍 ${it.distance_km} km</span>` : "";
      return `<li onclick="showDetail(${it.id})">
        <div class="inst-name">${it.name}</div>
        <div class="inst-meta">
          <span class="tag ${cls}">${lv}${it.level_sub ? "·" + it.level_sub : ""}</span>
          <span>${it.district || "—"}</span>
          <span>${it.category || "—"}</span>
          <span>科室 ${it.dept_count ?? 0}</span>
          ${it.key_specialty_count > 0 ? '<span class="tag l3">重点专科</span>' : ""}
          ${dist}
          <span class="inst-score">★ ${(it.score ?? 0).toFixed(3)}</span>
        </div>
      </li>`;
    })
    .join("");
}

function renderPager() {
  const el = $("pager");
  const btn = (label, page, on, disabled) =>
    `<button ${disabled ? "disabled" : ""} class="${on ? "on" : ""}" onclick="search(${page})">${label}</button>`;
  let html = btn("‹", curPage - 1, false, curPage <= 1);
  const start = Math.max(1, curPage - 2);
  const end = Math.min(totalPages, start + 4);
  for (let i = start; i <= end; i++) html += btn(i, i, i === curPage);
  html += btn("›", curPage + 1, false, curPage >= totalPages);
  el.innerHTML = html;
}

/* ---------- 详情 ---------- */
async function showDetail(id) {
  const d = await fetch(`/api/institutions/${id}`).then((r) => r.json());
  if (d.error) return;
  const rows = [
    ["区域", d.district || "—"],
    ["类型", `${d.category || "—"}（${d.category_norm || "—"}）`],
    ["等级", `${d.level_norm || "未定级"}${d.level_sub ? "·" + d.level_sub : ""}`],
    ["地址", d.addr || "—"],
    ["电话", d.phone || "—"],
    ["床位", d.beds ? d.beds + " 张" : "—"],
    ["坐标", d.lng ? `${d.lng}, ${d.lat}（${d.coord_precision}）` : "缺失"],
    ["数据来源", `${d.src_count_int ?? 1} 个源文件`],
  ];
  const deptChips = (d.departments || [])
    .map((x) => `<span class="chip ${x.is_key_specialty == 1 ? "key" : ""}">${x.dept_name}</span>`)
    .join("") || '<span class="empty">暂无科室数据</span>';
  $("detailBody").innerHTML = `
    <div class="detail-title">${d.name}</div>
    <div class="detail-sub">ID ${d.id} · ${d.district || "未知区域"}</div>
    <div class="detail-grid">${rows.map(([k, v]) => `<span class="k">${k}</span><span>${v}</span>`).join("")}</div>
    <div class="sec-title">诊疗科室（${(d.departments || []).length}）</div>
    <div class="dept-chips">${deptChips}</div>`;
  $("detailModal").hidden = false;
}

function closeModal() {
  $("detailModal").hidden = true;
}
$("detailModal")?.addEventListener("click", (e) => {
  if (e.target === $("detailModal")) closeModal();
});

/* ---------- ECharts ---------- */
function initCharts() {
  mapChart = echarts.init($("mapChart"));
  districtChart = echarts.init($("districtChart"));
  levelChart = echarts.init($("levelChart"));

  fetch("/static/json/beijing.json")
    .then((r) => r.json())
    .then((geo) => {
      echarts.registerMap("beijing", geo);
      mapChart.setOption({
        title: { text: "机构地理分布", left: 12, top: 8, textStyle: { color: "#e8eef7", fontSize: 14 } },
        tooltip: {
          trigger: "item",
          formatter: (p) => (p.data ? `${p.data.name}<br>${p.data.detail || ""}` : p.name),
        },
        geo: {
          map: "beijing",
          roam: true,
          itemStyle: { areaColor: "#142645", borderColor: "#2fd6c3" },
          emphasis: { itemStyle: { areaColor: "#1d3a66" }, label: { color: "#e8eef7" } },
          label: { color: "#8ba3c7", fontSize: 10 },
        },
        series: [{
          type: "scatter",
          coordinateSystem: "geo",
          symbolSize: 7,
          itemStyle: { color: "#3d8bff", opacity: 0.75 },
          emphasis: { itemStyle: { color: "#2fd6c3" } },
        }],
      });
    });

  districtChart.setOption({
    title: { text: "各区机构数量", left: 12, top: 8, textStyle: { color: "#e8eef7", fontSize: 14 } },
    tooltip: { trigger: "axis" },
    grid: { left: 60, right: 20, top: 44, bottom: 40 },
    xAxis: { type: "category", axisLabel: { color: "#8ba3c7", rotate: 40, fontSize: 10 } },
    yAxis: { type: "value", axisLabel: { color: "#8ba3c7" }, splitLine: { lineStyle: { color: "#24406b" } } },
  });

  levelChart.setOption({
    title: { text: "等级结构", left: 12, top: 8, textStyle: { color: "#e8eef7", fontSize: 14 } },
    tooltip: { trigger: "item" },
    series: [{
      type: "pie", radius: ["38%", "62%"], center: ["50%", "56%"],
      label: { color: "#8ba3c7", fontSize: 11 },
      data: [],
    }],
  });

  loadOverviewCharts();
  window.addEventListener("resize", () => {
    mapChart.resize(); districtChart.resize(); levelChart.resize();
  });
}

async function loadOverviewCharts() {
  const [districts, levels] = await Promise.all([
    fetch("/api/overview/districts").then((r) => r.json()),
    fetch("/api/overview/levels").then((r) => r.json()),
  ]);
  districtChart.setOption({
    xAxis: { data: districts.map((d) => d.district) },
    series: [{ type: "bar", data: districts.map((d) => d.inst_count), itemStyle: { color: "#3d8bff", borderRadius: [3, 3, 0, 0] } }],
  });
  const colorMap = { "三级": "#ff6b6b", "二级": "#ffc46b", "一级": "#3d8bff", "未定级": "#8ba3c7" };
  levelChart.setOption({
    series: [{
      data: levels.map((l) => ({
        name: l.level, value: l.inst_count,
        itemStyle: { color: colorMap[l.level] || "#8ba3c7" },
      })),
    }],
  });
}

function renderMapPoints(items) {
  if (!mapChart || !mapChart.getOption()) return;
  mapChart.setOption({
    series: [{
      data: items
        .filter((it) => it.lng && it.lat)
        .map((it) => ({
          name: it.name,
          value: [it.lng, it.lat],
          detail: `${it.district || ""} ${it.level || ""} · ${it.distance_km ?? "—"} km`,
        })),
    }],
  });
}
