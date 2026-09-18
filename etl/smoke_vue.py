# -*- coding: utf-8 -*-
"""Vue 前端（前后端分离形态）无头冒烟测试
=========================================
依赖：Flask 已在 127.0.0.1:5001 运行（web/app.py），Vue 已构建到 web/vue/dist。

覆盖：
  1. 启动后能拿到真实数据（机构总数 9,789）
  2. 7 个路由逐个可达且渲染出内容
  3. 图表页 canvas 真的画出来了（ECharts 有实例）
  4. 机构查询页列表有行、分页可翻
  5. 主题切换不报错
  6. 全程 0 个未捕获运行时错误

运行：
  python etl/smoke_vue.py
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5001/spa/"
ROUTES = [
    ("overview", "数据总览"),
    ("analytics", "医疗资源分析"),
    ("institutions", "机构查询"),
    ("filter", "智能筛选"),
    ("integration", "数据整合"),
    ("quality", "数据质量"),
    ("about", "系统说明"),
]


def main():
    errors = []
    checks = []

    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)
        pg = br.new_page(viewport={"width": 1600, "height": 1000})
        pg.on("console", lambda m: errors.append("console." + m.type + ": " + m.text)
              if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))

        pg.goto(BASE, wait_until="networkidle", timeout=45000)
        time.sleep(3.0)

        # ---- 1. 数据加载 ----
        try:
            kpi = pg.inner_text(".kpis").replace("\n", " ")
        except Exception:
            kpi = ""
        checks.append(("首页 KPI 渲染", "9,789" in kpi or "9789" in kpi, kpi[:150]))

        # ---- 2. 逐路由可达 ----
        results = []
        for name, title in ROUTES:
            pg.goto("%s#/%s" % (BASE, name), wait_until="networkidle", timeout=45000)
            time.sleep(2.2)
            info = pg.evaluate("""() => {
              const page = document.querySelector('.page') || document.querySelector('.maincol');
              const txt = page ? page.innerText.trim() : '';
              return {
                hasPage: !!document.querySelector('.page'),
                len: txt.length,
                head: txt.slice(0, 60).replace(/\\n/g, ' '),
                canvas: document.querySelectorAll('canvas').length,
                rows: document.querySelectorAll('.tbl tbody tr').length,
                navActive: (document.querySelector('.navtab.active .lbl') || {}).innerText || ''
              };
            }""")
            results.append((name, title, info))
            ok = info["hasPage"] and info["len"] > 60
            checks.append(("路由 %-12s 渲染" % name, ok,
                           "len=%d canvas=%d rows=%d nav=%s" % (
                               info["len"], info["canvas"], info["rows"], info["navActive"])))

        # ---- 3. 图表页 canvas ----
        ov = [r for r in results if r[0] == "overview"][0][2]
        checks.append(("总览页有 4 个图表 canvas", ov["canvas"] >= 4, "canvas=%d" % ov["canvas"]))
        an = [r for r in results if r[0] == "analytics"][0][2]
        checks.append(("分析页有 4 个图表 canvas", an["canvas"] >= 4, "canvas=%d" % an["canvas"]))
        qu = [r for r in results if r[0] == "quality"][0][2]
        checks.append(("质量页有图表 canvas", qu["canvas"] >= 1, "canvas=%d" % qu["canvas"]))

        # ---- 4. 机构列表 + 筛选 + 分页 ----
        inst = [r for r in results if r[0] == "institutions"][0][2]
        checks.append(("机构查询页有列表行", inst["rows"] > 0, "rows=%d" % inst["rows"]))

        pg.goto("%s#/institutions" % BASE, wait_until="networkidle", timeout=45000)
        time.sleep(2.2)
        try:
            def total_of():
                return pg.evaluate("""() => {
                  const tags = [...document.querySelectorAll('.panel h3 .tag')];
                  const t = tags.find(x => /^共/.test(x.innerText.trim()));
                  return t ? t.innerText.trim() : '';
                }""")
            t0 = total_of()
            # 选第一个区
            pg.evaluate("""() => {
              const s = document.querySelectorAll('select.ctl')[0];
              if (s && s.options.length > 1) { s.value = s.options[1].value;
                s.dispatchEvent(new Event('change', { bubbles: true })); }
            }""")
            time.sleep(2.2)
            t1 = total_of()
            n1 = pg.evaluate("() => document.querySelectorAll('.tbl tbody tr').length")
            ok = bool(t0) and bool(t1) and t0 != t1 and n1 > 0
            checks.append(("区域筛选生效", ok, "%s → %s（列表 %d 行）" % (t0, t1, n1)))
        except Exception as e:
            checks.append(("区域筛选生效", False, str(e)[:120]))

        # 翻页
        try:
            pg.evaluate("""() => {
              const bs = [...document.querySelectorAll('.pager .btn')];
              const idx = bs.findIndex(b => /下一页/.test(b.innerText));
              if (idx >= 0 && !bs[idx].disabled) bs[idx].click();
            }""")
            time.sleep(2.0)
            pageno = pg.evaluate("() => (document.querySelector('.pager .info')||{}).innerText || ''")
            checks.append(("分页可翻页", "第 2" in pageno, pageno.replace("\n", " ")[:80]))
        except Exception as e:
            checks.append(("分页可翻页", False, str(e)[:120]))

        # ---- 5. 详情抽屉 ----
        try:
            pg.goto("%s#/institutions" % BASE, wait_until="networkidle", timeout=45000)
            time.sleep(2.2)
            pg.evaluate("() => { const r = document.querySelector('.tbl tbody tr'); if (r) r.click(); }")
            time.sleep(2.5)
            dlen = pg.evaluate("() => ((document.querySelector('.drawer')||{}).innerText||'').length")
            checks.append(("详情抽屉打开", dlen > 80, "抽屉文本长度 %d" % dlen))
        except Exception as e:
            checks.append(("详情抽屉打开", False, str(e)[:120]))

        # ---- 6. 主题切换 ----
        try:
            pg.goto("%s#/overview" % BASE, wait_until="networkidle", timeout=45000)
            time.sleep(2.5)
            pg.evaluate("() => document.querySelector('.themebtn').click()")
            time.sleep(2.5)
            th = pg.evaluate("() => document.documentElement.getAttribute('data-theme')")
            canv = pg.evaluate("() => document.querySelectorAll('canvas').length")
            checks.append(("主题切换并重绘", th == "light" and canv >= 4, "theme=%s canvas=%d" % (th, canv)))
        except Exception as e:
            checks.append(("主题切换并重绘", False, str(e)[:120]))

        br.close()

    # ---- 汇总 ----
    print("=" * 78)
    print("Vue 前端冒烟测试结果")
    print("=" * 78)
    failed = 0
    for name, ok, detail in checks:
        print("  %s %-30s %s" % ("✓" if ok else "✗", name, detail))
        if not ok:
            failed += 1

    real_errors = [e for e in errors if "favicon" not in e.lower()]
    print("-" * 78)
    print("  未捕获运行时错误：%d" % len(real_errors))
    for e in real_errors[:10]:
        print("    ! " + e[:180])

    print("=" * 78)
    if failed == 0 and not real_errors:
        print("✅ 全部通过")
        return 0
    print("❌ 失败 %d 项，错误 %d 条" % (failed, len(real_errors)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
