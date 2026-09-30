"""Bounded, scope-owned conversation references. No language interpretation."""
import copy
from uuid import uuid4

from .domain import utc_now
from .silver_store import scope_key


class ConversationState:
    MAX_TURNS = 6
    MAX_EVENTS = 12

    def __init__(self, scope, conversation_id):
        self.scope = scope_key(scope)
        self.conversation_id = conversation_id
        self.clear()

    def clear(self):
        self.epoch = uuid4().hex
        self.turns = []
        self.events = {}
        self.focus = None

    def new_turn(self, text, reported_at=None):
        return dict(id=uuid4().hex, raw_text=text, reported_at=reported_at or utc_now(),
                    conversation_id=self.conversation_id, epoch=self.epoch)

    def owns(self, turn):
        return turn['conversation_id'] == self.conversation_id and turn['epoch'] == self.epoch

    def resolve(self, kind, rid):
        if kind == 'message':
            return next((t for t in self.turns if t['id'] == rid), None)
        if kind == 'event':
            event = self.events.get(rid)
            return event if event and event['reference_status'] == 'active' else None
        return None

    def accept(self, turn, dialogue_act, claims):
        if not self.owns(turn):
            raise ValueError('对话引用已失效')
        self.turns.append(dict(copy.deepcopy(turn), dialogue_act=dialogue_act))
        self.turns = self.turns[-self.MAX_TURNS:]
        for claim in claims:
            self.events[claim['id']] = dict(copy.deepcopy(claim), reference_status='active', record_revision=None)
        live = {t['id'] for t in self.turns}
        self.events = {k: v for k, v in self.events.items() if v['source_message_id'] in live}
        self.events = dict(list(self.events.items())[-self.MAX_EVENTS:])
        self.focus = claims[-1]['id'] if claims else self.focus
        if self.focus not in self.events:
            self.focus = None

    def saved(self, rid, revision):
        if rid in self.events:
            self.events[rid]['record_revision'] = revision

    def invalidate(self, rid):
        if rid in self.events:
            self.events[rid]['reference_status'] = 'invalid'
        if self.focus == rid:
            self.focus = None

    def packet(self):
        # Scope identities, consent tokens, DB rows, and audit history never leave here.
        fields = ('id', 'source_message_id', 'raw_text', 'reported_at', 'dialogue_act',
                  'subject', 'time_reference', 'proposition', 'certainty', 'relation')
        return dict(conversation_id=self.conversation_id, epoch=self.epoch, focus=self.focus,
                    turns=[{k: t[k] for k in ('id', 'raw_text', 'reported_at', 'dialogue_act')} for t in self.turns],
                    events=[{k: copy.deepcopy(e[k]) for k in fields} for e in self.events.values()
                            if e['reference_status'] == 'active'])
