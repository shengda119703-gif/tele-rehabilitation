"""Owned guided-practice records, separate from measured sessions and dose progress.

Uses the existing SQLite writer/transaction. No new patient database, model,
automatic-plan gate or measurement fact is introduced by this adapter.
"""
from __future__ import annotations

import copy
import json
import re

from fastapi import HTTPException, Request
from app.assessment import build_body_profile
from app.automatic_plans import feedback_block, validate_automatic_use
from app.domain import dumps, utc_now

POLICY = 'saved-arrangement-guided-1'
KEY = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')


def exact(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise HTTPException(400, '练习记录含未知或缺失字段')


def key(value):
    if not isinstance(value, str) or not KEY.fullmatch(value):
        raise HTTPException(400, '练习编号无效')


def table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS guided_practices(
        owner TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY(owner,id))''')


def read(conn, owner, identity):
    table(conn)
    row = conn.execute('SELECT payload FROM guided_practices WHERE owner=? AND id=?',
                       (owner, identity)).fetchone()
    if not row:
        raise HTTPException(404, '未找到本人的这次练习记录')
    return json.loads(row[0])


def context(participant):
    return dict(participant_id=participant, provider='hosted-legacy-1',
                source_context='REPLAY_FILE:SELF_USE', policy_version=POLICY)


def stopped(item):
    """Later edits cannot silently revoke a previously explicit stop signal."""
    end = item.get('finish_payload')
    return bool(end and (end['reason'] == 'discomfort'
                        or feedback_block({'training_feedback': end['feedback']})
                        or any(feedback_block({'training_feedback': r['values']})
                               for r in item.get('practice_feedback', {}).get('operations', []))))


def feedback_snapshot(item):
    feedback = item.get('practice_feedback')
    return dict(practice_id=item['id'], context=copy.deepcopy(item['context']),
                revision=feedback['revision'] if feedback else 0,
                values=copy.deepcopy(feedback['values'] if feedback else dict(
                    **(item.get('finish_payload') or {}).get('feedback', dict(pain=None, fatigue=None)), note=None)),
                saved_at=feedback['saved_at'] if feedback else None)


def feedback_operation(item, operation):
    key(operation)
    found = next((r for r in item.get('practice_feedback', {}).get('operations', [])
                  if r['operation_id'] == operation), None)
    if not found:
        raise HTTPException(404, '未找到本次感受填写的保存回执')
    return dict(practice_id=item['id'], context=copy.deepcopy(item['context']),
                status='COMMITTED', **copy.deepcopy(found))


def save_feedback(conn, uid, identity, value):
    exact(value, ('operation_id', 'expected_revision', 'values'))
    key(value['operation_id'])
    if type(value['expected_revision']) is not int or value['expected_revision'] < 0:
        raise HTTPException(400, '感受记录版本无效')
    exact(value['values'], ('pain', 'fatigue', 'note'))
    values = value['values']
    if (any(n is not None and (type(n) is not int or not 0 <= n <= 10)
            for n in (values['pain'], values['fatigue']))
            or values['note'] is not None and (not isinstance(values['note'], str)
                                              or not values['note'].strip() or len(values['note']) > 500)
            or all(v is None for v in values.values())):
        raise HTTPException(400, '请填写真实感受；未填写的项目保持空白')
    conn.execute('BEGIN IMMEDIATE')
    item = read(conn, uid, identity)
    if item['state'] != 'COMMITTED':
        raise HTTPException(409, dict(code='PRACTICE_NOT_COMMITTED', message='先确认练习保存，再提交感受。'))
    feedback = item.get('practice_feedback', dict(revision=0, operations=[]))
    old = next((r for r in feedback['operations'] if r['operation_id'] == value['operation_id']), None)
    if old:
        if old['expected_revision'] != value['expected_revision'] or old['values'] != values:
            raise HTTPException(409, dict(code='FEEDBACK_KEY_CONFLICT', message='填写编号已用于另一份内容。'))
        return feedback_operation(item, value['operation_id'])
    if feedback['revision'] != value['expected_revision']:
        raise HTTPException(409, dict(code='FEEDBACK_REVISION_CONFLICT', message='感受记录已在另一处更新，请先核对。'))
    if len(feedback['operations']) >= 100:
        raise HTTPException(507, '本次感受修改记录空间已满；原内容保留')
    receipt = dict(operation_id=value['operation_id'], expected_revision=value['expected_revision'],
                   revision=feedback['revision'] + 1, values=copy.deepcopy(values), saved_at=utc_now())
    item['practice_feedback'] = dict(revision=receipt['revision'], values=copy.deepcopy(values),
                                    saved_at=receipt['saved_at'], operations=feedback['operations'] + [receipt])
    conn.execute('UPDATE guided_practices SET payload=? WHERE owner=? AND id=?',
                 (dumps(item), uid, identity))
    return feedback_operation(item, value['operation_id'])


def projection(conn, uid, item):
    """Query-time permission is not a rewrite of the saved grant/facts."""
    result = copy.deepcopy(item)
    result.update(execution_allowed=False, execution_reason=None)
    if item['state'] != 'PRACTICING':
        return result
    previous = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM guided_practices WHERE owner=?', (uid,))]
    if any(stopped(r) and r['plan_ref']['id'] == item['plan_ref']['id'] for r in previous):
        result['execution_reason'] = '本轮已记录不适，请先停止并核对安排。'
        return result
    row = conn.execute('SELECT payload FROM training_plans WHERE id=?', (item['plan_ref']['id'],)).fetchone()
    plan = json.loads(row[0]) if row else None
    participant = item['context']['participant_id']
    if (not plan or plan.get('participant_id') != participant or plan['revision'] != item['plan_ref']['revision']
            or plan.get('status') != 'ACTIVE' or plan.get('source_kind') != 'REPLAY_FILE'
            or plan.get('usage_context') != 'SELF_USE'):
        result['execution_reason'] = '原安排已变化；可以结束并保存已经发生的练习。'
        return result
    sessions = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM sessions')]
    row = conn.execute('SELECT payload FROM participants WHERE id=?', (participant,)).fetchone()
    person = json.loads(row[0]) if row else None
    try:
        validate_automatic_use(plan, item['plan_ref']['entry_key'],
                               build_body_profile(sessions, participant, 'REPLAY_FILE', 'SELF_USE'), sessions, person)
    except ValueError as error:
        result['execution_reason'] = str(error)
        return result
    result['execution_allowed'] = True
    return result


def create(conn, uid, participant, value):
    exact(value, ('operation_id', 'plan_id', 'plan_revision', 'entry_key'))
    key(value['operation_id'])
    if (not isinstance(value['plan_id'], str) or not isinstance(value['entry_key'], str)
            or type(value['plan_revision']) is not int or value['plan_revision'] < 1):
        raise HTTPException(400, '请使用本人的已保存安排')
    conn.execute('BEGIN IMMEDIATE')
    table(conn)
    old = conn.execute('SELECT payload FROM guided_practices WHERE owner=? AND id=?',
                       (uid, value['operation_id'])).fetchone()
    if old:
        saved = json.loads(old[0])
        if saved['start_payload'] != value:
            raise HTTPException(409, '该练习编号已用于另一项安排')
        return projection(conn, uid, saved)
    row = conn.execute('SELECT payload FROM training_plans WHERE id=?', (value['plan_id'],)).fetchone()
    plan = json.loads(row[0]) if row else None
    if not plan or plan.get('participant_id') != participant:
        raise HTTPException(404, '未找到本人的已保存安排')
    if (plan['revision'] != value['plan_revision'] or plan.get('source_kind') != 'REPLAY_FILE'
            or plan.get('usage_context') != 'SELF_USE' or plan.get('status') != 'ACTIVE'):
        raise HTTPException(409, '本项安排或来源已变化，请核对当前安排')
    sessions = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM sessions')]
    row = conn.execute('SELECT payload FROM participants WHERE id=?', (participant,)).fetchone()
    person = json.loads(row[0]) if row else None
    profile = build_body_profile(sessions, participant, 'REPLAY_FILE', 'SELF_USE')
    # Deliberately reuse EVERY original gate. Camera READY is not one of these
    # arrangement gates; nothing below fabricates a qualified assessment.
    try:
        validate_automatic_use(plan, value['entry_key'], profile, sessions, person)
    except ValueError as error:
        raise HTTPException(409, dict(code='ARRANGEMENT_NOT_ALLOWED', category='EXECUTION_BLOCK',
                                     applies_to='GUIDED_PRACTICE', message=str(error)))
    previous = [json.loads(r[0]) for r in conn.execute(
        'SELECT payload FROM guided_practices WHERE owner=?', (uid,))]
    if any(p['plan_ref']['id'] == plan['id'] and stopped(p) for p in previous):
        raise HTTPException(409, dict(code='PRACTICE_STOP_RECORDED', category='EXECUTION_BLOCK',
                                     applies_to='GUIDED_PRACTICE', message='本轮已记录不适，请先停止并核对安排。'))
    if any(p['state'] == 'PRACTICING' for p in previous):
        raise HTTPException(409, dict(code='ORIGINAL_PRACTICE_OPEN', category='TECHNICAL',
                                     applies_to='GUIDED_PRACTICE', message='上次练习尚未结束，请先返回原记录。'))
    entry = next(i for i in plan['items'] if i['key'] == value['entry_key'])
    item = dict(schema_version=1, id=value['operation_id'], context=context(participant),
                state='PRACTICING', start_payload=copy.deepcopy(value), created_at=utc_now(),
                plan_ref=dict(id=plan['id'], revision=plan['revision'], entry_key=entry['key']),
                exercise_id=entry['exercise_id'], side=entry['side'], settings=copy.deepcopy(entry['settings']),
                record_origin='GUIDED_PRACTICE', visual_session_ref=None, confirmed_count=None,
                formal_plan_contribution=None, finish_payload=None)
    conn.execute('INSERT INTO guided_practices VALUES (?,?,?)', (uid, item['id'], dumps(item)))
    return projection(conn, uid, item)


def finish(conn, uid, identity, value):
    exact(value, ('operation_id', 'count', 'elapsed_ms', 'reason', 'feedback'))
    key(value['operation_id'])
    if value['count'] is not None and (type(value['count']) is not int or not 0 <= value['count'] <= 10000):
        raise HTTPException(400, '请填写本组实际总次数，或留空')
    if type(value['elapsed_ms']) is not int or not 0 <= value['elapsed_ms'] <= 86400000:
        raise HTTPException(400, '练习页面时间无效')
    if value['reason'] not in ('ended', 'completed_set', 'discomfort'):
        raise HTTPException(400, '结束方式无效')
    exact(value['feedback'], ('pain', 'fatigue'))
    if any(n is not None and (type(n) is not int or not 0 <= n <= 10) for n in value['feedback'].values()):
        raise HTTPException(400, '请填写真实感受，或留空')
    conn.execute('BEGIN IMMEDIATE')
    item = read(conn, uid, identity)
    if item['finish_payload']:
        if item['finish_payload'] != value:
            raise HTTPException(409, '本次已保存，请先查看原结束记录')
        return projection(conn, uid, item)
    # Ended facts may always be saved after a later eligibility change; that
    # does not grant any further execution or contribute to the formal plan.
    item.update(state='COMMITTED', ended_at=utc_now(), finish_payload=copy.deepcopy(value),
                self_reported_count=value['count'], count_scope='set_total', set_index=1,
                elapsed_source='frontend_active_time_not_observed_hold',
                record_origin='SELF_RECORDED' if value['count'] is not None else 'GUIDED_PRACTICE')
    item['mode_segments'] = [dict(mode='GUIDED', start=item['created_at'], end=item['ended_at'],
                                 reason='allowed_saved_arrangement', time_basis='server_receipt_time',
                                 source='GUIDED_PRACTICE', set_index=1)]
    conn.execute('UPDATE guided_practices SET payload=? WHERE owner=? AND id=?',
                 (dumps(item), uid, identity))
    return projection(conn, uid, item)


def install_practice(app, owner, store_for, small_json, participant_for):
    @app.get('/api/practice/{identity}/feedback')
    def get_feedback(identity: str, request: Request):
        uid = owner(request)
        key(identity)
        with store_for(uid) as store:
            return store._call(lambda c: feedback_snapshot(read(c, uid, identity)))

    @app.get('/api/practice/{identity}/feedback/operations/{operation}')
    def get_feedback_operation(identity: str, operation: str, request: Request):
        uid = owner(request)
        key(identity)
        with store_for(uid) as store:
            return store._call(lambda c: feedback_operation(read(c, uid, identity), operation))

    @app.post('/api/practice/{identity}/feedback')
    async def post_feedback(identity: str, request: Request):
        uid, value = owner(request), await small_json(request)
        key(identity)
        def save():
            with store_for(uid) as store:
                return store._call(lambda c: save_feedback(c, uid, identity, value))
        import asyncio
        return await asyncio.to_thread(save)

    @app.get('/api/practice/context')
    def get_context(request: Request):
        uid = owner(request)
        return context(participant_for(uid))

    @app.get('/api/practice')
    def list_practice(request: Request):
        uid = owner(request)
        with store_for(uid) as store:
            def collect(conn):
                table(conn)
                return [projection(conn, uid, json.loads(r[0])) for r in conn.execute(
                    'SELECT payload FROM guided_practices WHERE owner=? ORDER BY rowid DESC', (uid,))]
            return store._call(collect)

    @app.get('/api/practice/{identity}')
    def get_practice(identity: str, request: Request):
        uid = owner(request)
        key(identity)
        with store_for(uid) as store:
            return store._call(lambda c: projection(c, uid, read(c, uid, identity)))

    @app.post('/api/practice')
    async def start(request: Request):
        uid, value = owner(request), await small_json(request)
        def save():
            with store_for(uid) as store:
                return store._call(lambda c: create(c, uid, participant_for(uid), value))
        import asyncio
        return await asyncio.to_thread(save)

    @app.post('/api/practice/{identity}/finish')
    async def end(identity: str, request: Request):
        uid, value = owner(request), await small_json(request)
        key(identity)
        def save():
            with store_for(uid) as store:
                return store._call(lambda c: finish(c, uid, identity, value))
        import asyncio
        return await asyncio.to_thread(save)
