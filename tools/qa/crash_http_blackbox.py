"""Kill only our exact owned TEST process tree during real HTTP confirmations.

Delay windows are external timing, never proof of a particular SQL instruction.
All expected facts/receipts are read back through HTTP after a new lifecycle.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import json
from pathlib import Path
import time
import psutil
from ankang_care_blackbox import Run, require

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();run=Run(a.output)
    def kill_owned():
        parent=psutil.Process(run.process.pid)
        owned=parent.children(recursive=True)+[parent]
        metadata=[{'pid':x.pid,'name':x.name(),'createdAt':x.create_time()} for x in owned]
        for process in reversed(owned):
            try:process.kill()
            except psutil.NoSuchProcess:pass
        gone,alive=psutil.wait_procs(owned,timeout=5)
        require(not alive,{'alive':[p.pid for p in alive]})
        run.process.wait(timeout=5)
        return metadata
    try:
        run.start();run.pair();run.medicine()
        clocks=[f'08:{n:02d}' for n in range(9)]
        run.post('daily.medSchedule',dict(medId='TEST-med-A',times=clocks,start=date.today().isoformat(),end=''))
        for index,delay in enumerate([0,10,100]*3):
            clock=clocks[index]
            def check(clock=clock,delay=delay):
                pending=run.prepare([run.dose(clock)])
                payload=dict(id=pending['id'],confirmationToken=pending['confirmationToken'],confirmed=True)
                before=len(run.daily()['doseAudit'])
                def confirm():
                    try:
                        r=run.client.post('/api/unified/care.confirm',json=payload)
                        return {'httpStatus':r.status_code,'body':r.json()}
                    except Exception as error:return {'transportError':type(error).__name__}
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future=pool.submit(confirm);time.sleep(delay/1000)
                    owned=kill_owned();first=future.result(timeout=35)
                run.stop();run.start();run.pair()
                state=run.post('care.status',{'id':pending['id']})['status']
                final=run.confirm(pending)
                require(final['status']=='succeeded',final)
                require(len(run.daily()['doseAudit'])==before+1)
                require(run.confirm(pending)['status']=='succeeded')
                require(len(run.daily()['doseAudit'])==before+1)
                run.stop();run.start();run.pair()
                require(len(run.daily()['doseAudit'])==before+1)
                require(run.post('care.status',{'id':pending['id']})['status']=='succeeded')
                return {'delayMs':delay,'ownedProcesses':owned,'firstResponse':first,'recoveredState':state,
                        'auditDeltaAfterRetryAndSecondReopen':1}
            run.case('真实确认进程树崩溃 '+str(index+1)+' 延迟'+str(delay)+'ms',
                     '可查询/重试；唯一服药审计；二次重开保留',check)
        run.completed=True
    except Exception as error:run.fatal_error=repr(error);raise
    finally:
        run.stop();result=run.save();print(json.dumps({'completed':run.completed,'counts':result['counts']},ensure_ascii=False))
    return int(result['counts']['FAIL']>0)

if __name__=='__main__':raise SystemExit(main())
