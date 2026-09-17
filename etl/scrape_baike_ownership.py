#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""办别/医院等级联网核实（百度百科第三轮抓取）：
对「办别未标注医院」与「等级缺失医院」批量打开百科词条，
提取信息栏（医院等级 / 医院类型 / 经营性质 / 经济类型 / 主管部门）与
全文「医院性质/公立/民营」上下文句，供 build_ownership_online.py 合并。
增量 JSONL 落盘可断点续抓。用法：
  python scrape_baike_ownership.py [targets_json] [out_jsonl]
"""
import json, os, random, re, sys, time, urllib.parse

from playwright.sync_api import sync_playwright

TARGET = sys.argv[1] if len(sys.argv) > 1 else '/tmp/ownership_targets.json'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(
    '~/Desktop/毕设/data/processed/baike_ownership.jsonl')

LABELS = ['中文名', '成立时间', '主管部门', '医院等级', '医院类型', '医院性质',
          '经营性质', '经济类型', '医保定点', '院长', '重点专科', '开放住院床位']

# 全文兜底：医院性质/办医主体上下文句
CTX_KEYS = ['医院性质', '公立医院', '民营医院', '私营', '政府办', '国有', '集体办',
            '军队医院', '部队医院', '非营利性', '营利性']


def query_variants(name):
    """检索形态：全名 → 去括号 → 去空格分段首段 → 去院区后缀"""
    v = [name]
    s = re.sub(r'[（(][^（）()]*[）)]', '', name).strip()
    if s and s != name:
        v.append(s)
    first = re.split(r'\s+', name)[0].strip()
    if len(first) >= 4 and first not in v:
        v.append(first)
    out, seen = [], set()
    for x in v:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def parse_infobox(lines):
    info, i, n = {}, 0, len(lines)
    while i < n:
        ln = lines[i].strip()
        base = re.sub(r'\s+', '', ln)
        hit = None
        for lab in LABELS:
            if base.startswith(lab) and len(base) <= len(lab) + 2:
                hit = lab
                break
        if hit:
            vals = []
            j = i + 1
            while j < n:
                nxt = lines[j].strip()
                nb = re.sub(r'\s+', '', nxt)
                if not nxt or any(nb.startswith(l2) and len(nb) <= len(l2) + 2
                                  for l2 in LABELS):
                    break
                if nxt in ('相关视频', '查看全部') or re.match(r'^\d+:\d\d$', nxt):
                    break
                vals.append(nxt)
                j += 1
            if vals:
                info[hit] = '；'.join(vals)
            i = j
        else:
            i += 1
    return info


def ctx_sentences(body):
    out = []
    for key in CTX_KEYS:
        pos = 0
        cnt = 0
        while cnt < 2:
            i = body.find(key, pos)
            if i < 0:
                break
            seg = body[max(0, i - 40): i + 60].replace('\n', ' ').strip()
            if seg not in out:
                out.append(seg)
            pos = i + len(key)
            cnt += 1
    return out[:12]


JS_EXTRACT = """() => {
  const head = document.title;
  const body = document.body.innerText;
  return {head, body};
}"""


def main():
    targets = json.load(open(TARGET, encoding='utf-8'))
    names = [t['name'] if isinstance(t, dict) else t for t in targets]
    done = set()
    if os.path.exists(OUT):
        for ln in open(OUT, encoding='utf-8'):
            try:
                done.add(json.loads(ln)['query'])
            except Exception:
                pass
    todo = []
    for n in names:
        for v in query_variants(n):
            if v not in done:
                todo.append((n, v))
    print(f'[todo] {len(todo)} queries for {len(names)} hospitals', flush=True)

    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        ctx = b.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
            locale='zh-CN', viewport={'width': 1366, 'height': 900},
            extra_http_headers={'Accept-Language': 'zh-CN,zh;q=0.9'})
        pg = ctx.new_page()
        out = open(OUT, 'a', encoding='utf-8')
        ok = fail = 0
        try:
            for i, (orig, q) in enumerate(todo):
                url = 'https://baike.baidu.com/item/' + urllib.parse.quote(q)
                rec = {'name': orig, 'query': q, 'url': url, 'found': False}
                try:
                    pg.goto(url, timeout=20000, wait_until='domcontentloaded')
                    pg.wait_for_timeout(1200 + random.randint(0, 600))
                    d = pg.evaluate(JS_EXTRACT)
                    body = d['body']
                    rec['head'] = d['head']
                    disambig = bool(re.search(r'百度百科尚未收录|消歧义|多义词', body[:3000]))
                    rec['disambig'] = disambig
                    lines = body.split('\n')
                    rec['infobox'] = parse_infobox(lines)
                    rec['ctx'] = ctx_sentences(body)
                    rec['found'] = ('百度百科' in body or len(rec['infobox']) > 0) and not disambig
                    ok += rec['found']
                    if not rec['found']:
                        fail += 1
                except Exception as e:
                    rec['error'] = f'{type(e).__name__}: {e}'[:120]
                    fail += 1
                out.write(json.dumps(rec, ensure_ascii=False) + '\n')
                out.flush()
                if (i + 1) % 20 == 0:
                    print(f'[{i+1}/{len(todo)}] ok={ok} miss={fail} last={q} found={rec.get("found")}', flush=True)
                time.sleep(0.5 + random.random() * 0.6)
        finally:
            out.close()
            b.close()
        print(f'[done] ok={ok} miss={fail} -> {OUT}')


if __name__ == '__main__':
    main()
