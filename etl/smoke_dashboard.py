# -*- coding: utf-8 -*-
"""
前端大屏无头冒烟测试（答辩前 + 每次重建产物后跑）
================================================================================
为什么需要它：三份产物是"字符串注入"式拼装出来的（内联快照 + 内联 ECharts），
锚点错位会**静默产出坏页面**——能打开、不报错，只是列表空、KPI 空白、图表无数据。
本脚本用无头 Chrome 真跑一遍，证明「数据加载 → 七个视图渲染（含智能筛选页）→ 筛选联动」都活着。

关键做法（否则 headless 会永久挂起）：
  * 把内联 ECharts 换成**空桩**。ECharts 的持续动画会让 headless 虚拟时间永不收敛，
    --dump-dom 到点也不返回。空桩按**内容标记**定位（'ECharts 5.5.1 - inlined'），
    **绝不按体积挑块**——本项目里数据快照(6.3MB)比 ECharts(1.0MB)还大，
    按体积取最大会把数据块删掉，页面不报错但列表全空，极易误判成"改版改坏了"。
  * 探针写进 document.title：比在 7MB DOM 里翻找快得多。
  * 探针用 setTimeout 延迟，先让应用初始化跑完。
  * 错误捕获器早于所有脚本注入，否则 ERR 永远是 unknown。

用法：
  python3 etl/smoke_dashboard.py
  python3 etl/smoke_dashboard.py --src web/dashboard_offline.html --wait 2500
"""

import argparse
import os
import re
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
STUB_HTML = "/tmp/smoke_dashboard.html"

# ECharts 空桩：app.js 实际用到 init / getMap / registerMap / graphic 四个 API
ECHARTS_STUB = """
window.echarts = {
  init: function () {
    return {
      setOption: function () {}, resize: function () {}, dispose: function () {},
      on: function () {}, off: function () {}, clear: function () {},
      showLoading: function () {}, hideLoading: function () {},
      dispatchAction: function () {}, getOption: function () { return {}; },
      getZr: function () { return { on: function () {}, off: function () {} }; }
    };
  },
  getMap: function () { return undefined; },
  registerMap: function () {},
  graphic: { LinearGradient: function () { return {}; } }
};
"""

CATCH_JS = """<script>window.__ERRS=[];
window.addEventListener('error',function(e){window.__ERRS.push(String((e&&e.message)||e));});
window.addEventListener('unhandledrejection',function(e){window.__ERRS.push('REJ:'+String((e&&e.reason)||e));});
</script>
"""

