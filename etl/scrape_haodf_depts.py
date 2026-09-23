#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网抓取「好大夫在线」北京医院科室设置（第三轮联网补全）。

背景：主表 9,789 家机构里只有 34 家有在线核实的科室数（前两轮走百度百科），
      机构列表因此大片显示「科室资料待补全」。百科对一级/二级医院覆盖很差，
      好大夫在线对**北京全体医院**有成体系的科室数据，且直接给出官方口径的
      「N个科室」，正好补上前两轮的窟窿。

两步走：
  1) 目录：/hospital/list-11.html（北京市全部医院）→ 435 家 (id, name)
  2) 逐家：/hospital/<id>.html           → 「N个科室 / M位医生」官方口径 + 等级/性质
           /hospital/<id>/keshi/list.html → 完整科室列表（科室名 + 医生数）

产出（增量 JSONL，可断点续抓）：
  data/processed/haodf_depts.jsonl
    {hid, name, dept_count, doctor_count, level_txt, intro_claim, depts:[{name,group,doctors}],
     url, ts, ok}
  data/processed/haodf_hospital_index.json   目录快照（id → name）

用法:
  python etl/scrape_haodf_depts.py                # 全量（自动跳过已抓）
  python etl/scrape_haodf_depts.py --limit 20     # 只抓前 20 家（试跑）
  python etl/scrape_haodf_depts.py --index-only   # 只刷新目录
