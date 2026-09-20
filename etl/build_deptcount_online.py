# -*- coding: utf-8 -*-
"""科室数量在线核实合并（幂等）：
baike_deptcount.jsonl（百科「主要科室/科室设置」章节）→ 主表新列
  dept_count_online  在线核实科室数（claims 官网口径优先，否则科室表计数）
  dept_count_src     来源标注：baike_claim（官网口径转述）/ baike_table（词条科室表计数）
覆盖策略：在线值非空即覆盖（报告列出变小案例人工复核）；无在线值保持源口径。
产出：data/processed/govern_report_deptcount_online.md

⚠️ 两道质检关（2026-09-20 补，此前缺失导致 22 家医院凭空多出「59 个科室」）：

  1) 模板污染检测：同一句 ctx 原句被 ≥3 家**不同机构**命中，判为百科模板文字 /
     词条张冠李戴，整条 claim 作废。实例：「开放编制床位2500张；共设59个临床、医技科室」
     被 22 家首医系医院共用（百度百科这几家词条共用同一段简介）；
     「局内设17个科室，所属机构包括社区矫正中心」是**司法局**的词条，
     却命中了延庆区医院、怀柔医院（搜索串词条）。
     判「不同机构」时先做名称归并，避免把同一家的简称/全称当成两家而误伤。
  2) 口径筛选：废弃原先的 max(claims.n) —— 它会把「19 个科室及专业为国家临床重点专科」
     这类**非科室总数**的数字当成科室数。改为按语义优先级挑：临床+医技合计 > 含医技 > 其它，
     并直接排除含「重点专科/护理单元/床位/病区/职工」的句子。
"""
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict

sys.path.insert(0, 'etl')
from build_specialty_online import ALIAS, norm  # noqa: E402  复用别名归一（import 副作用安全：有 __main__ 保护）

MASTER = 'data/processed/master_institutions.csv'
JSONL = 'data/processed/baike_deptcount.jsonl'
REPORT = 'data/processed/govern_report_deptcount_online.md'

# 判为「同一机构」所需的最少不同机构数；低于此值不判污染（宁可漏判，不可误伤）
TEMPLATE_MIN_ORGS = 3

# 数字 n 后面紧接的必须形如「个(临床/医技/…)科室」才算科室总数
_DEPT_AFTER = re.compile(
    r'^个?(?:临床、医技|临床和医技|临床及医技|临床与医技|临床|医技|综合|全|一级|二级|三级)?科室')
# 反例：「19个科室及专业为国家临床重点专科」——数字是重点专科数，不是科室总数
_NOT_TOTAL_AFTER = re.compile(r'^个?科室(及|和)?(专业)?(为|是)?国家临床重点专科')
# 反向表述：「临床科室 59 个」
_DEPT_BEFORE = re.compile(r'科室[^，。；]{0,6}$')

# 机构名前缀：剥离后用于判断两条词条名是否指向同一家
_ORG_PREFIX = (
    '首都医科大学附属', '首都医科大学', '北京大学附属', '北京大学',
    '清华大学附属', '清华大学', '中国医学科学院', '中国中医科学院',
    '中国中医研究院', '北京中医药大学附属', '北京中医药大学',
    '中国人民解放军', '中国人民', '中国',
)


def org_core(name):
    """机构名核心：剥离「XX大学附属」等前缀，用于同机构别名的粗判定"""
    s = norm(name)
    for p in _ORG_PREFIX:
        if s.startswith(p):
            return s[len(p):]
    return s


def same_org(a, b):
    """两条词条名是否指向同一机构（同 id 由调用方负责，这里只比名字）"""
    a, b = norm(a), norm(b)
    if a == b:
        return True
    ca, cb = org_core(a), org_core(b)
    if ca == cb:
        return True
    # 简称/全称：如「北京儿童医院」⊂「首都医科大学附属北京儿童医院」
    if len(ca) >= 4 and len(cb) >= 4 and (ca in cb or cb in ca):
        return True
    return False


def group_orgs(names):
    """把词条名按「同一机构」归并成若干组，返回组列表"""
    groups = []
    for n in names:
        for g in groups:
            if any(same_org(n, x) for x in g):
                g.append(n)
                break
        else:
            groups.append([n])
    return groups


