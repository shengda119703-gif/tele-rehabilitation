"""Additive local product arrangements; never changes measurement or Agent records."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
import json
import re
import secrets
import sqlite3
from pathlib import Path

CATEGORIES = ('health', 'rehab', 'medication')


class DailyStore:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / 'product_daily.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS data(owner TEXT, kind TEXT, value TEXT, PRIMARY KEY(owner,kind))')
            db.execute('CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, owner TEXT, at TEXT, action TEXT, payload TEXT)')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                db.execute('PRAGMA busy_timeout=10000')
                yield db
        finally:
            db.close()

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def get(db, owner, kind, default=None):
        row = db.execute('SELECT value FROM data WHERE owner=? AND kind=?', (owner, kind)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, db, owner, kind, value):
        db.execute('INSERT OR REPLACE INTO data VALUES(?,?,?)', (owner, kind, json.dumps(value, ensure_ascii=False)))

    def audit(self, db, owner, action, value):
        db.execute('INSERT INTO audit(owner,at,action,payload) VALUES(?,?,?,?)',
                   (owner, self.now(), action, json.dumps(value, ensure_ascii=False)))

    def snapshot(self, owner, scope):
        with self.connect() as db:
            return {'onboarding': self.get(db, owner, 'onboarding', {}),
                    'schedules': self.get(db, owner, self.schedule_key(scope), []),
                    'medSchedules': self.get(db, owner, 'medSchedules', {}),
                    'doses': self.get(db, owner, 'doses', {}),
                    'links': self.get(db, owner, 'links', []),
                    'grants': self.get(db, owner, 'grants', {}),
                    'planVersions': self.get(db, owner, 'planVersions', []),
                    'doseAudit': [{'at': at, 'record': json.loads(payload)} for at, payload in db.execute(
                        "SELECT at,payload FROM audit WHERE owner=? AND action='dose.record' ORDER BY id DESC LIMIT 300", (owner,))]}

    @staticmethod
    def schedule_key(scope):
        return 'schedule:' + str(scope.get('source_kind')) + ':' + str(scope.get('usage_context'))

    def apply(self, owner, operation, payload, scope):
        if not owner:
            raise ValueError('请先建立本机档案。')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if operation == 'daily.onboarding':
                value = dict(payload)
                value.update(completedAt=self.now())
                self.put(db, owner, 'onboarding', value)
                if not value.get('skipped'):
                    key = self.schedule_key(scope)
                    entries = self.get(db, owner, key, [])
                    if not entries:
                        weekdays=value.get('days') or list(range(7))
                        first=next(date.today()+timedelta(days=i) for i in range(7) if (date.today()+timedelta(days=i)).weekday() in weekdays)
                        entries.append({'id': secrets.token_hex(12), 'date': first.isoformat(),
                                        'time': value.get('time', '09:00'), 'kind': 'assessment',
                                        'name': '首次康复评估', 'createdAt': self.now()})
                        self.put(db, owner, key, entries)
            elif operation == 'daily.schedule':
                day = date.fromisoformat(payload['date'])
                clock = payload['time']
                if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', clock):
                    raise ValueError('请选择有效时间。')
                if day < date.today():
                    raise ValueError('不能新增过去日期的安排；过去记录仍保留。')
                key = self.schedule_key(scope)
                entries = self.get(db, owner, key, [])
                value = dict(payload, id=payload.get('id') or secrets.token_hex(12), createdAt=self.now())
                if not value.get('planId') and value.get('kind') != 'assessment':
                    raise ValueError('请选择已保存的计划。')
                if any(e['date'] == value['date'] and e['time'] == clock and e.get('planId') == value.get('planId')
                       and e['id'] != value['id'] for e in entries):
                    raise ValueError('该时间已经安排了同一计划。')
                entries = [e for e in entries if e['id'] != value['id']] + [value]
                self.put(db, owner, key, entries)
            elif operation == 'daily.unschedule':
                key = self.schedule_key(scope)
                entries = self.get(db, owner, key, [])
                if not any(e['id'] == payload['id'] for e in entries):
                    raise ValueError('安排已变化，请刷新。')
                self.put(db, owner, key, [e for e in entries if e['id'] != payload['id']])
            elif operation == 'daily.medSchedule':
                clock = sorted(set(payload['times']))
                if not 1 <= len(clock) <= 12 or any(not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', t) for t in clock):
                    raise ValueError('请填写 HH:mm 时间，多个时间用逗号分隔，最多 12 次。')
                start = date.fromisoformat(payload['start'])
                end = date.fromisoformat(payload['end']) if payload.get('end') else None
                if end and end < start:
                    raise ValueError('结束日期不能早于开始日期。')
                schedules = self.get(db, owner, 'medSchedules', {})
                schedules[payload['medId']] = dict(times=clock, start=start.isoformat(),
                    end=end.isoformat() if end else '', savedAt=self.now())
                self.put(db, owner, 'medSchedules', schedules)
            elif operation == 'daily.dose':
                day = date.fromisoformat(payload['date'])
                if day > date.today():
                    raise ValueError('未来用药不能预先标记为已服用。')
                if payload['status'] not in ('taken', 'skipped', 'unrecorded'):
                    raise ValueError('用药记录状态无效。')
                key = payload['medId'] + '|' + day.isoformat() + '|' + payload['time']
                doses = self.get(db, owner, 'doses', {})
                scheduled = self.get(db, owner, 'medSchedules', {}).get(payload['medId'])
                if key not in doses and (not scheduled or payload['time'] not in scheduled['times'] or day.isoformat() < scheduled['start'] or (scheduled['end'] and day.isoformat() > scheduled['end'])):
                    raise ValueError('该次服药不在已保存的时间安排中。')
                value = dict(payload, recordedAt=self.now(), previous=doses.get(key, {}).get('status', 'unrecorded'))
                doses[key] = {k: v for k, v in value.items() if k != 'previous'}
                self.put(db, owner, 'doses', doses)
                self.audit(db, owner, 'dose.record', value)
            elif operation == 'daily.familyInvite':
                code = secrets.token_hex(4).upper()
                self.put(db, owner, 'invite', {'code': code, 'expires': (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()})
                return {'dailyReceipt': True, 'code': code}
            elif operation == 'daily.familyBind':
                code = str(payload.get('code', '')).strip().upper()
                candidates = [(other, json.loads(raw)) for other, raw in db.execute("SELECT owner,value FROM data WHERE kind='invite'")]
                other = next((o for o, v in candidates if v['code'] == code and datetime.fromisoformat(v['expires']) > datetime.now(timezone.utc)), None)
                if not other or other == owner:
                    raise ValueError('邀请码无效、已过期或属于本人。请家人在其本机档案生成邀请码。')
                for first, second in ((owner, other), (other, owner)):
                    links = self.get(db, first, 'links', [])
                    if second not in links:
                        links.append(second)
                    self.put(db, first, 'links', links)
                db.execute("DELETE FROM data WHERE owner=? AND kind='invite'", (other,))
            elif operation in ('daily.familyGrant', 'daily.familyUnbind'):
                other = payload['member']
                if other not in self.get(db, owner, 'links', []):
                    raise ValueError('请先关联家人。')
                if operation == 'daily.familyGrant':
                    categories = payload['categories']
                    if not isinstance(categories, list) or any(c not in CATEGORIES for c in categories):
                        raise ValueError('共享范围无效。')
                    grants = self.get(db, owner, 'grants', {})
                    grants[other] = list(set(categories))
                    self.put(db, owner, 'grants', grants)
                else:
                    for first, second in ((owner, other), (other, owner)):
                        self.put(db, first, 'links', [o for o in self.get(db, first, 'links', []) if o != second])
                        grants = self.get(db, first, 'grants', {})
                        grants.pop(second, None)
                        self.put(db, first, 'grants', grants)
            else:
                raise ValueError('未知本机产品操作。')
            self.audit(db, owner, operation, payload)
        return {'dailyReceipt': True}

    def allowed_members(self, owner):
        with self.connect() as db:
            return [(member, self.get(db, member, 'grants', {}).get(owner, []))
                    for member in self.get(db, owner, 'links', []) if owner in self.get(db, member, 'links', [])]

    def remember_plan(self, owner, plan):
        with self.connect() as db:
            values = self.get(db, owner, 'planVersions', [])
            if not any(v['id'] == plan['id'] and v['revision'] == plan['revision'] for v in values):
                values.append(plan)
                self.put(db, owner, 'planVersions', values)
                self.audit(db, owner, 'plan.version', {'id': plan['id'], 'revision': plan['revision']})

    def clear(self, owner):
        with self.connect() as db:
            for other, _ in self.allowed_members(owner):
                self.put(db, other, 'links', [v for v in self.get(db, other, 'links', []) if v != owner])
                grants = self.get(db, other, 'grants', {})
                grants.pop(owner, None)
                self.put(db, other, 'grants', grants)
            db.execute("DELETE FROM data WHERE owner=? AND kind NOT LIKE 'schedule:%' AND kind!='planVersions'", (owner,))
            db.execute('DELETE FROM audit WHERE owner=?', (owner,))
