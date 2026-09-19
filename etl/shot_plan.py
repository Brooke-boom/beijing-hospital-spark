# -*- coding: utf-8 -*-
"""就医决策主线截图脚本（给用户看效果，不做断言）
=====================================================
依赖：Flask 已在 127.0.0.1:5001 运行，Vue 已构建到 web/vue/dist。

产出 5 张图到 OUT_DIR：
  01_入口_就医决策.png      首屏就是任务台（不是图表大屏）
  02_分诊与候选.png         说需求 → 分诊结论 + 候选机构 + 匹配度
  03_横向对比.png           勾选 3 家 → 横向对比表
  04_就医方案.png           方案卡（可复制/下载/打印/保存）
  05_查阅_资源画像.png      支撑页形态（子标签）
运行：python etl/shot_plan.py [输出目录]
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5001/spa/"
OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/plan_shots"

QUERY = "孩子反复发烧咳嗽三天了"


def shot(pg, name, full=False):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name)
    pg.screenshot(path=p, full_page=full)
    print("  ✓ %s (%d KB)" % (name, os.path.getsize(p) // 1024))


def click_text(pg, *words, debug=False):
    """点第一个可见且文案命中任一关键词的按钮

    可见性判定用 getClientRects()（offsetParent 对 position:fixed/sticky 祖先会返回 null，
    会把底部操作条里的按钮误判成不可见）。
    """
    return pg.evaluate(
        """([words, debug]) => {
          const vis = b => b.getClientRects().length > 0 && !b.disabled;
          const all = [...document.querySelectorAll('button')];
          if (debug) {
            console.log('BTNS: ' + all.map(b =>
              (vis(b) ? '[v]' : '[x]') + b.innerText.replace(/\\s+/g, ' ').trim().slice(0, 24)
            ).join(' | '));
          }
          const hit = all.filter(vis).find(b => words.some(w => b.innerText.includes(w)));
          if (hit) { hit.click(); return hit.innerText.replace(/\\s+/g, ' ').trim().slice(0, 30); }
          return null;
        }""", [list(words), debug])


def main():
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)
        pg = br.new_page(viewport={"width": 1600, "height": 1000})
        pg.on("console", lambda m: print("  ·", m.text)
              if m.text.startswith("BTNS:") else None)
        pg.goto(BASE, wait_until="networkidle", timeout=45000)
        time.sleep(3.0)

        # ---- 01 首屏 = 任务台 ----
        print("01 首屏")
        shot(pg, "01_入口_就医决策.png")

        # ---- 02 说需求 → 分诊 + 候选 ----
        print("02 分诊与候选")
        pg.fill(".ask", QUERY)
        time.sleep(0.3)
        print("  点击：", click_text(pg, "生成就医方案"))
        for _ in range(30):
            time.sleep(0.8)
            if pg.evaluate("() => document.querySelectorAll('.cand').length") > 0:
                break
        time.sleep(1.2)
        n = pg.evaluate("() => document.querySelectorAll('.cand').length")
        print("  候选卡数量 =", n)
        shot(pg, "02_分诊与候选.png", full=True)

        # ---- 03 对比（注意：候选默认已预选前 3 家，不要再点"加入对比"，那是取消） ----
        print("03 横向对比")
        picked = pg.evaluate("() => document.querySelectorAll('.cand.picked').length")
        print("  默认预选 =", picked)
        if picked < 2:
            pg.evaluate(
                """() => {
                  [...document.querySelectorAll('.cand')]
                    .filter(c => !c.className.includes('picked'))
                    .slice(0, 3)
                    .forEach(c => {
                      const b = [...c.querySelectorAll('button')].find(x => /加入对比/.test(x.innerText));
                      if (b) b.click();
                    });
                }""")
            time.sleep(0.8)
        print("  点击：", click_text(pg, "对比选中的"))
        time.sleep(2.2)
        rows = pg.evaluate("() => document.querySelectorAll('table.cmp tbody tr').length")
        print("  对比表行数 =", rows)
        shot(pg, "03_横向对比.png", full=True)

        # ---- 04 设主选 → 生成方案 ----
        print("04 就医方案")
        alt = pg.evaluate(
            """() => {
              const bs = [...document.querySelectorAll('table.cmp button')];
              const b = bs.find(x => /设为主选/.test(x.innerText));
              if (b) { b.click(); return 'ok'; }
              return 'already';
            }""")
        print("  设为主选 =", alt)
        time.sleep(0.8)
        print("  点击：", click_text(pg, "生成就医方案 →", "生成就医方案"))
        time.sleep(2.0)
        card = pg.evaluate("() => !!document.querySelector('.plancard')")
        print("  方案卡存在 =", card)
        shot(pg, "04_就医方案.png", full=True)

        # ---- 05 查阅支撑页 ----
        print("05 查阅支撑页")
        pg.goto(BASE + "#/profile", wait_until="networkidle", timeout=45000)
        time.sleep(3.0)
        shot(pg, "05_查阅_资源画像.png", full=False)
        pg.goto(BASE + "#/find", wait_until="networkidle", timeout=45000)
        time.sleep(3.0)
        shot(pg, "05b_查阅_找机构.png", full=False)

        br.close()
    print("\n输出目录：%s" % OUT)


if __name__ == "__main__":
    main()
