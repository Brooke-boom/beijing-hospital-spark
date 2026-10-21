const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[2],'utf8');
const code=source.slice(source.indexOf('function renderAnalysisEvidence('),source.indexOf('function setAnalysisDetail('));
const data=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));let box={};
const context={$:()=>box,DATA:data,num:n=>n.toLocaleString(),esc:s=>String(s).replace(/[<>&]/g,'_')};vm.createContext(context);vm.runInContext(code,context);
const split=x=>String(x||'').split(';').filter(Boolean),member=(r,i)=>i===0?['核心','成员'].includes(r.net_pediatric):i===1?r.net_stroke==='1':r[i===2?'net_neonatal':'net_maternal']==='市级';
function draw(rows,topic){box={};context.$=()=>box;context.renderAnalysisEvidence(rows,[...new Set(rows.map(r=>r.district))].map(name=>({name})),topic,member,split);return box.innerHTML||box.textContent;}
assert(draw(data.institutions,'region').includes('180'));
assert(draw(data.institutions.filter(r=>r.district==='海淀区'),'region').includes('28'));
assert(draw(data.institutions,'evidence').includes('772'));
assert(draw(data.institutions,'network').includes('24.72%'));
assert(draw([],'network').includes('为空'));
assert(!draw(data.institutions.filter(r=>r.level==='一级'),'region').includes('并列最多'));
console.log('6 evidence-chain checks passed');
