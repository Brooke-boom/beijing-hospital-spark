# -*- coding: utf-8 -*-
"""清洗 master_institutions.csv 的 key_depts 列（展示层脏数据治理）。

问题: 早期 ETL 把部分源文件的"诊疗科目许可"整串直接灌入 key_depts，
形如 '内科;呼吸内科专业 /外科;普通外科专业  /中医科******' ——
含空格/斜杠/星号污染，导致大屏详情弹窗"重点科室"显示为 '/外科' 之类乱码。

清洗规则(仅对含 '*' 或 空白+斜杠 的行):
  - 按 '/' 拆一级块，每块取 ';'/'；' 前的一级科目段（丢弃二级专业）
  - 一级段内再按 '、/，/,' 拆并列科目，去重保序，';' 连接
不污染的行原样保留。

与 apply_* 脚本同约定:
  - 备份: data/归档_旧版命名/processed_backup/master_institutions_<ts>.csv
  - 审计: data/processed/enrichment/clean_key_depts_log_<ts>.csv
  - master 改完后由调用方重跑 merge_hospital_wide.py 同步宽表

用法: python clean_key_depts.py
"""
import os, csv, re, shutil, datetime

BASE = os.path.expanduser("~/Desktop/毕设")
MASTER = os.path.join(BASE, 'data/processed/master_institutions.csv')
BAKDIR = os.path.join(BASE, 'data/归档_旧版命名/processed_backup')
AUDIT_DIR = os.path.join(BASE, 'data/processed/enrichment')
ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
os.makedirs(BAKDIR, exist_ok=True)
os.makedirs(AUDIT_DIR, exist_ok=True)


def is_dirty(v):
    return ('*' in v) or ('＊' in v) or bool(re.search(r'\s*/\s*', v))


def clean(v):
    s = v.replace('＊', '*')
    s = re.sub(r'\s*/\s*', '/', s)
    out = []
    for seg in s.split('/'):
        seg = seg.rstrip('*').strip()
        if not seg:
            continue
        primary = re.split(r'[；;]', seg)[0]
        for tok in re.split(r'[、，,]', primary):
            tok = tok.strip()
            if tok and tok not in out:
                out.append(tok)
    return ';'.join(out)


with open(MASTER, encoding='utf-8-sig') as f:
    rows = list(csv.DictReader(f))
fn = list(rows[0].keys())

audit, n = [], 0
for r in rows:
    old = (r.get('key_depts') or '').strip()
    if not old or not is_dirty(old):
        continue
    new = clean(old)
    if not new or new == old.replace('*', '').strip():
        # 清洗结果为空或实质无变化(纯星号尾巴)时也修正为干净串
        pass
    audit.append(dict(id=r['id'], name=r['name'], field='key_depts',
                      old=old[:100], new=new[:150]))
    r['key_depts'] = new
    n += 1

shutil.copy2(MASTER, os.path.join(BAKDIR, 'master_institutions_' + ts + '.csv'))
with open(MASTER, 'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=fn)
    w.writeheader()
    w.writerows(rows)

with open(os.path.join(AUDIT_DIR, 'clean_key_depts_log_' + ts + '.csv'),
          'w', newline='', encoding='utf-8-sig') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'name', 'field', 'old', 'new'])
    w.writeheader()
    w.writerows(audit)

print(f'清洗 key_depts 脏行: {n} 家')
print(f'备份: {BAKDIR}/master_institutions_{ts}.csv')
print(f'审计: clean_key_depts_log_{ts}.csv')
