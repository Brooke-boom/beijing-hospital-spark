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
    checks.append(("快照机构数 = 9789", n_snap == 9789, str(n_snap)))
    checks.append(("七个视图齐备", kv.get("views") == "7", kv.get("views", "?")))
    checks.append(("导航项 7 个", kv.get("nav") == "7", kv.get("nav", "?")))
    sw = kv.get("switch", "")
    checks.append(("七视图均可显示", sw.count("+") == 7, sw))
    rows = int(kv.get("rows_inst", "0") or 0)
    checks.append(("机构列表有行", rows > 0, "rows_inst=%d" % rows))
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
