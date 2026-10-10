"""Bound care tools; existing DailyStore owns writes and RehabReadTools owns rehab facts."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from ..rehab_read_tools import RehabReadTools, TOOLS


class CareHost:
    def __init__(self, data_dir, daily, owner, scope, *, profile_reader=None, rehab_reader=None):
        if not owner or scope.get('participant_id') != owner or scope.get('source_kind') not in ('LIVE_CAMERA', 'REPLAY_FILE', 'SYNTHETIC') or scope.get('usage_context') not in ('SELF_USE', 'TEST', 'CONTROLLED_DEMO'):
            raise ValueError('照护工具必须绑定当前本人档案。')
        self.root, self.daily, self.owner, self.scope = Path(data_dir), daily, owner, dict(scope)
        self.profile_reader, self.rehab_reader = profile_reader, rehab_reader

    def medications(self):
        if self.profile_reader:
            return self.profile_reader()
        key = 'profile:' + self.owner
        file = self.root / 'product' / 'profiles' / (hashlib.sha256(key.encode()).hexdigest() + '.json')
        value = json.loads(file.read_text(encoding='utf-8'))
        stored = value.get('value', {})
        if value.get('version') != 1 or value.get('key') != key or stored.get('ownerId') != self.owner:
            raise ValueError('本人用药档案无法核对。')
        return stored['profile'].get('medicationRecords', [])

    def rehab(self):
        if self.rehab_reader:
            return self.rehab_reader()
        view = RehabReadTools(self.root / 'home_rehab.sqlite3', self.scope).desktop_snapshot()
        return {'plans': view[TOOLS[0]]['records'], 'history': view[TOOLS[2]]['records']}

    def read(self):
        return dict(scope=self.scope, medications=self.medications(), daily=self.daily.snapshot(self.owner, self.scope), **self.rehab())

    def execute(self, action, key, expires_at=None):
        if not isinstance(action, dict) or set(action) != {'operation', 'payload', 'expected', 'label'}:
            raise ValueError('照护动作结构无效。')
        operation, payload, expected = action['operation'], dict(action['payload']), action['expected']
        fields = {'daily.dose': {'medId', 'date', 'time', 'status'},
                  'daily.schedule': {'id', 'date', 'time', 'kind', 'name', 'planId', 'revision'}}
        if operation not in fields or set(payload) != fields[operation] or not isinstance(expected, dict):
            raise ValueError('没有该照护执行能力或参数含未知字段。')
        deadline = None
        if expires_at is not None:
            if not isinstance(expires_at, str):
                raise ValueError('照护确认期限无效。')
            deadline = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            if deadline.tzinfo is None:
                raise ValueError('照护确认期限须有时区。')

        def validate(db, target):
            # DailyStore checks the committed receipt first. Expiry blocks only a NEW business write.
            if deadline is not None and datetime.now(timezone.utc) > deadline:
                raise ValueError('确认已过期；已保存回执仍可核对，未执行项需要重新提议。')
            if operation == 'daily.dose':
                medicine = next((m for m in self.medications() if m['id'] == target['medId']), None)
                schedules = self.daily.get(db, self.owner, 'medSchedules', {})
                doses = self.daily.get(db, self.owner, 'doses', {})
                occurrence = target['medId'] + '|' + target['date'] + '|' + target['time']
                actual = {'medicine': medicine, 'schedule': schedules.get(target['medId']), 'dose': doses.get(occurrence)}
                if actual != expected or not medicine:
                    raise ValueError('药物或该次服药记录已变化，请重新核对。')
                target.update(medName=medicine['name'], dose=medicine.get('dose', ''))
            else:
                schedules = self.daily.get(db, self.owner, self.daily.schedule_key(self.scope), [])
                current = next((s for s in schedules if s['id'] == target['id']), None)
                plan = next((p for p in self.rehab()['plans'] if current and p['id'] == current.get('planId')), None)
                actual = {'schedule': current, 'plan': {'id': plan['id'], 'revision': plan['revision']} if plan else None}
                if actual != expected or not current or not plan or current.get('revision') != plan['revision']:
                    raise ValueError('训练安排或原计划已变化，请重新核对。')
                if any(target.get(k) != current.get(k) for k in ('id', 'kind', 'name', 'planId', 'revision')):
                    raise ValueError('改期只能修改原安排的日期和时间。')

        return self.daily.apply(self.owner, operation, payload, self.scope,
                                idempotency_key=key, expected=expected, care_validate=validate)

    def __call__(self, name, arguments):
        if name == 'care.read' and arguments == {}:
            return self.read()
        if name == 'care.execute' and isinstance(arguments, dict) and set(arguments) == {'action', 'idempotencyKey', 'expiresAt'}:
            return self.execute(arguments['action'], arguments['idempotencyKey'], arguments['expiresAt'])
        raise ValueError('未知照护工具或参数。')
