# 归档说明（legacy）

本目录存放已废弃、但按"零删除原则"保留副本的历史文件。

- `static_js_app_flask_legacy.js`：旧版 Flask 前端脚本（原 `web/static/js/app.js`）。
  - 归档原因：Flask 后端已改为直接伺服单页应用（`render_template("index.html")`，即 SPA 内联版本），该独立 JS 文件不再被任何模板引用，属死代码。
  - 归档时间：2026-09-09（与床位移除、协作网络整合同期整理）。
