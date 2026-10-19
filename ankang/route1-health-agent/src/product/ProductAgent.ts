/** Model plans are untrusted. This registry is the complete executable boundary. */
import {canUseModuleTools} from '../runtime/operationalIntent';
export const agentModules=['home','rehab','fitness','health','medication','family','assistant','history','settings','notifications'] as const;
export interface AgentCall {name:string;arguments:Record<string,unknown>}
export interface AgentTool {
  name:string;description:string;mode:'read'|'navigation';available:boolean;
  run(now:Date):Promise<{reply:string;data?:unknown}>;
}
export interface ProductAgentModel {
  select(text:string,tools:{name:string;description:string;parameters:unknown}[]):Promise<AgentCall[]>;
}
export interface AgentResult {reply:string;steps:{name:string;status:'succeeded'|'failed';reply:string;data?:unknown}[];navigation?:string;modelError?:boolean}
const empty={type:'object',properties:{},additionalProperties:false};
export class ProductAgent {
  constructor(private tools:AgentTool[],private model?:ProductAgentModel){}
  catalogue(){return [...this.tools.map(({name,description,mode,available})=>({name,description,mode,available})),
    {name:'open_module',description:'打开已有页面；摄像头、训练、分享与删除仍需在原页面确认',mode:'navigation',available:true}];}
  async replyToText(text:string,now:Date,check:()=>void):Promise<AgentResult|null>{
    if(!canUseModuleTools(text))return null;
    text=text.trim().replace(/[。！？?!]+$/,'');
    let calls:AgentCall[]=[],modelError=false;
    // Local commands remain usable offline. Writes belong exclusively to CareCoordinator.
    const query=/查看|看看|查询|有哪些|列出|状态|情况|记录|资料|安排|任务|功能|能力|怎么|我的|最近|能做什么|下一步|下一项/.test(text);
    const select=(name:string,pattern:RegExp)=>{if(query&&pattern.test(text))calls.push({name,arguments:{}});};
    select('health_overview',/健康(?:记录|数据|概况)|血压|血糖|身体档案/);
    select('body_overview',/身体汇总/);
    select('medication_list',/药(?:物|品|单|清单)|用药(?:清单|安排)/);
    select('archive_list',/资料|附件|报告文件/);
    select('family_status',/家庭(?:绑定|共享|状态|权限)|家属(?:绑定|权限)/);
    select('notification_list',/通知|提醒(?:状态|记录)/);
    select('extension_status',/设备|语音|同步|HealthKit|连接状态/);
    select('agent_capabilities',/功能|能力|能做什么/);
    select('rehab_plan',/训练计划|康复计划/);
    select('rehab_assessments',/评估结果|最近.*评估/);
    select('rehab_history',/(?:训练|康复)(?:记录|历史)/);
    select('daily_overview',/今天.*(?:安排|任务|做什么)|今日安排/);
    select('rehab_next',/(?:康复|训练).*(?:下一步|下一项)|(?:下一步|下一项).*(?:康复|训练)/);
    const modules:Record<string,string>={'首页':'home','康复':'rehab','康复计划':'rehab','健身':'fitness','健康':'health','用药':'medication','家庭':'family','管家':'assistant','记录':'history','设置':'settings','通知':'notifications'};
    // Those legacy tools do not have a dedicated product page; explain the real entry.
    if(/^(?:请|帮我)?(?:打开|进入|切到)(体态|居家)(?:页|页面|模块)?$/.test(text))
      return {reply:'体态与居家工具保留在康复模块的原工作台，请进入康复页后选择对应工具。',steps:[]};
    const open=text.match(/^(?:请|帮我)?(?:打开|进入|切到)(首页|康复(?:计划)?|健身|健康|用药|家庭|管家|记录|设置|通知)(?:页|页面|模块)?$/);
    if(open)calls=[{name:'open_module',arguments:{module:modules[open[1]]}}];
    calls=calls.filter(c=>c.name==='open_module'||this.tools.some(t=>t.name===c.name&&t.available));
    if(!calls.length&&this.model){
      try{
        calls=await this.model.select(text,[...this.tools.filter(t=>t.available).map(t=>({name:t.name,description:t.description,parameters:empty})),
          {name:'open_module',description:'用户明确要求打开模块时导航，不开始任务或采集',parameters:{type:'object',properties:{module:{type:'string',enum:agentModules}},required:['module'],additionalProperties:false}}]);
      }catch{modelError=true;}
      check();
    }
    if(!Array.isArray(calls)||calls.length>6)throw Error('管家工具计划无效，请缩小查询范围');
    if(!calls.length)return modelError?{reply:'联网理解暂时不可用。可以使用“查看健康记录”“查看药物清单”“查看资料”或直接打开模块。',steps:[],modelError}:null;
    // Validate the WHOLE plan before invoking a host, even for reads.
    const seen=new Set<string>();
    for(const c of calls){
      if(!c||typeof c.name!=='string'||!c.arguments||typeof c.arguments!=='object'||Array.isArray(c.arguments)||seen.has(c.name))throw Error('管家工具计划含重复或无效操作');
      seen.add(c.name);
      if(c.name==='open_module'){
        if(Object.keys(c.arguments).length!==1||!agentModules.includes(c.arguments.module as any)||!/打开|进入|切到/.test(text))throw Error('管家导航目标或导航意图无效');
      }else if(!this.tools.some(t=>t.name===c.name&&t.available)||Object.keys(c.arguments).length)throw Error('管家请求了未开放的工具或字段');
    }
    const result:AgentResult={reply:'',steps:[]};
    for(const c of calls){
      check();
      if(c.name==='open_module'){result.navigation=String(c.arguments.module);result.steps.push({name:c.name,status:'succeeded',reply:'已准备打开所选模块；请在页面继续操作。'});continue;}
      try{const value=await this.tools.find(t=>t.name===c.name)!.run(now);check();result.steps.push({name:c.name,status:'succeeded',...value});}
      catch{check();result.steps.push({name:c.name,status:'failed',reply:'该模块读取失败，请刷新或在原页面核对。'});}
    }
    // Facts are rendered by trusted adapters; generated prose cannot invent an execution receipt.
    result.reply=result.steps.map(s=>s.reply).join('\n\n');return result;
  }
}
