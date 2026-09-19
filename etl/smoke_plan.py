# -*- coding: utf-8 -*-
"""就医决策主线（任务态四步流）端到端冒烟测试
================================================
依赖：Flask 已在 127.0.0.1:5001 运行（web/app.py），Vue 已构建到 web/vue/dist。

覆盖这条主线是不是真的"能办事"（而不是只能看的图表）：
  1. 导航分级：首屏即就医决策；查阅页收进分组；侧栏可见 8 个入口
  2. 步骤 1 说需求：输入"孩子发烧" → 生成方案（后端返回 ok）
  3. 步骤 2 看候选：出现分诊结论 + 候选卡 + 匹配度，且儿科排前（人群词加权）
  4. 步骤 3 做比较：勾选 2 家 → 横向对比表有数据 → 可设主选
  5. 步骤 4 拿方案：方案卡含机构/科室/地址/准备清单/预约入口；文本可导出
  6. 留痕：保存到我的方案 → 刷新后"我的方案"列表能读回
  7. 全程 0 个未捕获运行时错误

运行：python etl/smoke_plan.py
"""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5001/spa/"


def run_plan(pg, q, tries=30):
    """填需求 → 生成方案 → 等候选渲染；返回是否出现候选卡"""
    pg.fill(".ask", q)
    time.sleep(0.3)
    pg.evaluate("""() => {
      const b = [...document.querySelectorAll('button')].find(x => /生成就医方案/.test(x.innerText));
      if (b) b.click();
    }""")
    for _ in range(tries):
        time.sleep(0.8)
        if pg.evaluate("() => document.querySelectorAll('.cand').length") > 0:
            time.sleep(0.6)
            return True
    return False


def home_state(pg):
    """读取"是否处于起始页"的可观测量"""
    return pg.evaluate("""() => ({
      hash: location.hash,
      onStep1: !!document.querySelector('.ask'),
      q: (document.querySelector('.ask') || {}).value || '',
      cand: document.querySelectorAll('.cand').length,
      homeDisabled: (document.querySelector('.pl-home') || {}).disabled === true
    })""")


