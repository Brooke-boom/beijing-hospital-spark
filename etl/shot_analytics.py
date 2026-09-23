#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析页四段截图（浅色 / 深色）—— 文档与答辩材料的配图来源
================================================================================
为什么单独有个截图脚本：
  「数字对、图长错」这类故障探针查不出来 —— 断言只看 series 结构是否合法，
  而截图能一眼看出编码错、行序反、末两档同色、面板空白。
  本项目已多次出现「闸门全绿但图是错的」，所以把截图固化成可复现的一步。

做法：
  * 用**真** ECharts（不空桩），否则截出来的是空白面板。
  * 每段先用 JS 把 `sec-title` 与紧随其后的图栅格包进一个临时 wrapper，
    再对 wrapper 做元素截图 —— 这样标题与图同框，且不用算 clip 坐标
    （clip 坐标在滚动后会越界报错，实测踩过）。
  * 截完立刻还原 DOM，避免影响下一段。

用法：
  python3 etl/shot_analytics.py                      # 四段 × 浅色
  python3 etl/shot_analytics.py --theme dark
  python3 etl/shot_analytics.py --segs 03            # 只截 03 空间格局
  python3 etl/shot_analytics.py --src web/dashboard_standalone.html
"""

import argparse
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = os.path.join(BASE, "web", "dashboard_offline.html")
DEFAULT_OUT = os.path.join(BASE, "docs", "images")

# 段落号 → 文件名词根（与既有 docs/images/analytics_*_seg0N_*.png 命名保持一致）
SEG_SLUG = {"01": "structure", "02": "specialty", "03": "space", "04": "integration"}

WRAP_JS = """(n) => {
  const titles = [...document.querySelectorAll('.sec-title')];
  const t = titles.find(x => x.querySelector('.n') && x.querySelector('.n').textContent.trim() === n);
  if (!t) return false;
  const g = t.nextElementSibling;
  const w = document.createElement('div');
  w.id = '__shotwrap';
  w.style.cssText = 'padding:4px 0 10px';
  t.parentNode.insertBefore(w, t);
  w.appendChild(t);
  if (g) w.appendChild(g);
  w.scrollIntoView({block: 'start'});
  return true;
}"""

UNWRAP_JS = """() => {
  const w = document.getElementById('__shotwrap');
  if (!w) return 0;
  const p = w.parentNode;
  while (w.firstChild) p.insertBefore(w.firstChild, w);
  p.removeChild(w);
  return 1;
}"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DEFAULT_SRC)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--theme", default="light", choices=["light", "dark"])
    ap.add_argument("--segs", default="01,02,03,04")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--scale", type=float, default=2.0)
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ 需要 playwright：pip install playwright && playwright install chromium")
        return 2

    os.makedirs(args.out, exist_ok=True)
    src = args.src if os.path.isabs(args.src) else os.path.join(BASE, args.src)

    with sync_playwright() as pw:
        br = pw.chromium.launch(channel="chrome", headless=True)
        pg = br.new_page(viewport={"width": args.width, "height": 1000},
                         device_scale_factor=args.scale)
        pg.goto("file://" + src, wait_until="load", timeout=90000)
        pg.wait_for_timeout(2600)
        pg.evaluate("(t) => applyTheme(t)", args.theme)
        pg.evaluate("() => switchView('analytics')")
        pg.wait_for_timeout(2600)

        for seg in [s.strip() for s in args.segs.split(",") if s.strip()]:
            got = pg.evaluate(WRAP_JS, seg)
            if not got:
                print("  ✗ 未找到 %s 段" % seg)
                continue
            pg.wait_for_timeout(1400)          # 等 ECharts 动画落定
            fn = "analytics_%s_seg%s_%s.png" % (args.theme, seg, SEG_SLUG.get(seg, "seg"))
            path = os.path.join(args.out, fn)
            pg.locator("#__shotwrap").screenshot(path=path)
            sz = os.path.getsize(path)
            print("  ✓ %-42s %.0f KB" % (fn, sz / 1024.0))
            pg.evaluate(UNWRAP_JS)
            pg.wait_for_timeout(300)

        errs = pg.evaluate("() => (window.__ERRS || []).slice(0, 3)")
        if errs:
            print("  ! 页面运行时报错：%s" % errs)
        br.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
