# -*- coding: utf-8 -*-
"""单文件大屏口径同步（2026-09-19）
====================================
本页（dashboard.html → standalone / offline / templates/index）定位为**查阅形态**，
任务主线是 Vue 工作台「就医决策」（在线形态 /spa/）。
本次改动把这个分工写进侧栏与「系统说明」页，并让工作台入口在离线形态下给出提示
而不是跳到不存在的页面。

改完需重跑 bash web/build_spa.sh 同步 4 份产物。
"""
import sys
from pathlib import Path

P = Path("web/dashboard.html")
s = P.read_text(encoding="utf-8")
orig = len(s)
n = 0

# ---------- 1. 新增样式：任务入口 + 分组标签 ----------
ANCHOR_CSS = ".sidebar .navaux{margin-top:auto}"
CSS_ADD = """\
.sidebar .navaux{margin-top:auto}
/* —— 任务主线入口与分组标签（2026-09-19：明确"办事主线 / 数据查阅"的分工） —— */
.sidebar .navcta{text-decoration:none;border:1px solid rgba(var(--acc-rgb),.42);
  background:rgba(var(--acc-rgb),.12);color:var(--acc);font-weight:600}
.sidebar .navcta:hover{background:rgba(var(--acc-rgb),.2);color:var(--acc)}
.sidebar .navcta .ico{color:var(--acc)}
.navcap{font-size:10.5px;color:var(--ink-4);letter-spacing:.08em;padding:2px 6px 4px}"""
assert s.count(ANCHOR_CSS) == 1, "CSS 锚点不唯一: %d" % s.count(ANCHOR_CSS)
s = s.replace(ANCHOR_CSS, CSS_ADD, 1)
n += 1

# ---------- 2. 侧栏：工作台入口 + 「查阅」分组 ----------
NAV_ANCHOR = '<nav class="navbar" id="navbar">\n  <button class="navtab active" data-view="overview">'
NAV_NEW = """\
<nav class="navbar" id="navbar">
  <a class="navtab navcta" id="nav_workbench" href="/spa/"
     title="就医决策工作台（在线形态）：说清需求 → 分诊排序 → 横向对比 → 生成可带走的方案">
    <span class="ico"><svg class="ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="6" cy="18" r="2.6"/><circle cx="18" cy="6" r="2.6"/><path d="M8.4 17.2h4.1a3.5 3.5 0 000-7H10a3.5 3.5 0 010-7h2"/></svg></span><span class="lbl">就医决策</span>
  </a>
  <div class="navcap">查阅</div>
  <button class="navtab active" data-view="overview">"""
assert s.count(NAV_ANCHOR) == 1, "导航锚点不唯一: %d" % s.count(NAV_ANCHOR)
s = s.replace(NAV_ANCHOR, NAV_NEW, 1)
n += 1

# ---------- 3. 侧栏脚注：说清本页是什么 ----------
FOOT_OLD = ('<div class="sidefoot"><span class="navnote">7 维筛选 · 地图与列表悬停互指'
            '<br>勾选 2–3 家横向对比</span></div>')
FOOT_NEW = ('<div class="sidefoot"><span class="navnote">本页为<b>查阅形态</b>（离线可用）：'
            '摊开数据供查阅<br>办事主线在「就医决策」工作台</span></div>')
assert s.count(FOOT_OLD) == 1, "脚注锚点不唯一: %d" % s.count(FOOT_OLD)
s = s.replace(FOOT_OLD, FOOT_NEW, 1)
n += 1

# ---------- 4. 系统说明页：两种形态的分工 ----------
AB_ANCHOR = 'id="view-about" class="view">\n  <div class="about-grid">'
AB_NEW = """\
id="view-about" class="view">
  <div class="about-grid">
    <div class="panel" style="grid-column:1/-1">
      <h3>两种形态的分工 <span class="tag">TASK vs LOOKUP</span></h3>
      <div class="notice">
        本页是<b>查阅形态</b>：把整合后的机构数据摊开来看，回答"北京有哪些医疗机构、资源怎么分布"。<br>
        系统的<b>任务主线是「就医决策」工作台</b>（在线形态 <code>/spa/</code>）：说清症状与偏好 → 系统判断应就诊科室并按偏好排序机构 → 挑 2–3 家横向对比 → 生成一份可打印、可带走的就医方案，方案自动留痕可回看。<br>
        单文件离线形态不含工作台（它依赖后端接口与数据库），因此只保留查阅能力；用 Flask 启动后访问 <code>/spa/</code> 即可使用主线。
      </div>
    </div>
  </div>
  <div class="about-grid">"""
assert s.count(AB_ANCHOR) == 1, "系统说明锚点不唯一: %d" % s.count(AB_ANCHOR)
s = s.replace(AB_ANCHOR, AB_NEW, 1)
n += 1

# ---------- 5. 离线形态：入口给提示而不是跳到 404 ----------
BODY_END = "</body>"
assert s.count(BODY_END) == 1, "</body> 不唯一: %d" % s.count(BODY_END)
SCRIPT = """\
<script>
/* 离线单文件（file://）没有后端：工作台入口给出提示，而不是跳到不存在的页面 */
(function () {
  var a = document.getElementById('nav_workbench');
  if (!a) return;
  if (location.protocol === 'file:') {
    a.addEventListener('click', function (e) {
      e.preventDefault();
      alert('「就医决策」工作台需要后端服务。\\n\\n请在项目目录执行：\\nbash web/start.sh\\n\\n然后访问 http://localhost:5001/spa/');
    });
  }
})();
</script>
</body>"""
s = s.replace(BODY_END, SCRIPT, 1)
n += 1

P.write_text(s, encoding="utf-8")
print("✓ web/dashboard.html 已更新 %d 处 | %d → %d 字节" % (n, orig, len(s)))
sys.exit(0)
