"""Original HTTP/SQLite initialization, no patient or measurement fixtures."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading
import time

from fastapi.testclient import TestClient
import pytest

from mobile_rehab import server
from mobile_rehab.tests.test_mobile import HEADERS, owner


def test_independent_cold_page_reads_initialize_original_storage_once_at_a_time(tmp_path, monkeypatch):
    actual_storage = server.Storage
    count_lock, together = threading.Lock(), threading.Barrier(4)
    active, peak = 0, 0

    def tracked_storage(*args, **kwargs):
        nonlocal active, peak
        with count_lock:
            active += 1
            peak = max(peak, active)
        try:
            # A slow initializer must not make a second constructor inspect a partial schema.
            time.sleep(.025)
            return actual_storage(*args, **kwargs)
        finally:
            with count_lock:
                active -= 1

    monkeypatch.setattr(server, 'Storage', tracked_storage)
    app = server.create_app(tmp_path, pair_key='TEST-only', runner=lambda item: None)
    with TestClient(app, headers=HEADERS) as client:
        assert client.post('/api/pair', json={'code': 'TEST-only'}).status_code == 200

        def read(route):
            together.wait(timeout=10)
            return client.get(route)

        routes = ['/api/practice', '/api/practice/arrangements', '/api/practice', '/api/practice/arrangements']
        with ThreadPoolExecutor(max_workers=4) as executor:
            replies = list(executor.map(read, routes))
        assert all(reply.status_code == 200 for reply in replies)
        assert all(reply.json() == [] for reply in replies)
        assert peak == 1
        database = app.state.jobs.root / owner(client) / 'assessments.sqlite3'
        with sqlite3.connect(database) as conn:
            assert conn.execute('PRAGMA user_version').fetchone()[0] == 4
            assert conn.execute('SELECT count(*) FROM sessions').fetchone()[0] == 0


def test_initialization_lock_does_not_bypass_unknown_original_database_guard(tmp_path):
    app = server.create_app(tmp_path, pair_key='TEST-only', runner=lambda item: None)
    with TestClient(app, headers=HEADERS) as client:
        assert client.post('/api/pair', json={'code': 'TEST-only'}).status_code == 200
        database = app.state.jobs.root / owner(client) / 'assessments.sqlite3'
        database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database) as conn:
            conn.execute('CREATE TABLE TEST_unknown_original (value TEXT)')
            conn.execute("INSERT INTO TEST_unknown_original VALUES ('TEST keep original')")
        with pytest.raises(RuntimeError, match='未知旧数据库'):
            client.get('/api/practice')
        with sqlite3.connect(database) as conn:
            assert conn.execute('PRAGMA user_version').fetchone()[0] == 0
            assert conn.execute('SELECT value FROM TEST_unknown_original').fetchone()[0] == 'TEST keep original'
