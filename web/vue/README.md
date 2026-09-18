# Vue 前端（前后端分离形态）

本目录是系统的 **Vue 3 单页应用**，与 `web/app.js` + `web/dashboard.html` 的单文件大屏
**并存**，两者共用同一套后端接口：

| 形态 | 入口 | 数据来源 | 用途 |
| --- | --- | --- | --- |
| Vue 在线形态 | `http://127.0.0.1:5001/spa/` | `GET /api/*` → Flask → MySQL | 前后端分离的标准工程形态 |
| 单文件离线形态 | `web/dashboard_offline.html` | 内联快照（`window.__SNAPSHOT__`） | 零依赖兜底，双击即开，答辩现场用 |

## 一、技术选型

| 依赖 | 版本 | 职责 |
| --- | --- | --- |
| Vue | 3.5 | 视图层，全部使用 `<script setup>` 组合式 API |
| Vue Router | 4.x | 哈希路由（`createWebHashHistory`），7 个视图按需动态 import |
| Pinia | 2.x | 单一数据仓库：查询条件、分页、基准点、对比选择、主题 |
| ECharts | 5.5 | 图表渲染（`src/charts.js` 统一封装） |
| axios | 1.x | 唯一 HTTP 通道，统一拦截响应与错误 |
| Vite | 6.x | 构建与开发服务器 |

**为什么用哈希路由**：Flask 把产物挂在 `/spa/` 子路径，哈希模式不需要服务端配置
history 回退，产物直接双击打开也能跑（离线兜底）。`vite.config.js` 的 `base` 设为 `/spa/`。

## 二、目录结构

```
web/vue/
├─ index.html              入口（内联空 favicon，避免 404）
├─ vite.config.js          base=/spa/，dev 期把 /api 代理到 Flask:5001
├─ build.sh                一键构建 / 启动开发服务器
├─ src/
│  ├─ main.js              挂载 Vue + Pinia + Router
│  ├─ router.js            7 个视图的路由表
│  ├─ api.js               接口封装（唯一数据出入口）
│  ├─ store.js             Pinia 仓库（查询、分页、基准点、对比、主题）
│  ├─ charts.js            ECharts 封装：从 CSS 变量读实色 → 主题切换自动重绘
│  ├─ styles.css           设计令牌（与 dashboard.html 同一套变量名，双主题只换变量）
│  ├─ components/          SideNav / TopBar / FilterBar / InstTable / DetailDrawer / CompareDialog
│  └─ views/               七个视图，每个对应一个侧栏导航项
└─ dist/                   构建产物（已入库，Flask 挂载点）
```

## 三、七个视图

| 路由 | 视图 | 对接接口 |
| --- | --- | --- |
| `#/overview` | 数据总览 | `/api/health`、`/api/overview/districts`、`/api/overview/levels`、`/api/overview/depts`、`/api/meta/filters`、`/api/specialty/groups` |
| `#/analytics` | 医疗资源分析 | `/api/overview/*`、`/api/specialty/groups`、`/api/institutions?net=*` |
| `#/institutions` | 机构查询 | `/api/institutions`（筛选 + 分页 + 排序）、`/api/inst/<id>/detail`、`/api/inst/compare` |
| `#/filter` | 智能筛选 | `/api/institutions`、`/api/geocode` |
| `#/integration` | 数据整合 | `/api/about`（流水线、数据来源、库表清单） |
| `#/quality` | 数据质量 | `/api/about`、`/api/overview/districts`、`/api/overview/levels` |
| `#/about` | 系统说明 | `/api/about` |

## 四、构建与运行

```bash
# 1) 安装依赖（首次；node_modules 不入库）
cd web/vue && npm install --registry=https://registry.npmmirror.com

# 2) 构建产物到 web/vue/dist（Flask 会挂载到 /spa/）
bash web/vue/build.sh

# 3) 启动后端（同时提供 / 与 /spa/）
bash web/start.sh
#    Vue 在线形态: http://127.0.0.1:5001/spa/
#    离线单文件:   http://127.0.0.1:5001/

# 开发模式（Vite HMR，/api 自动代理到 Flask:5001）
bash web/vue/build.sh --dev        # → http://127.0.0.1:5173/spa/
```

## 五、两个容易翻车的点

1. **ECharts 不认 CSS 变量**。`var(--acc)` 只在 DOM 样式里成立，canvas 拿不到。
   因此所有图表配色必须经 `src/charts.js` 的 `tokens()` 读出**实色**再喂给 `setOption`；
   切换主题后必须重新 `tokens()` 并重绘，否则暗色下仍是亮色配色。
2. **`formatter` 传函数时不做模板替换**。`formatter: (p) => '{b}\n{c}'` 会把
   `{b}` 原样打印到图上。函数形态必须自己拼好字符串：`p.name + '\n' + p.value`。

## 六、收尾校验

改动前端源码后，务必重跑构建并校验产物：

```bash
bash web/vue/build.sh                        # 重新构建
python3 etl/verify_artifacts.py              # 校验三份单文件产物 + Vue 产物
python3 etl/smoke_vue.py                     # 无头浏览器端到端冒烟（需先启动 Flask）
```

`verify_artifacts.py` 会检查：dist 引用资源是否齐全、七个视图 chunk 是否都在、
产物是否旧于源码；`smoke_vue.py` 会真实驱动浏览器走完 7 条路由并断言 0 运行时错误。
