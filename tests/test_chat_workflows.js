const {fixture}=require('./helpers/chat_fixture.js');
(async()=>{await fixture('concurrent');await fixture('failure');console.log('PASS 连续提问、回复乱序、清空后迟到回复、断网回退与结果联动');})().catch(e=>{console.error(e);process.exitCode=1;});
