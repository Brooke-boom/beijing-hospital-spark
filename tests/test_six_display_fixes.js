const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const snapshot=JSON.parse(fs.readFileSync('web/snapshot_data.json','utf8'));
const nodes=new Map(),node=id=>nodes.get(id)||(nodes.set(id,{innerHTML:'',value:'',textContent:'',style:{},addEventListener(){},querySelector(){return null},querySelectorAll(){return[]}}),nodes.get(id));
const c={console,setTimeout(){},clearTimeout(){},URLSearchParams,Blob,URL,location:{protocol:'file:',hostname:'',port:'',hash:''},document:{readyState:'loading',addEventListener(){},getElementById:node,querySelectorAll(){return[]}},localStorage:{getItem(){return null}},navigator:{},matchMedia(){return{matches:false}},snapshot};c.window=c;vm.createContext(c);
vm.runInContext(fs.readFileSync(process.env.APP_SOURCE||'web/app.js','utf8'),c);vm.runInContext('DATA=snapshot;FILTERED=DATA.institutions;',c);
const run=s=>vm.runInContext(s,c),r=snapshot.institutions.find(x=>x.id==='1150');c.row=r;
assert.equal(run('currentSpecialtyCoverage()'),90);assert.equal(run('specialtyMetrics(row).national.length'),40);assert.equal(run('specialtyMetrics(row).municipal.length'),7);assert.equal(run('specialtyMetrics(row).entries'),47);assert.equal(run('currentSpecialtyCount(row)'),41);assert.equal(run('specialtyMetrics(row).mappings.length'),24);assert.equal(run('specialtyMetrics(row).legacy'),36);assert.equal(run('specialtyMetrics({id:"1150"}).mappings.length'),24);
assert.match(run('specialtyHTML(row)'),/名单名称去重 41/);assert.match(run('specialtyHTML(row)'),/跨层级重复名称 6/);assert.match(run('specialtyHTML(row)'),/36/);assert.equal(run('clinicalNames(row.feature).length'),36);
assert.equal(run('clinicalNames("骨科；眼科;骨科、内科").length'),3);assert.equal(run('clinicalNames("骨科（创伤；关节）；眼科").length'),2);
assert.equal(run('phoneNumbers(row.phone).length'),3);assert.equal(run('phoneNumbers(row.phone)[1].dial'),'01069155564');const phones=run('phoneLinksHTML(row.phone)');assert.equal((phones.match(/href="tel:/g)||[]).length,3);assert.equal((phones.match(/data-phone-copy=/g)||[]).length,3);assert.ok(!/tel:[^"]*\//.test(phones));assert.equal(run('phoneNumbers("010-12345678转123")[0].dial'),'01012345678;ext=123');assert.ok(!run('phoneLinksHTML("<script>bad</script>")').includes('<script>'));
const local=run('localCompareRow(row)');assert.equal(local.key_specialty_count,41);assert.equal(local.legacy_specialty_count,36);
c.unknown={id:'none',name:'未收录样例',networks_text:'未纳入',national_specialty:'',municipal_specialty:''};const unknown=run('apiCompareRow(unknown)');assert.equal(unknown.networks_text,'未收录／未核实');assert.equal(unknown.key_specialty_count,null);assert.equal(unknown.national_specialty_count,null);
run('renderIntegration()'); // source page and about must use the same definition
assert.match(node('integration_results').innerHTML,/90/);run('loadAbout()');assert.match(node('ab_counts').innerHTML,/90/);
console.log('PASS 专科覆盖统一90、40/7/47/41/24/36口径、中文分隔符、分机和三号码独立链接、缺失不作0或未纳入、两页面指标一致');

c.payload={id:r.id,contact:{},links:{},around:{},around_enabled:false,specialty:{national:r.national_specialty.split(';'),municipal:r.municipal_specialty.split(';'),feature:[r.feature]}};run('DW_CUR=row;paintDrawerFull(payload)');assert.match(node('pane-spec').innerHTML,/映射 24 类/);assert.match(node('pane-spec').innerHTML,/历史专科汇总字段：36/);console.log('PASS 在线详情二次渲染保留机构ID、24类映射及历史36字段');
