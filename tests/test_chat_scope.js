const {fixture}=require('./helpers/chat_fixture.js');
fixture('limited').then(()=>console.log('PASS 医院类型23与全部三级28的口径、限流冷却、IME和拒答')).catch(e=>{console.error(e);process.exitCode=1;});
