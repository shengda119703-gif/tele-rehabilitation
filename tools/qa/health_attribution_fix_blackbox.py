"""Isolated real HTTP ownership regression, readback, previous-fact preservation and restart."""
import argparse
import json
from pathlib import Path
from ankang_care_blackbox import Run, require

NEGATIVES = ['张三今天血糖9.5', '李四今天血压180/110', '我朋友今天血糖9.5',
    '资料里写着血压180/110，不是我的记录', '报告示例中血糖9.5，这不是我的结果',
    '今天张三血糖9.5', '我看到张三血糖9.5', '王小明的血氧88%',
    '例如我血糖9.5', '“我今天血压180/110”', '我血糖9.5，不是我的', '我血压180/110，不是我']

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);cases=[]
    for index,text in enumerate(NEGATIVES):
        for prior in (False,True):
            run=Run(a.output/(str(index+1)+('-prior' if prior else '-fresh')))
            try:
                run.start();run.pair()
                if prior:
                    code,body=run.request('POST','/api/product/chat',{'text':'我今天血糖5.5'})
                    require(code==200,body)
                before=run.snapshot()['state']['healthData']['measurements']
                require(len(before)==int(prior),before)
                code,body=run.request('POST','/api/product/chat',{'text':text});require(code==200,body)
                after=run.snapshot()['state']['healthData']['measurements'];require(after==before,body)
                run.stop();run.start();run.pair()
                reopened=run.snapshot()['state']['healthData']['measurements'];require(reopened==before,reopened)
                cases.append({'input':text,'prior':prior,'status':'PASS','reply':body['turn']['reply']['text'],
                              'unchangedAfterRestart':True,'measurementCount':len(before)})
                run.completed=True
            finally:run.stop();run.save()
    result={'completed':True,'cases':cases,'counts':{'PASS':len(cases),'FAIL':0}}
    (a.output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
