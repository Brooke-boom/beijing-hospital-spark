#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
响应式版面校验：四个页面 × 四档宽度，专查「排得乱不乱」。

为什么单独有这个脚本：
  smoke_dashboard.py 固定用无头 Chrome 默认窗口 800x600（为了覆盖 ≤1080 的图标侧栏），
  而版面问题几乎都出在宽屏 —— 段内行不齐、末行留白、左右栏不等高，800px 下全被塌成单列掩盖掉了。
  这里用 Playwright 显式设视口，把「宽屏排布」这件事固化成断言。

四类判据（都属于"看着乱"的可量化定义）：
  ① 溢出   —— 横向滚动条 / 内容漏出面板（overflow:visible 却比容器大）
  ② 参差   —— 同一行的面板高度不一致（对齐了才叫排整齐）
  ③ 留白   —— 末行填充率 < 99%（3 + 1 那种缺半边的排法）
  ④ 齐平   —— 左右两栏/上下两块的边缘没对齐

第五类判据（2026-09-21 补，教训来自「办别构成」面板空白）：
  ⑤ 空板   —— 图表容器的 id 不在高度清单里 → clientHeight=0 →
              ECharts 照样 init、照样 setOption、series 里数据齐全，
              但页面上只有标题和一块空白。**这是最像"没数据"的故障，其实数据全在，
              缺的是容器高度**。静态（id 是否登记）+ 运行时（clientHeight>0）双查。