"""
import argparse
import json
import os
import random
import re
import sys
import time

import requests

ROOT = os.path.expanduser('~/Desktop/毕设/data/processed')
OUT = os.path.join(ROOT, 'haodf_depts.jsonl')
INDEX = os.path.join(ROOT, 'haodf_hospital_index.json')

LIST_URL = 'https://www.haodf.com/hospital/list-11.html'
HOSP = 'https://www.haodf.com/hospital/{hid}.html'
KESHI = 'https://www.haodf.com/hospital/{hid}/keshi/list.html'

HDRS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://www.haodf.com/',
}

_TAG = re.compile(r'<[^>]+>')
_WS = re.compile(r'\s+')


def clean(s):
    return _WS.sub(' ', _TAG.sub('', s or '')).strip()


def get(url, tries=3, timeout=20):
    """带指数退避的 GET；返回 HTML 文本或 None

    ⚠️ 编码：好大夫**列表页**响应头声明 `charset=gbk`，**详情页**是 UTF-8。
       第一版图省事写死 r.encoding='utf-8'，结果列表页整片解成 U+FFFD ——
       435 家医院的名称全成了乱码（详情页的科室名反而是好的，所以肉眼没发现）。
       现在一律交给 apparent_encoding（GB18030 / UTF-8 都能识别）定夺。
    """
    for i in range(tries):
        try:
            r = requests.get(url, headers=HDRS, timeout=timeout)
            if r.status_code == 200:
                r.encoding = r.apparent_encoding or r.encoding or 'utf-8'
                return r.text
            if r.status_code == 404:
                return None
        except Exception:
            pass
        time.sleep(1.5 * (i + 1) + random.random())
    return None


# ---------------------------------------------------------------- 1) 目录
def fetch_index():
    t = get(LIST_URL)
    if not t:
        raise SystemExit('✗ 无法获取北京医院目录页：' + LIST_URL)
    pat = re.compile(r'<a[^>]+href="[^"]*?/hospital/(\d+)\.html"[^>]*>(.*?)</a>', re.S)
    seen = {}
    for m in pat.finditer(t):
        name = clean(m.group(2))
        if name and m.group(1) not in seen:
            seen[m.group(1)] = name
    idx = [{'hid': h, 'name': n} for h, n in seen.items()]
    with open(INDEX, 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    print('  目录：%d 家医院 → %s' % (len(idx), INDEX))
    return idx


# ---------------------------------------------------------------- 2) 详情
def parse_hosp(t):
    """医院主页：科室数 / 医生数 / 基本标签 / 「N个临床科室」类声明句"""
    out = {'dept_count': None, 'doctor_count': None, 'level_txt': '', 'intro_claim': ''}
    # 「医院科室」区块里的 <span class="black">68个科室 </span>
    blk = re.search(r'医院科室(.{0,600}?)item-wrap', t, re.S)
    seg = blk.group(1) if blk else t
    m = re.search(r'>\s*(\d+)\s*个科室', seg) or re.search(r'(\d+)\s*个科室', t)
    if m:
        out['dept_count'] = int(m.group(1))
    m = re.search(r'(\d+)\s*位医生', t)
    if m:
        out['doctor_count'] = int(m.group(1))
    # 基本标签：页头形如「简称: 北京协和医院 | 公立 | 三甲 | 综合医院」
    txt = clean(re.sub(r'<script.*?</script>|<style.*?</style>', '', t, flags=re.S))
    tm = (re.search(r'简称[:：]\s*[^|]{0,40}?((?:公立|民营|私立|军队|部队)'
                    r'(?:\s*\|\s*[^|]{1,18}){0,3})', txt)
          or re.search(r'\|\s*((?:公立|民营|私立)(?:\s*[|·]\s*[^|·]{1,18}){1,3})', txt))
    out['level_txt'] = re.sub(r'\s*\|\s*', ' / ', tm.group(1)).strip()[:120] if tm else ''
    # 简介里的官方口径声明（可与页头数字互校）
    body = clean(re.sub(r'<script.*?</script>|<style.*?</style>', '', t, flags=re.S))
    m = re.search(r'[^。；\n]{0,30}?(\d{1,3})\s*个(?:临床、医技|临床和医技|临床及医技|临床|医技)?科室', body)
    if m:
        out['intro_claim'] = body[max(0, m.start() - 30):m.end() + 6].strip()[:120]
    return out


def parse_keshi(t):
    """科室列表页：按分组取科室名 + 医生数"""
    depts, group = [], ''
    # 顺序扫描 <h3 class="keshi-name..."> 分组名 与 <div class="name-txt">科室名</div>
    pat = re.compile(r'class="keshi-name[^"]*"[^>]*>(.*?)</h3>|class="name-txt"[^>]*>(.*?)</div>'
                     r'(?:\s*<div class="count"[^>]*>(.*?)</div>)?', re.S)
    for m in pat.finditer(t):
        if m.group(1) is not None:
            group = clean(m.group(1))
        else:
            nm = clean(m.group(2))
            if not nm:
                continue
            doc = None
            if m.group(3):
                dm = re.search(r'(\d+)', clean(m.group(3)))
                if dm:
                    doc = int(dm.group(1))
            depts.append({'name': nm, 'group': group, 'doctors': doc})
    # 去重（同一科室可能因锚点重复出现）
    seen, out = set(), []
    for d in depts:
        if d['name'] in seen:
            continue
        seen.add(d['name'])
        out.append(d)
    return out


def load_done():
    done = set()
    if os.path.exists(OUT):
        for line in open(OUT, encoding='utf-8'):
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get('ok'):
                done.add(str(o.get('hid')))
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--index-only', action='store_true')
    args = ap.parse_args()

    idx = fetch_index()
    if args.index_only:
        return

    done = load_done()
    todo = [x for x in idx if x['hid'] not in done]
    if args.limit:
        todo = todo[:args.limit]
    print('  待抓 %d 家（已完成 %d）' % (len(todo), len(done)))

    ok = 0
    with open(OUT, 'a', encoding='utf-8') as f:
        for i, it in enumerate(todo, 1):
            hid, name = it['hid'], it['name']
            t = get(HOSP.format(hid=hid))
            rec = {'hid': hid, 'dir_name': name, 'name': name, 'ok': False,
                   'url': HOSP.format(hid=hid), 'ts': int(time.time())}
            if t:
                info = parse_hosp(t)
                rec.update(info)
                # 页头标题里的规范名（「北京协和医院好不好/怎么样 - …」→ 北京协和医院）
                tm = re.search(r'<title>(.*?)</title>', t, re.S)
                if tm:
                    rec['page_title'] = clean(tm.group(1))
                kt = get(KESHI.format(hid=hid), tries=2)
                rec['depts'] = parse_keshi(kt) if kt else []
                rec['ok'] = bool(rec.get('dept_count') or rec['depts'])
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            f.flush()
            if rec['ok']:
                ok += 1
            if i % 20 == 0 or i == len(todo):
                print('  [%d/%d] 成功 %d | 最近：%s (%s个科室/%d个科室名)'
                      % (i, len(todo), ok, name, rec.get('dept_count'),
                         len(rec.get('depts') or [])))
            time.sleep(0.55 + random.random() * 0.6)
    print('  完成：新增成功 %d / 尝试 %d → %s' % (ok, len(todo), OUT))


if __name__ == '__main__':
    main()
