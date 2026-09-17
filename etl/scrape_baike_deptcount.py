# -*- coding: utf-8 -*-
"""科室数量联网核实（第二轮百科抓取）：
对上轮已解析出词条 URL 的医院，重新打开词条页，提取「主要科室/科室设置」正文章节：
  1) 权威声明：正则抓「设置/设有/开设 N 个临床(、医技)?科室 / N 个科室」句（多为医院官网口径）
  2) 兜底计数：「科室一栏/科室列表」表格条目数
增量 JSONL 落盘可断点续抓。用法：
  python scrape_baike_deptcount.py <queries_with_urls.json> <out.jsonl>
"""
import json
import re
import sys
import time

from playwright.sync_api import sync_playwright

JS = """() => {
  const body = document.body ? document.body.innerText : '';
  const t = document.title || '';
  return {t, body};
}"""

# 权威声明句式（医院官网口径，百科转述）
PATTERNS = [
    r'[设设]?[置有立开]\s*([0-9０-９]+)\s*个临床(?:[、和与]+医技)?科室',
    r'([0-9０-９]+)\s*个临床(?:[、和与]+医技)?科室',
    r'[设置有开]\s*([0-9０-９]+)\s*个(?:医疗)?科室',
    r'共\s*([0-9０-９]+)\s*个科室',
    r'下辖\s*([0-9０-９]+)\s*个科室',
]
# 兜底：科室表条目计数的关键词
SEC_KEYS = ['主要科室', '科室设置', '科室介绍', '科室一览', '医疗科室', '科室列表', '重点科室']


def to_half(s):
    return s.translate({ord(c): chr(ord(c) - 0xFEE0) for c in '０１２３４５６７８９'})


def extract(body):
    out = {'claims': [], 'table_count': None}
    # 1) 声明句
    for m in re.finditer(r'[^。\n]{0,26}[0-9０-９]{2,4}\s*个[^。\n]{0,14}科室[^。\n]{0,14}', body):
        seg = m.group(0)
        for pat in PATTERNS:
            mm = re.search(pat, seg)
            if mm:
                n = int(to_half(mm.group(1)))
                if 5 <= n <= 400:
                    out['claims'].append({'n': n, 'ctx': seg.strip()[:80]})
                break
    # 去重同 n
    seen, dedup = set(), []
    for c in out['claims']:
        if c['n'] not in seen:
            seen.add(c['n'])
            dedup.append(c)
    out['claims'] = dedup[:5]
    # 2) 科室表兜底：取「科室」类章节下带 ▪ / 空行交替的条目段
    #    依据 301 页面结构：『科室一栏』后出现大量 "\n\n科室名\n\n" 交替，直到空行/下一标题
    for key in SEC_KEYS:
        idxs = [m.start() for m in re.finditer(re.escape(key), body)]
        # 取正文出现（跳过目录区：目录区特征是后随 ▪ 链接列表）
        for i in idxs:
            seg = body[i + len(key): i + len(key) + 5000]
            if '参考资料' not in seg and len(seg.strip()) >= 40:
                # 只保留"长得像科室名"的条目：以 科/室/中心/部/组/病区/门诊 等结尾，
                # 过滤类别行、参考资料、更新截至、院区标题等噪声
                NAME_SUFFIX = ('科', '室', '中心', '部', '组', '病区', '门诊',
                               '研究所', '研究室', 'ICU', 'MICU')
                NOISE = ('类别', '参考资料', '播报', '编辑', '更新截至', '院区科室',
                         '非手术科室', '手术科室', '诊断相关', '国际医疗', '附属医院',
                         '科室一栏', '医疗团队', '医科大学', '医学院', '医院介绍',
                         '医院地址', '就医指南', '医院排名', '科室设置',
                         '查看全部', '收起', '展开', '更多')
                items = []
                for chunk in re.split(r'[、;；\n]+', seg):
                    t = chunk.strip()
                    if not t or len(t) > 16 or re.search(r'[0-9]{4}|（|\(|\[|：|:|，|。', t):
                        continue
                    if any(n in t for n in NOISE):
                        continue
                    if t.endswith(NAME_SUFFIX):
                        items.append(t)
                if len(items) >= 8:
                    out['table_count'] = len(items)
                    out['table_src'] = key
                    out['table_items'] = items[:80]
                    break
        if out['table_count']:
            break
    return out


def main(inp, outp):
    todo = json.load(open(inp, encoding='utf-8'))  # [[query, url], ...]
    done = set()
    try:
        for l in open(outp, encoding='utf-8'):
            done.add(json.loads(l)['query'])
    except FileNotFoundError:
        pass
    todo = [x for x in todo if x[0] not in done]
    print('待抓 %d（已完成 %d）' % (len(todo), len(done)))
    with sync_playwright() as p:
        b = p.chromium.launch(channel='chrome', headless=True)
        pg = b.new_page(user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36')
        for k, (query, url) in enumerate(todo):
            rec = {'query': query, 'url': url, 'found': False}
            try:
                pg.goto(url, timeout=30000)
                pg.wait_for_timeout(2200)
                d = pg.evaluate(JS)
                body = d['body']
                if '百度百科尚未收录' not in body[:3000] and len(body) > 2000:
                    rec['found'] = True
                    rec.update(extract(body))
            except Exception as e:
                rec['error'] = '%s: %s' % (type(e).__name__, str(e)[:120])
            with open(outp, 'a', encoding='utf-8') as f:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            if (k + 1) % 20 == 0:
                print('  %d/%d' % (k + 1, len(todo)))
            time.sleep(0.7)
        b.close()
    print('done ->', outp)


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
