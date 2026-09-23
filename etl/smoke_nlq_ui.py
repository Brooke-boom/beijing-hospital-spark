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
                        // ── J. 科室数的展示口径（三轮整治）
                        //    第一轮：22 家医院凭空多出「59 个科室」（百度百科模板文字污染）；
                        //    第二轮：撤掉污染后暴露出 dept_count 有 97% 是 rule/name 推导，
                        //    1,805 家会重复显示同一个模板数字（2/6/7/13/19），另有 468 家只登记到 1 条。
                        //    第三轮（2026-09-22 联网补全）：三档口径 ——
                        //      ① 在线核实的真实值（dept_count_src 非空）→ 显数字；
                        //      ② 基层机构「不设科室分科」（诊所/村卫生室/门诊部/社区卫生服务站/
                        //         医务室/护理站，按各自《基本标准》以「诊疗科目」核准执业，
                        //         本就没有科室建制）→ 如实说明，不再说"待补全"；
                        //      ③ 真正应当收录却未取得的，才叫「科室资料待补全」。
                        //    ⚠️ 判定必须按 span 正文，不能按 title 前缀：title 是人读的解释性
                        //       文案，措辞一改断言就静默失效（前一版改用 title 前缀正是栽在这）。
                        function _scanMetas(){
                          var acc = {on:0, pend:0, nodept:0, other:0, num:0, rows:0, n59:0};
                          var ms = document.querySelectorAll('#nlq_list .row .meta');
                          acc.rows = ms.length;
                          for (var _mi = 0; _mi < ms.length; _mi++) {
                            var _mt = ms[_mi].innerText || '';
                            if (_mt.indexOf('59 个科室') >= 0) acc.n59++;
                            var _sps = ms[_mi].querySelectorAll('span[title]');
                            for (var _si = 0; _si < _sps.length; _si++) {
                              var _tx = (_sps[_si].textContent || '').trim();
                              // 数字判定用手写循环，避免把正则的反斜杠塞进 Python 字符串
                              var _hasNum = false;
                              for (var _ci = 0; _ci < _tx.length; _ci++) {
                                var _cc = _tx.charCodeAt(_ci);
                                if (_cc >= 48 && _cc <= 57) { _hasNum = true; break; }
                              }
                              if (_hasNum) acc.num++;
                              if (_tx === '不设科室分科') acc.nodept++;
                              else if (_tx === '科室资料待补全') acc.pend++;
                              else if (_tx.indexOf('个科室') >= 0) acc.on++;
                              else if (_tx.indexOf('科室') >= 0 || _tx.indexOf('补全') >= 0) acc.other++;
                            }
                          }
                          return acc;
                        }
                        var _A = _scanMetas();
                        r.push('dept59=' + _A.n59);
                        r.push('dept_tiponline=' + _A.on);
                        r.push('dept_tippending=' + _A.pend);
                        r.push('dept_tipnodept=' + _A.nodept);
                        r.push('dept_tipother=' + _A.other);
                        r.push('dept_numeric=' + _A.num);
                        r.push('dept_rows=' + _A.rows);
                        r.push('dept_head=' + (document.querySelectorAll('#nlq_list .row .meta')[0]
                                 ? document.querySelectorAll('#nlq_list .row .meta')[0].innerText.replace(/[ \\t\\r\\n]+/g, ' ').trim() : ''));
                        // ── K. 基层机构：应落「不设科室分科」档（本轮修复的核心覆盖点）
                        //    海淀区诊所按《诊所基本标准》以诊疗科目执业、不设科室建制 →
                        //    必须全落 nodept 档，且**不得**出现任何"个科室"数字或"待补全"字样。
                        setQ('海淀区的诊所'); go();
                        setTimeout(function(){
                          var _B = _scanMetas();
                          r.push('base_nodept=' + _B.nodept);
                          r.push('base_pending=' + _B.pend);
                          r.push('base_online=' + _B.on);
                          r.push('base_other=' + _B.other);
                          r.push('base_numeric=' + _B.num);
                          r.push('base_rows=' + _B.rows);
                          r.push('base_count=' + tx('nlq_count'));
                          r.push('base_chips=' + tx('nlq_chips'));
                          done();
                        }, 1300);
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
    # 期望家数**不写死**（2026-09-22 教训，与 etl/verify_offline_nlq.py 同处注释一致）：
    #   40 → 36（科室明细新增好大夫在线逐家核实的真实科室，online 压过 key_depts/name/rule）
    #   36 → 31（主表同名合并治理：海淀区内「一行登记多块牌子」的重复记录被合并）
    # 写死的 startswith("36") 在每次数据治理后都会变成假报警。这里只断言 UI 端确实返回了结果
    # （防「条件卡片都在、结果 0 家」的退化）；具体家数的权威核对交给
    # verify_offline_nlq.py 的「库里 SQL vs 离线引擎两端一致」。
    _dcn = re.sub(r"\D", "", kv.get("dept_count", "") or "")
    checks.append(("海淀区+骨科 返回家数 > 0", bool(_dcn) and int(_dcn) > 0,
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
    _tnd = int(kv.get("dept_tipnodept", "0") or 0)
    _trows = int(kv.get("dept_rows", "0") or 0)
    checks.append(("科室项三档穷尽、无未归类分支",
                   _toth == 0 and (_ton + _tpd + _tnd) > 0,
                   "在线=%s 待补全=%s 不设分科=%s 行=%s 未归类=%s" % (
                       _ton, _tpd, _tnd, _trows, _toth)))
    # ── 基层机构口径（本轮核心修复）：诊所/村卫生室/门诊部/社区卫生服务站/医务室/护理站
    #    按各自《基本标准》以「诊疗科目」核准执业，本就没有科室建制 —— 必须如实说明，
    #    而不是把它们和"源数据没查到"混为一谈（此前一次误报 8,279 家，占全量 84.6%）。
    _bnd = int(kv.get("base_nodept", "0") or 0)
    _bpd = int(kv.get("base_pending", "0") or 0)
    _bon = int(kv.get("base_online", "0") or 0)
    _brows = int(kv.get("base_rows", "0") or 0)
    checks.append(("基层机构（海淀区诊所）标注「不设科室分科」",
                   _brows > 0 and _bnd == _brows and _bpd == 0 and _bon == 0,
                   "行=%s 不设分科=%s 待补全=%s 在线=%s | %s" % (
                       _brows, _bnd, _bpd, _bon, (kv.get("base_chips", "") or "")[:40])))
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
