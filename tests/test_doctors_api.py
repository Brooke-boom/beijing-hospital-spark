"""python tests/test_doctors_api.py; local Flask client, no database required."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
import doctors
from app import app

assert len(doctors.search({})[0]) == len(doctors.load_directory()[0]['doctors'])
with app.test_client() as client:
    for path, count in [('/api/doctors', len(doctors.load_directory()[0]['doctors'])), ('/api/doctors?hospital=1498&department=泌尿外科', 3),
                        ('/api/inst/1547/doctors', 4), ('/api/inst/1303/doctors', len(doctors.search({'hospital':'1303'})[0]))]:
        response = client.get(path)
        assert response.status_code == 200
        assert response.json['total'] == count
        assert response.json['booking_url'] == 'https://www.114yygh.com/'
    assert client.get('/api/inst/not-found/doctors').status_code == 404
    assert client.get('/api/doctors?page=bad').status_code == 400
    page = client.get('/api/doctors?page_size=2&page=2').json
    assert len(page['items']) == 2 and page['total'] == len(doctors.load_directory()[0]['doctors'])
print('PASS 医生数据完整性、API过滤、分页、院区关联、空结果和无效参数')

rows=doctors.coverage()
assert len(rows)==180 and sum(x["grade"]=="三甲" for x in rows)==101
assert sum(x["doctor_count"]>0 for x in rows)>=14
assert not any(x["completeness"]=="complete" for x in rows)
assert len(doctors.search({"hospital":"1403","department":"心内科"})[0])==1

with app.test_client() as client:
    coverage_response=client.get('/api/doctors/coverage')
    assert coverage_response.status_code==200
    body=coverage_response.json
    assert body['target_records']==180
    assert body['missing_records']+body['records_with_doctors']==180
    assert {r['institution_id'] for r in body['items']}=={str(h['id']) for h in doctors.load_directory()[1].values() if h['level']=='三级'}
    for h in body['items']:
        response=client.get('/api/inst/'+h['institution_id']+'/doctors')
        assert response.status_code==200
        assert response.json['total']==h['doctor_count']
print('PASS 全部180条三级机构医生入口与覆盖状态逐项一致')
