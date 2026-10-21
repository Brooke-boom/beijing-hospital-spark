// Actual chat controller and NLQ engine under a deterministic DOM/network model.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {NLQ}=require(process.cwd()+'/web/app.nlq.js');NLQ.init(require(process.cwd()+'/web/nlq_lexicon.json').lex);
class Element{
 constructor(){this.children=[];this.events={};this.attrs={};this.value='';this.disabled=false;this._html='';this.className='';this.textContent='';this.style={};this.clientHeight=300;this.scrollHeight=500;this.scrollTop=200;}
 set innerHTML(s){this._html=s;if(!s)this.children=[];if(s.includes('class="chatwho"')){this.who=new Element();this.body=new Element();this.body._html=s.split('<div class="chatbody">')[1]?.split('</div>')[0]||'';}}
 get innerHTML(){return this._html;}setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k];}
 appendChild(e){this.children.push(e);e.parentNode=this;return e;}
 addEventListener(k,f){(this.events[k]??=[]).push(f);}querySelector(s){return s==='.chatbody'?this.body:s==='.chatwho'?this.who:null;}
 querySelectorAll(){return this.children;}focus(){}click(){if(!this.disabled)(this.events.click||[]).forEach(f=>f({target:this}));}
}
async function fixture(mode){
 const elements=new Map(),get=id=>elements.get(id)||(elements.set(id,new Element()),elements.get(id));
 let modelCalls=0,resolveModel,resolvers=[];
 const c={console,NLQ,DATA:JSON.parse(fs.readFileSync('web/snapshot_data.json','utf8')),ENV:{api:true,backend:true},location:{protocol:'http:'},setTimeout(){},document:{getElementById:get,createElement(){return new Element();}},UX:{request(url){if(url.includes('health'))return Promise.resolve({json:()=>Promise.resolve({ok:true,llm_enabled:true})});modelCalls++;if(mode==='failure')return Promise.reject(new Error('offline'));return new Promise(resolve=>{resolveModel=payload=>resolve({json:()=>Promise.resolve(payload)});resolvers.push(resolveModel);});}},updateFabBadge(){},curBase(){return{name:'天安门',lng:116.397428,lat:39.90923};},useSmartResults(res){c.used=res.total;}};
 c.window=c;vm.createContext(c);vm.runInContext(fs.readFileSync(process.env.CHAT_SOURCE||'web/app.chat.js','utf8'),c);c.__CHAT__.enter();
 const pending=c.__CHAT__.ask('海淀区的三级医院有哪些？');
 const reply=get('ai_log').children.find(x=>x.className==='chatmsg ai');assert.ok(reply,'query result must appear synchronously before model response');assert.match(reply.body.innerHTML,/共命中 28 家/);assert.equal(get('ai_send').disabled,false);assert.equal(get('ai_clear').disabled,false);
 get('ai_in').value='未发送的中文草稿';const key=get('ai_in').events.keydown[0];key({key:'Enter',isComposing:true,preventDefault(){throw Error('IME was intercepted');}});assert.equal(get('ai_in').value,'未发送的中文草稿');
 // 本地结果返回后允许继续发送；输入法组成阶段仍不发送。
 for(let i=0;i<6;i++)await Promise.resolve();
 if(mode==='concurrent'){
 const second=c.__CHAT__.ask('朝阳区的三级医院有哪些？');for(let i=0;i<8;i++)await Promise.resolve();
 assert.equal(get('ai_send').disabled,false);assert.equal(modelCalls,2);let replies=get('ai_log').children.filter(x=>x.className==='chatmsg ai');assert.equal(replies.length,2);assert.match(replies[1].body.innerHTML,/23 家/);
 resolvers[1]({ok:true,reply:'朝阳区23家'});await second;resolvers[0]({ok:true,reply:'海淀区28家'});await pending;
 assert.match(replies[0].body.innerHTML,/海淀区28家/);assert.match(replies[1].body.innerHTML,/朝阳区23家/);
 const third=c.__CHAT__.ask('朝阳区的三级医院有哪些？');for(let i=0;i<8;i++)await Promise.resolve();get('ai_clear').click();const size=get('ai_log').children.length;resolvers[2]({ok:true,reply:'不应恢复的旧回答'});await third;assert.equal(get('ai_log').children.length,size);return;
 }
 if(mode!=='failure')resolveModel({ok:false,reason:'llm_rate_limited'});
 await pending;
 assert.equal(get('ai_log').children.filter(x=>x.className==='chatmsg ai').length,1,'enrichment must update the same reply');assert.equal(get('ai_send').disabled,false);assert.equal(get('ai_clear').disabled,false);assert.match(reply.who.textContent,/本地查询结果/);assert.match(reply.body.innerHTML,/28 家/);
 const action=reply.children.find(x=>x.className==='chat-actions').children[0];action.click();assert.equal(c.used,28);
 if(mode!=='failure'){await c.__CHAT__.ask('海淀区的三级医院有哪些？');assert.equal(modelCalls,1,'cooldown must avoid repeat model calls');}
 if(mode==='limited'){await c.__CHAT__.ask('海淀区和朝阳区的三级医院分别有多少家？');const scopeReply=get('ai_log').children.filter(x=>x.className==='chatmsg ai').at(-1);assert.match(scopeReply.body.innerHTML,/仅医院类型的三级记录/);assert.match(scopeReply.body.innerHTML,/朝阳区 23 家/);assert.match(scopeReply.body.innerHTML,/朝阳区 28 条/);assert.match(scopeReply.body.innerHTML,/机构类型：医院/);await c.__CHAT__.ask('朝阳区三级机构有多少家？');const allReply=get('ai_log').children.filter(x=>x.className==='chatmsg ai').at(-1);assert.match(allReply.body.innerHTML,/28 家/);assert.match(allReply.body.innerHTML,/未限类型/);}
 const before=get('ai_log').children.length;key({key:'Enter',isComposing:true,preventDefault(){throw Error('IME was intercepted');}});assert.equal(get('ai_log').children.length,before);
 await c.__CHAT__.ask('头疼发烧吃什么药');assert.ok(get('ai_log').children.some(x=>x.className==='chatmsg refuse'));assert.equal(get('ai_send').disabled,false);
}
module.exports={fixture};
