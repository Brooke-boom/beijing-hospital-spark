"""Read-only regression tests: Flask SQL against deterministic SQLite fixtures,
and the offline JS engine against the same records. No real database required."""
import json
import math
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'web'))
import app as webapp
import nlq

class FilteringTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        for name, fn, n in [('RADIANS', math.radians, 1), ('SIN', math.sin, 1),
                            ('COS', math.cos, 1), ('ASIN', math.asin, 1),
                            ('SQRT', math.sqrt, 1), ('POWER', pow, 2), ('LEAST', min, 2)]:
            self.db.create_function(name, n, fn)
        snap = json.loads((ROOT / 'web/snapshot_data.json').read_text())['institutions'][0]
        self.rows = []
        for i, (lv, sub, precision, lng, src) in enumerate([
            ('三级', '甲等', 'high', 116.397428, 'online'),
            ('三级', '乙等', 'high', 116.397428, 'rule'),
            ('三级', '', 'rough', 116.397428, 'name'),
            ('二级', '乙等', 'high', 116.397428, 'key_depts'),
            ('三级', '甲等', 'high', 117.4, 'specialty'),
            ('三级', '甲等', 'missing', None, 'online'),
        ], 1):
            r = {**snap, 'id': str(i), 'name': f'测试医院{i}', 'district': '朝阳区',
                 'level': lv, 'level_sub': sub, 'coord_precision': precision,
                 'lng': lng, 'lat': 39.90923 if lng is not None else None,
                 'depts': '骨科', 'recorded_depts': '骨科' if src not in ('rule', 'name') else ''}
            r.update(level_norm=lv, category_norm='医院', category='医院', dept_count_src=src)
            self.rows.append(r)
        cols = list(self.rows[0])
        self.db.execute('CREATE TABLE ads_inst_search (' + ','.join('"'+c+'"' for c in cols) + ')')
        for r in self.rows:
            vals = [r[c] if not isinstance(r[c], (dict, list)) else json.dumps(r[c]) for c in cols]
            self.db.execute('INSERT INTO ads_inst_search VALUES ('+','.join('?' for c in cols)+')', vals)
        self.db.execute('CREATE TABLE dwd_dept_relation_clean (hospital_id, dept_name, source)')
        self.db.executemany('INSERT INTO dwd_dept_relation_clean VALUES (?, ?, ?)',
                            [(str(i), '骨科', src) for i, src in enumerate(['online','rule','name','key_depts','specialty','online'], 1)])
        self.client = webapp.app.test_client()
        self.mock = patch.object(webapp, 'query', self.query)
        self.mock.start()

    def tearDown(self):
        self.mock.stop()
        self.db.close()

    def query(self, sql, args=None, one=False):
        rows = [dict(r) for r in self.db.execute(sql.replace('%s', '?'), args or [])]
        return rows[0] if one and rows else (None if one else rows)

    def test_grade_preserves_sublevel_and_excludes_missing(self):
        result = nlq.run_filter(self.query, nlq.parse('三甲医院')['conditions'])
        self.assertEqual({r['id'] for r in result['items']}, {'1', '5', '6'})
        self.assertNotIn('kw', nlq.parse('三级甲等医院')['conditions'])
        self.assertEqual(nlq.parse('三甲')['conditions'], {'grades':['三级甲等']})
        pairs = nlq.run_filter(self.query, nlq.parse('三甲和二乙医院')['conditions'])
        self.assertEqual({r['id'] for r in pairs['items']}, {'1', '4', '5', '6'})

    def test_manual_natural_language_radius_and_evidence_agree(self):
        manual = self.client.get('/api/institutions?level=三甲&radius=5&dept=骨科&dept_evidence=recorded').get_json()
        automatic = nlq.run_filter(self.query, {'grades':['三级甲等'], 'radius':5, 'dept':'骨科', 'dept_evidence':'recorded'})
        self.assertEqual(manual['total'], 1)
        self.assertEqual(manual['total'], automatic['total'])
        self.assertEqual(manual['items'][0]['id'], automatic['items'][0]['id'])
        self.assertEqual(manual['items'][0]['score'], 1)

    def test_radius_excludes_rough_missing_and_far(self):
        result = nlq.run_filter(self.query, {'radius': 5})
        self.assertEqual({r['id'] for r in result['items']}, {'1', '2', '4'})
        stats = nlq.run_stats(self.query, {'radius':5}, 'district')
        self.assertEqual(stats['rows'][0]['cnt'], result['total'])

    def test_evidence_excludes_name_and_rule(self):
        result = nlq.run_filter(self.query, {'dept':'骨科','dept_evidence':'recorded'})
        self.assertEqual({r['id'] for r in result['items']}, {'1','4','5','6'})

    def test_evidence_without_dept_still_filters(self):
        """dept_evidence=recorded 未指定科室时也必须过滤，否则控件形同虚设。"""
        result = nlq.run_filter(self.query, {'dept_evidence':'recorded'}, page_size=100)
        self.assertEqual({r['id'] for r in result['items']}, {'1','4','5','6'})
        manual = self.client.get('/api/institutions?dept_evidence=recorded').get_json()
        self.assertEqual(manual['total'], 4)
        self.assertEqual(manual['total'], result['total'])

    def test_nl_parses_evidence_and_radius(self):
        """自然语言入口：「有来源记录」「N 公里/米内」必须落成结构化条件，且不漏进 kw。"""
        c = nlq.parse('东城区有来源记录的儿科医院', dept_names=['儿科'])['conditions']
        self.assertEqual(c.get('dept_evidence'), 'recorded')
        self.assertEqual(c.get('dept'), '儿科')
        self.assertNotIn('kw', c)
        c2 = nlq.parse('天安门5公里内的三甲医院')['conditions']
        self.assertEqual(c2.get('radius'), 5.0)
        self.assertEqual(c2.get('grades'), ['三级甲等'])
        self.assertNotIn('kw', c2)
        c3 = nlq.parse('1000米内的医院')['conditions']
        self.assertEqual(c3.get('radius'), 1.0)
        self.assertNotIn('kw', c3)

    def test_invalid_input_is_rejected(self):
        for qs in ['radius=nan', 'radius=0', 'radius=-1', 'radius=201', 'lng=nan&lat=40', 'lng=181&lat=40', 'lng=116', 'lng=oops&lat=40']:
            self.assertEqual(self.client.get('/api/institutions?'+qs).status_code, 400, qs)
        self.assertEqual(self.client.post('/api/nlq/query', json={'conditions':{'radius':5},'lng':'nan','lat':40}).status_code, 400)

    def test_sql_placeholders_match_for_source_statistics(self):
        calls=[]
        nlq.run_stats(lambda sql,args: calls.append((sql,args)) or [], {'district':['朝阳区'],'radius':5}, 'source')
        sql,args = calls[0]
        self.assertEqual(sql.count('%s'),len(args))

    def test_offline_matches_real_sql_and_fails_closed_on_old_evidence(self):
        cases=[{'grades':['三级甲等']}, {'grades':['三级甲等','二级乙等']}, {'radius':5}, {'dept':'骨科','dept_evidence':'recorded'}, {'dept_evidence':'recorded'}]
        script = """const {NLQ}=require('./web/app.nlq.js');const fs=require('fs');NLQ.init(JSON.parse(fs.readFileSync('web/nlq_lexicon.json')).lex);let x=JSON.parse(fs.readFileSync(0,'utf8'));let results=x.cases.map(c=>NLQ.runFilter(x.rows,c,1,100).items.map(r=>r.id));let old=x.rows.map(r=>{delete r.recorded_depts;return r});let rejected=NLQ.runFilter(old,{dept_evidence:'recorded'}).unsupported; console.log(JSON.stringify({results,rejected}));"""
        result=json.loads(subprocess.check_output(['node','-e',script], input=json.dumps({'rows':self.rows,'cases':cases}).encode(),cwd=ROOT))
        for cond, ids in zip(cases, result['results']):
            actual=nlq.run_filter(self.query,cond,page_size=100)
            self.assertEqual(set(ids),{r['id'] for r in actual['items']})
        self.assertEqual(result['rejected'],'dept')

if __name__ == '__main__':
    unittest.main()
