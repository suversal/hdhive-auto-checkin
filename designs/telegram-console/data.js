const DEMO_NOW = new Date('2026-11-09T10:42:00+08:00');
const EMPTY_TASK = {name:'',accountId:'a1',kind:'message',target:'',targetName:'',targetType:'bot',steps:[{type:'send',text:''},{type:'wait',seconds:60}],schedule:'daily',time:'08:30',timezone:'Asia/Shanghai',weekdays:[1,2,3,4,5],interval:24,once:'2026-11-10T08:30',cron:'30 8 * * *',jitter:0,notify:'failure',successWords:'',failureWords:'',enabled:true};
const TEMPLATES = [
 {id:'text',name:'机器人文字签到',category:'签到',icon:'bot',color:'',desc:'每天给机器人发一句签到指令，收到回复后留档。',tag:'最适合第一次使用',message:'/checkin',steps:[{type:'send',text:'/checkin'},{type:'wait',seconds:60}]},
 {id:'button',name:'带按钮的签到',category:'签到',icon:'click',color:'blue',desc:'先发指令，再点击回复中的签到按钮，按顺序完成。',tag:'2 分钟配置',message:'/start',steps:[{type:'send',text:'/start'},{type:'wait',seconds:60},{type:'click',text:'每日签到'},{type:'wait',seconds:60}]},
 {id:'remind',name:'群组定时提醒',category:'提醒',icon:'users',color:'amber',desc:'把固定的提醒按时发到群里，省去每天重复输入。',tag:'只发送，不等回复',message:'新的一天，记得记录今天的进展。',steps:[{type:'send',text:'新的一天，记得记录今天的进展。'}]},
 {id:'query',name:'周期查询',category:'查询',icon:'search',color:'lavender',desc:'定期查询积分、配额或服务状态，集中查看原始返回。',tag:'保留原始回复',message:'/balance',steps:[{type:'send',text:'/balance'},{type:'wait',seconds:60}]},
 {id:'weekly',name:'每周备忘',category:'提醒',icon:'calendar',color:'',desc:'每周固定时间，把需要记住的事情发给自己。',tag:'发送到收藏夹',message:'留一点时间，回顾这一周。',steps:[{type:'send',text:'留一点时间，回顾这一周。'}]},
];
const TARGETS = [
 {id:'@HDHiveBot',name:'HDHive',type:'bot',sub:'机器人 · @HDHiveBot',icon:'bot'},
 {id:'@daily_checkin_demo_bot',name:'每日签到机器人',type:'bot',sub:'机器人 · 示例会话',icon:'bot'},
 {id:'@credits_demo_bot',name:'积分查询助手',type:'bot',sub:'机器人 · 示例会话',icon:'bot'},
 {id:'@daily_notes_demo',name:'日常分享小组',type:'group',sub:'群组 · 示例会话',icon:'users'},
 {id:'me',name:'收藏夹',type:'self',sub:'仅自己可见 · Saved Messages',icon:'book'},
 {id:'@weekly_demo_channel',name:'每周通讯',type:'channel',sub:'频道 · 示例管理员身份',icon:'send'},
];
function initialStore(empty=false){
 const base={version:1,settings:{workspace:'我的工作空间',timezone:'Asia/Shanghai',language:'zh-CN',proxyType:'none',proxyHost:'',proxyPort:'7890',notification:'failure',summaryTime:'21:00',retention:'30',hasApi:!empty},accounts:[],tasks:[],runs:[]};
 if(empty)return base;
 base.accounts=[{id:'a1',name:'我的主账号',phone:'+86 ···· 0216',username:'daily_notes',status:'connected',letter:'S'},{id:'a2',name:'备用账号',phone:'+86 ···· 0839',username:'quiet_days',status:'invalid',letter:'Q'}];
 const task=(id,extra)=>({...structuredClone(EMPTY_TASK),id,...extra});
 base.tasks=[
 task('t1',{name:'HDHive 每日签到',target:'@HDHiveBot',targetName:'HDHive',steps:[{type:'send',text:'赌狗签到'},{type:'wait',seconds:60}],time:'08:30',lastStatus:'replied'}),
 task('t2',{name:'日常分享群提醒',target:'@daily_notes_demo',targetName:'日常分享小组',targetType:'group',steps:[{type:'send',text:'午间休息一下，也别忘了喝水。'}],time:'12:30',lastStatus:'sent'}),
 task('t3',{name:'云盘机器人签到',target:'@daily_checkin_demo_bot',targetName:'每日签到机器人',kind:'buttons',steps:[{type:'send',text:'/start'},{type:'wait',seconds:60},{type:'click',text:'每日签到'},{type:'wait',seconds:60}],time:'09:10',successWords:'签到成功',lastStatus:'success'}),
 task('t4',{name:'晚间积分查询',target:'@credits_demo_bot',targetName:'积分查询助手',steps:[{type:'send',text:'/balance'},{type:'wait',seconds:60}],time:'18:00',lastStatus:'timeout'}),
 task('t5',{name:'周五回顾提醒',target:'me',targetName:'收藏夹',targetType:'self',steps:[{type:'send',text:'留一点时间，回顾这一周。'}],schedule:'weekly',weekdays:[5],time:'18:30',enabled:false,lastStatus:'sent'}),
 task('t6',{name:'备用账号签到',accountId:'a2',target:'@daily_checkin_demo_bot',targetName:'每日签到机器人',steps:[{type:'send',text:'/checkin'},{type:'wait',seconds:60}],time:'09:00',enabled:false,lastStatus:'error'}),
 ];
 base.runs=[
 {id:'r1',taskId:'t4',taskName:'晚间积分查询',accountId:'a1',target:'@credits_demo_bot',at:'2026-11-09T10:00:00+08:00',status:'timeout',duration:'60.0 秒',message:'/balance',reply:'等待 60 秒后，仍未收到可确认的回复。',sent:true},
 {id:'r2',taskId:'t3',taskName:'云盘机器人签到',accountId:'a1',target:'@daily_checkin_demo_bot',at:'2026-11-09T09:10:00+08:00',status:'success',duration:'3.2 秒',message:'/start → 每日签到',reply:'签到成功，获得 5 积分。',sent:true},
 {id:'r3',taskId:'t1',taskName:'HDHive 每日签到',accountId:'a1',target:'@HDHiveBot',at:'2026-11-09T08:30:00+08:00',status:'replied',duration:'1.8 秒',message:'赌狗签到',reply:'签到成功！今日获得 8 积分，当前积分 128。',sent:true},
 {id:'r4',taskId:'t2',taskName:'日常分享群提醒',accountId:'a1',target:'@daily_notes_demo',at:'2026-11-09T08:00:00+08:00',status:'sent',duration:'0.6 秒',message:'早上好，记得为今天留一点自己的时间。',reply:'消息已发送。本任务无需等待回复。',sent:true},
 {id:'r5',taskId:'t1',taskName:'HDHive 每日签到',accountId:'a1',target:'@HDHiveBot',at:'2026-11-08T08:30:00+08:00',status:'replied',duration:'2.1 秒',message:'赌狗签到',reply:'你已经签到过了，明天再来吧。',sent:true},
 ];return base;
}
const STATUS={success:{text:'规则匹配成功',type:'',icon:'check'},replied:{text:'已收到回复',type:'blue',icon:'message'},sent:{text:'已发送',type:'',icon:'check'},timeout:{text:'等待回复超时',type:'warn',icon:'clock'},failed:{text:'规则匹配失败',type:'danger',icon:'alert'},error:{text:'执行异常',type:'danger',icon:'alert'},running:{text:'执行中',type:'blue',icon:'loader'},paused:{text:'已暂停',type:'neutral',icon:'pause'},cancelled:{text:'已取消',type:'neutral',icon:'close'}};
function uid(prefix='id'){return prefix+'-'+Date.now().toString(36)+'-'+Math.random().toString(36).slice(2,6);}
function scheduleLabel(t){return t.schedule==='daily'?`每天 ${t.time}`:t.schedule==='weekly'?`每周${t.weekdays.map(x=>'日一二三四五六'[x]).join('、')} ${t.time}`:t.schedule==='interval'?`每 ${t.interval} 小时`:t.schedule==='once'?`仅一次 · ${t.once.replace('T',' ')}`:`Cron · ${t.cron}`;}
function formatAt(iso,short=false,tz='Asia/Shanghai'){return new Intl.DateTimeFormat('zh-CN',{timeZone:tz,month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false,...(short?{}:{year:'numeric'})}).format(new Date(iso));}
function getNextRuns(t,count=3){
 const offset={'Asia/Shanghai':480,'Asia/Hong_Kong':480,'Asia/Tokyo':540,UTC:0}[t.timezone]??480;
 const now=DEMO_NOW.getTime(), out=[];
 if(t.schedule==='interval'){const h=Math.max(1,Number(t.interval)||24);return Array.from({length:count},(_,i)=>new Date(now+h*3600000*(i+1)));}
 if(t.schedule==='once'){const d=new Date(t.once+':00'+(offset===0?'Z':offset===540?'+09:00':'+08:00'));return d.getTime()>now?[d]:[];}
 const cronMatch=(value,field,min,max)=>{if(!field)return false;return field.split(',').some(part=>{const [range,stepRaw]=part.split('/');const step=Number(stepRaw||1);if(!Number.isInteger(step)||step<1)return false;let lo=min,hi=max;if(range!=='*'){const vals=range.split('-').map(Number);lo=vals[0];hi=vals.length>1?vals[1]:lo;}return Number.isInteger(lo)&&Number.isInteger(hi)&&lo>=min&&hi<=max&&value>=lo&&value<=hi&&(value-lo)%step===0;});};
 const fields=t.cron.trim().split(/\s+/);
 for(let ms=Math.floor(now/60000)*60000+60000;ms<now+15*86400000&&out.length<count;ms+=60000){const local=new Date(ms+offset*60000),h=local.getUTCHours(),m=local.getUTCMinutes(),day=local.getUTCDay();let match=false;
 if(t.schedule==='cron'&&fields.length===5){const dom=cronMatch(local.getUTCDate(),fields[2],1,31),dow=cronMatch(day,fields[4],0,6);match=cronMatch(m,fields[0],0,59)&&cronMatch(h,fields[1],0,23)&&cronMatch(local.getUTCMonth()+1,fields[3],1,12)&&(fields[2]!=='*'&&fields[4]!=='*'?(dom||dow):(dom&&dow));}
 else {const [th,tm]=(t.time||'08:30').split(':').map(Number);match=h===th&&m===tm&&(t.schedule!=='weekly'||t.weekdays.includes(day));}
 if(match)out.push(new Date(ms));}return out;
}
function exportJSON(data,name){const a=document.createElement('a'),url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
