from datetime import datetime, timedelta, timezone

from app.runtime import Runtime
from app.storage import Storage
from test_automatic_plans import SCOPE, measured
from test_training_runtime import response


def test_runtime_reads_saved_assessment_no_camera_no_mutation(tmp_path):
    now = datetime.now(timezone.utc)
    store = Storage(tmp_path/'home_rehab.sqlite3')
    store.save_session(measured(start_utc=(now-timedelta(minutes=2)).isoformat(),
                                end_utc=(now-timedelta(minutes=1)).isoformat()))
    store.close()
    runtime = Runtime(tmp_path)
    try:
        assert runtime.ready.wait(5)
        messages = response(runtime, 'rehab_agent', scope=SCOPE, text='今天练什么', request_id='turn-1')
        assert not [m for m in messages if m['kind'] == 'error']
        m = next(m for m in messages if m['kind'] == 'rehab_agent')
        assert m['request_id'] == 'turn-1' and m['result']['evidence']
        assert runtime.camera.worker is None
        runtime.controller.state = 'SAVE_FAILED'
        messages = response(runtime, 'rehab_agent', scope=SCOPE, text='继续', request_id='blocked')
        error = next(m for m in messages if m['kind'] == 'error')
        assert error['request_id'] == 'blocked' and '保存' in error['text']
        runtime.controller.state = 'UNSELECTED'
    finally:
        response(runtime, 'shutdown')
        runtime.thread.join(5)
        assert not runtime.thread.is_alive()
    store = Storage(tmp_path/'home_rehab.sqlite3')
    try:
        assert len(store.list_sessions()) == 1
        assert not store.list_training_plans(SCOPE)
    finally:
        store.close()
