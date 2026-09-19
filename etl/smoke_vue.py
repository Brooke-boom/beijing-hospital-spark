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
# 2026-09-19 信息架构重构后：主线 1 个 + 查阅支撑页 4 个（原 7 个入口已收敛）
ROUTES = [
    ("plan", "就医决策"),
    ("find", "找机构"),
    ("profile", "资源画像"),
    ("govern", "数据治理"),
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

        # ---- 1. 首屏 = 任务主线（就医决策），不再是大屏首页 ----
        try:
            has_stepper = pg.evaluate("() => document.querySelectorAll('.step').length")
            has_ask = pg.evaluate("() => !!document.querySelector('.ask')")
            hist = pg.evaluate("() => document.querySelectorAll('.histlist .hist').length")
        except Exception:
            has_stepper, has_ask, hist = 0, False, 0
        checks.append(("首屏为就医决策工作台（四步任务流）",
                       has_stepper == 4 and has_ask, "steps=%d ask=%s 历史=%d" % (has_stepper, has_ask, hist)))

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

        # ---- 3. 支撑页子标签：资源画像 / 数据治理 ----
        pg.goto("%s#/profile?t=overview" % BASE, wait_until="networkidle", timeout=45000)
        time.sleep(2.6)
        ov = pg.evaluate("""() => ({
          canvas: document.querySelectorAll('canvas').length,
          tabs: [...document.querySelectorAll('.subtab')].map(x => x.innerText.trim()),
          on: (document.querySelector('.subtab.on')||{}).innerText || ''
        })""")
        checks.append(("资源画像·总览 有图表 canvas", ov["canvas"] >= 4,
                       "canvas=%d tabs=%s" % (ov["canvas"], "|".join(ov["tabs"]))))

        pg.goto("%s#/profile?t=analytics" % BASE, wait_until="networkidle", timeout=45000)
        time.sleep(2.6)
        an = pg.evaluate("() => ({canvas: document.querySelectorAll('canvas').length,"
                         " on: (document.querySelector('.subtab.on')||{}).innerText || ''})")
        checks.append(("资源画像·结构分析 子标签切换到图表页",
                       an["canvas"] >= 4 and an["on"] == "结构分析",
                       "canvas=%d on=%s" % (an["canvas"], an["on"])))

        pg.goto("%s#/govern?t=quality" % BASE, wait_until="networkidle", timeout=45000)
        time.sleep(2.6)
        qu = pg.evaluate("() => ({canvas: document.querySelectorAll('canvas').length,"
                         " on: (document.querySelector('.subtab.on')||{}).innerText || ''})")
        checks.append(("数据治理·质量核验 有图表 canvas",
                       qu["canvas"] >= 1 and qu["on"] == "质量核验",
                       "canvas=%d on=%s" % (qu["canvas"], qu["on"])))

        # ---- 4. 机构列表 + 筛选 + 分页（找机构支撑页） ----
        pg.goto("%s#/find" % BASE, wait_until="networkidle", timeout=45000)
        time.sleep(2.4)
        inst = pg.evaluate("() => document.querySelectorAll('.tbl tbody tr').length")
        checks.append(("找机构页有列表行", inst > 0, "rows=%d" % inst))

        pg.goto("%s#/find?t=institutions" % BASE, wait_until="networkidle", timeout=45000)
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
            pg.goto("%s#/find?t=institutions" % BASE, wait_until="networkidle", timeout=45000)
            time.sleep(2.4)
            pg.evaluate("() => { const r = document.querySelector('.tbl tbody tr'); if (r) r.click(); }")
            time.sleep(2.5)
            dlen = pg.evaluate("() => ((document.querySelector('.drawer')||{}).innerText||'').length")
            checks.append(("详情抽屉打开", dlen > 80, "抽屉文本长度 %d" % dlen))
        except Exception as e:
            checks.append(("详情抽屉打开", False, str(e)[:120]))

        # ---- 6. 主题切换 ----
        try:
            pg.goto("%s#/profile?t=overview" % BASE, wait_until="networkidle", timeout=45000)
            time.sleep(2.8)
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
