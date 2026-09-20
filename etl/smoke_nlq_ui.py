# -*- coding: utf-8 -*-
"""
智能筛选页（自然语言 + 条件双通道）无头冒烟测试
================================================================================
为什么需要它（而不是只靠 verify_artifacts 的"文件齐备"检查）：
  "词表 + 引擎 + 界面层都进了产物"只能证明文件在，不能证明页面真的能用。
  这一页还有三条只有真跑才能验证的性质：
    ① 自然语言解析出条件后，**结果真的来自数据**（KPI/列表/来源说明都有内容）；
    ② 病征类输入必须**拒答**，不能硬凑一个结果（这是本项目的定位红线）；
    ③ 两条通道（自然语言 / 条件）与维度统计走的是同一条结果链，不能只活一条。

做法与 smoke_dashboard.py 一致：
  * ECharts 换成空桩（持续动画会让 headless 虚拟时间永不收敛）；
  * 探针写进 document.title；错误捕获器早于所有脚本注入；
  * 探针按"真实用户动作"驱动：填输入框 → 点按钮 → 读 DOM，而不是直接调内部函数。

用法：
  python3 etl/smoke_nlq_ui.py
  python3 etl/smoke_nlq_ui.py --src web/dashboard_offline.html --wait 2500
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import smoke_dashboard as sd          # 复用空桩 / 错误捕获器 / 无头 Chrome 启动器

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STUB_HTML = "/tmp/smoke_nlq_ui.html"

PROBE_JS = """<script>
setTimeout(function(){
  function cnt(x){return document.querySelectorAll(x).length;}
  function tx(id){var e=document.getElementById(id);return e?String(e.textContent||'').replace(/\\s+/g,' ').trim().slice(0,70):'MISSING';}
  var r=[];
  function done(){
    try{ r.push('ERR='+(((window.__ERRS||[]).join('~')).slice(0,200)||'none')); }catch(e){}
    document.title='T|'+r.join(' ;; ');
  }
  function setQ(v){document.getElementById('f_ai').value=v;}
  function go(){document.getElementById('btn_ai').click();}
  try{
    if(typeof switchView==='function') switchView('filter');
    setTimeout(function(){
      // ── A. 自然语言：多条件（两个区 + 三级）
      setQ('朝阳区和海淀区的三级医院'); go();
      setTimeout(function(){
        r.push('vis=' + (document.getElementById('view-filter').offsetHeight>0));
        r.push('chips=' + cnt('#nlq_chips .nlqchip'));
        r.push('chip1=' + tx('nlq_chips'));
        r.push('count=' + tx('nlq_count'));
        r.push('kpi=' + tx('nlq_kpis'));
        r.push('rows=' + cnt('#nlq_list .row'));
        r.push('pager=' + tx('nlq_pg'));
        r.push('summary=' + tx('nlq_summary'));
        r.push('src=' + tx('nlq_source'));
        r.push('sorts=' + tx('nlq_sortnote'));
        // ── B. 条件卡片可逐项移除
        var ch=document.querySelector('#nlq_chips .nlqchip');
        if(ch) ch.click();
        setTimeout(function(){
          r.push('chips_after_drop=' + cnt('#nlq_chips .nlqchip'));
          // ── C. 病征类输入必须拒答（定位红线）
          setQ('75岁女性腰椎滑脱走路困难'); go();
          setTimeout(function(){
            r.push('refuse=' + (cnt('#nlq_msg.nlqrefuse')>0));
            r.push('refuse_txt=' + tx('nlq_msg'));
            r.push('refuse_rows=' + cnt('#nlq_list .row'));
            // ── D. 条件筛选通道
            document.querySelector('#nlq_tabs .nlqtab[data-ntab="cond"]').click();
            var d=document.getElementById('q_district');
            d.value='海淀区';
            document.getElementById('q_run').click();
            setTimeout(function(){
              r.push('cond_vis=' + (document.getElementById('nlq_pane_cond').classList.contains('active')));
              r.push('cond_count=' + tx('nlq_count'));
              r.push('cond_rows=' + cnt('#nlq_list .row'));
              // ── E. 维度统计（AI 统计 + 图表联动）
              document.querySelector('#nlq_tabs .nlqtab[data-ntab="nl"]').click();
              setQ('按行政区统计三级医院的数量'); go();
              setTimeout(function(){
                r.push('stats_show=' + (document.getElementById('nlq_statsbox').style.display!=='none'));
                r.push('stats_title=' + tx('nlq_stats_title'));
                r.push('stats_summary=' + tx('nlq_summary'));
                // ── F. 清空条件后应回到空态
                r.push('stats_kpi=' + tx('nlq_kpis'));
                r.push('stats_grid=' + document.getElementById('nlq_kpis').className);
                r.push('stats_list=' + tx('nlq_list'));
                done();
              }, 900);
            }, 900);
          }, 900);
        }, 900);
      }, 900);
    }, 400);
  }catch(e){ document.title='T|PROBE_FAIL='+e.message; }
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
    s, e = ech.start(1), ech.end(1)
    d = d[:s] + sd.ECHARTS_STUB + d[e:]
    assert "window.__SNAPSHOT__" in d and '"institutions"' in d, "打桩后快照丢失！"
    d = d.replace("<head>", "<head>\n" + sd.CATCH_JS, 1)
    k = d.rfind("</html>")
    assert k > 0, "未找到 </html> 锚点"
    d = d[:k] + PROBE_JS.replace("WAIT_MS", str(wait_ms)) + d[k:]
    open(STUB_HTML, "w", encoding="utf-8").write(d)
    print("  已生成打桩页 %s (%.2f MB)" % (STUB_HTML, os.path.getsize(STUB_HTML) / 1024 / 1024))
    return STUB_HTML


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(BASE, "web", "dashboard_offline.html"))
    ap.add_argument("--wait", type=int, default=2200)
    ap.add_argument("--budget", type=int, default=30000)
    args = ap.parse_args()

    print("=" * 70)
    print("  智能筛选页无头冒烟测试（自然语言 / 条件 / 统计 / 拒答）")
    print("=" * 70)
    print("▶ 1. 生成打桩页")
    page = build_stub_page(args.src, args.wait)
    if not page:
        return 1

    print("\n▶ 2. 无头 Chrome 加载")
    dom = sd.run_chrome(page, args.budget)
    if dom is None:
        return 1
    print("  DOM 返回 %s 字节" % "{:,}".format(len(dom)))
    m = re.search(r"<title>(.*?)</title>", dom, re.S)
    title = m.group(1) if m else "(未取到 title)"
    print("  title: %s" % title)

    print("\n▶ 3. 断言")
    if not title.startswith("T|"):
        print("  ✗ 探针未执行（title 无 T| 前缀）"); return 1
    kv = {}
    for p in [x.strip() for x in title[2:].split(";;")]:
        if "=" in p:
            k, v = p.split("=", 1); kv[k] = v

    checks = []
    checks.append(("智能筛选页可见", kv.get("vis") == "true", kv.get("vis", "?")))
    checks.append(("自然语言解析出条件卡片", int(kv.get("chips", "0") or 0) >= 3,
                   "chips=%s" % kv.get("chips")))
    checks.append(("条件卡片含行政区与等级",
                   "行政区" in kv.get("chip1", "") and "医院等级" in kv.get("chip1", ""),
                   kv.get("chip1", "?")[:64]))
    checks.append(("结果计数非空", "家" in kv.get("count", "") and "—" not in kv.get("count", ""),
                   kv.get("count", "?")))
    checks.append(("KPI 概览有真实数字", "命中机构" in kv.get("kpi", "") and "三级医院" in kv.get("kpi", ""),
                   kv.get("kpi", "?")[:64]))
    checks.append(("结果列表有行", int(kv.get("rows", "0") or 0) > 0, "rows=%s" % kv.get("rows")))
    checks.append(("结果说明来自模板", len(kv.get("summary", "")) > 20, kv.get("summary", "?")[:64]))
    checks.append(("数据来源说明已渲染", "数据来源" in kv.get("src", ""), kv.get("src", "?")[:64]))
    checks.append(("排序口径已标注", "排序" in kv.get("sorts", ""), kv.get("sorts", "?")[:64]))
    checks.append(("条件卡片可移除", int(kv.get("chips_after_drop", "9") or 9) == 2,
                   "chips=%s" % kv.get("chips_after_drop")))
    checks.append(("病征输入被拒答", kv.get("refuse") == "true", kv.get("refuse_txt", "?")[:64]))
    checks.append(("拒答时不产生结果行", kv.get("refuse_rows") == "0", "rows=%s" % kv.get("refuse_rows")))
    checks.append(("条件筛选通道可用", kv.get("cond_vis") == "true" and int(kv.get("cond_rows", "0") or 0) > 0,
                   "cond_count=%s / rows=%s" % (kv.get("cond_count"), kv.get("cond_rows"))))
    checks.append(("维度统计面板出现", kv.get("stats_show") == "true", kv.get("stats_show", "?")))
    checks.append(("统计标题为该维度", "行政区" in kv.get("stats_title", ""), kv.get("stats_title", "?")))
    checks.append(("统计说明有内容", len(kv.get("stats_summary", "")) > 20, kv.get("stats_summary", "?")[:64]))
    checks.append(("筛选结果分页已渲染", "/" in kv.get("pager", ""), kv.get("pager", "?")))
    checks.append(("统计 KPI 换口径", "统计机构总数" in kv.get("stats_kpi", ""), kv.get("stats_kpi", "?")[:64]))
    checks.append(("统计 KPI 用四列栅格", "k4" in kv.get("stats_grid", ""), kv.get("stats_grid", "?")))
    checks.append(("统计结果区不谎报列表", "统计" in kv.get("stats_list", ""), kv.get("stats_list", "?")[:64]))
    errs = kv.get("ERR", "?")
    checks.append(("无运行时错误", errs == "none", errs))

    ok = True
    for name, passed, detail in checks:
        print("  %s %-22s %s" % ("✓" if passed else "✗", name, detail))
        if not passed:
            ok = False
    print("\n" + "=" * 70)
    print("  %s" % ("✅ 智能筛选页冒烟通过：自然语言 / 条件 / 统计 / 拒答 全部正常" if ok
                    else "❌ 存在未通过项，见上方 ✗ 标记"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
