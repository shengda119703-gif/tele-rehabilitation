/** Care execution coordinates existing services; it never supplies a prescription or training dose. */
import { createTurnQueue } from '../engine/turnQueue';
import type { MedicationRecord } from '../types';
import { parsePrivacyIntent } from '../engine/privacy';
import { understandElderInput } from '../engine/understanding';

export interface CareFacts {
  scope: {participant_id:string;source_kind:string;usage_context:string};
  medications: MedicationRecord[];
  daily: {medSchedules:Record<string,any>;doses:Record<string,any>;schedules:any[]};
  plans: any[];
  history: any[];
}
export interface CareAction {
  operation:'daily.dose'|'daily.schedule';
  payload:Record<string,any>;
  expected:unknown;
  label:string;
}
export interface CareReceipt {
  status:'succeeded';idempotencyKey:string;operation:string;[key:string]:unknown;
}
export interface CarePort {
  read():Promise<CareFacts>;
  /** Host must check its durable receipt BEFORE the expected-state check, atomically with its business write. */
  execute(action:CareAction,idempotencyKey:string,expiresAt:string):Promise<CareReceipt>;
}
export interface CareStorage {read<T>(key:string):T|null;write(key:string,value:unknown):void;}
export interface CareStep {action:CareAction;status:'pending'|'executing'|'succeeded'|'failed';receipt?:CareReceipt;error?:string;}
export interface CareWorkflow {
  id:string;requestId:string;requestSignature:string;scope:CareFacts['scope'];
  status:'needs_clarification'|'awaiting_confirmation'|'executing'|'succeeded'|'failed'|'partially_succeeded'|'cancelled'|'expired';
  createdAt:string;expiresAt:string;approvedAt?:string;confirmationToken?:string;steps:CareStep[];reply:string;
}
type Registry={version:1;workflows:CareWorkflow[]};
export function canonical(value:any):string {
  if(value===undefined)return 'null';
  if(value===null||typeof value!=='object')return JSON.stringify(value);
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  return '{'+Object.keys(value).sort().filter(k=>value[k]!==undefined).map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
}
const clone=<T>(v:T):T=>structuredClone(v);
export function localDay(now:Date):string {
  if(!Number.isFinite(now.getTime()))throw Error('无效时间');
  return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
}
function validDay(day:unknown):day is string {
  return typeof day==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(day)&&Number.isFinite(Date.parse(day+'T12:00:00Z'))&&new Date(day+'T12:00:00Z').toISOString().slice(0,10)===day;
}
const validTime=(v:unknown):v is string=>typeof v==='string'&&/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(v);
function exact(value:any,keys:string[]) {
  if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!keys.includes(k)))throw Error('操作含未知字段');
}
function factsCheck(f:CareFacts):CareFacts {
  if(!f?.scope||!['participant_id','source_kind','usage_context'].every(k=>typeof (f.scope as any)[k]==='string'&&(f.scope as any)[k])
    ||!Array.isArray(f.medications)||!f.daily?.medSchedules||!f.daily.doses||!Array.isArray(f.daily.schedules)||!Array.isArray(f.plans)||!Array.isArray(f.history))throw Error('照护事实接口无效');
  return clone(f);
}
export function actionEvidence(f:CareFacts,a:Pick<CareAction,'operation'|'payload'>):unknown {
  if(a.operation==='daily.dose'){
    const p=a.payload;
    return {medicine:f.medications.find(m=>m.id===p.medId)??null,schedule:f.daily.medSchedules[p.medId]??null,
      dose:f.daily.doses[p.medId+'|'+p.date+'|'+p.time]??null};
  }
  const schedule=f.daily.schedules.find(s=>s.id===a.payload.id)??null;
  const p=schedule?.planId?f.plans.find(p=>p.id===schedule.planId):null;
  return {schedule,plan:p?{id:p.id,revision:p.revision}:null};
}

