#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
总览页首屏探针：FILTERED 到底是多少家 / 两张右栏图算的是什么
================================================================================
背景：首页「医疗机构类型构成」在截图里显示 医院 96 家，而同页 KPI 写「医院数量 732」。
两张图都读同一个数组（FILTERED），所以先要判断：
  (a) 是默认状态就带了筛选 → 两张图算的是"某子集"，属口径/交互问题；
  (b) 还是渲染时字段缺失 → 属数据问题。
本探针把 FILTERED 的长度、两张图真实的轴数据、以及各字段的非空率一起打出来。

用法：
  python3 etl/probe_overview.py                 # 默认开 web/dashboard_offline.html
  python3 etl/probe_overview.py --src web/dashboard_standalone.html
  python3 etl/probe_overview.py --page qual     # 切到「数据质量」页再探
"""
import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = os.path.join(BASE, "web", "dashboard_offline.html")

# 关动画：ECharts 的补间会让 headless 的虚拟时间不收敛（详见技能 single-file-spa-verify）
KILL_JS = """<script>(function(){
  if (typeof echarts === 'undefined') return;
  var raw = echarts.init;
  echarts.init = function(){
    var it = raw.apply(this, arguments), so = it.setOption;
    it.setOption = function(o){
      try { if (o && typeof o === 'object') {
        o.animation = false;
        if (o.series && o.series.forEach)
          o.series.forEach(function(s){ if (s && typeof s === 'object') s.animation = false; });
      } } catch (e) {}
      return so.apply(this, arguments);
    };
    return it;
  };
})();</script>
"""

PROBE = r"""() => {
  const out = {};
  out.filtered = (typeof FILTERED !== 'undefined' && FILTERED) ? FILTERED.length : null;
  out.data = (typeof DATA !== 'undefined' && DATA && DATA.institutions) ? DATA.institutions.length : null;
  out.snapshotTotal = (window.__SNAPSHOT__ || {}).total;
  out.page = (typeof PAGE_KEY !== 'undefined') ? PAGE_KEY : (location.hash || '');

  const optOf = (c) => {
    try {
      if (!c) return null;
      const o = c.getOption();
      const axis = (o.yAxis && o.yAxis[0] && o.yAxis[0].data) || (o.xAxis && o.xAxis[0] && o.xAxis[0].data) || [];
      const ser = (o.series && o.series[0] && o.series[0].data) || [];
      return { axis: axis, series: ser };
    } catch (e) { return 'ERR:' + e.message; }
  };
  out.ch2 = optOf(typeof CH2 !== 'undefined' ? CH2 : null);
  out.ch3 = optOf(typeof CH3 !== 'undefined' ? CH3 : null);

  // 关键字段非空率（以 FILTERED 为分母，与前端卡片同口径）
  const F = (typeof FILTERED !== 'undefined' && FILTERED) || [];
  const flds = ['district','addr','profit','key_depts','level','phone','beds','traffic','website'];
  out.fields = {};
  flds.forEach(f => {
    const k = F.filter(r => r[f] != null && r[f] !== '').length;
    out.fields[f] = [k, F.length ? +(k / F.length * 100).toFixed(1) : 0];
  });

  // 质量卡片里实际渲染出来的数字（DOM 文本），用于核对是否与真实数据一致
  const t = document.getElementById('qual_field_table');
  out.qualTable = t ? t.innerText.replace(/\n+/g, ' | ') : null;
  return out;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--page", default="", help="切页：overview / qual ...")
    ap.add_argument("--width", type=int, default=1600)
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("需要 playwright")
        return 2

    src = args.src if os.path.isabs(args.src) else os.path.join(BASE, args.src)
    # 关动画补丁打到临时文件，不动原始产物
    raw = open(src, encoding="utf-8").read()
    patched = raw.replace("<script>window.__SNAPSHOT__", KILL_JS + "<script>window.__SNAPSHOT__", 1)
    if patched == raw:
        print("⚠️ 关动画补丁未注入（锚点未命中），继续但可能超时")
    tmp = os.path.join(BASE, "web", "__probe_tmp.html")
    open(tmp, "w", encoding="utf-8").write(patched)

    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="chrome", headless=True)
        pg = br.new_page(viewport={"width": args.width, "height": 1000})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto("file://" + tmp, wait_until="load", timeout=60000)
        pg.wait_for_timeout(3500)
        if args.page:
            try:
                pg.evaluate("(p) => { try { nav(p); } catch(e) { location.hash = '#' + p; } }", args.page)
                pg.wait_for_timeout(2500)
            except Exception as e:
                print("切页失败:", e)
        res = pg.evaluate(PROBE)
        # 顺带截一张右栏，便于肉眼看
        try:
            el = pg.query_selector(".panel-stack")
            if el:
                el.screenshot(path=os.path.join(BASE, "docs", "images", "_probe_overview_stack.png"))
        except Exception:
            pass
        br.close()

    print(json.dumps(res, ensure_ascii=False, indent=2))
    if errs:
        print("\n=== pageerror ===")
        for e in errs[:10]:
            print(" -", e)
    try:
        os.remove(tmp)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
