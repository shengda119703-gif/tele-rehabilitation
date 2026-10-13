"""Real HTTP health language, family consent directions and source isolation."""
import argparse
import json
from pathlib import Path
from ankang_care_blackbox import Run, OWNER, require

OTHER='TEST-blackbox-other'

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run=Run(a.output)
    def product():
        code,body=run.request('GET','/api/product');require(code==200,body);return body['snapshot']
    def actor(owner):run.stop();run.start(owner);run.pair()
    def measurements():return product()['state']['healthData']['measurements']
    def chat(text):
        code,body=run.request('POST','/api/product/chat',{'text':text});require(code==200,body);return body
    try:
        run.start();run.pair()
        for text, expected in [
            ('我今天血压120/80',{'systolic':120,'diastolic':80}),
            ('我今天高压一百二十低压八十',{'systolic':120,'diastolic':80}),
            ('我今天血压 150／90',{'systolic':150,'diastolic':90}),
            ('我今天低压90高压150',{'systolic':150,'diastolic':90}),
            ('我今天高压150',{'systolic':150}),
            ('我今天体重65公斤',{'weight':65}),
            ('我今天血糖5.5',{'bloodGlucose':5.5}),
            ('我今天血氧97%',{'spo2':97}),
            ('我今天静息心率68',{'restingHr':68}),
        ]:
            def positive(text=text,expected=expected):
                before={x['id'] for x in measurements()};answer=chat(text)
                rows=[x for x in measurements() if x['id'] not in before]
                actual={x['metric']:x['value'] for x in rows}
                require(actual==expected,{'actual':actual,'reply':answer.get('turn',{}).get('reply')})
                return actual
            run.case('真实聊天结构化记录 '+text,'精确记录 '+repr(expected),positive)
        for text in [
            '我爸爸今天血压180/110','我朋友今天体重65公斤','张三今天血糖9.5',
            '我看到我爸血压180/110','我觉得他血压180/110','如果我血压180/110怎么办',
            '假设血糖9.5应该怎么办','明天要测血压120/80','我没有测出血压180/110',
            '医生说如果血压180/110就联系他','资料里写着血压180/110，不是我的记录',
            '不要记录：我今天血压180/110','我没让你记录血压180/110',
        ]:
            def negative(text=text):
                before=measurements();answer=chat(text);after=measurements()
                require(after==before,{'added':[x for x in after if x not in before],'reply':answer.get('turn',{}).get('reply')})
                return {'measurementCountUnchanged':len(after)}
            run.case('他人/假设/否定/私密数值不入本人 '+text,'本人指标不变',negative)
        for text in ['查看健康记录','查看药物清单','查看我的资料','查看家庭权限','查看通知记录',
                     '查看连接状态','查看训练计划','查看康复记录','查看身体汇总',
                     '查看健康记录、药物清单和训练计划']:
            def query(text=text):
                before=measurements();answer=chat(text)
                require(measurements()==before)
                turn=answer.get('turn',{});require(turn.get('agent') is not None or turn.get('care') is not None,turn)
                return {'agent':turn.get('agent'),'care':turn.get('care')}
            run.case('真实模块查询 '+text,'真实查询回执且指标不写入',query)
        for text in ['我不查看健康记录','我没让你查看药物清单','张三健康记录有哪些','我朋友今天安排有哪些']:
            def denied(text=text):
                answer=chat(text);turn=answer.get('turn',{})
                require(not turn.get('agent') and not (turn.get('care') or {}).get('data'),turn)
                return {'noModuleRead':True}
            run.case('否定/他人模块读取拒绝 '+text,'不读取模块事实',denied)
        run.case('来源隔离：实时安排不混入录像', '不同来源安排独立',lambda:require(
            run.request('GET','/api/unified?source=REPLAY_FILE')[1]['snapshot']['dailyProduct']['schedules']==[]))
        invite=run.post('daily.familyInvite')['code']
        run.case('自己不能关联自己的邀请码','400',lambda:require(run.request('POST','/api/unified/daily.familyBind',{'code':invite})[0]==400))
        actor(OTHER)
        run.case('另一档案通过真实邀请码关联','200',lambda:run.post('daily.familyBind',{'code':invite}))
        def default_private():
            rows=run.snapshot()['familyMembers'];require(len(rows)==1 and rows[0]['categories']==[],rows)
            require(not rows[0].get('health') and not rows[0].get('rehab'),rows)
            return rows
        run.case('关联后默认不共享','无健康/康复事实',default_private)
        run.case('邀请码不能重复用于新绑定','400',lambda:require(run.request('POST','/api/unified/daily.familyBind',{'code':invite})[0]==400))
        actor(OWNER)
        run.case('反向关联也默认不共享','categories=[]',default_private)
        for categories in (['all'],['chat'],['archives'],['health','unknown']):
            run.case('禁止家庭不支持类别 '+repr(categories),'400',lambda cats=categories:require(run.request('POST','/api/unified/daily.familyGrant',{'member':OTHER,'categories':cats})[0]==400))
        run.case('本人明确只共享健康类别','200',lambda:run.post('daily.familyGrant',{'member':OTHER,'categories':['health']}))
        run.case('授权方向不自动互惠','本人读取对方仍为空',default_private)
        actor(OTHER)
        def granted():
            row=run.snapshot()['familyMembers'][0];require(row['categories']==['health'],row)
            require(not row.get('medication') and not row.get('rehab') and 'chat' not in row and 'attachments' not in row,row)
            return row
        run.case('对方仅能看到本人允许类别','仅health，无聊天/原件',granted)
        run.case('绑定不赋予对方编辑权限','未知写操作404',lambda:require(run.request('POST','/api/unified/profile.save',{'owner':OWNER})[0]==404))
        actor(OWNER)
        run.case('撤销健康类别','200',lambda:run.post('daily.familyGrant',{'member':OTHER,'categories':[]}))
        actor(OTHER)
        run.case('旧关系刷新后权限立即撤销','无获准事实',default_private)
        actor(OWNER)
        run.case('真实解除关联','200',lambda:run.post('daily.familyUnbind',{'member':OTHER}))
        run.case('本人解除后无家庭关系','空数组',lambda:require(run.snapshot()['familyMembers']==[]))
        actor(OTHER)
        run.case('对方重开也无家庭关系','空数组',lambda:require(run.snapshot()['familyMembers']==[]))
        run.completed=True
    except Exception as error:
        run.fatal_error=f'{type(error).__name__}: {error}';raise
    finally:
        run.stop();result=run.save();print(json.dumps({'completed':run.completed,'counts':result['counts']},ensure_ascii=False))
    return int(result['counts']['FAIL']>0)

if __name__=='__main__':raise SystemExit(main())
