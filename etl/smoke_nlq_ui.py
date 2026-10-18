# -*- coding: utf-8 -*-
"""
智能问答窗口（悬浮球 · Agnes AI）无头冒烟测试
================================================================================
2026-10-18 重构后接管原「智能筛选页」冒烟：悬浮球窗口已改为纯 AI 问答聊天
（条件卡片 / 结果列表 / 地图 / KPI 全部下线），本闸门改为验证聊天链路的三条
只有真跑才能验证的性质：
  ① 提问后回答**真的来自数据**：回答文本里有机构名与家数，且悬浮球徽标数字
     与回答中的家数一致（断言锚在「两处一致」关系上，不写死绝对值）；
  ② 病征类输入必须**拒答**（本地判定，不进模型）——这是本项目的定位红线；
  ③ 后端不可达时降级为「离线模板」气泡且**明确标注**，绝不冒充 AI 生成；
    旧的结果列表 UI 必须真的下线（DOM 里不应再出现）。

做法与 smoke_dashboard.py 一致：
  * ECharts 换成空桩（持续动画会让 headless 虚拟时间永不收敛）；
  * 探针写进 document.title；错误捕获器早于所有脚本注入；
  * 探针按"真实用户动作"驱动：点示例 → 读气泡 → 填输入框 → Enter → 读 DOM。
  * 打桩页无后端（file://），/api/ai/* 探活必失败 → 稳定落在离线模板分支，
    断言因此是确定性的；Agnes 在线路径由 /api/ai/chat 的服务端测试与缓存覆盖。

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
  function tx(id){var e=document.getElementById(id);return e?String(e.textContent||'').replace(/\\s+/g,' ').trim().slice(0,90):'MISSING';}
  function lastOf(sel){var m=document.querySelectorAll(sel);return m.length?m[m.length-1]:null;}
  function bubble(sel){var m=lastOf(sel);return m?String(m.textContent||'').replace(/\\s+/g,' ').trim().slice(0,160):'NONE';}
  var r=[];
  function done(){
    try{ r.push('ERR='+(((window.__ERRS||[]).join('~')).slice(0,200)||'none')); }catch(e){}
    document.title='T|'+r.join(' ;; ');
  }
  function badge(){var b=document.getElementById('fab_badge');
    return (b && b.style.display!=='none') ? String(b.textContent||'') : 'hidden';}
  try{
    // 进入聊天窗口 = smartDockSet(true) 打开浮层面板（__CHAT__ 懒初始化在里面触发）
    if(typeof smartDockSet==='function') smartDockSet(true);
    else if(typeof switchView==='function') switchView('filter');
    setTimeout(function(){
      r.push('vis=' + (document.getElementById('view-filter').offsetHeight>0));
      r.push('status=' + tx('ai_status'));
      r.push('welcome=' + cnt('#ai_log .chatmsg'));
      r.push('examples=' + cnt('#ai_ex .ex'));
      // ── A. 旧 UI 必须真的下线（2026-10-18 重构的残留检查）
      r.push('old_fai=' + (document.getElementById('f_ai')?1:0));
      r.push('old_list=' + (document.getElementById('nlq_list')?1:0));
      r.push('old_map=' + (document.getElementById('nlq_map')?1:0));
      // ── B. 点示例提问 → 离线模板回答（真实查询结果）
      var exs = document.querySelectorAll('#ai_ex .ex');
      if (exs[0]) exs[0].click();
      setTimeout(function(){
        r.push('log_after_filter=' + cnt('#ai_log .chatmsg'));
        r.push('ans_filter=' + bubble('#ai_log .chatmsg.ai:not(.wait)'));
        r.push('ans_tag=' + (function(){var m=lastOf('#ai_log .chatmsg.ai:not(.wait)');
          var w=m?m.querySelector('.chatwho'):null;return w?w.textContent.trim():'';})());
        r.push('badge_filter=' + badge());
        // ── C. 维度统计提问（同一引擎的 stats 分支；示例 #3 = 按行政区统计）
        var exs2 = document.querySelectorAll('#ai_ex .ex');
        if (exs2[2]) exs2[2].click();
        setTimeout(function(){
          r.push('ans_stats=' + bubble('#ai_log .chatmsg.ai:not(.wait)'));
          r.push('badge_stats=' + badge());
          // ── D. 病征输入必须拒答（本地判定，不产生 AI 结果气泡）
          var inp=document.getElementById('ai_in');
          inp.value='75岁女性腰椎滑脱走路困难';
          inp.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));
          setTimeout(function(){
            r.push('refuse=' + (cnt('#ai_log .chatmsg.refuse')>0));
            r.push('refuse_txt=' + bubble('#ai_log .chatmsg.refuse'));
            // ── E. 清空对话 → 回到欢迎态、徽标隐藏
            var clr=document.getElementById('ai_clear');
            if (clr) clr.click();
            setTimeout(function(){
              r.push('log_after_clear=' + cnt('#ai_log .chatmsg'));
              r.push('badge_after_clear=' + badge());
              done();
            }, 700);
          }, 900);
        }, 1200);
      }, 1200);
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


def _num(s):
    m = re.search(r"共命中\s*([0-9,]+)\s*家", s or "")
    return int(m.group(1).replace(",", "")) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(BASE, "web", "dashboard_offline.html"))
    ap.add_argument("--wait", type=int, default=2200)
    ap.add_argument("--budget", type=int, default=30000)
    args = ap.parse_args()

    print("=" * 70)
    print("  智能问答窗口无头冒烟测试（Agnes 聊天 / 真实数据 / 拒答 / 离线降级）")
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
    checks.append(("聊天窗口可见", kv.get("vis") == "true", kv.get("vis", "?")))
    # 打桩页无后端 → 探活必失败 → 离线模板。这个分支是确定性的。
    checks.append(("离线状态明确标注", "离线模板" in kv.get("status", ""),
                   kv.get("status", "?")))
    checks.append(("欢迎气泡已就位", int(kv.get("welcome", "0") or 0) >= 2,
                   "bubbles=%s" % kv.get("welcome")))
    checks.append(("示例问题齐备", int(kv.get("examples", "0") or 0) >= 4,
                   "examples=%s" % kv.get("examples")))
    # ── A. 旧 UI 残留检查：列表 / 地图 / 双通道输入必须真的下线
    checks.append(("旧结果列表已下线", kv.get("old_list") == "0", "nlq_list=%s" % kv.get("old_list")))
    checks.append(("旧结果地图已下线", kv.get("old_map") == "0", "nlq_map=%s" % kv.get("old_map")))
    checks.append(("旧双通道输入已下线", kv.get("old_fai") == "0", "f_ai=%s" % kv.get("old_fai")))
    # ── B. 示例提问 → 离线模板回答（真实数据）
    ans = kv.get("ans_filter", "")
    n1 = _num(ans)
    checks.append(("筛选提问有回答气泡", len(ans) > 30 and "NONE" != ans[:4], ans[:72]))
    checks.append(("回答标注离线模板来源", "离线模板" in kv.get("ans_tag", ""),
                   kv.get("ans_tag", "?")))
    checks.append(("回答含真实家数", n1 is not None and n1 > 0, "共命中=%s" % n1))
    checks.append(("回答含机构名", "医院" in ans or "中心" in ans, ans[:60]))
    # 徽标数字必须与回答里的家数一致（锚定「两处一致」关系，不写死绝对值）
    checks.append(("悬浮球徽标与回答家数一致",
                   kv.get("badge_filter", "") == str(n1) if n1 else False,
                   "badge=%s / 回答=%s" % (kv.get("badge_filter"), n1)))
    # ── C. 维度统计提问（stats 分支）
    ans2 = kv.get("ans_stats", "")
    checks.append(("统计提问有回答", len(ans2) > 30, ans2[:72]))
    checks.append(("统计回答含维度口径", ("行政区" in ans2 or "区" in ans2) and "家" in ans2,
                   ans2[:64]))
    # ── D. 病征拒答
    checks.append(("病征输入被拒答", kv.get("refuse") == "true",
                   kv.get("refuse_txt", "?")[:64]))
    checks.append(("拒答话术说清边界",
                   ("不提供" in kv.get("refuse_txt", "")) or ("不做" in kv.get("refuse_txt", "")),
                   kv.get("refuse_txt", "?")[:64]))
    # ── E. 清空对话
    checks.append(("清空后回到欢迎态", int(kv.get("log_after_clear", "0") or 0) >= 2,
                   "bubbles=%s" % kv.get("log_after_clear")))
    checks.append(("清空后徽标隐藏", kv.get("badge_after_clear") == "hidden",
                   "badge=%s" % kv.get("badge_after_clear")))
    errs = kv.get("ERR", "?")
    checks.append(("无运行时错误", errs == "none", errs))

    ok = True
    for name, passed, detail in checks:
        print("  %s %-22s %s" % ("✓" if passed else "✗", name, detail))
        if not passed:
            ok = False
    print("\n" + "=" * 70)
    print("  %s" % ("✅ 智能问答窗口冒烟通过：真实数据回答 / 拒答 / 离线降级 全部正常" if ok
                    else "❌ 存在未通过项，见上方 ✗ 标记"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
