const assert=require('node:assert/strict'), fs=require('node:fs'),vm=require('node:vm');
const directory=JSON.parse(fs.readFileSync('web/doctors_data.json','utf8'));
const snapshot=JSON.parse(fs.readFileSync('web/snapshot_data.json','utf8'));
const ctx={window:null,DATA:snapshot,__DOCTORS__:directory,document:{readyState:'loading',addEventListener(){}},URL,URLSearchParams,location:{hash:""},Date,console};ctx.window=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync('web/app.doctors.js','utf8'),ctx);
const d=ctx.Doctors;
assert.equal(d.filter().length,directory.doctors.filter(x=>x.status==='published').length);
assert.equal(d.filter({hospital:'1150',department:'心血管内科'}).length,4);
assert.equal(d.filter({hospital:'1498',department:'泌尿外科',district:'海淀区'}).length,3);
assert.equal(d.filter({hospital:'1498',district:'东城区'}).length,0);
assert.equal(d.filter({hospital:'1547',district:'西城区'}).length,4);
assert.ok(d.filter({hospital:'1303'}).length>0); // Independently sourced Yanqing records, never copied from Peking University Third Hospital.
assert.equal(d.filter({name:'张洪宪'}).length,1);
assert.equal(d.filter({name:'<img>'}).length,0);
for(const q of ['北京协和医院有哪些心内科医生','协和的心血管内科医生','中国医学科学院北京协和医院有哪些心内科医生']){const c=d.parseQuestion(q);assert.equal(c.hospital,'1150');assert.equal(c.department,'心内科');assert.equal(d.filter(c).length,4);}
assert.ok(d.filter(d.parseQuestion('海淀区有哪些心内科医生')).every(x=>snapshot.institutions.find(h=>h.id===x.institution_id).district==='海淀区'));
assert.equal(d.parseQuestion('北医三院有哪些泌尿外科医生').department,'泌尿外科');
assert.equal(d.parseQuestion('不存在的医院有哪些心内科医生').unknownHospital,true);
assert.equal(d.parseQuestion('我胸口疼，推荐医生'),null);
assert.equal(d.parseQuestion('海淀区三级医院'),null);
assert.equal(d.filter(d.parseQuestion('北京协和医院有哪些神经内科医生')).length,0);
assert.match(d.answer('北京协和医院有哪些神经内科医生'),/没有匹配资料/);
assert.ok(!d.answer('未知医院有哪些医生').includes('刘震宇'));
for(const row of directory.doctors){assert.ok(d.source(row).startsWith('https://'));assert.ok(!('schedule' in row));assert.ok(!('slots' in row));}
assert.equal(d.source({source_url:'javascript:alert(1)'}),'');
console.log('PASS 医生过滤、科室同义词、医院及院区别名、未覆盖医院、未知科室、诊断边界与来源链接');
assert.equal(d.parseQuestion('北医三院延庆医院有哪些医生').hospital,'1303');

assert.ok(d.filter({grade:"三甲"}).every(x=>snapshot.institutions.find(h=>h.id===x.institution_id).level_sub==="甲等"));
assert.equal(d.filter({hospital:"1403",department:"心内科"}).length,1);

const targets=snapshot.institutions.filter(h=>h.level==='三级');
assert.equal(targets.length,180);
assert.equal(d.coverageRows().length,180);
assert.deepEqual(Array.from(d.coverageRows(),h=>h.institution_id).sort(),targets.map(h=>String(h.id)).sort());
assert.ok(d.coverageRows().some(h=>h.category==='社区卫生服务中心'));
console.log('PASS 找医生目标与三级查询180条逐ID一致，保留原始机构类型');

assert.ok(d.filter({hospital:'1524',department:'高压氧治疗科'}).some(x=>x.name==='王培福'));
assert.ok(d.filter({hospital:'1303'}).every(x=>x.institution_id==='1303'));
assert.equal(d.parseQuestion('延庆区医院有哪些心内科医生').hospital,'1303');

assert.equal(d.filter({hospital:'1474',department:'三区'}).length,0);
assert.ok(d.filter({hospital:'1474',department:'冠心病外科中心一区、三区'}).length>0);

assert.match(d.entryLabel('1476'),/待补录/);assert.match(d.entryLabel('1498'),/已收录/);console.log('PASS 医生入口按真实收录状态区分');
