# -*- coding: utf-8 -*-
"""刷新 docs/功能点-代码对应表.md 里的代码行号引用。

引用形态：
  A 函数名  ：`renderKPI` L1427          → function/def/const/var NAME
  B Flask 路由：`GET /api/x` | L113       → @app.route("/api/x")
  C 文件内语句：`layer_dwd.py`（171 行）L137/147 → 无锚点，原样保留

消歧：多命中时用「同一行里其它唯一命中的引用所在文件」投票
      （表格一行通常只引用同一个文件）。

用法：python etl/refresh_linerefs.py [--write]   # 不写 --write 为 dry-run
"""
import os, re, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # etl/ 的上一级 = 项目根
DOC = os.path.join(BASE, 'docs', '功能点-代码对应表.md')
CANDIDATES = ['web/app.js', 'web/app.nlq.js', 'web/app.nlq.ui.js', 'web/app.py', 'web/nlq.py']
WRITE = '--write' in sys.argv

src = {}
for rel in CANDIDATES:
    p = os.path.join(BASE, rel)
    if os.path.exists(p):
        src[rel] = open(p, encoding='utf-8').read().split('\n')


def find_def(name):
    """返回 [(rel, lineno)]，行号 1-based。"""
    out = []
    n = re.escape(name)
    pat = re.compile(r'(?:function\s+%s\s*\(|def\s+%s\s*\(|(?:const|let|var)\s+%s\s*=|^%s\s*=\s*[\[({])'
                     % (n, n, n, n))
    for rel, lines in src.items():
        for i, l in enumerate(lines, 1):
            if pat.search(l):
                out.append((rel, i))
    return out


def find_route(path):
    out = []
    for rel, lines in src.items():
        for i, l in enumerate(lines, 1):
            if '@app.route(' in l:
                chunk = ' '.join(lines[i - 1:i + 2])
                if ('"%s"' % path) in chunk or ("'%s'" % path) in chunk:
                    out.append((rel, i))
    return out


doc = open(DOC, encoding='utf-8').read()
lines = doc.split('\n')

patA = re.compile(r'`([A-Za-z_][A-Za-z0-9_]*)`\s*L(\d{3,4})')
patB = re.compile(r'`((?:GET|POST|PUT|DELETE|\|)+)\s*(/[A-Za-z0-9_/<>]*)\s*`\s*\|\s*L(\d{3,4})')

# ---------- 第一轮：收集 ----------
rows = []   # (li, [ (kind, name, old, hits) ])
for li, line in enumerate(lines, 1):
    if not re.search(r'L\d{3,4}', line):
        continue
    items = []
    for m in patB.finditer(line):
        items.append(('route', m.group(2), int(m.group(3)), find_route(m.group(2))))
    for m in patA.finditer(line):
        items.append(('func', m.group(1), int(m.group(2)), find_def(m.group(1))))
    if items:
        rows.append((li, items))

# ---------- 第二轮：投票消歧 ----------
plans, skipped = [], []
newlines = {}
for li, items in rows:
    # 本行唯一命中项的文件投票
    votes = {}
    for kind, name, old, hits in items:
        if len(hits) == 1:
            votes[hits[0][0]] = votes.get(hits[0][0], 0) + 1
    best = None
    if votes:
        top = sorted(votes.items(), key=lambda kv: -kv[1])
        if len(top) == 1 or top[0][1] > top[1][1]:
            best = top[0][0]
    line = lines[li - 1]
    newline = line
    for kind, name, old, hits in items:
        pick = None
        if len(hits) == 1:
            pick = hits[0]
        elif len(hits) > 1 and best:
            same = [h for h in hits if h[0] == best]
            if len(same) == 1:
                pick = same[0]
        if pick is None:
            if len(hits) == 0:
                skipped.append((li, kind, name, '未找到定义（可能已改名，需人工）'))
            else:
                skipped.append((li, kind, name, '多命中且无法投票: ' +
                                ','.join('%s L%d' % h for h in hits)))
            continue
        rel, actual = pick
        if actual == old:
            plans.append((li, kind, name, old, actual, rel + ' [已对]'))
            continue
        if kind == 'route':
            newline = newline.replace('L%d' % old, 'L%d' % actual, 1)
        else:
            newline = newline.replace('`%s` L%d' % (name, old), '`%s` L%d' % (name, actual), 1)
        plans.append((li, kind, name, old, actual, rel))
    if newline != line:
        newlines[li] = newline

changed = [p for p in plans if p[3] != p[4]]
already = [p for p in plans if p[3] == p[4]]

print('=' * 80)
print('将刷新 %d 处 / 已正确 %d 处 / 需人工 %d 处' % (len(changed), len(already), len(skipped)))
print('=' * 80)
print('\n--- 将刷新 ---')
for li, kind, name, old, new, rel in changed:
    print('  第%4d行  %-24s L%-5d → L%-5d  (%s)' % (li, name, old, new, rel))
print('\n--- 已正确 ---')
for li, kind, name, old, new, rel in already:
    print('  第%4d行  %-24s L%-5d  (%s)' % (li, name, old, rel))
print('\n--- 需人工 ---')
for li, kind, name, why in skipped:
    print('  第%4d行  %-24s %s' % (li, name, why))

if WRITE:
    for li, nl in newlines.items():
        lines[li - 1] = nl
    open(DOC, 'w', encoding='utf-8').write('\n'.join(lines))
    print('\n✅ 已写入（%d 处刷新）' % len(changed))
else:
    print('\n（dry-run，未写入）')
