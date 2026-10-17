import type {ChatMessage} from '../types';

export interface ConversationModel {
  reply(input:{messages:{role:'user'|'assistant';content:string}[];purpose?:'understanding'|'reply'}):Promise<string>;
}

/** Operations outside the registered host grammar must never become invented receipts. */
export function isOperationalConversation(text:string) {
  return /(?:查看|看看|读取|查询|查一下|列出|搜索|打开|进入|切到|记录|保存|修改|更改|删除|删掉|清除|清空|导出|分享|发送|授权|确认|取消|启动|开启|关闭|关掉|开始|停止|安排|调度|改期|改到|设置|绑定|连接).{0,40}(?:健康|血压|血糖|血氧|心率|资料|档案|药|服用|训练|健身|康复|家属|家庭|通知|附件|文件|记录|摄像|相机|录像|页面|网页|首页|管家|设置|模块|数据|权限|备份|计划|报告|待办|日程|任务)/.test(text)
    || /(?:健康|药|训练|康复|家属|通知|摄像|相机|录像|网页|文件|档案|资料|数据|计划|报告).{0,30}(?:记录|保存|修改|删除|删掉|删|清除|清空|导出|分享|发送|授权|启动|开启|关闭|关掉|开始|停止|改期|改到|安排|绑定|连接)/.test(text)
    || /(?:血压|血糖|血氧|心率|药物|药单|健康记录|训练记录|康复记录|健康数据).{0,20}(?:多少|有哪些|怎么样|如何|什么|情况)/.test(text)
    || /(?:健康记录|训练记录|康复记录|药物清单|药单|病历|健康数据|资料|档案)(?:呢|吗|有何|有哪些)/.test(text)
    || /(?:给|发|告诉).{0,20}(?:家属|家庭|儿子|女儿|爸爸|妈妈)/.test(text)
    || /(?:有没有|刚才|之前|到底|究竟).{0,30}(?:分享|告诉|发送|同步|通知).{0,20}(?:家属|家庭|孩子|儿子|女儿)/.test(text)
    || /^(?:请|帮我|我要|我想)?(?:确认|取消|重试)(?:执行|操作|待办|任务)?[。！!\s]*$/.test(text);
}

export function conversationMessages(chat:ChatMessage[],text:string,sessionId:string,context:string) {
  // Only host-marked ordinary pairs leave the device. Old/private/health/tool
  // replies are intentionally absent even if their text contains no privacy words.
  const messages:{role:'user'|'assistant';content:string}[]=[];
  let budget=10000-text.length;
  for(let i=chat.length-2;i>=0;i-=2){
    const user=chat[i],reply=chat[i+1];
    if(user.role!=='elder'||reply.role!=='agent'||user.persisted===false||reply.persisted===false||
      !user.id.startsWith(sessionId+':')||!reply.id.startsWith(sessionId+':')||
      user.conversationContext!==context||reply.conversationContext!==context||
      user.conversation?.status!=='replied'||reply.conversation?.provider!=='deepseek'||reply.conversation?.status!=='replied')continue;
    const cost=user.text.length+reply.text.length;
    if(cost>budget||messages.length>=12)break;
    budget-=cost;messages.unshift({role:'user',content:user.text},{role:'assistant',content:reply.text});
  }
  messages.push({role:'user',content:text});
  return messages;
}

export function localConversation(text:string) {
  if(/(?:对象|恋人|男朋友|女朋友|喜欢我|爱我)/.test(text))return '我可以作为 AI 陪你聊天、听你说心事，也帮你处理康复相关的事情。你想聊聊最近的生活，还是有什么心事？';
  if(/你好|嗨|hello|早上好|晚上好/i.test(text))return '你好，我是安康康复管家。你可以和我聊天，也可以让我查看已有记录、打开页面或核对待办。';
  return '我在听。你可以再说具体一点；已有记录查询和页面操作也可以直接告诉我。';
}