def claim_is_dept_total(n, ctx):
    """判断 ctx 里的数字 n 是否表示「科室总数」。

    只看数字**紧邻**的上下文，不看整句——否则「设有80个科室，展开床位2763张」
    会因为句中有「床位」二字而被误杀（早期版本按整句关键词判，误杀 8 家真实值）。
    """
    s = str(n)
    for m in re.finditer(r'(?<![0-9])' + re.escape(s) + r'(?![0-9])', ctx):
        after = ctx[m.end():m.end() + 16]
        before = ctx[max(0, m.start() - 12):m.start()]
        if _NOT_TOTAL_AFTER.match(after):
            return False
        if _DEPT_AFTER.match(after):
            return True
        if _DEPT_BEFORE.search(before) and after.startswith('个'):
            return True
    return False


def pick_claim(claims):
    """从候选 claims 里挑最可信的一条：临床+医技合计 > 含医技 > 其它（同级取大）"""
    if not claims:
        return None
    def rank(c):
        ctx = c['ctx']
        if '临床、医技' in ctx or '临床和医技' in ctx:
            return 0
        return 1 if '医技' in ctx else 2
    return sorted(claims, key=lambda c: (rank(c), -c['n']))[0]


def main():
    rows = list(csv.DictReader(open(MASTER, encoding='utf-8-sig')))
    # 源口径 dept_count 基准：取最近一次构建的快照（与 MySQL ads_inst_search 一致）
    old_by_id = {}
    try:
        snap = json.load(open('web/snapshot_data.json', encoding='utf-8'))
        old_by_id = {r['id']: (r.get('dept_count') or 0) for r in snap['institutions']}
    except Exception as e:
        print('⚠️ 快照读取失败，源口径对比将按 0 处理：', e)
    by_name = {r['name']: r for r in rows}
    by_norm = {}
    for r in rows:
        by_norm.setdefault(norm(r['name']), r)

    # 本脚本专属别名（词条名 → 主表名），不改公共 ALIAS
    EXTRA_ALIAS = {
        '中国人民解放军总医院': '中国人民解放军总医院(301医院)',
        '北京市延庆区医院': '北京市延庆区医院（北京大学第三医院延庆医院）',
        '北京市中关村医院': '北京市中关村医院（中国科学院中关村医院）',
    }

    def resolve(name):
        n = EXTRA_ALIAS.get(name.strip(), ALIAS.get(name.strip(), name.strip()))
        return by_name.get(n) or by_norm.get(norm(n))

    recs = [json.loads(l) for l in open(JSONL, encoding='utf-8')]

    # ---------- 质检一：模板污染检测 ----------
    # 同一句 ctx 被多个**不同机构**命中 → 百科模板文字（或搜索串了词条），整条作废
    ctx_names = defaultdict(set)
    for rec in recs:
        if not rec.get('found'):
            continue
        for c in (rec.get('claims') or []):
            ctx_names[c['ctx']].add(rec['query'])
    template_ctx, template_detail = set(), []
    for ctx, names in ctx_names.items():
        groups = group_orgs(names)
        if len(groups) >= TEMPLATE_MIN_ORGS:
            template_ctx.add(ctx)
            template_detail.append((ctx, len(groups), sorted(names)[:3]))
    template_detail.sort(key=lambda x: -x[1])

    # ---------- 质检二：口径筛选 + 选值 ----------
    upd, unmatched, smaller, rejected = {}, [], [], []
    hit_claim = hit_table = 0
    for rec in recs:
        if not rec.get('found'):
            continue
        claims = rec.get('claims') or []
        online, src = None, None
        if claims:
            good = [c for c in claims
                    if c['ctx'] not in template_ctx and claim_is_dept_total(c['n'], c['ctx'])]
            for c in claims:
                if c in good:
                    continue
                rejected.append((rec['query'], c['n'], c['ctx'][:60],
                                 '模板污染' if c['ctx'] in template_ctx else '非科室总数'))
            pick = pick_claim(good)
            if pick:
                online = pick['n']
                src = 'baike_claim'
        if not online and rec.get('table_count'):
            online = int(rec['table_count'])
            src = 'baike_table'
        if not online:
            continue
        r = resolve(rec['query'])
        if not r:
            unmatched.append(rec['query'])
            continue
        old_n = int(old_by_id.get(r['id']) or 0)
        # 同一机构多词条（主名+分院区变体）时取更大值
        if r['id'] in upd and upd[r['id']]['n'] >= online:
            continue
        # ⚠️ 不能因为 online == old_n 就 continue：写回时 upd 里没有的机构会被清空，
        # 而「在线值没变」的恰恰是最稳定的那批，第二次执行就会把它们误删（原脚本的坑）。
        if online < old_n:
            smaller.append((r['name'], old_n, online, src))
        upd[r['id']] = {'n': online, 'src': src}
        if src == 'baike_claim':
            hit_claim += 1
        else:
            hit_table += 1

    # 写回主表（新增两列，幂等）
    hdr = list(rows[0].keys())
    for c in ('dept_count_online', 'dept_count_src'):
        if c not in hdr:
            hdr.append(c)
    for r in rows:
        u = upd.get(r['id'])
        r['dept_count_online'] = str(u['n']) if u else ''
        r['dept_count_src'] = u['src'] if u else ''
    with open(MASTER, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        w.writerows(rows)

        bigger = sum(1 for r in rows if r.get('dept_count_online'))
        with open(REPORT, 'w', encoding='utf-8') as f:
            f.write('# 科室数量在线核实报告（百度百科「主要科室/科室设置」，官网口径转述优先）\n\n')
            f.write('- 抓取词条 %d，成功解析在线值 %d（声明口径 %d + 科室表计数 %d）\n' %
                    (len(recs), len(upd), hit_claim, hit_table))
            f.write('- 主表新增列：dept_count_online / dept_count_src；ADS 层 dept_count = COALESCE(online, 源条目数)\n')
            f.write('- 未匹配词条 %d 个：%s\n\n' % (len(unmatched), unmatched[:20]))

            f.write('## 质检：模板污染（同一句被 ≥%d 家不同机构命中，整条作废）\n\n'
                    % TEMPLATE_MIN_ORGS)
            if template_detail:
                f.write('| 涉及机构数 | 原句 | 样例机构 |\n|---|---|---|\n')
                for ctx, n, sample in template_detail:
                    f.write('| %d | %s | %s |\n' % (n, ctx.replace('|', '/'), '、'.join(sample)))
            else:
                f.write('（无）\n')
            f.write('\n共作废 %d 条 claim，涉及 %d 家机构。\n\n'
                    % (sum(1 for r in rejected if r[3] == '模板污染'),
                       len({r[0] for r in rejected if r[3] == '模板污染'})))

            f.write('## 质检：非科室总数的表述（已剔除）\n\n')
            f.write('| 词条 | 数字 | 原句 | 判定 |\n|---|---|---|---|\n')
            for q, n, ctx, why in rejected[:40]:
                f.write('| %s | %d | %s | %s |\n' % (q, n, ctx.replace('|', '/'), why))
            f.write('\n共剔除 %d 条。\n\n' % len(rejected))

            f.write('## 覆盖后变小的案例（人工复核）\n\n')
            f.write('| 医院 | 源口径 | 在线核实 | 来源 |\n|---|---|---|---|\n')
            for n, o, v, s in sorted(smaller, key=lambda x: x[1] - x[2])[:40]:
                f.write('| %s | %d | %d | %s |\n' % (n, o, v, s))
            f.write('\n## 头部机构对照（top 修正幅度）\n\n| 医院 | 源口径 | 在线核实 | 来源 |\n|---|---|---|---|\n')
            delta = []
            for r in rows:
                if r.get('dept_count_online'):
                    old_n = int(old_by_id.get(r['id']) or 0)
                    delta.append((int(r['dept_count_online']) - old_n, r['name'], old_n,
                                  r['dept_count_online'], r['dept_count_src']))
            for d, n, o, v, s in sorted(delta, reverse=True)[:30]:
                f.write('| %s | %d | %s | %s |\n' % (n, o, v, s))
    print('updated=%d (claim=%d table=%d) unmatched=%d smaller=%d' %
          (len(upd), hit_claim, hit_table, len(unmatched), len(smaller)))


if __name__ == '__main__':
    main()