页面用 ECharts 空桩（结构真、图表假）：版面只由 CSS 决定，桩掉图表既快又不受动画干扰。
「容器高度为 0」本身就是 CSS 决定的，所以空桩页照样能查出来。
"""
import os
import re
import sys
import argparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = os.path.join(BASE, 'web', 'dashboard_offline.html')
DEFAULT_JS = os.path.join(BASE, 'web', 'app.js')

STUB = (
    '<script>window.echarts={init:function(){return{setOption:function(){},resize:function(){},'
    'dispose:function(){},on:function(){},off:function(){},clear:function(){},showLoading:function(){},'
    'hideLoading:function(){},dispatchAction:function(){},getOption:function(){return{};},'
    'getZr:function(){return{on:function(){},off:function(){}};}};},getMap:function(){},'
    'registerMap:function(){},graphic:{LinearGradient:function(){return{};}}};</script>'
)


# ---------------------------------------------------------------------------
#  ⑤ 图表容器体检：这是「面板在、图是白的」那一类静默故障的唯一抓手
# ---------------------------------------------------------------------------
def scan_chart_containers(js_text):
    """从 app.js 里抽出所有交给 echarts.init 的容器 id。

    三种写法都要认，漏认一种就等于留一个盲区：
      a) mk('ch_own')                        —— 分析页批量初始化（16 张）
      b) echarts.init($('ch1'))              —— 总览页手写初始化
      c) const qc = $('ch_qcoord'); … echarts.init(qc)
                                             —— 先取元素再 init（质量页），
                                               最容易漏：id 只出现在 $() 里，
                                               不看变量绑定就找不到
    """
    var2id = dict(re.findall(r"(?:const|let|var)\s+(\w+)\s*=\s*\$\('([^']+)'\)", js_text))
    ids = set(re.findall(r"mk\(\s*'([^']+)'\s*\)", js_text))
    ids |= set(re.findall(r"echarts\.init\(\s*\$\('([^']+)'\)", js_text))
    for v in re.findall(r"echarts\.init\(\s*(\w+)\s*[,)]", js_text):
        if v in var2id:
            ids.add(var2id[v])
    return ids


def chart_container_static(product_src, js_path):
    """静态查图表容器的两个方向。

    合格的高度来源只有三种：在高度 id 清单里 / 带 .achart 类 / 是 #map。
    当初「办别构成」空白，就是因为它三种都不是。

    返回 dict：
      ids        echarts.init 用到的全部 id
      listed     高度清单里的 id
      no_height  ★【HTML 里有元素，却没有高度来源】—— 就是白板故障，必须报红
      no_init    ☆【HTML 里有 ch* 容器，但没有任何 JS 去 init 它】—— id 改了名字忘改 JS
      dead       有 init、HTML 里却没有元素（运营后台等已下线模块的遗留，无害，只提示）
    """
    html = open(product_src, encoding='utf-8').read()
    js = open(js_path, encoding='utf-8').read()
    ids = scan_chart_containers(js)

    m = re.search(r'((?:#[A-Za-z_][\w-]*\s*,?\s*)+)\{[^}]*width:100%;height:100%[^}]*\}', html)
    listed = set(re.findall(r'#([A-Za-z_][\w-]*)', m.group(1))) if m else set()

    # HTML 里所有像图表容器的元素：id 以 ch 开头（本项目 ch* 一律是 ECharts 容器）
    dom_chart = set(re.findall(r'<[^>]*\bid="(ch[A-Za-z_0-9]*)"', html))

    no_height, dead = [], []
    for i in sorted(ids):
        el = re.search(r'<[^>]*\bid="%s"[^>]*>' % re.escape(i), html)
        if not el:
            dead.append(i)
            continue
        if i in listed or i == 'map' or 'achart' in el.group(0):
            continue
        no_height.append(i)

    no_init = sorted(dom_chart - ids)
    return {'ids': ids, 'listed': listed, 'no_height': no_height,
            'no_init': no_init, 'dead': dead}


CONTS = r"""
() => {
  const sec = document.querySelector('section.view.active');
  const out = [];
  if (sec) {
    sec.querySelectorAll('[id^="ch"],[id^="a_"]').forEach(el => {
      out.push([el.id, el.clientWidth, el.clientHeight]);
    });
    const mp = sec.querySelector('#map');
    if (mp) out.push(['map', mp.clientWidth, mp.clientHeight]);
  }
  return out;
}
"""

# 每档宽度的视口。1180 是整合页「塌成单列」的既有断点，900 是分析网格降至单列的断点，
# 两侧都要取到，否则断点附近的问题查不出来。
WIDTHS = [1440, 1280, 1200, 1080, 900]

PROBE = r"""
() => {
  const D = document.documentElement;
  const n = v => Math.round(v);
  const rect = e => { const r = e.getBoundingClientRect();
    return {x:n(r.x), y:n(r.y + window.scrollY), w:n(r.width), h:n(r.height),
            b:n(r.bottom + window.scrollY), r:n(r.right)}; };
  const contentW = g => g.clientWidth
      - parseFloat(getComputedStyle(g).paddingLeft) - parseFloat(getComputedStyle(g).paddingRight);
  const gapX = g => parseFloat(getComputedStyle(g).columnGap) || 0;

  // 按 top 分行（容差 3px，避开亚像素舍入）
  const rowsOf = g => {
    const kids = [...g.children].map(rect), rows = [];
    kids.forEach(c => {
      let row = rows.find(r => Math.abs(r.t - c.y) <= 3);
      if (!row) { row = {t: c.y, items: []}; rows.push(row); }
      row.items.push(c);
    });
    return rows;
  };
  // 同一行内最高的与最矮的差多少
  const ragged = rows => rows.reduce((m, r) =>
      Math.max(m, Math.max(...r.items.map(i => i.h)) - Math.min(...r.items.map(i => i.h))), 0);
  // 末行填充率：末行各块宽 + 间隙 占内容宽的比例
  const fill = (g, rows) => {
    const last = rows[rows.length - 1], cw = contentW(g);
    const used = last.items.reduce((s, i) => s + i.w, 0) + gapX(g) * (last.items.length - 1);
    return cw ? Math.round(used / cw * 100) : 0;
  };

  const out = {v: {}};
  const views = ['overview', 'analytics', 'integration', 'quality'];

  // ① 内容逃逸：比容器大、又不给滚动条的元素
  const escapes = sec => {
    const bad = [];
    if (!sec) return bad;
    sec.querySelectorAll('*').forEach(el => {
      const cs = getComputedStyle(el);
      if (cs.display === 'none' || el.id === 'map_diag') return;
      const dx = el.scrollWidth - el.clientWidth, dy = el.scrollHeight - el.clientHeight;
      if ((dx > 2 && cs.overflowX === 'visible') || (dy > 2 && cs.overflowY === 'visible')) {
        bad.push((el.id || el.className || el.tagName) + ':' + dx + 'x' + dy);
      }
    });
    return bad.slice(0, 4);
  };

  for (const v of views) {
    if (typeof switchView === 'function') switchView(v);
    const sec = document.querySelector('#view-' + v);
    const m = {overflow: D.scrollWidth - D.clientWidth, escape: escapes(sec)};

    if (v === 'overview') {
      const map = document.querySelector('.mapwrap'), rail = document.querySelector('.panel-stack');
      if (map && rail) m.railDiff = Math.abs(n(map.getBoundingClientRect().height - rail.getBoundingClientRect().height));
      const k = document.querySelector('#view-overview .kpis');
      if (k) m.kpiFill = fill(k, rowsOf(k));
    }
    if (v === 'analytics') {
      const gs = [...document.querySelectorAll('#view-analytics .agrid')];
      m.ragged = Math.max(0, ...gs.map(g => ragged(rowsOf(g))));
      m.minFill = Math.min(...gs.map(g => fill(g, rowsOf(g))));
      // 每段首行的格数：低于 2 说明网格退化成「一条一条往下堆」，页面的分段节奏就散了
      m.minRowN = Math.min(...gs.map(g => rowsOf(g)[0].items.length));
      // 行内等宽：同一行的面板宽度不一致，最像「没对齐」
      m.widthSpread = Math.max(0, ...gs.map(g => rowsOf(g).reduce((mx, r) => {
        const ws = r.items.map(i => i.w);
        return Math.max(mx, Math.max(...ws) - Math.min(...ws));
      }, 0)));
      const st = document.querySelector('#view-analytics .sec-title');
      if (st) {
        const cs = getComputedStyle(st);
        m.titleFs = parseFloat(cs.fontSize);
        m.titleFw = parseInt(cs.fontWeight, 10) || 0;
        m.titleLine = cs.borderBottomWidth;
      }
    }
    if (v === 'integration') {
      const src = document.querySelector('.integ-col.src'), pipe = document.querySelector('.integ-col.pipe');
      const res = document.querySelector('.integ-col.res'), full = document.querySelector('.integ-full');
      if (src && pipe && res) {
        m.igCols = rowsOf(document.querySelector('.integ-grid'))[0].items.length;
        m.igWidthDiff = Math.abs(n(src.getBoundingClientRect().width - pipe.getBoundingClientRect().width));
        m.igBottomDiff = Math.abs(n(res.getBoundingClientRect().bottom - pipe.getBoundingClientRect().bottom));
        m.igLeftDiff = Math.abs(n(src.getBoundingClientRect().left - res.getBoundingClientRect().left));
      }
      const g = document.querySelector('.integ-grid');
      if (full && g) m.igFullFill = Math.round(full.getBoundingClientRect().width / contentW(g) * 100);
    }
    if (v === 'quality') {
      const g = document.querySelector('#view-quality .agrid');
      if (g) {
        const rows = rowsOf(g);
        m.qRows = rows.map(r => r.items.length);
        m.qRagged = ragged(rows);
      }
    }
    out.v[v] = m;
  }
  if (typeof switchView === 'function') switchView('overview');
  return out;
}
"""


def build_page(src_path):
    src = open(src_path, encoding='utf-8').read()
    k = src.find('ECharts 5.5.1')
    if k < 0:
        k = src.find('echarts')
    b, e = src.rfind('<script', 0, k), src.find('</script>', k)
    if k < 0 or b < 0 or e < 0:
        raise SystemExit('❌ 在 %s 里找不到内联 ECharts 块，无法打桩' % src_path)
    out = '/tmp/verify_layout.html'
    open(out, 'w', encoding='utf-8').write(src[:b] + STUB + src[e + 9:])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', default=DEFAULT_SRC, help='待校验的单文件产物')
    ap.add_argument('--js', default=DEFAULT_JS, help='图表初始化所在的 app.js（静态查容器 id 用）')
    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('❌ 需要 playwright：pip install playwright && playwright install chromium')
        return 2

    page_path = build_page(args.src)
    print('源：%s' % args.src)
    print('桩页：%s（ECharts 空桩，只量 CSS 版面）\n' % page_path)

    checks = []
    with sync_playwright() as pw:
        br = pw.chromium.launch(channel='chrome', headless=True)
        for w in WIDTHS:
            pg = br.new_page(viewport={'width': w, 'height': 900})
            pg.goto('file://' + page_path, wait_until='domcontentloaded')
            pg.wait_for_timeout(1600)
            r = pg.evaluate(PROBE)
            v = r['v']

            # ⑤ 空板：容器没有高度，图就是白的。逐个视图量（隐藏的视图量不准）
            empty = []
            for view_id in ['overview', 'analytics', 'integration', 'quality']:
                pg.evaluate('(x) => switchView(x)', view_id)
                pg.wait_for_timeout(90)
                for cid, cw, ch2 in pg.evaluate(CONTS):
                    if cw <= 0 or ch2 <= 0:
                        empty.append('%s/%s=%dx%d' % (view_id, cid, cw, ch2))
            pg.close()
            v = r['v']
            two_col = w > 1180          # 两个「塌成单列」的断点：1180（整合）、900（分析网格）
            wide = w > 900

            tag = 'W%d' % w
            ovf = max(m['overflow'] for m in v.values())
            esc = [(k, m['escape']) for k, m in v.items() if m['escape']]
            checks.append(('%s 无横向溢出' % tag, ovf == 0, ovf))
            checks.append(('%s 无内容逃逸' % tag, not esc, esc if esc else 'clean'))
            checks.append(('%s 图表容器均有尺寸' % tag, not empty, empty if empty else 'all > 0'))

            ov = v['overview']
            # ≤700 地图与右栏上下堆叠，不再要求等高
            if ov.get('railDiff') is not None and w > 700:
                checks.append(('%s 总览·地图栏与右栏等高' % tag, ov['railDiff'] == 0, ov['railDiff']))
            checks.append(('%s 总览·KPI 行铺满' % tag, ov['kpiFill'] >= 99, ov['kpiFill']))

            an = v['analytics']
            checks.append(('%s 分析·段内面板等高' % tag, an['ragged'] == 0, an['ragged']))
            checks.append(('%s 分析·行内面板等宽' % tag, an['widthSpread'] == 0, an['widthSpread']))
            checks.append(('%s 分析·末行铺满' % tag, an['minFill'] >= 99, an['minFill']))
            if wide:
                # 每段每行至少 2 格。退化成一格一行时，上面两条（等高/铺满）都是平凡成立的，
                # 只有这条能把「网格塌了但没溢出」的情况抓出来。
                checks.append(('%s 分析·每行至少 2 格' % tag, an['minRowN'] >= 2, an['minRowN']))

            ig = v['integration']
            if two_col:
                checks.append(('%s 整合·两栏等宽' % tag, ig['igWidthDiff'] <= 2, ig['igWidthDiff']))
                checks.append(('%s 整合·左右齐平' % tag, ig['igBottomDiff'] <= 2, ig['igBottomDiff']))
                checks.append(('%s 整合·左栏两块同边' % tag, ig['igLeftDiff'] <= 2, ig['igLeftDiff']))
                checks.append(('%s 整合·块数=3+整行' % tag, ig['igCols'] == 2, ig['igCols']))
            checks.append(('%s 整合·表格独占整行' % tag, ig['igFullFill'] >= 99, ig['igFullFill']))

            q = v['quality']
            checks.append(('%s 质量·行内面板等高' % tag, q['qRagged'] == 0, q['qRagged']))
            if wide:
                checks.append(('%s 质量·2×2 排布' % tag, q['qRows'] == [2, 2], q['qRows']))

        # 标题权重与各档宽度无关，只查一次
        st_fs = r['v']['analytics'].get('titleFs', 0)
        st_fw = r['v']['analytics'].get('titleFw', 0)
        st_bd = r['v']['analytics'].get('titleLine', '0')
        checks.append(('分段标题字号 ≥15px', st_fs >= 15, st_fs))
        checks.append(('分段标题字重 ≥700', st_fw >= 700, st_fw))
        checks.append(('分段标题有分隔线', st_bd not in ('0px', '0', ''), st_bd))
        br.close()

    # ⑤ 静态部分：容器 id 是否登记了高度来源（不看渲染，读源码就能判）
    st = chart_container_static(args.src, args.js)
    checks.append(('图表容器 id 均已登记高度来源', not st['no_height'],
                   st['no_height'] if st['no_height'] else '共 %d 个' % len(st['ids'])))
    checks.append(('HTML 图表容器均有 JS 初始化', not st['no_init'],
                   st['no_init'] if st['no_init'] else '%d 个全部命中' % len(st['ids'] - set(st['dead']))))
    if st['dead']:
        print('  ℹ  %d 个 init 目标在 HTML 里已无元素（下线模块遗留，mk() 已做空值保护）：%s'
              % (len(st['dead']), ', '.join(st['dead'])))

    print('▶ 断言')
    bad = 0
    for name, ok, got in checks:
        if not ok:
            bad += 1
        print('  %s %-30s %s' % ('✓' if ok else '✗', name, got))
    print()
    if bad:
        print('❌ 版面校验未通过：%d/%d 项失败' % (bad, len(checks)))
        return 1
    print('✅ 版面校验通过：%d 项（%d 档宽度 × 4 个页面）' % (len(checks), len(WIDTHS)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
