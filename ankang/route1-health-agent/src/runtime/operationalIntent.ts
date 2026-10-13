/** Host-side boundary for module reads/navigation, before either local matching or an LLM.
 * This deliberately accepts a finite self/module grammar; an unrecognised subject is not self.
 * Clinical statements, corrections and confirmed writes keep their original runtime paths.
 */
export function canUseModuleTools(input:string):boolean {
  const text=input.trim().replace(/[。！？?!]+$/,'');
  if(!text||/不|没|未|别|勿|无需|无须|禁止|如果|假如|假设|假定|举例|例子|例如|比如|引用|[“”「」"]|撤回|撤销|更正|纠正|删除|清空|取消|改到|改为|挪到|调整到|开始训练|启动相机|导出/.test(text.replace(/有没有/g,'有')))return false;
  if(/(?:他|她|他们|她们)(?:的|今天|最近|数据|记录)|朋友|家人|妈妈|爸爸|母亲|父亲|爷爷|奶奶|外公|外婆|儿子|女儿|哥哥|姐姐|老伴|丈夫|妻子|患者|病人/.test(text))return false;
  if(/你(?:的|今天|最近)|家庭(?:的)?(?:健康|训练|用药|药物|身体)/.test(text))return false;
  // "家属权限" is the current owner's binding state; a relative's health facts
  // require the separate authorized family view, never the self registry.
  if(/家属/.test(text)&&!/家属(?:的)?(?:绑定|权限|状态)/.test(text))return false;
  // Validate the entire clause, not just a self/time prefix. Unknown names in the
  // middle ("今天张三安排有哪些") must not silently resolve to the current owner.
  const words=['请','帮我','帮忙','我','本人','自己','你','今天','今日','最近','下一步','下一项','有','哪些','什么','怎么','能','做','练','功能','能力','想','要','知道','了解','告诉','查看','看看','查','查询','一下','列出','打开','进入','切到','的','和','与','及','还有','以及','已保存','保存','健康','记录','数据','概况','血压','血糖','身体','档案','药物','药品','药单','药清单','用药','药','清单','安排','任务','训练','康复','计划','评估','结果','历史','资料','附件','报告','文件','文档','家庭','家属','绑定','共享','权限','状态','情况','通知','提醒','设备','语音','同步','HealthKit','首页','健身','体态','居家','管家','设置','页面','页','模块','本地','连接','有没有','变化','哪些','所有','目前','现在'];
  words.push('是','可以','最新','然后','汇总');
  words.sort((a,b)=>b.length-a.length);
  const clauses=text.split(/[，,、。；;！？?]/).map(s=>s.replace(/\s/g,''));
  // Greedy token scanning is bounded by input length. An alternation with +
  // would backtrack exponentially on repeated overlapping words and an unknown suffix.
  return clauses.some(Boolean)&&clauses.filter(Boolean).every(s=>{
    let offset=0;
    while(offset<s.length){
      const word=words.find(w=>s.startsWith(w,offset));
      if(!word)return false;
      offset+=word.length;
    }
    return true;
  });
}
