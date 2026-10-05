import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from mobile_rehab.jsonio import read_json, write_json
from mobile_rehab.replay_status import replay_ended
from mobile_rehab.server import Jobs


def test_read_lock_is_retried_and_optional_progress_can_be_omitted(tmp_path, monkeypatch):
    path = tmp_path/'progress.json'
    write_json(path, {'processed_frames': 3})
    original = Path.read_text
    calls=[]
    def flaky(self, **kw):
        calls.append(1)
        if len(calls) < 3:
            raise PermissionError('sharing lock')
        return original(self, **kw)
    monkeypatch.setattr(Path, 'read_text', flaky)
    monkeypatch.setattr('mobile_rehab.jsonio.time.sleep', lambda _: None)
    assert json.loads(read_json(path)) == {'processed_frames': 3}
    assert len(calls) == 3
    monkeypatch.setattr(Path, 'read_text', lambda *a, **kw: (_ for _ in ()).throw(PermissionError()))
    assert read_json(path, optional=True) is None
    with pytest.raises(PermissionError):
        read_json(path)


def test_atomic_write_retries_without_losing_previous_value(tmp_path, monkeypatch):
    path=tmp_path/'result.json'
    write_json(path, {'old': True})
    original=Path.replace
    calls=[]
    def flaky(self, target):
        calls.append(1)
        if len(calls)<3:
            raise PermissionError('sharing lock')
        return original(self,target)
    monkeypatch.setattr(Path,'replace',flaky)
    monkeypatch.setattr('mobile_rehab.jsonio.time.sleep', lambda _: None)
    write_json(path, {'new': True})
    assert json.loads(path.read_text()) == {'new': True}
    assert not list(tmp_path.glob('*.tmp'))
    monkeypatch.setattr(Path,'replace',lambda *a: (_ for _ in ()).throw(PermissionError()))
    with pytest.raises(PermissionError):
        write_json(path, {'must_not_claim_saved': True})
    assert json.loads(path.read_text()) == {'new': True}
    assert not list(tmp_path.glob('*.tmp'))


def test_progress_lock_does_not_break_job_polling(tmp_path, monkeypatch):
    jobs=Jobs(tmp_path, runner=lambda item: None)
    try:
        item=jobs.reserve('a'*32,'shoulder_abduction','left')
        folder=jobs.folder(item)
        write_json(folder/'progress.json', {'processed_frames': 9})
        original=Path.read_text
        def locked(self, **kw):
            if self.name=='progress.json':
                raise PermissionError('sharing lock')
            return original(self,**kw)
        monkeypatch.setattr(Path,'read_text',locked)
        monkeypatch.setattr('mobile_rehab.jsonio.time.sleep', lambda _: None)
        public=jobs.public(item)
        assert public['state']=='uploading' and 'progress' not in public
        write_json(folder/'result.json', {'summary': {'completed': 1}})
        jobs.update(item['id'],state='done')
        assert jobs.public(jobs.get(item['id'],item['owner']))['result']['summary']['completed']==1
    finally:
        jobs.close()


def test_result_lock_returns_retryable_status_not_fake_completion(tmp_path, monkeypatch):
    jobs=Jobs(tmp_path,runner=lambda item: None)
    try:
        item=jobs.reserve('a'*32,'shoulder_abduction','left')
        write_json(jobs.folder(item)/'result.json', {'summary': {'completed': 1}})
        jobs.update(item['id'],state='done')
        monkeypatch.setattr(Path,'read_text',lambda *a,**kw: (_ for _ in ()).throw(PermissionError()))
        monkeypatch.setattr('mobile_rehab.jsonio.time.sleep', lambda _: None)
        with pytest.raises(HTTPException) as exc:
            jobs.public(jobs.get(item['id'], item['owner']))
        assert exc.value.status_code == 503
    finally:
        jobs.close()


def test_replay_status_keeps_omission_and_actual_error():
    timing={}
    assert not replay_ended([dict(status='REPLAY_PREROLL_SKIPPED',skipped_frames=1,raw_time_s=-.033)],timing)
    assert timing['skipped_leading_frames']==1
    assert replay_ended([dict(status='EOF'),dict(status='RELEASED')],timing)
    with pytest.raises(ValueError,match='非单调'):
        replay_ended([dict(status='ERROR',message='录像媒体时间非单调')],timing)
    with pytest.raises(ValueError,match='提前结束'):
        replay_ended([dict(status='RELEASED')],timing)
