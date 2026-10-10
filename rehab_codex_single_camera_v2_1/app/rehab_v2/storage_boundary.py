"""Rehab-only SQLite fault semantics on the original Storage owning thread.

Never recreate or repair a failed database automatically. A failed request is
not proof of an absent receipt: callers must query and retry the same key once
storage is available. Business constraints and programming errors stay intact.
"""
from __future__ import annotations

import sqlite3

from .sessions import SessionError

VERSION = 'rehab-storage-boundary-1'
BUSY_TIMEOUT_MS = 250
SQLITE_REASONS = {
    sqlite3.SQLITE_FULL: 'capacity', sqlite3.SQLITE_READONLY: 'readonly',
    sqlite3.SQLITE_CORRUPT: 'corrupt', sqlite3.SQLITE_NOTADB: 'corrupt',
    sqlite3.SQLITE_BUSY: 'busy', sqlite3.SQLITE_LOCKED: 'busy',
    sqlite3.SQLITE_IOERR: 'io', sqlite3.SQLITE_CANTOPEN: 'unavailable',
}


class StorageFault(SessionError):
    def __init__(self, reason, sqlite_code):
        super().__init__('formal_store_'+reason, 503)
        self.reason, self.sqlite_code = reason, sqlite_code

    @property
    def public(self):
        return dict(version=VERSION, reason=self.reason, sqlite_code=self.sqlite_code,
                    commit_state='not_confirmed_by_this_error', automatic_recreation=False,
                    recovery=('preserve_database_and_require_explicit_recovery' if self.reason == 'corrupt'
                              else 'restore_storage_then_query_commit_and_retry_same_key'))


def classify_sqlite_fault(error):
    if not isinstance(error, sqlite3.Error):
        return None
    code = getattr(error, 'sqlite_errorcode', None)
    reason = SQLITE_REASONS.get(code & 255) if type(code) is int else None
    return StorageFault(reason, code) if reason is not None else None


class RehabStorageBoundary:
    """Small adapter, not another connection, writer, queue or transaction."""
    def __init__(self, storage, on_fault):
        self.storage, self.on_fault = storage, on_fault
        # This connection belongs only to the opt-in v2 host, not legacy stores.
        self._call(lambda conn: conn.execute('PRAGMA busy_timeout='+str(BUSY_TIMEOUT_MS)).fetchone())

    @property
    def path(self):
        return self.storage.path

    @property
    def readonly(self):
        return self.storage.readonly

    @property
    def contract(self):
        return dict(version=VERSION, sqlite_busy_timeout_ms=BUSY_TIMEOUT_MS,
                    writer='existing_storage_owning_thread', new_connection=False,
                    fact_authority='original_sql_transaction', automatic_recreation=False,
                    physical_disk_full_validation=False)

    def _call(self, fn):
        try:
            return self.storage._call(fn)
        except sqlite3.Error as error:
            fault = classify_sqlite_fault(error)
            if fault is None:
                raise
            self.on_fault(fault)
            raise fault from None  # No private SQL/paths/error text in the response.
