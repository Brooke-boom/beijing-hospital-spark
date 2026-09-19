#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单文件形态的「就医决策」主线端到端冒烟。

背景：单文件大屏点「就医决策」原本跳 /spa/，在 GitHub Pages（https）上是 404 ——
分享出去的链接等于没有主线。现在主线内嵌进单文件，本脚本就是这道验收：
在**没有后端、没有数据库**的前提下，一个 HTML 文件能否走完
「说需求 → 看候选 → 做比较 → 拿方案」，并且大屏原有查阅功能不回归。

跑两种环境：
  file://  最严苛，双击打开的场景
  http://  用本地静态服务模拟 GitHub Pages

用法：
    python etl/smoke_offline_plan.py
    SHOT_DIR=/tmp/plan_shots python etl/smoke_offline_plan.py   # 顺带留档四步截图
"""
from __future__ import annotations

import functools
import http.server
import os
import socketserver
import sys
import threading
import time

from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE_URL = "file://" + os.path.join(ROOT, "web", "dashboard_offline.html")
PORT = 8931
SHOT_DIR = os.environ.get("SHOT_DIR", "")

PASS, FAIL, ERRORS = [], [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"  ✓ {name}")
    else:
        FAIL.append(f"{name} {detail}")
        print(f"  ✗ {name} {detail}")


def serve():
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    httpd.allow_reuse_address = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def run_case(pg, url, tag, shot_dir=None):
    print(f"\n=== {tag} ===")
    pg.on("pageerror", lambda e: ERRORS.append(f"[{tag}] pageerror: {e}"))
    pg.on("console", lambda m: ERRORS.append(
        f"[{tag}] console.{m.type}: {m.text} @ {(m.location or {}).get('url', '?')}")
        if m.type == "error" else None)

    def shot(name):
        """只为留档而截，不参与断言（断言在别处，截图失败不该让验收挂掉）。"""
        if not shot_dir:
            return
        os.makedirs(shot_dir, exist_ok=True)
        try:
            pg.screenshot(path=os.path.join(shot_dir, name), full_page=True)
        except Exception as e:
            print(f"  · 截图 {name} 失败：{e}")

    pg.goto(url, wait_until="load", timeout=90000)
    pg.wait_for_timeout(2500)

    # ---- 1. 入口不再是会 404 的硬链接 ----
    info = pg.evaluate("""() => {
        const a = document.getElementById('nav_workbench');
        return a ? { tag: a.tagName, href: a.getAttribute('href'),
                     view: a.getAttribute('data-view'),
                     dead: [...document.querySelectorAll('a[href="/spa/"]')].length } : null;
    }""")
    check("入口存在", bool(info))
    check("入口是按钮而非 /spa/ 硬链接", info and info["tag"] == "BUTTON" and not info["href"],
          f"→ {info}")
    check("页面内无残留的 /spa/ 死链", info and info["dead"] == 0, f"→ {info and info['dead']}")

    # ---- 2. 切到工作台 ----
    pg.click("#nav_workbench")
    pg.wait_for_timeout(600)
    check("切换到工作台视图",
          pg.evaluate("() => document.getElementById('view-workbench').classList.contains('active')"))
    shot("01_工作台_起始页.png")
    check("工作台数据包已内嵌",
          pg.evaluate("() => !!window.__PLAN_DATA__ && window.__PLAN_DATA__.strength.length > 10000"),
          f"→ {pg.evaluate('() => window.__PLAN_DATA__ ? window.__PLAN_DATA__.strength.length : 0')} 行")

    # ---- 3. 说需求 → 生成 ----
    pg.fill("#wb_q", "孩子反复发烧咳嗽三天了")
    pg.click("#wb_run")
    pg.wait_for_timeout(900)

    tri = pg.inner_text("#wb_triage")
    check("给出分诊结论（儿科）", "儿科" in tri, f"→ {tri[:80]}")
    check("分诊含判断依据", "判断依据" in tri)
    check("步骤条推进到第 2 步",
          pg.evaluate("() => document.querySelector('.wb-step[data-step=\"2\"]').classList.contains('on')"))

    # ---- 4. 候选 ----
    cards = pg.evaluate("() => document.querySelectorAll('#wb_cands .wb-cand').length")
    check("候选卡渲染", cards >= 3, f"→ {cards} 张")
    top1 = pg.evaluate("() => (document.querySelector('#wb_cands .wb-cname')||{}).textContent || ''")
    check("旗舰用例排序正确（儿童医院居首）", "儿童医院" in top1, f"→ {top1}")
    check("候选卡含匹配度", "匹配度" in pg.inner_text("#wb_cands"))
    check("默认预选 3 家做对比",
          pg.evaluate("() => document.querySelectorAll('#wb_cands .wb-cand.picked').length") == 3)

    shot("02_分诊与候选.png")

    # ---- 5. 对比 ----
    check("下一步按钮可用", pg.evaluate("() => !document.getElementById('wb_to_cmp').disabled"))
    pg.click("#wb_to_cmp")
    pg.wait_for_timeout(600)
    rows = pg.evaluate("() => document.querySelectorAll('#wb_cmp table tbody tr').length")
    cols = pg.evaluate("() => document.querySelectorAll('#wb_cmp table thead th').length")
    check("对比表渲染（11 项 × 3 家）", rows == 11 and cols == 4, f"→ {rows} 行 {cols} 列")
    check("对比表含专科实力与集中度依据",
          "专科实力" in pg.inner_text("#wb_cmp"))

    shot("03_横向对比.png")

    # ---- 6. 主选 → 方案 ----
    pg.evaluate("""() => {
        const b = document.querySelector('#wb_cmp [data-act="primary"]');
        if (b) b.click();
    }""")
    pg.wait_for_timeout(400)
    pg.click("#wb_to_plan")
    pg.wait_for_timeout(700)
    plan = pg.inner_text("#wb_plancard")
    check("方案卡渲染", len(plan) > 200, f"→ {len(plan)} 字")
    for seg in ("为什么推荐这家", "备选机构", "就诊前准备", "预约挂号", "不构成诊断意见"):
        check(f"方案含「{seg}」", seg in plan)
    check("方案有可带走动作",
          pg.evaluate("""() => ['wb_copy','wb_download','wb_print','wb_save']
              .every(i => !!document.getElementById(i))"""))

    shot("04_就医方案.png")

    # ---- 7. 回到起始页（进得去也要出得来） ----
    check("「重新开始」可用", pg.evaluate("() => !document.getElementById('wb_home').disabled"))
    pg.click("#wb_home")
    pg.wait_for_timeout(500)
    check("回到起始页且输入已清空",
          pg.evaluate("() => document.getElementById('wb_q').value === '' && !document.querySelector('#wb_cands .wb-cand')"))
    check("步骤条退回到第 1 步",
          pg.evaluate("() => document.querySelector('.wb-step[data-step=\"1\"]').classList.contains('on')"))

    # ---- 8. 查阅形态不回归 ----
    pg.click('.navtab[data-view="overview"]')
    pg.wait_for_timeout(1200)
    check("数据总览仍可渲染",
          pg.evaluate("() => document.getElementById('view-overview').classList.contains('active')"))
    kpi = pg.evaluate("() => (document.getElementById('v_total')||{}).textContent || ''")
    check("总览 KPI 有值", kpi.strip() not in ("", "—"), f"→ {kpi}")
    for v in ("analytics", "institutions", "filter", "integration", "quality", "about"):
        pg.click(f'.navtab[data-view="{v}"]')
        pg.wait_for_timeout(260)
        ok = pg.evaluate(f"() => document.getElementById('view-{v}').classList.contains('active')")
        if not ok:
            check(f"查阅页 {v} 可切换", False)
            break
    else:
        check("查阅页 6 个视图全部可切换", True)

    # ---- 9. 主题切换后工作台仍可用（ECharts 重绘 + 变量装载） ----
    pg.click("#btn_theme")
    pg.wait_for_timeout(600)
    pg.click("#nav_workbench")
    pg.wait_for_timeout(400)
    check("切换主题后工作台可用",
          pg.evaluate("() => document.getElementById('view-workbench').classList.contains('active')"))


def main():
    srv = serve()
    url_http = f"http://127.0.0.1:{PORT}/web/dashboard_offline.html"
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome")
        for i, (url, tag) in enumerate(((FILE_URL, "file:// 双击打开"),
                                        (url_http, "http:// 模拟 Pages"))):
            pg = br.new_page(viewport={"width": 1500, "height": 1000})
            try:
                # 只对第一个环境留档，http 环境的流程完全相同
                run_case(pg, url, tag, shot_dir=SHOT_DIR if i == 0 else None)
            finally:
                pg.close()
        br.close()
    srv.shutdown()

    print("\n" + "=" * 62)
    real = [e for e in ERRORS if "favicon" not in e]
    if real:
        print(f"运行时错误 {len(real)} 条：")
        for e in real[:8]:
            print("   " + e[:160])
    if FAIL:
        print(f"❌ 失败 {len(FAIL)} 项 / 通过 {len(PASS)} 项")
        for f in FAIL:
            print("   " + f)
        sys.exit(1)
    print(f"✅ 全部通过：{len(PASS)} 项断言 · 运行时错误 {len(real)} 条")
    if real:
        sys.exit(1)


if __name__ == "__main__":
    main()
