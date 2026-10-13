"""Offscreen native UI QA with fictitious TEST accounts and temporary stores only."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
os.environ['ANKANG_PRODUCT_DISABLE_MODEL']='1'
os.environ['ANKANG_VOICE_DISABLED']='1'
import argparse, sys, tempfile, time
from pathlib import Path
root=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(root/'rehab_codex_single_camera_v2_1'),str(root/'rehab_codex_single_camera_v2_1/tests'),str(root)]
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont,QFontDatabase
from PySide6.QtTest import QTest
from cloud_service.config import Settings
from cloud_service.database import Database
from cloud_service.security import bootstrap_doctor
from cloud_service.app import BASE,create_app
from cloud_service.tests.test_accounts import client as web_client,login
from cloud_service.tests.test_workbench import publish,plan_body
from test_cloud_account import MemoryVault
from test_workbench_clients import LocalHTTP,OWNER,SCOPE
from test_saved_training_plans import assessment
from test_product_window import PassiveRuntime
from app.cloud_account import CloudAccount
from app.storage import Storage
from app.product.backend import ProductBackend
from app.ui.product_window import ProductWindow
from app.ui.cloud_account import CloudAccountDialog

def wait(app,predicate):
 end=time.monotonic()+15
 while not predicate() and time.monotonic()<end:
  app.processEvents();QTest.qWait(20)
 assert predicate(),'TEST Qt rendering timeout'

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('output',type=Path)
out=parser.parse_args().output.resolve()
if root/'.runtime' not in out.parents:
 raise SystemExit('Use a fresh output directory inside the repository .runtime; real data is never used')
out.mkdir(parents=True,exist_ok=False)
app=QApplication.instance() or QApplication([])
for name in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):
 path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
 if path.exists():QFontDatabase.addApplicationFont(str(path))
app.setFont(QFont('Microsoft YaHei UI',10))
with tempfile.TemporaryDirectory(prefix='ankang-TEST-native-qa-',dir=out) as folder:
 local=Path(folder)/'local';db=Database('sqlite:///'+str(Path(folder)/'TEST-server.sqlite3'))
 settings=Settings(db.url,'x'*40,('http://testserver',),'test') if hasattr(db,'url') else Settings('sqlite:///'+str(Path(folder)/'TEST-server.sqlite3'),'x'*40,('http://testserver',),'test')
 db.migrate();bootstrap_doctor(db,settings,'1');server=create_app(settings,db)
 account=CloudAccount(local/'cloud-account',LocalHTTP(server),MemoryVault());account.register('test-native-qa','1');account.login('test-native-qa','1');account.bind(OWNER);account.consent(OWNER,True);account.grant(True)
 doctor=web_client(server);assert login(doctor,'doctor').is_success
 patient=account.session()['patient_id'];account.send(str(uuid4()),'TEST 患者：这是虚构的界面验收消息，本周训练后没有不适。')
 assert doctor.post(BASE+'/patients/'+patient+'/messages',json={'operation_id':str(uuid4()),'text':'TEST 医生：已查看这份测试记录，请先核对本机评估与左右侧，再选择发布方案。'}).is_success
 body=plan_body(title='TEST 医生发布的训练方案');body['items'][0]['settings']['target_angle_deg']=40
 publish(doctor,patient,body)
 store=Storage(local/'home_rehab.sqlite3');now=datetime.now(timezone.utc);store.save_session(assessment(**SCOPE,id='TEST-qa-assessment',start_utc=(now-timedelta(minutes=2)).isoformat(),end_utc=(now-timedelta(minutes=1)).isoformat(),test_fixture=True))
 backend=ProductBackend(local);backend.call('profile.save',OWNER,{'profile':{'name':'TEST 虚构患者','age':35,'conditions':[],'medications':[]}},SCOPE)
 runtime=PassiveRuntime(local);runtime.store=store;window=ProductWindow(runtime=runtime,backend=backend);window.legacy.busy=0;window.show();wait(app,lambda:bool(window.snapshot) and window.pending==0)
 dialog=CloudAccountDialog(local/'cloud-account',OWNER,'TEST 虚构患者',store.list_sessions,window,client=account,rehab_store=store,scope=SCOPE,product_snapshot=lambda:backend.call('snapshot',OWNER,{},SCOPE))
 dialog.confirm.setChecked(True);dialog.show();dialog.resize(920,880)
 for mode in ('light','dark'):
  window.product_theme.apply(mode)
  for view,work in (('chat',account.messages),('plans',account.plans)):
   dialog.run(work,'TEST 隔离虚构账号 · 本图仅用于界面验收','messages' if view=='chat' else 'plans');wait(app,lambda:dialog.future is None);app.processEvents();QTest.qWait(100)
   assert dialog.grab().save(str(out/(mode+'-'+view+'.png')))
 dialog.close();window.legacy._allow_close=True;window.close();app.processEvents();store.close();db.engine.dispose()
print('TEST native screenshots:',out)