/** Finite local commands; ambiguous drug/day/time/arrangement is a clarification, not a guessed action. */
export function isCareText(text:string):boolean {
  return /今天.*(?:安排|任务|做什么)|今日安排|(?:康复|训练).*(?:下一步|下一项)|(?:下一步|下一项).*(?:康复|训练)|(?:训练|康复).*(?:改到|改为|挪到|调整到)|(?:药|服用).*(?:吃了|已服用|记一下)|(?:记录|登记|记下).*药/.test(text);
}
function statedDay(text:string,now:Date):string|undefined {
  const days=new Set(text.match(/\d{4}-\d{2}-\d{2}/g)??[]);
  if(text.includes('今天'))days.add(localDay(now));
  if(text.includes('明天')){const next=new Date(now);next.setDate(next.getDate()+1);days.add(localDay(next));}
  return days.size===1?[...days][0]:undefined;
}
function statedTime(text:string):string|undefined {
  const clocks=[...text.matchAll(/(?<!\d)(\d{1,2}:\d{2})(?!\d)/g)];
  const times=[...text.matchAll(/([零一二两三四五六七八九十\d]{1,3})点(半)?/g)];
  if(clocks.length+times.length!==1)return;
  if(clocks.length){
    let [hour,minute]=clocks[0][1].split(':').map(Number);
    if((hour===12&&/晚上/.test(text))||(hour===0&&/晚上|下午|中午/.test(text)))return;
    if(hour<3&&/中午/.test(text))hour+=12;
    if(hour<12&&/下午|晚上/.test(text))hour+=12;
    if(hour===12&&/凌晨/.test(text))hour=0;
    return `${String(hour).padStart(2,'0')}:${String(minute).padStart(2,'0')}`;
  }
  const m=times[0];
  // Unsupported minute phrases must never be truncated to the hour.
  if(/^[零一二两三四五六七八九十\d刻]/.test(text.slice(m.index!+m[0].length)))return;
  const cn:Record<string,number>={零:0,一:1,二:2,两:2,三:3,四:4,五:5,六:6,七:7,八:8,九:9,十:10,十一:11,十二:12};
  let hour=/^\d+$/.test(m[1])?Number(m[1]):cn[m[1]];
  if(hour===undefined||hour>23)return;
  if((hour===12&&/晚上/.test(text))||(hour===0&&/晚上|下午|中午/.test(text)))return; // Midnight needs an explicit calendar date and 00:00.
  if(hour<3&&/中午/.test(text))hour+=12;
  if(hour<12&&/(下午|晚上)/.test(text))hour+=12;
  else if(hour<=12&&!/(上午|早上|凌晨|中午|下午|晚上)/.test(text))return;
  if(hour===12&&/(凌晨)/.test(text))hour=0;
  return `${String(hour).padStart(2,'0')}:${m[2]?'30':'00'}`;
}
function textIntents(text:string,f:CareFacts,now:Date):{intents:any[];clarification?:string} {
  // Symptom understanding does not classify every operational utterance. Guard direct API text too.
  const controlText=f.medications.reduce((s,m)=>m.name?s.split(m.name).join('已保存药物'):s,text);
  if(/不|没|未|别|勿|无需|无须|毋|莫|忘|漏|如果|假如|假设|假定|可能|好像|也许|或许|[?？]|吗|是否|能否|会不会|怎么样|举例|例子|比如|例如|引用|他说|她说|[“”「」"]|他|她|家人|妈妈|爸爸|母亲|父亲|爷爷|奶奶|外公|外婆|儿子|女儿|哥哥|姐姐|兄弟|姐妹|老伴|丈夫|妻子|医生|患者|病人|后天|下周|下个月|星期|周[一二三四五六日天]|昨天|前天/.test(controlText))
    return{intents:[],clarification:'请直接说明本人的实际记录或明确要修改的安排；否定、假设、提问、示例和他人情况不会生成执行操作。'};
  const understanding=understandElderInput(text,localDay(now),[]);
  if(understanding.correction||understanding.claims.some(c=>!['self','unknown'].includes(c.subject)||c.status!=='occurred'))
    return{intents:[],clarification:'人物、肯否或确定性需要核对，不能把家人或未发生的情况写入本人记录。'};
  const clauses=text.split(/[，,。；;]|然后|并且/).filter(c=>c.trim());
  const intents:any[]=[];
  for(const clause of clauses){
    if(/(?:训练|康复).*(?:改到|改为|挪到|调整到)/.test(clause)){
      const parts=clause.split(/改到|改为|挪到|调整到/);
      const originalDay=statedDay(parts[0],now),originalTime=statedTime(parts[0]);
      const date=parts.length===2?statedDay(parts[1],now)??originalDay:undefined;
      const time=parts.length===2?statedTime(parts[1]):undefined;
      const schedules=f.daily.schedules.filter(s=>s.kind==='training'&&s.date===originalDay&&(!originalTime||s.time===originalTime));
      const ambiguousTarget=parts.length===2&&/今天|明天|\d{4}-\d{2}-\d{2}/.test(parts[1])&&!statedDay(parts[1],now);
      const ambiguousOriginal=/\d{1,2}:\d{2}|点/.test(parts[0])&&!originalTime;
      if(!originalDay||!date||!time||ambiguousTarget||ambiguousOriginal||schedules.length!==1)return{intents:[],clarification:'请明确原训练的日期、时间，以及要改到的日期、时间；有多项安排时不能替您选择。'};
      intents.push({kind:'reschedule_rehab',scheduleId:schedules[0].id,date,time});
    }else if(/药|服用/.test(clause)){
      if(/没|未|不|忘|漏|如果|假如|可能|好像|妈妈|爸爸|家人|母亲|父亲/.test(clause))return{intents:[],clarification:'请核对这是本人哪一天、哪种药、哪个服药时间的记录，以及已服用、跳过还是未记录。'};
      const medicines=f.medications.filter(m=>clause.includes(m.name));
      const date=statedDay(clause,now)??statedDay(text,now),time=statedTime(clause);
      if(medicines.length!==1||!date||!time||!/(吃了|已服用|已吃|服用了)/.test(clause))return{intents:[],clarification:'请明确药名、日期、原安排中的服药时间和实际状态；例如“记录今天08:00的某药已服用”。'};
      intents.push({kind:'record_dose',medId:medicines[0].id,date,time,status:'taken'});
    }else return{intents:[],clarification:'这句话包含尚未支持的操作，请分别核对服药记录或训练改期的具体内容。'};
  }
  return{intents};
}

export class CareCoordinator {
  private queue=createTurnQueue();
  private key:string;
  constructor(ownerScope:string,private storage:CareStorage,private host:CarePort){this.key='care:'+ownerScope;}
  private registry():Registry {const r=this.storage.read<Registry>(this.key)??{version:1,workflows:[]};if(r.version!==1||!Array.isArray(r.workflows))throw Error('照护任务记录无法读取');return clone(r);}
  private save(registry:Registry){this.storage.write(this.key,clone(registry));}
  async overview(now:Date){
    const f=factsCheck(await this.host.read()),day=localDay(now);
    const doses=f.medications.filter(m=>m.status==='active').flatMap(m=>{
      const s=f.daily.medSchedules[m.id];if(!s||s.start>day||(s.end&&s.end<day))return[];
      return (s.times as string[]).map(time=>({medId:m.id,name:m.name,dose:m.dose,date:day,time,
        status:f.daily.doses[m.id+'|'+day+'|'+time]?.status??'unrecorded'}));
    }).sort((a,b)=>a.time.localeCompare(b.time));
    return {scope:f.scope,date:day,doses,schedules:f.daily.schedules.filter(s=>s.date===day).sort((a,b)=>a.time.localeCompare(b.time)),
      note:'未记录不等于漏服；安排存在不等于训练已完成。'};
  }
  async nextStep(now:Date){
    localDay(now);const f=factsCheck(await this.host.read()),p=f.plans.find(p=>p.progress?.next_key||p.has_next);
    return {scope:f.scope,planId:p?.id??null,revision:p?.revision??null,nextKey:p?.progress?.next_key??null,
      available:p?.next_available===true,reason:p?.progress?.blocked||p?.availability_reason||(p?'下一项尚未取得可执行回执':'没有可继续的已保存计划'),
      history:f.history.slice(0,3)};
  }
  async replyToText(text:string,now:Date,requestId:string):Promise<{reply:string;workflow?:CareWorkflow;data?:unknown}|null>{
    if(!isCareText(text))return null;
    // Family/negation/hypothesis inputs remain in the original understanding and safety paths.
    if(/妈妈|爸爸|家人|母亲|父亲|如果|假如|可能|好像|头晕|胸痛|不舒服|漏服|忘.*药/.test(text))return null;
    if(/今天.*(?:安排|任务|做什么)|今日安排/.test(text)&&!/(改到|改为|挪到|调整到|记录|登记|记下|吃了|已服用)/.test(text)){
      const d=await this.overview(now);
      const items=[...d.doses.map(x=>`${x.time} ${x.name}：${({taken:'已服用',skipped:'已跳过',unrecorded:'未记录'} as any)[x.status]??'状态待核对'}`),
        ...d.schedules.map(x=>`${x.time} ${x.name}（仅为安排）`)];
      return {reply:(items.length?'今天的安排：\n'+items.join('\n'):'今天没有已保存的服药或康复安排。')+'\n'+d.note,data:d};
    }
    if(/(?:康复|训练).*(?:下一步|下一项)|(?:下一步|下一项).*(?:康复|训练)/.test(text)){
      const d=await this.nextStep(now);return{reply:d.available?'已保存计划的下一项目前通过原康复规则核对，请进入康复页核对后开始。':d.reason,data:d};
    }
    const workflow=await this.prepare({requestId,text},now);return{reply:workflow.reply,workflow};
  }
  prepare(input:any,now:Date):Promise<CareWorkflow>{return this.queue.enqueue(async()=>{
    localDay(now);exact(input,['requestId','intents','text']);
    if(typeof input.requestId!=='string'||!/^[-\w:]{1,160}$/.test(input.requestId))throw Error('请提供有效的请求编号');
    if((input.intents===undefined)===(input.text===undefined))throw Error('请提供结构化需求或原话，不能同时提供');
    if(input.text!==undefined&&(typeof input.text!=='string'||!input.text.trim()||input.text.length>2000))throw Error('请输入简短完整需求');
    if(input.text!==undefined&&parsePrivacyIntent(input.text)!=='none')throw Error('隐私或分享意图不进入照护操作记录，请使用原隐私流程');
    const signature=canonical(input),registry=this.registry(),old=registry.workflows.find(w=>w.requestId===input.requestId);
    const f=factsCheck(await this.host.read());
    if(old){if(old.requestSignature!==signature||canonical(old.scope)!==canonical(f.scope))throw Error('请求编号已用于不同需求或来源');return clone(old);}
    if(registry.workflows.length>=200)throw Error('照护任务记录已满，请先导出核对，不自动删除待处理记录');
    const parsed:{intents:any[];clarification?:string}=input.text!==undefined?textIntents(input.text,f,now):{intents:input.intents};
    if(!Array.isArray(parsed.intents)||(!parsed.clarification&&(parsed.intents.length<1||parsed.intents.length>4)))throw Error('每次支持1至4项明确操作');
    const seen=new Set<string>(),steps:CareStep[]=[];
    for(const i of parsed.intents){
      let action:CareAction;
      if(i.kind==='record_dose'){
        exact(i,['kind','medId','date','time','status']);
        if(typeof i.medId!=='string'||!validDay(i.date)||i.date>localDay(now)||!validTime(i.time)||!['taken','skipped','unrecorded'].includes(i.status))throw Error('请核对药物、已发生的日期、时间和实际状态');
        const medicine=f.medications.find(m=>m.id===i.medId),s=f.daily.medSchedules[i.medId],key=i.medId+'|'+i.date+'|'+i.time;
        if(!medicine||(!f.daily.doses[key]&&(!s||!s.times.includes(i.time)||i.date<s.start||(s.end&&i.date>s.end))))throw Error('该次服药不在已保存的安排中');
        if(seen.has('dose:'+key))throw Error('同一服药记录不能重复提议');seen.add('dose:'+key);
        action={operation:'daily.dose',payload:{medId:i.medId,date:i.date,time:i.time,status:i.status},expected:null,
          label:`${i.date} ${i.time} ${medicine.name} → ${({taken:'已服用',skipped:'已跳过',unrecorded:'未记录'} as any)[i.status]}`};
      }else if(i.kind==='reschedule_rehab'){
        exact(i,['kind','scheduleId','date','time']);
        if(typeof i.scheduleId!=='string'||!validDay(i.date)||i.date<localDay(now)||!validTime(i.time))throw Error('请核对训练安排编号、日期和时间');
        const s=f.daily.schedules.find(s=>s.id===i.scheduleId&&s.kind==='training');
        if(!s||!f.plans.some(p=>p.id===s.planId&&p.revision===s.revision))throw Error('没有同来源的有效计划安排，请刷新核对');
        if(seen.has('schedule:'+s.id))throw Error('同一训练安排不能重复提议');seen.add('schedule:'+s.id);
        action={operation:'daily.schedule',payload:{id:s.id,date:i.date,time:i.time,kind:s.kind,name:s.name,planId:s.planId,revision:s.revision},expected:null,
          label:`${s.name}：${s.date} ${s.time} → ${i.date} ${i.time}（仅改安排）`};
      }else throw Error('该操作没有受限执行工具');
      action.expected=actionEvidence(f,action);steps.push({action,status:'pending'});
    }
    const w:CareWorkflow={id:crypto.randomUUID(),requestId:input.requestId,requestSignature:signature,scope:f.scope,
      status:parsed.clarification?'needs_clarification':'awaiting_confirmation',createdAt:now.toISOString(),expiresAt:new Date(now.getTime()+15*60000).toISOString(),
      ...(steps.length?{confirmationToken:crypto.randomUUID()}:{}),steps,
      reply:parsed.clarification??'以下操作尚未执行，请逐项核对后确认：\n'+steps.map(s=>s.action.label).join('\n')};
    registry.workflows.push(w);this.save(registry);return clone(w);
  });}
  private workflow(registry:Registry,id:string,token?:string){const w=registry.workflows.find(w=>w.id===id);if(!w)throw Error('没有当前用户的照护任务');if(token!==undefined&&(!w.confirmationToken||token!==w.confirmationToken))throw Error('确认凭据无效');return w;}
  status(id:string){const w=this.workflow(this.registry(),id);const publicValue=clone(w);delete publicValue.confirmationToken;delete (publicValue as any).requestSignature;return publicValue;}
  audit(){return this.registry().workflows.map(w=>({id:w.id,requestId:w.requestId,scope:w.scope,status:w.status,
    createdAt:w.createdAt,expiresAt:w.expiresAt,approvedAt:w.approvedAt,
    steps:w.steps.map(s=>({operation:s.action.operation,label:s.action.label,status:s.status,receipt:s.receipt,error:s.error}))}));}
  cancel(id:string,token:string){return this.queue.enqueue(async()=>{const r=this.registry(),w=this.workflow(r,id,token);
    const f=factsCheck(await this.host.read());if(canonical(f.scope)!==canonical(w.scope))throw Error('任务来源或使用情境已变化，请返回原来源核对');
    if(w.approvedAt||w.steps.some(s=>s.status!=='pending'))throw Error('已开始执行的任务不能撤销已发生的事实');w.status='cancelled';w.reply='已取消，未执行操作。';this.save(r);return clone(w);});}
  confirm(id:string,token:string,now:Date):Promise<CareWorkflow>{return this.queue.enqueue(async()=>{
    localDay(now);const r=this.registry(),w=this.workflow(r,id,token);
    if(['cancelled','needs_clarification'].includes(w.status))throw Error('该任务不能执行，请重新提出明确需求');
    const f=factsCheck(await this.host.read());if(canonical(f.scope)!==canonical(w.scope))throw Error('任务来源或使用情境已变化，请返回原来源核对');
    if(w.status==='succeeded'||w.status==='expired')return clone(w);
    if(!w.approvedAt&&now.getTime()>Date.parse(w.expiresAt)){w.status='expired';w.reply='确认已过期，请重新核对当前安排。';this.save(r);return clone(w);}
    w.approvedAt??=now.toISOString();w.status='executing';this.save(r);
    for(let index=0;index<w.steps.length;index++){
      const step=w.steps[index];if(step.status==='succeeded')continue;
      step.status='executing';delete step.error;this.save(r); // Failure here prevents a host write.
      const key=w.id+':'+index;
      try{
        const receipt=await this.host.execute(clone(step.action),key,w.expiresAt);
        if(receipt?.status!=='succeeded'||receipt.idempotencyKey!==key||receipt.operation!==step.action.operation)throw Error('执行回执不完整，请核对实际记录');
        step.status='succeeded';step.receipt=clone(receipt);
      }catch(error){step.status='failed';step.error=String(error);}
      this.save(r); // Host's atomic receipt permits safe replay if this write fails after the business commit.
      if(step.status==='failed')break;
    }
    const completed=w.steps.filter(s=>s.status==='succeeded').length;
    w.status=completed===w.steps.length?'succeeded':completed?'partially_succeeded':'failed';
    w.reply=w.steps.map(s=>`${s.action.label}：${s.status==='succeeded'?'已保存':s.status==='failed'?'失败，请核对后重试':'尚未执行'}`).join('\n');
    this.save(r);return clone(w);
  });}
}
