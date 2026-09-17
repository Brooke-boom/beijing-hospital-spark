#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量抓取百度百科医院词条：重点专科 / 科室设置 / 医院等级 / 成立时间等
产出: data/processed/baike_depts.jsonl (每行 {name, query, url, found, infobox{...}, key_depts_section[], national_mentions[]})
支持断点续抓（跳过已抓 query），抓取失败记 found=false。
用法: /Users/brooke/.workbuddy/binaries/python/envs/default/bin/python etl/scrape_baike_depts.py [target_json] [out_jsonl]
"""
import json, os, random, re, sys, time, urllib.parse

from playwright.sync_api import sync_playwright

TARGET = sys.argv[1] if len(sys.argv) > 1 else '/tmp/target_hospitals.json'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(
    '~/Desktop/毕设/data/processed/baike_depts.jsonl')

LABELS = ['中文名', '外文名', '成立时间', '地理位置', '主管部门', '院长', '医院等级',
          '医院类型', '医保定点', '经济类型', '经营性质', '职工人数', '重点专科',
          '科室设置', '开放住院床位', '建筑面积', '官网', '服务热线']

def query_variants(name):
    """同一名词的多个检索形态：全名 → 去括号 → 去院区后缀"""
    v = [name]
    s = re.sub(r'[（(][^（）()]*[）)]', '', name).strip()
    if s and s != name:
        v.append(s)
    return v

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
                if not nxt or any(re.sub(r'\s+', '', x).startswith(l2) and len(re.sub(r'\s+', '', x)) <= len(l2) + 2
                                  for l2 in LABELS for x in [nxt]):
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

def extract_key_section(lines):
    """取正文「重点专科」章节的子标题（科室名）"""
    idxs = [i for i, ln in enumerate(lines) if ln.strip() == '重点专科']
    if not idxs:
        return []
    # 正文标题通常是最后一次出现（前面是目录）
    start = idxs[-1]
    out = []
    for ln in lines[start + 1:]:
        s = ln.strip()
        if re.match(r'^\d{1,2}(?!\d)', s) and len(s) <= 14:  # 下一个顶级章节
            break
        if s and not s.startswith('▪') and not s.startswith('播放') and not re.match(r'^\d+:\d\d$', s) \
           and len(s) <= 16 and '百度百科' not in s:
            out.append(s)
        if len(out) > 40:
            break
    return out

JS_EXTRACT = """() => {
  const head = document.title;
  const body = document.body.innerText;
  // h2 → h3 目录树
  const hs = Array.from(document.querySelectorAll('h1,h2,h3'));
  const toc = [];
  let cur = null;
  for (const e of hs) {
    if (e.tagName === 'H2') { cur = {h2: e.innerText.replace(/\\s/g,''), h3: []}; toc.push(cur); }
    else if (e.tagName === 'H3' && cur) cur.h3.push(e.innerText.replace(/\\s/g,''));
  }
  const secOf = n => { const t = toc.find(x => x.h2 === n); return t ? t.h3 : []; };
  const keySection = secOf('重点专科');
  const deptSection = toc.filter(x => /科室|专科|特色/.test(x.h2)).flatMap(x => x.h3);
  const disambig = /百度百科尚未收录|消歧义|多义词/.test(body.slice(0, 3000)) && keySection.length === 0;
  // 国家临床重点专科 上下文句
  const ctx = [];
  let pos = 0;
  while (ctx.length < 8) {
    const i = body.indexOf('国家临床重点专科', pos);
    if (i < 0) break;
    ctx.push(body.slice(Math.max(0, i - 60), i + 70).replace(/\\s+/g, ' '));
    pos = i + 8;
  }
  return {head, body, keySection, deptSection, disambig, ctx};
}"""

def main():
    names = json.load(open(TARGET, encoding='utf-8'))
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
                    rec['head'] = d['head']
                    rec['disambig'] = d['disambig']
                    lines = d['body'].split('\n')
                    rec['infobox'] = parse_infobox(lines)
                    rec['key_depts_section'] = d['keySection'] or d['deptSection'] or extract_key_section(lines)
                    rec['national_context'] = d['ctx']
                    ncm = sorted(set(re.findall(r'国家临床重点专科[^，。；\n]{0,14}', d['body'])))[:6]
                    rec['national_mentions'] = ncm
                    rec['found'] = ('百度百科' in d['body'] or len(rec['infobox']) > 0) and not d['disambig']
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
