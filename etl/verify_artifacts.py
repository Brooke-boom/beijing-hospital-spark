# -*- coding: utf-8 -*-
"""
三份前端产物一致性校验（收尾固定动作）
================================================================================
背景：web/dashboard.html + web/app.js 是唯一的源，构建脚本 web/build_spa.sh
      会派生出三份产物。构建是"字符串注入"式的（把快照 JSON 与 ECharts 内联进
      HTML），一旦锚点错位会**静默产出坏页面**——页面能打开但白屏/无数据。
      故每次构建后必须跑本脚本。

校验项：
  1. 三份产物都存在，且体积在合理区间（防止被截断或误替换）
  2. window.__SNAPSHOT__ 恰好出现 1 次（重复注入 = 锚点命中了旧块）
  3. 内联快照 JSON 可解析，institutions 条数 == 期望值（默认从主表现算）
  4. 内联的是本次构建的快照（前后两份产物快照内容一致）
  5. 离线版含内联 ECharts（零依赖），在线版走 CDN
  6. 产物中不得残留 data-page-node-id（IDE 预览注入的脏标记，不应入库）

用法：
  python3 etl/verify_artifacts.py
  python3 etl/verify_artifacts.py --expect 9678   # 显式指定时覆盖主表现算值
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(BASE, "web")

ARTIFACTS = [
    ("web/dashboard_standalone.html", "在线静态版（内联快照 + ECharts 走 CDN）"),
    ("web/templates/index.html", "Flask 渲染版（应与上一份逐字节一致）"),
    ("web/dashboard_offline.html", "完全离线版（内联快照 + 内联 ECharts）"),
]
SNAPSHOT_MARK = "__SNAPSHOT__"
ECHARTS_INLINE_MARK = "ECharts 5.5.1 - inlined"

# 体积区间（字节），2026-09-18 实测：6.5 MB / 6.5 MB / 7.5 MB
MIN_SIZE = 5 * 1024 * 1024
MAX_SIZE = 20 * 1024 * 1024


def extract_snapshot(html):
    """取出 window.__SNAPSHOT__ = {...}; 的 JSON 文本（括号配平扫描，不依赖正则贪婪）"""
    idx = html.find("window.__SNAPSHOT__")
    if idx < 0:
        return None
    start = html.find("{", idx)
    if start < 0:
        return None
    depth, i, in_str, esc = 0, start, False, False
    while i < len(html):
        ch = html[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return html[start:i + 1]
        i += 1
    return None


def _master_row_count():
    """主表真实行数 —— 作为机构条数的期望值，避免写死数字在每次治理后变成假报警。"""
    path = os.path.join(BASE, "data", "processed", "master_institutions.csv")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8-sig") as f:
        return sum(1 for _ in csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    # 期望条数默认从主表现算 —— 写死会在每次数据治理后变成假报警
    ap.add_argument("--expect", type=int, default=None,
                    help="期望机构条数（默认读 data/processed/master_institutions.csv）")
    args = ap.parse_args()

    ok = True
    snapshots = {}

    print("=" * 70)
    print("  三份前端产物一致性校验")
    print("=" * 70)

    for rel, desc in ARTIFACTS:
        path = os.path.join(BASE, rel)
        print("\n▶ %s" % rel)
        print("  %s" % desc)

        if not os.path.exists(path):
            print("  ✗ 文件不存在"); ok = False; continue

        size = os.path.getsize(path)
        html = open(path, encoding="utf-8").read()
        print("  体积 %s (%.2f MB)" % ("{:,}".format(size), size / 1024 / 1024))
        if not (MIN_SIZE <= size <= MAX_SIZE):
            print("  ✗ 体积超出合理区间 %d–%d" % (MIN_SIZE, MAX_SIZE)); ok = False

        # 注意：app.js 里会多次**引用** window.__SNAPSHOT__（注释 + 取值判断），
        # 真正要卡的是"赋值"只有一次——重复赋值意味着锚点命中了旧块、注入了两遍。
        n_assign = len(re.findall(r"window\.__SNAPSHOT__\s*=", html))
        n_ref = html.count(SNAPSHOT_MARK)
        print("  %s 快照赋值 %d 次（应为 1；另有 %d 处代码引用属正常）"
              % ("✓" if n_assign == 1 else "✗", n_assign, n_ref - n_assign))
        if n_assign != 1:
            ok = False

        raw = extract_snapshot(html)
        if raw is None:
            print("  ✗ 未找到内联快照"); ok = False; continue
        try:
            snap = json.loads(raw)
        except Exception as e:
            print("  ✗ 内联快照 JSON 解析失败: %s" % str(e)[:100]); ok = False; continue

        n_inst = len(snap.get("institutions") or [])
        if args.expect is None:
            args.expect = _master_row_count() or n_inst
        flag = "✓" if n_inst == args.expect else "✗"
        print("  %s 机构条数 %d（期望 %d）" % (flag, n_inst, args.expect))
        if n_inst != args.expect:
            ok = False
        print("  快照日期 %s / 顶层字段 %s" % (snap.get("snapshot_time"), ",".join(sorted(snap.keys()))))
        snapshots[rel] = hashlib.sha1(raw.encode("utf-8")).hexdigest()

        if "offline" in rel:
            has_inline = ECHARTS_INLINE_MARK in html or "echarts.min.js" not in html.split("__SNAPSHOT__")[0]
            print("  %s 内联 ECharts（离线自包含）" % ("✓" if has_inline else "✗"))
            if not has_inline:
                ok = False
        else:
            has_cdn = "echarts@5.5.1" in html or "cdn.jsdelivr.net" in html
            print("  %s ECharts 走 CDN" % ("✓" if has_cdn else "⚠ 未发现 CDN 引用"))

        if "data-page-node-id" in html:
            print("  ✗ 残留 IDE 预览脏标记 data-page-node-id（不应入库）"); ok = False
        else:
            print("  ✓ 无 IDE 预览脏标记")

    # 快照一致性：三份产物应内联同一份快照
    print("\n▶ 三份产物快照一致性")
    uniq = set(snapshots.values())
    if len(uniq) == 1:
        print("  ✓ 三份内联快照哈希一致 %s" % list(uniq)[0][:16])
    else:
        print("  ✗ 内联快照不一致：%s" % {k: v[:12] for k, v in snapshots.items()})
        ok = False

    # ---- 智能筛选页（自然语言 + 条件双通道）的离线能力是否真的进了产物 ----
    # 这三件套缺任何一件，单文件形态的"智能筛选"就会退化成空壳（页面在、点了没反应），
    # 且因为不报错，很容易在提交前被漏掉。
    print("\n▶ 智能筛选页离线能力（app.nlq.js + app.nlq.ui.js + 词表）")
    lex_js = os.path.join(WEB, "nlq_lexicon.json")
    if not os.path.exists(lex_js):
        print("  ✗ 缺少 web/nlq_lexicon.json（跑：python3 etl/export_nlq_lexicon.py）"); ok = False
    else:
        payload = json.load(open(lex_js, encoding="utf-8"))
        lex = payload.get("lex") or payload          # 外层是 {meta, lex}，真正的词表在 .lex
        print("  ✓ 词表 %s：区 %d / 类型 %d / 来源规则 %d / 科室别名 %d"
              % ("{:,}".format(os.path.getsize(lex_js)),
                 len(lex.get("districts") or []), len(lex.get("categories") or []),
                 len(lex.get("source_rules") or []), len(lex.get("category_alias") or {})))
        if not (lex.get("districts") and lex.get("categories") and lex.get("source_rules")):
            print("  ✗ 词表内容为空（导出脚本可能写错了层级）"); ok = False
    lex_hash = hashlib.sha1(open(lex_js, encoding="utf-8").read().encode("utf-8")).hexdigest() \
        if os.path.exists(lex_js) else ""
    for rel, _desc in ARTIFACTS:
        path = os.path.join(BASE, rel)
        if not os.path.exists(path):
            continue
        html = open(path, encoding="utf-8").read()
        problems = []
        for mark, label in (("window.__NLQ_LEX__", "内联词表"),
                            ("app.nlq.js", "解析引擎 app.nlq.js"),
                            ("app.nlq.ui.js", "界面层 app.nlq.ui.js")):
            if mark not in html:
                problems.append("缺 " + label)
        if "app.plan.js" in html or "app.plan.ui.js" in html:
            problems.append("残留已下线的 app.plan*.js")
        # 「就医决策」可以出现在**历史说明**里（更新日志写"已于某日下线/重构"是正常的，
        # 也是应该保留的），只有当成在跑的模块才算残留 —— 故用否定前行排除"下线 / 重构"语境。
        stale_plan = re.search(r"就医决策(?![^。；\n]{0,24}(?:下线|重构))", html)
        if stale_plan or "view-workbench" in html:
            problems.append("残留已下线的就医决策工作台")
        n_lex = len(re.findall(r"window\.__NLQ_LEX__\s*=", html))
        if n_lex != 1:
            problems.append("词表赋值 %d 次（应为 1）" % n_lex)
        if problems:
            print("  ✗ %s：%s" % (rel, "；".join(problems))); ok = False
        else:
            print("  ✓ %s：词表 + 引擎 + 界面层齐备，无下线模块残留" % rel)

    # ---- Vue 构建产物（前后端分离形态，Flask 挂在 /spa/）----
    print("\n▶ web/vue/dist（Vue 3 构建产物，由 Flask 挂载在 /spa/）")
    vue_dist = os.path.join(BASE, "web", "vue", "dist")
    if not os.path.isdir(vue_dist):
        print("  ⚠ 未构建（/spa/ 会返回 503）。构建：bash web/vue/build.sh")
    else:
        idx = os.path.join(vue_dist, "index.html")
        if not os.path.exists(idx):
            print("  ✗ 缺少 dist/index.html"); ok = False
        else:
            vhtml = open(idx, encoding="utf-8").read()
            # 解析 index.html 里引用的本地资源，逐个确认真的存在
            refs = re.findall(r'(?:src|href)="(/spa/[^"]+)"', vhtml)
            missing = []
            total_bytes = 0
            for r in refs:
                p = os.path.join(vue_dist, r[len("/spa/"):])
                if os.path.exists(p):
                    total_bytes += os.path.getsize(p)
                else:
                    missing.append(r)
            print("  ✓ index.html 引用 %d 个资源，合计 %.2f MB"
                  % (len(refs), total_bytes / 1024 / 1024))
            if missing:
                print("  ✗ 以下资源在 dist 中缺失：%s" % missing); ok = False
            else:
                print("  ✓ 引用资源全部存在")
            if "data-page-node-id" in vhtml:
                print("  ✗ 残留 IDE 预览脏标记"); ok = False
            else:
                print("  ✓ 无 IDE 预览脏标记")
            # 路由是按需动态 import 的，入口 html 只引用 app.js + css；
            # 其余 chunk 需单独点名，避免"少打包了几个视图"这种静默失败
            assets = os.path.join(vue_dist, "assets")
            if os.path.isdir(assets):
                files = sorted(os.listdir(assets))
                asize = sum(os.path.getsize(os.path.join(assets, f)) for f in files)
                expect_chunks = ["app.js", "charts.js", "index.css",
                                 "SmartFilterView.js", "HubView.js",
                                 "OverviewView.js", "AnalyticsView.js", "InstitutionsView.js",
                                 "FilterView.js", "IntegrationView.js", "QualityView.js",
                                 "AboutView.js"]
                miss = [c for c in expect_chunks if c not in files]
                print("  %s dist/assets 共 %d 个文件 / %.2f MB"
                      % ("✓" if not miss else "✗", len(files), asize / 1024 / 1024))
                if miss:
                    print("  ✗ 缺少预期 chunk：%s（九个视图应各自成块）" % miss); ok = False
                # 已下线的就医决策工作台不应再被打进产物
                stale = [f for f in files if f.startswith("PlanView") or f.startswith("PlanCandidateCard")]
                if stale:
                    print("  ✗ 残留已下线视图 chunk：%s" % stale); ok = False
                else:
                    print("  ✓ 无「就医决策」残留 chunk")
        # 源码比产物新 → 提示需要重新构建（只比 mtime，够用且零依赖）
        src_newest = 0.0
        for root, _dirs, files in os.walk(os.path.join(BASE, "web", "vue", "src")):
            for f in files:
                src_newest = max(src_newest, os.path.getmtime(os.path.join(root, f)))
        for extra in ("index.html", "vite.config.js", "package.json"):
            p = os.path.join(BASE, "web", "vue", extra)
            if os.path.exists(p):
                src_newest = max(src_newest, os.path.getmtime(p))
        dist_mtime = os.path.getmtime(idx) if os.path.exists(idx) else 0
        if dist_mtime < src_newest - 1:
            print("  ⚠ 前端源码比构建产物新，请重跑：bash web/vue/build.sh")
        else:
            print("  ✓ 构建产物不旧于源码")

    print("\n" + "=" * 70)
    print("  %s" % ("✅ 三份产物 + Vue 产物校验通过" if ok else "❌ 存在未通过项，见上方 ✗ 标记"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
