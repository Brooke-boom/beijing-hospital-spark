#!/usr/bin/env python3
"""Report the complete target institution set; linked directories never count as doctor data."""
import csv
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'web'))
from doctors import coverage, load_directory

rows = coverage()
rows.sort(key=lambda r: (r['district'], r['name']))
meta, _ = load_directory()
matched = {r['inst_id']: r for r in csv.DictReader((ROOT/'data/processed/haodf_match.csv').open(encoding='utf-8-sig'))}
for row in rows:
    old = matched.get(row['institution_id'])
    row['historical_department_directory'] = 'https://www.haodf.com/hospital/'+old['hid']+'/keshi/list.html' if old else ''
    row['directory_note'] = '历史科室来源候选，不作为医生资料或本次核验依据' if old else ''
summary = dict(target_records=len(rows), tertiary_a_records=sum(r['grade']=='三甲' for r in rows),
               records_with_partial_doctors=sum(r['doctor_count']>0 for r in rows),
               missing_records=sum(r['doctor_count']==0 for r in rows), complete_records=0,
               doctor_records=sum(d['status']=='published' for d in meta['doctors']),
               distinct_doctor_hospital_ids=len({d['institution_id'] for d in meta['doctors'] if d['status']=='published'}),
               scope='当前2026-10-18快照中的全部三级机构记录（与机构查询180条口径一致），含院区和旧称；非最新独立医院数量，非全市在岗医师总数')
out=ROOT/'data/processed/doctor_coverage';out.mkdir(exist_ok=True)
(out/'coverage.json').write_text(json.dumps(dict(summary=summary,items=rows),ensure_ascii=False,indent=2))
with (out/'coverage.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(ROOT/'docs/三级医院医生覆盖核查.md').write_text(f'''# 三级机构医生覆盖核查

版本：v6.12-all-tertiary-20261019。覆盖目标与机构查询仅选“三级”的结果逐ID一致，全部180条纳入，不再仅限医院/妇幼保健两类。

- 目标机构记录：{summary['target_records']} 条，其中三甲 {summary['tertiary_a_records']} 条。
- 已有部分医生资料：{summary['records_with_partial_doctors']} 条目标机构记录。
- 医生资料：{summary['doctor_records']} 条，关联 {summary['distinct_doctor_hospital_ids']} 个医院ID；同一医生跨科室可能有独立记录，不能当作去重人数。
- 待补录：{summary['missing_records']} 条机构记录。
- 全科室完整医生名单：尚无一家标为全量覆盖。

当前180条包含医院、妇幼保健、社区卫生服务中心、急救中心等类型，以及院区和旧称。本轮保留原快照类型和等级，未重新认定等级、未将180条当作180家独立且仍运营的三级医院。医院级资料关联明确的同院院区，但不确认个人具体出诊院区；不同附属医院不自动共用医生资料。

## 本轮补录

新增北京市延庆区医院107条、航天中心医院91条、北京同仁医院3条，共201条。延庆从官网156个个人介绍链接取得107条有明确医师职称和科室的记录；航天从目录中的首批100个链接取得91条。失败请求、护士/药师/技师和缺少必要字段的记录不发布。未收录专业方向标明“专业方向未收录”。本轮不将以上两家医院标为全量完成。

同仁3条来自北京市卫健委2025-01-09发布、明确署名“来源：北京同仁医院”的官方介绍，来源名称和原发布日期保留，不伪称当日发布。其东院区、南区记录仅关联医院级名单，具体出诊院区以114为准。

逐条来源和核验日期见web/doctors_data.json；核实批次保存在data/processed/doctor_coverage/reviewed_*_batch.jsonl。原始网页证据保存在本次工作目录official_evidence，不随独立页面复制网站脚本。覆盖清单见coverage.csv和coverage.json；仅有官网链接或挂号入口不算医生数据覆盖。

## 尚未完成

剩余{summary['missing_records']}条仍待逐院取得可靠名录。部分官网出现418、超时、证书链错误，未绕过验证或关闭证书校验。原快照中的旧称、重复院区和非医院类型还需进一步核对，不能依靠相似名称批量移植医生记录。预约始终使用北京114。
''')
print(json.dumps(summary,ensure_ascii=False))
