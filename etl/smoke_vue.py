# -*- coding: utf-8 -*-
"""Vue 前端（前后端分离形态）无头冒烟测试
=========================================
依赖：Flask 已在 127.0.0.1:5001 运行（web/app.py），Vue 已构建到 web/vue/dist。

覆盖：
  1. 首屏是任务主线「智能筛选」，能拿到真实数据（机构总数由主表现算）
  2. 6 个路由逐个可达且渲染出内容
  3. 主线能力：一句话 → 条件卡 → KPI/列表/来源说明；条件通道可用；维度统计出图；
     病征类输入被拒答且 0 结果
  4. 图表页 canvas 真的画出来了（ECharts 有实例）
  5. 机构查询页列表有行、分页可翻、详情抽屉可打开
  6. 主题切换不报错
  7. 全程 0 个未捕获运行时错误

运行：
  python etl/smoke_vue.py
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5001/spa/"
# 2026-09-19 起：主线 1 个（智能筛选）+ 查阅支撑页 4 个 + 系统说明（原 7 个入口已收敛）
ROUTES = [
    ("filter", "智能筛选"),
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

        # ---- 1. 首屏 = 任务主线（智能筛选），不再是大屏首页 ----
        try:
            tabs = pg.evaluate("() => document.querySelectorAll('.nlqtabs button').length")
            has_ask = pg.evaluate("() => !!document.querySelector('.nlqask textarea')")
            scope = pg.evaluate("() => (document.querySelector('.nlqscope')||{}).innerText||''")
        except Exception:
            tabs, has_ask, scope = 0, False, ''
        checks.append(("首屏为智能筛选（双通道输入 + 边界声明）",
                       tabs == 2 and has_ask and "不提供" in scope,
                       "tabs=%d textarea=%s 边界=%s" % (tabs, has_ask, bool(scope))))

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

        # ---- 2.5 主线能力：一句话 → 条件卡 → 结果（真实数据） ----
        def ask(text):
            """模拟真实用户动作：在输入框里敲一句话 → 点「开始筛选」→ 等结果。"""
            pg.goto("%s#/filter" % BASE, wait_until="networkidle", timeout=45000)
            time.sleep(2.0)
            pg.fill(".nlqask textarea", text)
            pg.evaluate("""() => {
              const bs = [...document.querySelectorAll('.btn')];
              const b = bs.find(x => /开始筛选/.test(x.innerText));
              if (b) b.click();
            }""")
            time.sleep(3.2)
            return pg.evaluate("""() => ({
              chips: [...document.querySelectorAll('.chip')].map(x => x.innerText.trim()),
              summary: (document.querySelector('.nlqmsg.info')||{}).innerText||'',
              refuse: (document.querySelector('.nlqmsg.refuse')||{}).innerText||'',
              rows: document.querySelectorAll('.tbl tbody tr').length,
              kv: [...document.querySelectorAll('.card .v')].map(x => x.innerText.trim()),
              canvas: document.querySelectorAll('canvas').length,
              src: (document.querySelector('.nlqsrc')||{}).innerText||''
            })""")

        try:
            r1 = ask("朝阳区和海淀区的三级公立医院")
            ok = (len(r1["chips"]) >= 3 and r1["rows"] > 0
                  and len(r1["kv"]) >= 6 and "查询库表" in r1["src"])
            checks.append(("主线·自然语言筛选出清单",
                           ok, "条件卡=%d 行=%d KPI=%d 来源=%s"
                           % (len(r1["chips"]), r1["rows"], len(r1["kv"]), bool(r1["src"]))))
        except Exception as e:
            checks.append(("主线·自然语言筛选出清单", False, str(e)[:140]))

        try:
            r2 = ask("按行政区统计三级医院的数量")
            ok = r2["canvas"] >= 1 and r2["rows"] > 0 and any("统计" in x or "维度" in x for x in r2["chips"] + [r2["summary"]])
            checks.append(("主线·维度统计出图", ok,
                           "canvas=%d 明细行=%d KPI=%s" % (r2["canvas"], r2["rows"], r2["kv"][:2])))
        except Exception as e:
            checks.append(("主线·维度统计出图", False, str(e)[:140]))

        try:
            r3 = ask("老人最近总心慌胸闷，该挂什么科")
            ok = bool(r3["refuse"]) and r3["rows"] == 0
            checks.append(("主线·病征输入被拒答且无结果", ok,
                           "拒答=%s 行=%d" % (bool(r3["refuse"]), r3["rows"])))
        except Exception as e:
            checks.append(("主线·病征输入被拒答且无结果", False, str(e)[:140]))

        # 口语化输入：填充词（想找 / 靠谱 / 那边 / 附近）是**意图**而不是机构名关键词。
        # 被误收成 kw 的话机构表里一个都匹配不到 → 句子读得懂、结果却是 0 条，且不报错。
        try:
            r4 = ask("想找个靠谱的大医院")
            r5 = ask("海淀那边有哪些大医院")
            bad = [c for c in r4["chips"] + r5["chips"] if "机构名称关键词" in c]
            ok = (not bad and r4["rows"] > 0 and r5["rows"] > 0
                  and any("海淀区" in c for c in r5["chips"]))
            checks.append(("主线·口语化输入不被当成机构名", ok,
                           "垃圾关键词=%s / 口语=%d行 / 海淀=%d行 %s" % (
                               bad, r4["rows"], r5["rows"], r5["chips"][:3])))
        except Exception as e:
            checks.append(("主线·口语化输入不被当成机构名", False, str(e)[:140]))

        # 条件通道：逐项填条件也能查出结果
        try:
            pg.goto("%s#/filter" % BASE, wait_until="networkidle", timeout=45000)
            time.sleep(2.0)
            pg.evaluate("""() => {
              const b = [...document.querySelectorAll('.nlqtabs button')].find(x => /逐项设置条件/.test(x.innerText));
              if (b) b.click();
            }""")
            time.sleep(1.0)
            pg.evaluate("""() => {
              const sels = [...document.querySelectorAll('select.ctl')];
              const one = sels[0];
              if (one && one.options.length > 1) {
                one.value = one.options[1].value;
                one.dispatchEvent(new Event('change', { bubbles: true }));
              }
              const b = [...document.querySelectorAll('.btn')].find(x => /按条件查询/.test(x.innerText));
              if (b) b.click();
            }""")
            time.sleep(3.0)
            c = pg.evaluate("""() => ({
              rows: document.querySelectorAll('.tbl tbody tr').length,
              chips: document.querySelectorAll('.chip').length
            })""")
            checks.append(("主线·条件通道可用", c["rows"] > 0 and c["chips"] >= 1,
                           "行=%d 条件卡=%d" % (c["rows"], c["chips"])))
        except Exception as e:
            checks.append(("主线·条件通道可用", False, str(e)[:140]))

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

        # 科室数口径（定版，2026-09-22 三档）：dept_count 97% 由 rule/name 推导——1,805 家会重复
        # 显示同一个模板数字（2/6/7/13/19），另有 468 家只登记到 1 条。因此**只有 dept_count_src
        # 非空（在线核实值，实测 301 家）才显示数字**。余下两档：
        #   · 基层六类（诊所/村卫生室/门诊部/社区卫生服务站/医务室/护理站，共 8,279 家 / 84.6%）
        #     按各自《基本标准》以「诊疗科目」核准执业、不设科室建制 → 「不设科室分科」
        #   · 真正应当收录却未取得的 → 「科室资料待补全」
        # 旧版把后两者并成一档，一次误报 8,279 家。
        dc = pg.evaluate("""() => {
          const tds = [...document.querySelectorAll('.tbl tbody tr')]
            .map(tr => tr.children[5]).filter(Boolean);
          return {
            n: tds.length,
            texts: tds.map(td => td.innerText.trim()),
            tips: tds.filter(td => td.getAttribute('title')).length,
            num: tds.filter(td => /[0-9]/.test(td.innerText)).length,
            pending: tds.filter(td => td.innerText.indexOf('科室资料待补全') >= 0).length,
            nodept: tds.filter(td => td.innerText.indexOf('不设科室分科') >= 0).length,
          };
        }""")
        checks.append(("科室数列不再出现「59」", '59' not in dc["texts"],
                       "取值=%s" % dc["texts"][:8]))
        checks.append(("科室数列逐格带口径提示", dc["n"] > 0 and dc["tips"] == dc["n"],
                       "带提示 %d/%d 行" % (dc["tips"], dc["n"])))
        checks.append(("科室数三档穷尽（在线值 / 待补全 / 不设分科）",
                       dc["n"] > 0 and dc["num"] + dc["pending"] + dc["nodept"] == dc["n"],
                       "显数字=%d 待补全=%d 不设分科=%d / 共 %d 行" % (
                           dc["num"], dc["pending"], dc["nodept"], dc["n"])))
        checks.append(("数字只出现在「不设分科」档之外",
                       dc["num"] + dc["nodept"] <= dc["n"],
                       "显数字=%d 不设分科=%d 共=%d" % (dc["num"], dc["nodept"], dc["n"])))

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
