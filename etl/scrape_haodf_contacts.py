#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""联网补全：联系电话 / 医院等级（数据源：好大夫在线 医院详情页）

背景
----
关键字段完整率里最刺眼的是 `phone` —— 9,789 家只有 570 家有电话（5.8%），
机构列表里绝大多数行点开都没法打电话。公开数据源里带电话的列已全部回收过
（见 `harvest_source_fields.py`），剩下的缺口只能联网补。

好大夫在线的医院详情页页头固定给出三样结构化信息：
    <div class="hos-address">地址：…</div>
    <div class="hos-phone">电话：010-84205566(总机),…</div>
    简介首句常写「…三级甲等医院…」
`haodf_depts.jsonl`（上一轮抓的 435 家北京医院）已经带 hid，直接复用同一批 id，
不必重新解析目录页。

产出（增量 JSONL，可断点续抓）
----
  data/processed/haodf_contacts.jsonl
    {hid, name, phone, addr, level, level_sub, level_ev, url, ts, ok}

用法
----
  python etl/scrape_haodf_contacts.py             # 增量（跳过已抓）
  python etl/scrape_haodf_contacts.py --limit 15  # 试跑
  python etl/scrape_haodf_contacts.py --refetch   # 忽略已有结果重抓
"""
import argparse
import json
import os
import random
import re
import sys
import time

import requests

BASE = os.path.expanduser('~/Desktop/毕设')
PROC = os.path.join(BASE, 'data', 'processed')
SRC = os.path.join(PROC, 'haodf_depts.jsonl')
OUT = os.path.join(PROC, 'haodf_contacts.jsonl')

HOSP = 'https://www.haodf.com/hospital/{hid}.html'
HDRS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 '
                   '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://www.haodf.com/',
}

_TAG = re.compile(r'<[^>]+>')
_WS = re.compile(r'\s+')
PHONE_DIV = re.compile(r'class="hos-phone"[^>]*>(.*?)</div>', re.S)
ADDR_DIV = re.compile(r'class="hos-address"[^>]*>(.*?)</div>', re.S)
# 「三级甲等医院」「二级乙等」「一级综合医院」——只要带"医院"二字的自述，避免抓到
# "下设 3 家二级医院" 这种别家机构的描述
LEVEL_EV = re.compile(r'([一二三]级(?:[甲乙丙]等)?)\s*(?:综合|专科|中医|中西医结合)?医院')
LV_ONLY = re.compile(r'([一二三]级)(?:[甲乙丙]等)?')
SUB_ONLY = re.compile(r'([一二三]级)([甲乙丙])等')

_PH_SPLIT = re.compile(r'[，,;；、]')
_CN_NUM = str.maketrans('０１２３４５６７８９（）－', '0123456789()-')


def clean(s):
    return _WS.sub(' ', _TAG.sub('', s or '')).strip()


def norm_phone(raw):
    """'电话：010-84205566(总机),010-84205288(咨询)' → '010-84205566 / 010-84205288'

    只保留号码本体，去掉「(总机)」「(咨询)」这类括注 —— 展示层不需要。
    """
    if not raw:
        return ''
    t = str(raw).translate(_CN_NUM)
    t = re.sub(r'^电话[：:]\s*', '', t).strip()
    out = []
    for seg in _PH_SPLIT.split(t):
        seg = re.sub(r'[（(][^（）()]*[）)]', '', seg).strip()
        m = re.search(r'(\d[\d\-\s]{5,})', seg)
        if not m:
            continue
        v = re.sub(r'\s+', '', m.group(1)).strip('-')
        d = re.sub(r'\D', '', v)
        if 7 <= len(d) <= 20:
            out.append(v)
    return ' / '.join(out[:3])


def parse_level(text, name=''):
    """从页面正文抽「医院等级」。返回 (level, level_sub, 证据句)

    只认「…级…等医院」这种**自述式**写法（`LEVEL_EV`），
    不认「我院下设 2 家二级医院」这类第三方描述 —— 后者会把别家医院的等级
    当成自己的。抽不到就留空，不推测。
    """
    for m in LEVEL_EV.finditer(text or ''):
        seg = text[max(0, m.start() - 30):m.end() + 10]
        # 排除明显在讲别家的
        if re.search(r'(下设|托管|所属|包括|设有|集团内)', seg):
            continue
        lv = m.group(1)
        lm = re.match(r'([一二三]级)([甲乙丙])?等?', lv)
        return lm.group(1), (lm.group(2) + '等' if lm.group(2) else ''), seg.strip()[:120]
    return '', '', ''


def get(url, tries=3, timeout=20):
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
        time.sleep(1.2 * (i + 1) + random.random())
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--refetch', action='store_true')
    ap.add_argument('--delay', type=float, default=0.7)
    args = ap.parse_args()

    src = []
    for line in open(SRC, encoding='utf-8'):
        line = line.strip()
        if line:
            src.append(json.loads(line))
    done = set()
    if os.path.exists(OUT) and not args.refetch:
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

    todo = [o for o in src if str(o.get('hid')) not in done]
    if args.limit:
        todo = todo[:args.limit]
    print('好大夫医院 %d 家，已抓 %d 家，本轮待抓 %d 家' % (len(src), len(done), len(todo)), flush=True)

    fh = open(OUT, 'a', encoding='utf-8')
    n_ph = n_lv = 0
    for i, o in enumerate(todo, 1):
        hid = str(o.get('hid'))
        url = HOSP.format(hid=hid)
        html = get(url)
        rec = {'hid': hid, 'name': o.get('name') or '', 'url': url,
               'ts': int(time.time()), 'ok': False, 'phone': '', 'addr': '',
               'level': '', 'level_sub': '', 'level_ev': '', 'traffic': ''}
        if html:
            body = clean(html)
            pm = PHONE_DIV.search(html)
            am = ADDR_DIV.search(html)
            rec['phone'] = norm_phone(clean(pm.group(1)) if pm else '')
            rec['addr'] = re.sub(r'^地址[：:]\s*', '', clean(am.group(1)) if am else '')
            lv, sub, ev = parse_level(body, rec['name'])
            rec['level'], rec['level_sub'], rec['level_ev'] = lv, sub, ev
            # 乘车路线：好大夫只在少数页面写「乘车路线：…」
            tm = re.search(r'乘车路线[：:]\s*([^\n。]{4,120})', body)
            if tm:
                rec['traffic'] = tm.group(1).strip()
            rec['ok'] = True
            if rec['phone']:
                n_ph += 1
            if rec['level']:
                n_lv += 1
        fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
        fh.flush()
        if i % 20 == 0 or i == len(todo):
            print('  %d/%d | 有电话 %d | 有等级 %d' % (i, len(todo), n_ph, n_lv), flush=True)
        time.sleep(args.delay + random.random() * 0.4)
    fh.close()
    print('✓ %s' % OUT)
    print('  本轮：%d 家，其中有电话 %d，有等级 %d' % (len(todo), n_ph, n_lv))
    return 0


if __name__ == '__main__':
    sys.exit(main())
