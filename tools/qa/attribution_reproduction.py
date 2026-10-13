"""Fresh database for every attribution counterexample; public HTTP only."""
import argparse
import json
from pathlib import Path
from ankang_care_blackbox import Run,require

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);cases=[]
    for index,text in enumerate(['张三今天血糖9.5','李四今天血压180/110',
             '资料里写着血压180/110，不是我的记录',
             '报告示例中血糖9.5，这不是我的结果',
             '我朋友今天血糖9.5']):
        run=Run(a.output/str(index+1))
        try:
            run.start();run.pair()
            before=run.snapshot()['state']['healthData']['measurements'];require(before==[])
            code,body=run.request('POST','/api/product/chat',{'text':text});require(code==200,body)
            after=run.snapshot()['state']['healthData']['measurements']
            reply=body['turn']['reply']['text']
            run.stop();run.start();run.pair()
            reopened=run.snapshot()['state']['healthData']['measurements']
            persisted=after==reopened
            cases.append({'input':text,'freshBeforeCount':0,'added':after,'reopened':reopened,
                          'persisted':persisted,'reply':reply,'status':'PASS' if not after else 'FAIL'})
            run.completed=True
        finally:run.stop();run.save()
    result={'completed':True,'scope':'fresh isolated TEST database per utterance; real HTTP, restart/readback',
            'cases':cases,'counts':{s:sum(c['status']==s for c in cases) for s in ('PASS','FAIL')}}
    (a.output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return int(result['counts']['FAIL']>0)

if __name__=='__main__':raise SystemExit(main())
