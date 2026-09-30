"""Mechanical schema/provenance validation, never Chinese semantic parsing.

Semantic labels are model interpretations, not clinical facts. Literal source
support prevents invented textual claims; it does not prove semantic entailment.
"""
import copy
from uuid import uuid4

VERSION = 'semantic-interpreter-3'
ACTS = {'new_report', 'follow_up', 'state_change', 'correction', 'question', 'request', 'chat', 'clarification'}
FIELDS = {'raw_text', 'evidence_span', 'subject', 'time_reference', 'proposition', 'certainty', 'context_refs', 'relation'}
SUBJECTS = {'self', 'family', 'other', 'unknown'}
TIME_VALUES = {'current', 'past', 'future', 'unknown'}
POLARITIES = {'affirmed', 'negated', 'hypothetical'}


class GroundingError(ValueError):
    pass


def reject():
    raise GroundingError('原文依据或对话引用未通过核验。请重新说明要补充、更正或描述的情况；本轮未保存。')


def keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        reject()


def string(value, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        reject()
    return value


def choice(value, allowed):
    if not isinstance(value, str) or value not in allowed:
        reject()


def validate_interpretation(payload, turn, state):
    keys(payload, {'dialogue_act', 'statements'})
    choice(payload['dialogue_act'], ACTS)
    if not state.owns(turn):
        reject()
    items = payload['statements']
    if not isinstance(items, list) or len(items) > 8:
        reject()
    if payload['dialogue_act'] in {'chat', 'question', 'request'} and items:
        reject()
    claims, seen = [], set()
    for item in items:
        keys(item, FIELDS)
        if item['raw_text'] != turn['raw_text']:
            reject()
        if string(item['evidence_span']) not in turn['raw_text']:
            reject()
        refs = item['context_refs']
        if not isinstance(refs, list) or len(refs) > 8:
            reject()
        referenced, evidence = {}, []
        for ref in refs:
            keys(ref, {'kind', 'id'})
            choice(ref['kind'], {'message', 'event'})
            string(ref['id'], 160)
            key = (ref['kind'], ref['id'])
            resolved = state.resolve(*key)
            if not resolved or key in referenced:
                reject()
            referenced[key] = resolved
            evidence.append(dict(kind=ref['kind'], id=ref['id'], raw_text=resolved['raw_text']))

        def quoted(source):
            keys(source, {'kind', 'id', 'quote'})
            choice(source['kind'], {'current', 'message', 'event'})
            string(source['id'], 160)
            quote = string(source['quote'])
            if source['kind'] == 'current':
                if source['id'] != 'current':
                    reject()
                original = turn['raw_text']
            else:
                record = referenced.get((source['kind'], source['id']))
                if not record:
                    reject()
                original = record['raw_text']
            if quote not in original:
                reject()
            return quote

        for field, values in (('subject', SUBJECTS), ('time_reference', TIME_VALUES)):
            keys(item[field], {'value', 'source'})
            choice(item[field]['value'], values)
            if item[field]['value'] == 'unknown':
                if item[field]['source'] is not None:
                    quoted(item[field]['source'])
            else:
                quoted(item[field]['source'])
                # Inheritance must agree with an existing structured value, not a recomputed sentence.
                source = item[field]['source']
                if source['kind'] == 'event':
                    original = referenced[('event', source['id'])]
                    if item[field]['value'] != original[field]['value']:
                        reject()
        proposition = item['proposition']
        keys(proposition, {'text', 'polarity', 'source'})
        choice(proposition['polarity'], POLARITIES)
        if string(proposition['text']) != quoted(proposition['source']):
            reject()
        choice(item['certainty'], {'certain', 'uncertain'})
        relation = item['relation']
        keys(relation, {'type', 'target'})
        choice(relation['type'], {'none', 'elaborates', 'updates', 'corrects'})
        target = None
        if relation['type'] == 'none':
            if relation['target'] is not None:
                reject()
        else:
            keys(relation['target'], {'kind', 'id'})
            link = relation['target']
            if link['kind'] == 'event':
                target = referenced.get(('event', string(link['id'], 160)))
            elif link['kind'] == 'statement' and type(link['id']) is int and 0 <= link['id'] < len(claims):
                target = claims[link['id']]
            if target is None:
                reject()
        act = payload['dialogue_act']
        allowed = {'new_report': {'none'}, 'follow_up': {'elaborates'},
                   'clarification': {'none', 'elaborates'}, 'state_change': {'none', 'updates'},
                   'correction': {'corrects'}}
        if relation['type'] not in allowed.get(act, set()):
            reject()
        if act == 'correction' and relation['target']['kind'] != 'event':
            reject()
        duplicate = (item['evidence_span'], proposition['text'], relation['type'], target['id'] if target else None)
        if duplicate in seen:
            reject()
        seen.add(duplicate)
        claims.append(dict(copy.deepcopy(item), id=uuid4().hex, source_message_id=turn['id'],
                           reported_at=turn['reported_at'], dialogue_act=act,
                           conversation_id=state.conversation_id, interpretation_version=VERSION,
                           relation=dict(type=relation['type'], target_event_id=target['id'] if target else None),
                           context_evidence=evidence,
                           target_snapshot=copy.deepcopy({k: target[k] for k in
                               ('id', 'raw_text', 'reported_at', 'subject', 'time_reference', 'proposition')}) if target else None))
    if payload['dialogue_act'] == 'state_change' and not any(c['relation']['type'] == 'updates' for c in claims):
        reject()
    return claims


def save_eligible(claim):
    """Execution policy on schema enums; never classify the user's language."""
    return (claim['dialogue_act'] in {'new_report', 'follow_up', 'clarification', 'state_change'}
            and claim['subject']['value'] == 'self' and claim['time_reference']['value'] in {'current', 'past'}
            and claim['certainty'] == 'certain'
            and (claim['proposition']['polarity'] == 'affirmed' or
                 (claim['dialogue_act'] == 'state_change' and claim['relation']['type'] == 'updates'
                  and claim['proposition']['polarity'] == 'negated')))
