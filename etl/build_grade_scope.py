# -*- coding: utf-8 -*-
"""派生 grade_scope（是否适用医院等级评审），解决"未定级"占比虚高问题。

背景：master 全表 9791 家中仅约 1282 家属于参加医院等级评审的医疗机构，
其余（诊所/村卫生室/门诊部/社区卫生服务站/医务室/急救/疾控/体检等）天然无
"一级/二级/三级"等级。Spark ETL 原先将空等级一律填为 lit("未定级")，
导致等级分布图中 87% 落入"未定级"，掩盖真实分布。

判定规则（自上而下短路）：
  1. level 非空                      -> applicable（有等级记录，必属参评机构）
  2. category/category_raw 属住院医院类 -> applicable
  3. 名称含"医院"且非下属门诊部/医务室/诊所 -> applicable
  4. 明确非参评类别                   -> not_applicable
  5. 其余                            -> unknown（待人工确认，默认不参评统计）

输出：data/processed/enrichment/grade_scope.csv
      （id,name,category,category_raw,level,level_sub,grade_scope,reason）
用法：python etl/build_grade_scope.py [--apply]   # --apply 时把 grade_scope 列写回 master_institutions.csv
"""
import os, csv, shutil, datetime, collections, argparse

BASE = os.path.expanduser("~/Desktop/毕设")
MASTER = os.path.join(BASE, 'data/processed/master_institutions.csv')
OUT = os.path.join(BASE, 'data/processed/enrichment/grade_scope.csv')
BAKDIR = os.path.join(BASE, 'data/归档_旧版命名/processed_backup')

# 住院医院类（参加医院评审）
INPATIENT_CAT = ('医院', '中医医院', '妇幼保健院', '疗养院', '保健院', '中西医结合')
# 明确不参加医院等级评审的机构类别
NON_GRADED_CAT = ('诊所', '村卫生室', '门诊部', '社区卫生服务站', '社区卫生服务中心',
                  '医务室', '急救机构', '公共卫生机构', '护理站', '体检机构', '其他医疗机构')
# 名称含"医院"但属于下属/分支性质，不单独参评
BRANCH_SUFFIX = ('医务室', '门诊部', '诊所', '服务站', '服务中心', '管理', '体检', '急救')


def decide(r):
    cat = (r.get('category') or '').strip()
    raw = (r.get('category_raw') or '').strip()
    name = (r.get('name') or '').strip()
    level = (r.get('level') or '').strip()

    if level:
        return 'applicable', '有等级记录'
    if any(k in cat for k in INPATIENT_CAT):
        return 'applicable', '住院医院类'
    if '医院' in name and not any(k in name for k in BRANCH_SUFFIX):
        return 'applicable', '名称含医院且非分支'
    if any(k in cat for k in NON_GRADED_CAT):
        return 'not_applicable', f'类别={cat} 不参加医院评审'
    if any(k in raw for k in INPATIENT_CAT):
        return 'applicable', '原始类别属住院医院'
    return 'unknown', '类别未识别'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='把 grade_scope 列写回 master_institutions.csv')
    args = ap.parse_args()

    with open(MASTER, encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    fn = list(rows[0].keys())

    out = []
    for r in rows:
        scope, reason = decide(r)
        out.append(dict(id=r['id'], name=r['name'], category=r.get('category', ''),
                        category_raw=r.get('category_raw', ''), level=r.get('level', ''),
                        level_sub=r.get('level_sub', ''), grade_scope=scope, reason=reason))
        r['grade_scope'] = scope

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
        w.writeheader()
        w.writerows(out)

    # 统计
    print('=== grade_scope 分布 ===')
    c = collections.Counter(x['grade_scope'] for x in out)
    for k, v in c.most_common():
        print(f'  {k}: {v}')
    app = [x for x in out if x['grade_scope'] == 'applicable']
    print(f'\n应参评(applicable) {len(app)} 家等级分布:')
    for k, v in collections.Counter(x['level'] or '(空)' for x in app).most_common():
        n = len(app)
        print(f'  {k}: {v}  ({v / n * 100:.1f}%)')
    unk = [x for x in out if x['grade_scope'] == 'unknown']
    print(f'\nunknown 样例(前10):')
    for x in unk[:10]:
        print('   ', x['id'], x['name'][:32], '|', x['category'], '|', x['reason'])
    print('\n已写:', OUT)

    if args.apply:
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        os.makedirs(BAKDIR, exist_ok=True)
        shutil.copy2(MASTER, os.path.join(BAKDIR, 'master_institutions_' + ts + '.csv'))
        if 'grade_scope' not in fn:
            fn.append('grade_scope')
        with open(MASTER, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=fn)
            w.writeheader()
            w.writerows(rows)
        print('已写回 master（含备份）:', MASTER)


if __name__ == '__main__':
    main()