PROBE_JS = """<script>
setTimeout(function(){
  function cnt(x){return document.querySelectorAll(x).length;}
  function tx(id){var e=document.getElementById(id);return e?String(e.textContent||'').replace(/\\s+/g,' ').trim().slice(0,50):'MISSING';}
  function vis(id){var e=document.getElementById(id);return !!(e&&e.offsetHeight>0);}
  var r=[];
  try{
    r.push('snap='+((window.__SNAPSHOT__||{}).institutions||[]).length);
    r.push('views='+cnt('section.view'));
    r.push('nav='+cnt('.navtab'));
    r.push('kpi_total='+tx('v_total'));
    var ids=['overview','analytics','institutions','filter','integration','quality','about'];
    var okv=[], rowsByView={};
    ids.forEach(function(v){
      try{ if(typeof switchView==='function') switchView(v); }catch(e){ r.push('switchfail_'+v+'='+e.message); }
      okv.push(v+(vis('view-'+v)?'+':'-'));
      rowsByView[v]=cnt('#list .row');
    });
    r.push('switch='+okv.join(','));
    r.push('rows_total='+rowsByView['overview']);
    r.push('rows_inst='+rowsByView['institutions']);
    // ── 分析页结构（2026-09-21 扩充：4 KPI → 6 KPI，8 图 → 15 图 / 4 个区段）──────
    //    图表的**内容**由 /tmp 的真浏览器探针（真 ECharts）负责，
    //    这里只钉住"结构没被改回去 + 渲染函数确实跑过"，打桩环境下做不到更多。
    //    之所以必须钉：新增面板全靠 app.js 的 initAnalyticsCharts 按 id 取容器，
    //    id 写错时页面不报错、只是那块永远空白——正是本脚本存在的理由。
    try{
      if(typeof switchView==='function') switchView('analytics');
      r.push('an_panels='+cnt('#view-analytics .apanel'));
      r.push('an_secs='+cnt('#view-analytics .sec-title'));
      r.push('an_kpis='+cnt('#view-analytics .kpis .card'));
      var anIds=['ch_catown','ch_spdist','ch_splv','ch_distsp','ch_distmx','ch_netlv','ch_srcmap'];
      var anMiss=[];
      anIds.forEach(function(id){ if(!vis(id)) anMiss.push(id); });
      r.push('an_newcharts='+(anIds.length-anMiss.length)+'/'+anIds.length+(anMiss.length?(' miss:'+anMiss.join(',')):''));
      r.push('an_scope='+((tx('an_scope')!=='MISSING'&&tx('an_scope')!=='')?'true':'false'));
      r.push('an_tools='+[vis('an_topn'),vis('an_csv'),vis('an_copy')].filter(Boolean).length);
      r.push('an_drill='+((typeof anDrill==='function'&&typeof anDrillDept==='function'&&typeof anExportCSV==='function')?'true':'false'));
    }catch(e){ r.push('an_fail='+e.message); }
    // ── 布局（2026-09-21 修）：① 侧栏必须 fixed 且滚到底仍贴视口顶 ② 表格型面板内容不得逃出面板 ──
    //    之所以必须钉：这两类都是"看着像好了、其实没有"的缺陷——
    //    侧栏用 sticky 时短页面上可停留范围只有几十像素，滚一点就跟着页面跑；
    //    面板定高 314px 而表格行数随数据变多时，末尾几行会画到面板外、叠在页脚上。
    //    二者都不报错、不留日志，只有量矩形才能发现。
    try{
      if(typeof switchView==='function') switchView('quality');
      var sb=document.querySelector('.sidebar'), mc=document.querySelector('.maincol');
      r.push('sb_pos='+getComputedStyle(sb).position);
      r.push('mc_left='+Math.round(mc.getBoundingClientRect().left));   // 主列必须让开侧栏宽度
      window.scrollTo(0, document.documentElement.scrollHeight);
      r.push('sb_top_bottom='+Math.round(sb.getBoundingClientRect().top));  // 滚到底仍应为 0
      window.scrollTo(0,0);
      var esc=0, ps=document.querySelectorAll('#view-quality .apanel');
      for(var qi=0;qi<ps.length;qi++){
        var qb=ps[qi].children[1]; if(!qb) continue;
        var inner=ps[qi].getBoundingClientRect().bottom-parseFloat(getComputedStyle(ps[qi]).paddingBottom||0);
        if(qb.getBoundingClientRect().bottom-inner>2) esc++;
      }
      r.push('qpanel_escape='+esc);
      r.push('qpanel_grow='+document.querySelectorAll('#view-quality .apanel.grow').length);
      if(typeof switchView==='function') switchView('overview');
    }catch(e){ r.push('layout_fail='+e.message); }
    // ── 定位（2026-09-21 修）：域外坐标不得被贴上「北京市XX区」的假区名 ──
    //    原实现无条件取「最近机构」的 district，而最近机构永远存在，
    //    于是南昌被判成「北京市大兴区」（大兴是北京最南端的区，南方来的点都落它头上）。
    //    危害是"标签假、距离真"：页面同显「北京市大兴区(±435m)」与「1175.9 km」。
    try{
      var hOut=(typeof locateHint==='function')?locateHint(115.89,28.68):null;  // 南昌
      var hIn =(typeof locateHint==='function')?locateHint(116.34,39.73):null;  // 北京大兴
      r.push('geo_out='+(hOut?((hOut.outOfCity?'y':'n')+'/'+(hOut.district||'-')+'/'+Math.round(hOut.nearKm)):'none'));
      r.push('geo_in='+(hIn?((hIn.outOfCity?'y':'n')+'/'+(hIn.district||'-')):'none'));
      // 自动定位落在域外时不得接管基准（否则整个列表按 1,000+ km 排序，毫无参考意义）。
      // 判据用 localStorage：接管才会写基点，不接管则读写前后都是 null。
      var b0=null,b1=null;
      try{ b0=localStorage.getItem('bjyy_base_v1'); }catch(e){}
      try{ if(typeof _applyGeoFix==='function') _applyGeoFix(115.89,28.68,435,{manual:false}); }catch(e){}
      try{ b1=localStorage.getItem('bjyy_base_v1'); }catch(e){}
      r.push('geo_auto_skip='+((b0===null&&b1===null)?'y':'n'));
    }catch(e){ r.push('geo_fail='+e.message); }
    // 筛选联动：列表分页（PAGE_SIZE=20），行数恒等于页容量，不能用行数判断；
    // 要看筛选命中总数 FILTERED.length 是否真的收缩。
    try{
      var f=document.getElementById('f_district');
      if(f&&f.options.length>1){
        var before=(typeof FILTERED!=='undefined'&&FILTERED)?FILTERED.length:-1;
        f.value=f.options[1].value;
        if(typeof applyFilter==='function') applyFilter();
        setTimeout(function(){
          var after=(typeof FILTERED!=='undefined'&&FILTERED)?FILTERED.length:-1;
          r.push('filtered='+before+'_to_'+after);
          fin(r);
        },600);
        return;
      }
    }catch(e){ r.push('filterskip='+e.message); }
    fin(r);
  }catch(e){ document.title='T|PROBE_FAIL='+e.message; }
  function fin(list){
    try{ list.push('ERR='+((window.__ERRS||[]).join('~').slice(0,180)||'none')); }catch(e){}
    document.title='T|'+list.join(' ;; ');
  }
}, WAIT_MS);
</script>
"""