def main():
    errors = []
    checks = []
    netfail = []

    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)
        pg = br.new_page(viewport={"width": 1600, "height": 1000})
        pg.on("console", lambda m: errors.append("console." + m.type + ": " + m.text)
              if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append("pageerror: " + str(e)))
        pg.on("response", lambda r: netfail.append("%s %s" % (r.status, r.url))
              if r.status >= 400 else None)

        pg.goto(BASE, wait_until="networkidle", timeout=45000)
        time.sleep(3.0)

        # ---- 1. 信息架构：首屏落在就医决策，导航分级 ----
        nav = pg.evaluate("""() => {
          const tabs = [...document.querySelectorAll('.navtab')];
          return {
            hash: location.hash,
            labels: tabs.map(t => (t.querySelector('.lbl')||t).innerText.trim()),
            groups: [...document.querySelectorAll('.navgroup')].map(g => g.innerText.trim().split('\\n')[0]),
            activeMain: !!document.querySelector('.navtab.main.active') ||
                        (tabs[0] && tabs[0].className.includes('active'))
          };
        }""")
        checks.append(("首屏落在就医决策（/plan）", nav["hash"].startswith("#/plan"), nav["hash"]))
        # 2026-09-19 信息架构重构后：主线 1 + 查阅支撑页 4 = 5 个入口
        checks.append(("侧栏入口数 = 5（主线 1 + 查阅 4）", len(nav["labels"]) == 5,
                       "|".join(nav["labels"])[:120]))
        checks.append(("导航分组存在", len(nav["groups"]) >= 1, "|".join(nav["groups"])))

        # ---- 2. 步骤 1：说需求 ----
        pg.fill(".ask", "孩子发烧")
        time.sleep(0.4)
        pg.evaluate("""() => {
          const b = [...document.querySelectorAll('button')].find(x => /生成就医方案/.test(x.innerText));
          if (b) b.click();
        }""")
        # 等 step 2 出现候选卡
        ok2 = False
        for _ in range(30):
            time.sleep(0.8)
            n = pg.evaluate("() => document.querySelectorAll('.cand').length")
            if n > 0:
                ok2 = True
                break
        checks.append(("步骤2 候选机构渲染", ok2,
                       "cand=%d" % pg.evaluate("() => document.querySelectorAll('.cand').length")))

        # ---- 3. 候选内容：分诊 + 儿科优先 + 匹配度 ----
        info = pg.evaluate("""() => {
          const pills = [...document.querySelectorAll('.deptpill')].map(x => x.innerText.trim());
          const cands = [...document.querySelectorAll('.cand')];
          return {
            pills, n: cands.length,
            first: cands.length ? cands[0].innerText.replace(/\\n/g, ' ').slice(0, 160) : '',
            hasScore: cands.some(c => /匹配|0\\.\\d+/.test(c.innerText))
          };
        }""")
        joined = " ".join(info["pills"])
        checks.append(("分诊结论给出科室", "儿科" in joined or "感染" in joined, joined[:110]))
        checks.append(("候选首位含儿科实力信号",
                       "儿科" in info["first"] or "儿童" in info["first"], info["first"][:120]))
        checks.append(("候选卡带匹配度", info["hasScore"], "n=%d" % info["n"]))

        # ---- 4. 步骤 3：勾选 2 家 -> 对比 ----
        # 默认会预选前 3 家，这里只保证"至少 2 家在对比清单里"，不盲目点击造成取消
        kept0 = pg.evaluate("() => document.querySelectorAll('.cand.picked').length")
        if kept0 < 2:
            pg.evaluate("""() => {
              const btns = [...document.querySelectorAll('.cand')]
                .filter(c => !c.className.includes('picked'))
                .map(c => [...c.querySelectorAll('button')].find(b => /加入对比/.test(b.innerText)))
                .filter(Boolean);
              btns.slice(0, 2 - document.querySelectorAll('.cand.picked').length)
                  .forEach(b => b.click());
            }""")
            time.sleep(0.8)
        keptN = pg.evaluate("() => document.querySelectorAll('.cand.picked').length")
        checks.append(("候选可加入对比（默认预选）", keptN >= 2, "picked=%d" % keptN))

        pg.evaluate("""() => {
          const b = [...document.querySelectorAll('button')].find(x => /下一步 · 对比/.test(x.innerText));
          if (b) b.click();
        }""")
        time.sleep(2.5)
        cmpinfo = pg.evaluate("""() => {
          const t = document.querySelector('table.cmp');
          if (!t) return { ok: false, rows: 0, cols: 0, hasPrimary: false };
          const ths = t.querySelectorAll('thead th');
          return {
            ok: true,
            rows: t.querySelectorAll('tbody tr').length,
            cols: ths.length - 1,
            hasPrimary: /主选/.test(t.innerText),
            text: t.innerText.replace(/\\n/g, ' ').slice(0, 150)
          };
        }""")
        checks.append(("步骤3 横向对比表有数据",
                       cmpinfo["ok"] and cmpinfo["rows"] >= 8 and cmpinfo["cols"] >= 2,
                       "行=%s 列=%s" % (cmpinfo.get("rows"), cmpinfo.get("cols"))))

        # 设为主选（第二列）
        pg.evaluate("""() => {
          const bs = [...document.querySelectorAll('table.cmp button')];
          const idx = bs.findIndex(b => /设为主选/.test(b.innerText));
          if (idx >= 0) bs[idx].click();
        }""")
        time.sleep(1.0)
        pg.evaluate("""() => {
          const b = [...document.querySelectorAll('button')].find(x => /生成就医方案 →/.test(x.innerText));
          if (b) b.click();
        }""")
        time.sleep(2.5)

        # ---- 5. 步骤 4：方案卡 ----
        pcard = pg.evaluate("""() => {
          const c = document.querySelector('.plancard');
          if (!c) return { ok: false, len: 0 };
          const txt = c.innerText;
          return {
            ok: true, len: txt.length,
            title: (document.querySelector('.ptitle')||{}).innerText || '',
            hasAddr: /地址/.test(txt), hasPhone: /电话/.test(txt),
            hasPrep: /就诊前准备/.test(txt), hasBook: /预约挂号/.test(txt),
            hasWhy: /为什么推荐这家/.test(txt),
            alts: document.querySelectorAll('.plancard .psec ol li').length
          };
        }""")
        checks.append(("步骤4 方案卡渲染", pcard["ok"] and pcard["len"] > 260,
                       "len=%s 主选=%s" % (pcard.get("len"), pcard.get("title")[:30])))
        checks.append(("方案含 依据/准备/预约 三段",
                       pcard.get("hasWhy") and pcard.get("hasPrep") and pcard.get("hasBook"),
                       "why=%s prep=%s book=%s" % (pcard.get("hasWhy"), pcard.get("hasPrep"),
                                                   pcard.get("hasBook"))))
        checks.append(("方案含地址与电话", pcard.get("hasAddr") and pcard.get("hasPhone"),
                       "addr=%s phone=%s" % (pcard.get("hasAddr"), pcard.get("hasPhone"))))

        # 导出文本（点"下载"会触发 download 事件）
        try:
            with pg.expect_download(timeout=8000) as dl:
                pg.evaluate("""() => {
                  const b = [...document.querySelectorAll('.btnrow button')].find(x => /下载/.test(x.innerText));
                  if (b) b.click();
                }""")
            d = dl.value
            checks.append(("方案可下载成文件", bool(d.suggested_filename),
                           d.suggested_filename))
        except Exception as e:
            checks.append(("方案可下载成文件", False, str(e)[:100]))

        # ---- 6. 留痕：保存 + 读回 ----
        pg.evaluate("""() => {
          const b = [...document.querySelectorAll('.btnrow button')].find(x => /保存/.test(x.innerText));
          if (b) b.click();
        }""")
        time.sleep(2.5)
        saved = pg.evaluate("""() => {
          const b = [...document.querySelectorAll('.btnrow button')].find(x => /保存/.test(x.innerText));
          return b ? b.innerText.trim() : '';
        }""")
        checks.append(("方案可保存留痕", "已保存" in saved, saved))

        # 注意：当前 URL 与目标 URL 相同（都在 #/plan），goto 属于同文档跳转不会重新加载，
        # 必须显式 reload 才能验证"刷新后从服务端读回留痕"。
        pg.reload(wait_until="networkidle", timeout=45000)
        time.sleep(3.0)
        hist = pg.evaluate("""() => {
          const items = [...document.querySelectorAll('.histlist .hist')];
          return { n: items.length, first: items.length ? items[0].innerText.replace(/\\n/g,' ').slice(0,100) : '',
                   step: document.querySelectorAll('.step.on').length };
        }""")
        checks.append(("刷新后能读回我的方案", hist["n"] >= 1, "n=%s %s" % (hist["n"], hist["first"][:80])))

        # ---- 6.5 回到起始页：页内「重新开始」+ 侧栏「就医决策」（2026-09-19 晚新增） ----
        # 起因：用户反馈"选择就医决策进入后，没有返回到起始页的入口"——
        # 跑过一轮后库存着 step/result，再点侧栏主任务没有任何反应，页内也只在步骤 4 底部有个按钮。
        pg.reload(wait_until="networkidle", timeout=45000)
        time.sleep(2.5)
        checks.append(("刷新后落在干净起始页（无残留候选）", home_state(pg)["cand"] == 0,
                       str(home_state(pg))))

        # 制造"进行中"状态
        ok_run = run_plan(pg, "腰疼想做检查")
        busy = pg.evaluate("""() => ({
          cand: document.querySelectorAll('.cand').length,
          home: !!document.querySelector('.pl-home'),
          homeDisabled: (document.querySelector('.pl-home') || {}).disabled === true
        })""")
        checks.append(("进行中出现「重新开始」入口且可用",
                       ok_run and busy["home"] and busy["homeDisabled"] is False and busy["cand"] > 0,
                       str(busy)))

        # (a) 页内「重新开始」→ 回到起始页且清空输入
        pg.evaluate("() => { const b = document.querySelector('.pl-home'); if (b) b.click(); }")
        time.sleep(1.0)
        a = home_state(pg)
        checks.append(("页内「重新开始」回到起始页（清空输入与候选）",
                       a["onStep1"] and a["q"] == "" and a["cand"] == 0 and a["homeDisabled"],
                       str(a)))

        # (b) 侧栏「就医决策」：停在步骤 2 时点它也要回起始页（原来点了没反应）
        ok_run = run_plan(pg, "孩子发烧")
        pg.evaluate("""() => {
          const t = [...document.querySelectorAll('.navtab.main')][0];
          if (t) t.click();
        }""")
        time.sleep(1.2)
        b = home_state(pg)
        checks.append(("侧栏「就医决策」回到起始页（不再点了没反应）",
                       ok_run and b["onStep1"] and b["q"] == "" and b["cand"] == 0
                       and b["hash"].startswith("#/plan"),
                       str(b)))

        # (c) 从查阅页点「就医决策」回来同样是起始页
        ok_run = run_plan(pg, "牙疼")
        pg.goto("%s#/profile" % BASE, wait_until="networkidle", timeout=45000)
        time.sleep(2.5)
        pg.evaluate("""() => {
          const t = [...document.querySelectorAll('.navtab.main')][0];
          if (t) t.click();
        }""")
        time.sleep(1.5)
        c = home_state(pg)
        checks.append(("从查阅页进「就医决策」也落在起始页",
                       ok_run and c["onStep1"] and c["cand"] == 0
                       and c["hash"].startswith("#/plan"),
                       str(c)))

        # ---- 6.6 从工作台返回查阅形态（单文件大屏）的入口 ----
        # 起因：从大屏点「就医决策」进来之后，工作台里没有任何回大屏的链接 —— 单向门。
        link = pg.evaluate("""() => {
          const a = document.querySelector('.lookbtn');
          return a ? { href: a.getAttribute('href'), text: a.innerText.trim() } : null;
        }""")
        checks.append(("顶栏有「查阅形态」返回入口且指向单文件大屏",
                       bool(link) and link["href"] == "/", str(link)))
        back = {"isLookup": False, "views": 0, "url": ""}
        try:
            if link:
                pg.evaluate("() => document.querySelector('.lookbtn').click()")
                time.sleep(4.5)
                back = pg.evaluate("""() => ({
                  url: location.pathname,
                  isLookup: !!document.querySelector('.navbar'),
                  views: document.querySelectorAll('.navtab[data-view]').length,
                  cta: !!document.getElementById('nav_workbench')
                })""")
        except Exception as e:
            back = {"isLookup": False, "views": 0, "url": str(e)[:80]}
        checks.append(("点它能回到大屏且大屏渲染正常（含回工作台入口）",
                       back.get("isLookup") and back.get("views", 0) >= 6 and back.get("cta"),
                       str(back)))

        # ---- 7. 查阅页仍可用（回归） ----
        pg.goto("%s#/find?t=institutions" % BASE, wait_until="networkidle", timeout=45000)
        time.sleep(2.5)
        rows = pg.evaluate("() => document.querySelectorAll('.tbl tbody tr').length")
        checks.append(("查阅页（找机构）仍可用", rows > 0, "rows=%d" % rows))

        br.close()

    print("=" * 78)
    print("就医决策主线冒烟测试结果")
    print("=" * 78)
    failed = 0
    for name, ok, detail in checks:
        print("  %s %-32s %s" % ("✓" if ok else "✗", name, detail))
        if not ok:
            failed += 1

    real_errors = [e for e in errors if "favicon" not in e.lower()]
    real_fail = [x for x in netfail if "favicon" not in x.lower() and "/api/" in x]
    print("-" * 78)
    print("  未捕获运行时错误：%d" % len(real_errors))
    for e in real_errors[:8]:
        print("    ! " + e[:170])
    print("  失败的 API 请求：%d" % len(real_fail))
    for e in real_fail[:8]:
        print("    ! " + e[:170])

    print("=" * 78)
    if failed == 0 and not real_errors and not real_fail:
        print("✅ 全部通过")
        return 0
    print("❌ 失败 %d 项，错误 %d 条，接口失败 %d 条" % (failed, len(real_errors), len(real_fail)))
    return 1


if __name__ == "__main__":
    sys.exit(main())
