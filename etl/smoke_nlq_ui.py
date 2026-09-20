# -*- coding: utf-8 -*-
"""
智能筛选页（自然语言 + 条件双通道）无头冒烟测试
================================================================================
为什么需要它（而不是只靠 verify_artifacts 的"文件齐备"检查）：
  "词表 + 引擎 + 界面层都进了产物"只能证明文件在，不能证明页面真的能用。
  这一页还有三条只有真跑才能验证的性质：
    ① 自然语言解析出条件后，**结果真的来自数据**（KPI/列表/来源说明都有内容）；
    ② 病征类输入必须**拒答**，不能硬凑一个结果（这是本项目的定位红线）；
    ③ 两条通道（自然语言 / 条件）与维度统计走的是同一条结果链，不能只活一条。

做法与 smoke_dashboard.py 一致：
  * ECharts 换成空桩（持续动画会让 headless 虚拟时间永不收敛）；
  * 探针写进 document.title；错误捕获器早于所有脚本注入；
  * 探针按"真实用户动作"驱动：填输入框 → 点按钮 → 读 DOM，而不是直接调内部函数。

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
  function tx(id){var e=document.getElementById(id);return e?String(e.textContent||'').replace(/\\s+/g,' ').trim().slice(0,70):'MISSING';}
  var r=[];
  function done(){
    try{ r.push('ERR='+(((window.__ERRS||[]).join('~')).slice(0,200)||'none')); }catch(e){}
    document.title='T|'+r.join(' ;; ');
  }
  function setQ(v){document.getElementById('f_ai').value=v;}
  function go(){document.getElementById('btn_ai').click();}
  try{
    if(typeof switchView==='function') switchView('filter');
    setTimeout(function(){
      // ── A. 自然语言：多条件（两个区 + 三级）
      setQ('朝阳区和海淀区的三级医院'); go();
      setTimeout(function(){
        r.push('vis=' + (document.getElementById('view-filter').offsetHeight>0));
        r.push('chips=' + cnt('#nlq_chips .nlqchip'));
        r.push('chip1=' + tx('nlq_chips'));
        r.push('count=' + tx('nlq_count'));
        r.push('kpi=' + tx('nlq_kpis'));
        r.push('rows=' + cnt('#nlq_list .row'));
        r.push('pager=' + tx('nlq_pg'));
        r.push('summary=' + tx('nlq_summary'));
        r.push('src=' + tx('nlq_source'));
        r.push('sorts=' + tx('nlq_sortnote'));
        // ── B. 条件卡片可逐项移除
        var ch=document.querySelector('#nlq_chips .nlqchip');
        if(ch) ch.click();
        setTimeout(function(){
          r.push('chips_after_drop=' + cnt('#nlq_chips .nlqchip'));
          // ── C. 病征类输入必须拒答（定位红线）
          setQ('75岁女性腰椎滑脱走路困难'); go();
          setTimeout(function(){
            r.push('refuse=' + (cnt('#nlq_msg.nlqrefuse')>0));
            r.push('refuse_txt=' + tx('nlq_msg'));
            r.push('refuse_rows=' + cnt('#nlq_list .row'));
            // ── D. 条件筛选通道
            document.querySelector('#nlq_tabs .nlqtab[data-ntab="cond"]').click();
            var d=document.getElementById('q_district');
            d.value='海淀区';
            document.getElementById('q_run').click();
            setTimeout(function(){
              r.push('cond_vis=' + (document.getElementById('nlq_pane_cond').classList.contains('active')));
              r.push('cond_count=' + tx('nlq_count'));
              r.push('cond_rows=' + cnt('#nlq_list .row'));
              // ── E. 维度统计（AI 统计 + 图表联动）
              document.querySelector('#nlq_tabs .nlqtab[data-ntab="nl"]').click();
              setQ('按行政区统计三级医院的数量'); go();
              setTimeout(function(){
                r.push('stats_show=' + (document.getElementById('nlq_statsbox').style.display!=='none'));
                r.push('stats_title=' + tx('nlq_stats_title'));
                r.push('stats_summary=' + tx('nlq_summary'));
                // ── F. 清空条件后应回到空态
                r.push('stats_kpi=' + tx('nlq_kpis'));
                r.push('stats_grid=' + document.getElementById('nlq_kpis').className);
                r.push('stats_list=' + tx('nlq_list'));
                // ── G. 科室维度：本轮修复的重点。
                //    此前离线快照只有科室**词表**、没有"哪家机构有哪些科室"的隶属关系，
                //    于是「海淀区骨科」解析成功（条件卡片都在）却查出 0 家，
                //    并提示"离线形态不支持按科室筛选"。
                document.querySelector('#nlq_tabs .nlqtab[data-ntab="nl"]').click();
                setQ('海淀区骨科'); go();
                setTimeout(function(){
                  r.push('env_win=' + (typeof window.ENV === 'object'));
                  r.push('dept_chips=' + tx('nlq_chips'));
                  r.push('dept_count=' + tx('nlq_count'));
                  r.push('dept_rows=' + cnt('#nlq_list .row'));
                  r.push('dept_list=' + tx('nlq_list'));
                  var drows = document.querySelectorAll('#nlq_list .row'), hd = 0;
                  for (var di = 0; di < drows.length; di++) {
                    if (drows[di].textContent.indexOf('海淀区') >= 0) hd++;
                  }
                  r.push('dept_in_haidian=' + hd + '/' + drows.length);
                  // ── H. 点开首行详情：专科页应能看到科室明细（来自离线快照的 depts）
                  if (drows[0]) drows[0].click();
                  setTimeout(function(){
                    r.push('drawer_show=' + (document.getElementById('drawer').className.indexOf('show') >= 0));
                    var heads = document.querySelectorAll('#pane-spec .blk h4'), h4 = 'NONE';
                    for (var hi = 0; hi < heads.length; hi++) {
                      if (heads[hi].textContent.indexOf('科室明细') >= 0) {
                        h4 = heads[hi].textContent.replace(/\\s+/g, ' ').slice(0, 30);
                      }
                    }
                    r.push('drawer_depthead=' + h4);
                    r.push('drawer_deptchips=' + document.querySelectorAll('#pane-spec .deptchips .chip').length);
                    // ── H2. 概览页的「同区同类机构 · 距离对标」
                    //    过去这里是「同区科室数 TOP10」——科室数混着三种口径
                    //    （源数据只登记 1~2 个 / 规则推导的通用 19 科室名单 / 百科自述值），
                    //    柱子高矮反映的是"数据怎么来的"，横向比会误导，故整块换掉。
                    //    补充（2026-09-20）：科室数已收敛为「仅在线核实值显数字」，
                    //    其余 9,755 家显示「科室资料待补全」（96.8% 的值由规则/名称推导而来）。
                    r.push('dw_scope=' + tx('dw_scope'));
                    r.push('dw_foot=' + tx('dw_foot'));
                    r.push('dw_oldblock=' + (document.getElementById('pane-ov').textContent.indexOf('同区科室数') >= 0));
                    r.push('dw_empty=' + cnt('#dw_chart .empty'));
                    // ── I. 口语化输入：不该被当成机构名关键词（本轮修复）
                    //    过去「想找个靠谱的大医院」会解析出 kw="想找靠谱大" → 0 家，
                    //    「海淀那边有哪些大医院」会解析出 kw="那边大" → 0 家。
                    //    这类错误**两端一致地错**，一致性校验查不出来，只有真跑页面才看得见。
                    var closeBtn = document.querySelector('#drawer .dw-hd button, #drawer .dw-close');
                    if (closeBtn) closeBtn.click();
                    setQ('想找个靠谱的大医院'); go();
                    setTimeout(function(){
                      r.push('oral1_chips=' + tx('nlq_chips'));
                      r.push('oral1_kwchip=' + cnt('#nlq_chips .nlqchip[data-ck="kw"]'));
                      r.push('oral1_count=' + tx('nlq_count'));
                      r.push('oral1_rows=' + cnt('#nlq_list .row'));
                      setQ('海淀那边有哪些大医院'); go();
                      setTimeout(function(){
                        r.push('oral2_chips=' + tx('nlq_chips'));
                        r.push('oral2_kwchip=' + cnt('#nlq_chips .nlqchip[data-ck="kw"]'));
                        r.push('oral2_count=' + tx('nlq_count'));
                        r.push('oral2_rows=' + cnt('#nlq_list .row'));
                        // ── J. 科室数的展示口径（两轮整治）
                        //    第一轮：22 家医院凭空多出「59 个科室」（百度百科模板文字污染）；
                        //    第二轮：撤掉污染后暴露出 dept_count 有 97% 是 rule/name 推导，
                        //    1,805 家会重复显示同一个模板数字（2/6/7/13/19），另有 468 家只登记到 1 条。
                        //    定版口径：**只有 dept_count_src 非空（在线核实值）才显示数字**，其余「科室资料待补全」。
                        var _metas = document.querySelectorAll('#nlq_list .row .meta');
                        var _n59 = 0, _tipOn = 0, _tipPend = 0, _tipOther = 0, _numeric = 0;
                        for (var _mi = 0; _mi < _metas.length; _mi++) {
                          var _mt = _metas[_mi].innerText || '';
                          if (_mt.indexOf('59 个科室') >= 0) _n59++;
                          var _sps = _metas[_mi].querySelectorAll('span[title]');
                          for (var _si = 0; _si < _sps.length; _si++) {
                            var _sp = _sps[_si];
                            var _ti = _sp.getAttribute('title') || '';
                            var _tx = (_sp.textContent || '').trim();
                            // 数字判定用手写循环，避免把正则的反斜杠塞进 Python 字符串
                            var _hasNum = false;
                            for (var _ci = 0; _ci < _tx.length; _ci++) {
                              var _cc = _tx.charCodeAt(_ci);
                              if (_cc >= 48 && _cc <= 57) { _hasNum = true; break; }
                            }
                            if (_hasNum) _numeric++;
                            if (_ti.indexOf('在线核实') === 0) _tipOn++;
                            else if (_ti.indexOf('源数据未收录该机构的科室设置') >= 0) _tipPend++;
                            else if (_tx.indexOf('个科室') >= 0 || _tx.indexOf('待补全') >= 0) _tipOther++;
                          }
                        }
                        r.push('dept59=' + _n59);
                        r.push('dept_tiponline=' + _tipOn);
                        r.push('dept_tippending=' + _tipPend);
                        r.push('dept_tipother=' + _tipOther);
                        r.push('dept_numeric=' + _numeric);
                        r.push('dept_head=' + (_metas.length ? _metas[0].innerText.replace(/\s+/g, ' ').trim() : ''));
                        done();
                      }, 1300);
                    }, 1300);
                  }, 800);
                }, 1200);
              }, 900);
            }, 900);
          }, 900);
        }, 900);
      }, 900);
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=os.path.join(BASE, "web", "dashboard_offline.html"))
    ap.add_argument("--wait", type=int, default=2200)
    ap.add_argument("--budget", type=int, default=30000)
    args = ap.parse_args()

    print("=" * 70)
    print("  智能筛选页无头冒烟测试（自然语言 / 条件 / 统计 / 拒答）")
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
    checks.append(("智能筛选页可见", kv.get("vis") == "true", kv.get("vis", "?")))
    checks.append(("自然语言解析出条件卡片", int(kv.get("chips", "0") or 0) >= 3,
                   "chips=%s" % kv.get("chips")))
    checks.append(("条件卡片含行政区与等级",
                   "行政区" in kv.get("chip1", "") and "医院等级" in kv.get("chip1", ""),
                   kv.get("chip1", "?")[:64]))
    checks.append(("结果计数非空", "家" in kv.get("count", "") and "—" not in kv.get("count", ""),
                   kv.get("count", "?")))
    checks.append(("KPI 概览有真实数字", "命中机构" in kv.get("kpi", "") and "三级医院" in kv.get("kpi", ""),
                   kv.get("kpi", "?")[:64]))
    checks.append(("结果列表有行", int(kv.get("rows", "0") or 0) > 0, "rows=%s" % kv.get("rows")))
    checks.append(("结果说明来自模板", len(kv.get("summary", "")) > 20, kv.get("summary", "?")[:64]))
    checks.append(("数据来源说明已渲染", "数据来源" in kv.get("src", ""), kv.get("src", "?")[:64]))
    checks.append(("排序口径已标注", "排序" in kv.get("sorts", ""), kv.get("sorts", "?")[:64]))
    checks.append(("条件卡片可移除", int(kv.get("chips_after_drop", "9") or 9) == 2,
                   "chips=%s" % kv.get("chips_after_drop")))
    checks.append(("病征输入被拒答", kv.get("refuse") == "true", kv.get("refuse_txt", "?")[:64]))
    checks.append(("拒答时不产生结果行", kv.get("refuse_rows") == "0", "rows=%s" % kv.get("refuse_rows")))
    checks.append(("条件筛选通道可用", kv.get("cond_vis") == "true" and int(kv.get("cond_rows", "0") or 0) > 0,
                   "cond_count=%s / rows=%s" % (kv.get("cond_count"), kv.get("cond_rows"))))
    checks.append(("维度统计面板出现", kv.get("stats_show") == "true", kv.get("stats_show", "?")))
    checks.append(("统计标题为该维度", "行政区" in kv.get("stats_title", ""), kv.get("stats_title", "?")))
    checks.append(("统计说明有内容", len(kv.get("stats_summary", "")) > 20, kv.get("stats_summary", "?")[:64]))
    checks.append(("筛选结果分页已渲染", "/" in kv.get("pager", ""), kv.get("pager", "?")))
    checks.append(("统计 KPI 换口径", "统计机构总数" in kv.get("stats_kpi", ""), kv.get("stats_kpi", "?")[:64]))
    checks.append(("统计 KPI 用四列栅格", "k4" in kv.get("stats_grid", ""), kv.get("stats_grid", "?")))
    checks.append(("统计结果区不谎报列表", "统计" in kv.get("stats_list", ""), kv.get("stats_list", "?")[:64]))
    # ── 科室筛选（本轮修复：离线形态此前一律 0 家并提示"不支持按科室筛选"）
    checks.append(("window.ENV 已挂到 window", kv.get("env_win") == "true",
                   "实测 typeof window.ENV = %s（const 声明不会成为 window 属性）" % kv.get("env_win")))
    checks.append(("科室条件解析成卡片",
                   "科室" in kv.get("dept_chips", "") and "骨科" in kv.get("dept_chips", ""),
                   kv.get("dept_chips", "?")[:64]))
    checks.append(("海淀区+骨科 = 40 家", kv.get("dept_count", "").replace(" ", "").startswith("40"),
                   kv.get("dept_count", "?")))
    checks.append(("科室筛选有结果行", int(kv.get("dept_rows", "0") or 0) > 0,
                   "rows=%s" % kv.get("dept_rows")))
    _hd = (kv.get("dept_in_haidian", "0/0") or "0/0").split("/")
    checks.append(("命中结果全部落在海淀区", len(_hd) == 2 and _hd[0] == _hd[1] and _hd[0] != "0",
                   kv.get("dept_in_haidian", "?")))
    checks.append(("不再提示「不支持按科室筛选」", "不支持按科室" not in kv.get("dept_list", ""),
                   kv.get("dept_list", "?")[:64]))
    checks.append(("点行可打开机构详情", kv.get("drawer_show") == "true", kv.get("drawer_show", "?")))
    checks.append(("详情专科页有科室明细", "科室明细" in kv.get("drawer_depthead", ""),
                   kv.get("drawer_depthead", "?")))
    checks.append(("科室明细列出了科室", int(kv.get("drawer_deptchips", "0") or 0) > 0,
                   "chips=%s" % kv.get("drawer_deptchips")))
    # 明细表头必须标注这份名录的来源，不能把它当成该院的科室总数
    _dh = kv.get("drawer_depthead", "")
    checks.append(("科室明细表头标注名录来源",
                   ("推导清单" in _dh) or ("已收录明细" in _dh),
                   _dh[:56]))
    # ── 概览页的「同区同类机构 · 距离对标」（本轮替换掉「同区科室数 TOP10」）
    _sc = kv.get("dw_scope", "")
    checks.append(("对标范围写出同区与家数", "同区" in _sc and "家" in _sc, _sc[:64]))
    checks.append(("给出本机构在同类中的位次", "排第" in kv.get("dw_foot", "")
                   and "km" in kv.get("dw_foot", ""), kv.get("dw_foot", "?")[:64]))
    checks.append(("旧的「同区科室数」整块已移除", kv.get("dw_oldblock") == "false",
                   "pane-ov 含旧块=%s" % kv.get("dw_oldblock")))
    checks.append(("该机构有坐标时不显示空态", kv.get("dw_empty") == "0",
                   "empty 块=%s" % kv.get("dw_empty")))
    # ── 口语化输入（本轮修复：填充词曾被当成机构名关键词 → 结果恒 0 家）
    checks.append(("口语输入不产出机构名关键词卡片", kv.get("oral1_kwchip") == "0",
                   "kw 卡片=%s / %s" % (kv.get("oral1_kwchip"),
                                        kv.get("oral1_chips", "?")[:52])))
    checks.append(("「想找个靠谱的大医院」有结果",
                   "家" in kv.get("oral1_count", "") and "—" not in kv.get("oral1_count", ""),
                   kv.get("oral1_count", "?")))
    checks.append(("「想找个靠谱的大医院」有结果行",
                   int(kv.get("oral1_rows", "0") or 0) > 0, "rows=%s" % kv.get("oral1_rows")))
    checks.append(("「海淀那边有哪些大医院」解析出海淀区",
                   "海淀区" in kv.get("oral2_chips", ""), kv.get("oral2_chips", "?")[:52]))
    checks.append(("「海淀那边有哪些大医院」不产出关键词卡片", kv.get("oral2_kwchip") == "0",
                   "kw 卡片=%s" % kv.get("oral2_kwchip")))
    checks.append(("「海淀那边有哪些大医院」有结果",
                   "家" in kv.get("oral2_count", "") and "—" not in kv.get("oral2_count", "")
                   and int(kv.get("oral2_rows", "0") or 0) > 0,
                   "%s / rows=%s" % (kv.get("oral2_count", "?"), kv.get("oral2_rows"))))
    checks.append(("「59 个科室」不再出现", int(kv.get("dept59", "-1") or -1) == 0,
                   "命中=%s" % kv.get("dept59")))
    _ton = int(kv.get("dept_tiponline", "0") or 0)
    _tpd = int(kv.get("dept_tippending", "0") or 0)
    _toth = int(kv.get("dept_tipother", "0") or 0)
    checks.append(("科室数只对在线核实值显数字",
                   int(kv.get("dept_numeric", "-1") or -1) == _ton and _ton > 0,
                   "显数字=%s 在线核实=%s" % (kv.get("dept_numeric"), _ton)))
    checks.append(("无在线值的机构显示「科室资料待补全」",
                   _tpd > 0,
                   "待补全=%s 在线核实=%s | 首行=%s" % (
                       _tpd, _ton, (kv.get("dept_head", "") or "")[:44])))
    checks.append(("科室项口径提示无未归类分支", _toth == 0,
                   "未归类=%s" % kv.get("dept_tipother")))
    errs = kv.get("ERR", "?")
    checks.append(("无运行时错误", errs == "none", errs))

    ok = True
    for name, passed, detail in checks:
        print("  %s %-22s %s" % ("✓" if passed else "✗", name, detail))
        if not passed:
            ok = False
    print("\n" + "=" * 70)
    print("  %s" % ("✅ 智能筛选页冒烟通过：自然语言 / 条件 / 统计 / 拒答 全部正常" if ok
                    else "❌ 存在未通过项，见上方 ✗ 标记"))
    print("=" * 70)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