def build_stub_page(src, wait_ms):
    d = open(src, encoding="utf-8").read()
    blocks = list(re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", d, re.S))

    ech = next((m for m in blocks if "ECharts 5.5.1 - inlined" in m.group(1)), None)
    if ech is None:
        print("❌ 未定位到内联 ECharts 块（标记 'ECharts 5.5.1 - inlined'）"); return None
    snap = next((m for m in blocks if "__SNAPSHOT__" in m.group(1)), None)
    if snap is None:
        print("❌ 未定位到内联快照块"); return None
    print("  定位：ECharts 块 %d 字节 / 快照块 %d 字节" % (len(ech.group(1)), len(snap.group(1))))

    s, e = ech.start(1), ech.end(1)
    d = d[:s] + ECHARTS_STUB + d[e:]
    # 打完桩立刻自检数据还在（这一步能马上暴露认错块）
    assert "window.__SNAPSHOT__" in d and '"institutions"' in d, "打桩后快照丢失！"

    d = d.replace("<head>", "<head>\n" + CATCH_JS, 1)
    k = d.rfind("</html>")
    assert k > 0, "未找到 </html> 锚点"
    d = d[:k] + PROBE_JS.replace("WAIT_MS", str(wait_ms)) + d[k:]

    open(STUB_HTML, "w", encoding="utf-8").write(d)
    print("  已生成打桩页 %s (%.2f MB)" % (STUB_HTML, os.path.getsize(STUB_HTML) / 1024 / 1024))
    return STUB_HTML


def run_chrome(page, budget):
    if not os.path.exists(CHROME):
        print("❌ 未找到 Chrome：%s" % CHROME); return None
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
           "--virtual-time-budget=%d" % budget, "--dump-dom", "file://" + page]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=120)
        return p.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        print("❌ Chrome 在 120s 内未返回（虚拟时间不收敛，检查打桩是否生效）")
        subprocess.run(["pkill", "-f", "Chrome.*--headless"], capture_output=True)
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(BASE, "web", "dashboard_offline.html"))
    ap.add_argument("--wait", type=int, default=2500, help="探针延迟(ms)")
    ap.add_argument("--budget", type=int, default=20000, help="Chrome 虚拟时间预算(ms)")
    args = ap.parse_args()

    print("=" * 70)
    print("  前端大屏无头冒烟测试")
    print("=" * 70)
    print("▶ 1. 生成打桩页")
    page = build_stub_page(args.src, args.wait)
    if not page:
        return 1

    print("\n▶ 2. 无头 Chrome 加载")
    dom = run_chrome(page, args.budget)
    if dom is None:
        return 1
    print("  DOM 返回 %s 字节" % "{:,}".format(len(dom)))   # 先看原始长度，别急着过滤

    m = re.search(r"<title>(.*?)</title>", dom, re.S)
    title = m.group(1) if m else "(未取到 title)"
    print("  title: %s" % title)

    print("\n▶ 3. 断言")
    if not title.startswith("T|"):
        print("  ✗ 探针未执行（title 无 T| 前缀）")
        return 1

    parts = [x.strip() for x in title[2:].split(";;")]
    kv = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            kv[k] = v
        elif "->" in p:
            kv[p.split("[")[0]] = p

    ok = True
    checks = []
    n_snap = int(kv.get("snap", "0") or 0)
    # 期望条数从主表现算，避免数据治理后变成假报警。
    # ⚠️ 必须用 csv.reader 计数：主表里有字段含换行（引号包裹的多行值），
    #    按物理行数统计会多加 20 条（实测 9698 ≠ 9678），又变成一次假报警。
    import csv as _csv
    with open("data/processed/master_institutions.csv", encoding="utf-8-sig", newline="") as _mf:
        _n_master = sum(1 for _ in _csv.reader(_mf)) - 1
    checks.append((f"快照机构数 = 主表 {_n_master}", n_snap == _n_master, str(n_snap)))
    checks.append(("七个视图齐备", kv.get("views") == "7", kv.get("views", "?")))
    checks.append(("导航项 7 个", kv.get("nav") == "7", kv.get("nav", "?")))
    sw = kv.get("switch", "")
    checks.append(("七视图均可显示", sw.count("+") == 7, sw))
    rows = int(kv.get("rows_inst", "0") or 0)
    checks.append(("机构列表有行", rows > 0, "rows_inst=%d" % rows))
    # ── 分析页（多维分析）结构与渲染 ──
    checks.append(("分析页面板 15 个", kv.get("an_panels") == "15", kv.get("an_panels", "?")))
    checks.append(("分析页四区段", kv.get("an_secs") == "4", kv.get("an_secs", "?")))
    checks.append(("分析页 KPI 六卡", kv.get("an_kpis") == "6", kv.get("an_kpis", "?")))
    checks.append(("新增 7 图容器可见", str(kv.get("an_newcharts", "")).startswith("7/7"),
                   kv.get("an_newcharts", "?")))
    checks.append(("分析页口径条非空", kv.get("an_scope") == "true", kv.get("an_scope", "?")))
    checks.append(("分析页工具条三键", kv.get("an_tools") == "3", kv.get("an_tools", "?")))
    checks.append(("分析页下钻函数就绪", kv.get("an_drill") == "true", kv.get("an_drill", "?")))
    # ── 布局（2026-09-21）：侧栏固定 + 表格型面板不溢出 ──
    # 无头 Chrome 默认窗口 800x600，落在 ≤1080 断点内，侧栏是 60px 图标条；
    # 断言两种宽度都接受，真正的判据是"主列左边界 == 侧栏宽度"。
    checks.append(("侧栏 fixed 定位", kv.get("sb_pos") == "fixed", kv.get("sb_pos", "?")))
    checks.append(("主列让开侧栏", kv.get("mc_left") in ("188", "60"),
                   "maincol.left=%s" % kv.get("mc_left", "?")))
    checks.append(("滚到底侧栏仍贴顶", kv.get("sb_top_bottom") == "0",
                   "top=%s" % kv.get("sb_top_bottom", "?")))
    checks.append(("质量页表格面板不溢出", kv.get("qpanel_escape") == "0",
                   "escape=%s" % kv.get("qpanel_escape", "?")))
    checks.append(("质量页表格面板 grow", kv.get("qpanel_grow") == "3",
                   kv.get("qpanel_grow", "?")))
    # ── 定位（2026-09-21）：域外判定 + 区名不臆造 ──
    # 判据必须钉在「域外不给区名」这个效果上，而不是「有没有这个函数」。
    go = kv.get("geo_out", "?")
    checks.append(("域外坐标不猜区名", go.startswith("y/-/"), go))
    gi = kv.get("geo_in", "?")
    checks.append(("域内坐标解析区名", gi.startswith("n/大兴区"), gi))
    checks.append(("自动定位域外不接管基准", kv.get("geo_auto_skip") == "y",
                   "localStorage 未写入=%s" % kv.get("geo_auto_skip", "?")))
    errs = kv.get("ERR", "?")
    checks.append(("无运行时错误", errs == "none", errs))

    fv = kv.get("filtered", "")
    f_ok, f_detail = False, fv or "未执行"
    if "_to_" in fv:
        try:
            b, a = [int(x) for x in fv.replace("filtered=", "").split("_to_")]
            f_ok = 0 < a < b
            f_detail = "命中 %d → %d（筛选生效）" % (b, a) if f_ok else "命中 %d → %d" % (b, a)
        except Exception:
            f_detail = fv
    checks.append(("筛选联动收缩结果", f_ok, f_detail))

    for name, passed, detail in checks:
        print("  %s %-18s %s" % ("✓" if passed else "✗", name, detail))
        if not passed:
            ok = False

    print("\n" + "=" * 70)
    print("  %s" % ("✅ 冒烟通过：数据加载 + 七视图渲染 + 筛选联动 全部正常" if ok
                    else "❌ 存在未通过项，见上方 ✗ 标记"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
