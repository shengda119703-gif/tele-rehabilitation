"""Consent-bound operations on grounded interpretations; no language parser."""
import copy
from uuid import uuid4

from .agent_privacy import parse_privacy_intent
from .agent_conversation import ModelError
from .agent_extraction import interpret
from .agent_grounding import GroundingError, validate_interpretation, save_eligible
from .agent_state import ConversationState
from .silver_store import scope_key
from .domain import utc_now, digest

KIND = 'agent_self_report'
SUBJECT_LABELS = {'self': '本人', 'family': '家人', 'other': '他人', 'unknown': '人物待确认'}
TIME_LABELS = {'current': '当前', 'past': '过去', 'future': '将来', 'unknown': '时间待确认'}


def raw_text(claim):
    return claim.get('raw_text', claim.get('text', ''))


def brief_claim(claim):
    if 'interpretation_version' not in claim:
        # Display-only A1/A2 compatibility. Never reinterpret historical claims.
        return ' · '.join((SUBJECT_LABELS.get(claim.get('subject'), '未知'),
                           TIME_LABELS.get(claim.get('time_scope'), '未知'),
                           claim.get('concept', claim.get('symptom', raw_text(claim)))))
    labels = [SUBJECT_LABELS[claim['subject']['value']], TIME_LABELS[claim['time_reference']['value']],
              claim['proposition']['text']]
    if claim['certainty'] == 'uncertain':
        labels.append('不确定')
    if claim['proposition']['polarity'] != 'affirmed':
        labels.append({'negated': '否定', 'hypothetical': '假设'}[claim['proposition']['polarity']])
    if claim['relation']['type'] != 'none':
        labels.append({'updates': '后续状态', 'corrects': '纠正', 'elaborates': '补充'}[claim['relation']['type']])
    return ' · '.join(labels)


def statement_reply(claims, act):
    if act == 'correction':
        return '已定位你引用的自报。请核对旧原话，逐条确认是否撤回；其他记录不变。'
    if act == 'state_change':
        return '这会新增一条后续状态，不会撤回先前内容。请单独核对后确认保存。'
    replies = []
    for claim in claims:
        subject = claim['subject']['value']
        if subject == 'unknown':
            message = '这是你本人还是家人的情况？'
        elif subject != 'self':
            message = '这是他人的情况，不会记到你的本人自报里。'
        elif claim['certainty'] == 'uncertain':
            message = '我还不能确定这件事是否实际发生，请再核对。'
        elif claim['proposition']['polarity'] == 'hypothetical':
            message = '这是一个假设，不会记录成已经发生。'
        elif claim['proposition']['polarity'] == 'negated':
            message = '这是对所述情况的否定，不会记录成本人的不适。'
        elif claim['time_reference']['value'] == 'unknown':
            message = '这是现在发生的，还是之前发生的？'
        elif claim['time_reference']['value'] == 'future':
            message = '这是将来的情况，不会记录成已经发生。'
        else:
            message = '请核对下面的原话和解释，逐条点击“确认保存”后才会记录。'
        if message not in replies:
            replies.append(message)
    return '\n'.join(replies) or '请说明你在补充哪件事、纠正哪条自报，或描述新的状态。'


class StatementSession:
    def __init__(self, scope, care_factory, conversation_id=None):
        self.scope = scope_key(scope)
        self.care_factory = care_factory
        self.state = ConversationState(scope, conversation_id or uuid4().hex)
        self.pending = {}
        self._seals = {}
        self.network = 'not_sent'

    def clear(self):
        self.pending.clear()
        self._seals.clear()
        self.state.clear()

    def result(self, text, *, claims=(), receipt=None, record_summary='', dialogue_act=None):
        return dict(scope=copy.deepcopy(self.scope), version='agent-statements-3', at=utc_now(),
                    text=text, main_text=text, source_label='用户原话 / 模型解释，非临床事实',
                    mode='local', mode_label=('DeepSeek 语义解释 · 本机引用核验' if self.network != 'not_sent'
                                              else '本机自报操作 · 未联网'), shareable=False,
                    actions=[], evidence=[], tools=[], local_text='', understanding=copy.deepcopy(list(claims)),
                    dialogue_act=dialogue_act, evidence_summary='\n'.join(brief_claim(c) for c in claims),
                    receipt=receipt or dict(status='not_saved', text='未写入自报记录。'), record_summary=record_summary,
                    proposed_actions=[dict(id=k, label=v['label'], summary=v['summary'], operation=v['operation'],
                                           requires_confirmation=True) for k, v in self.pending.items()],
                    privacy_notice=('本轮未发送给 DeepSeek；' if self.network == 'not_sent'
                                    else '本轮文字及有限近期对话按授权提交 DeepSeek（失败时也可能已发送）；')
                                   + '仅确认后保存到本机，未分享家属。',
                    privacy_status=dict(network=self.network, family='not_shared'), delivery_status='NOT_CONNECTED')

    def _propose(self, operation, claim, *, record=None, correction=None):
        if any(p['operation'] == operation and p['claim']['id'] == claim['id'] for p in self.pending.values()):
            return
        token = uuid4().hex
        target = claim.get('target_snapshot')
        summary = brief_claim(claim) + '\n原话：' + raw_text(claim)
        if target:
            summary += '\n关联原话：' + target['raw_text']
        label = ('确认保存：' if operation == 'save' else '确认撤回：')
        if 'interpretation_version' in claim:
            label += claim['proposition']['text'][:50] + '（' + TIME_LABELS[claim['time_reference']['value']] + '）'
        else:
            label += raw_text(claim)[:65]
        item = dict(operation=operation, claim=copy.deepcopy(claim), record=copy.deepcopy(record),
                    correction=copy.deepcopy(correction), label=label, summary=summary,
                    epoch=self.state.epoch, scope=copy.deepcopy(self.scope),
                    conversation_id=self.state.conversation_id)
        ref = self.state.events.get(claim.get('relation', {}).get('target_event_id'))
        item['target_revision'] = ref.get('record_revision') if ref else None
        self.pending[token] = item
        self._seals[token] = digest(item)

    def _refresh_references(self):
        for event in list(self.state.events.values()):
            if event['reference_status'] != 'active' or event['record_revision'] is None:
                continue
            record = self.care_factory().get(self.scope, KIND, event['id'])
            if not record or record['status'] != 'ACTIVE' or record['revision'] != event['record_revision']:
                self.state.invalidate(event['id'])

    def list_records(self):
        # Explicit UI command. No saved history is hydrated into model context.
        self.network = 'not_sent'
        self.pending.clear()
        self._seals.clear()
        lines = []
        for record in self.care_factory().records(self.scope, KIND)[:30]:
            status = '已撤回' if record['status'] == 'RETRACTED' else '已保存'
            lines.append(f"{status} · {brief_claim(record['claim'])}\n原话：{raw_text(record['claim'])}\n记录号：{record['id']} · 版本 {record['revision']}")
            if record['status'] == 'ACTIVE' and record['evidence_method'] == 'SELF_REPORTED':
                correction = dict(source_message_id=uuid4().hex, raw_text='查看自报记录后逐条确认撤回',
                                  dialogue_act='record_selection', interpretation_version='explicit-ui')
                self._propose('retract', record['claim'], record=record, correction=correction)
        return self.result('以下是本机自报记录，与摄像头评估分开。请按原话选择要撤回的具体一条。',
                           record_summary='\n\n'.join(lines) or '尚无已保存自报。',
                           receipt=dict(status='read', text='只读查看；没有修改记录。'))

    def turn(self, text, *, now=None, config=None, transport=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise ValueError('请输入 1–500 字的问题')
        self.network = 'not_sent'
        self.pending.clear()
        self._seals.clear()
        # Existing pre-network privacy veto is not a statement/relationship interpreter.
        if parse_privacy_intent(text) != 'none':
            self.state.clear()
            return None
        self._refresh_references()
        turn = self.state.new_turn(text, now.isoformat() if now else None)
        try:
            if config is not None:
                config.validate()
                self.network = 'may_have_been_sent'
            payload = interpret(turn, self.state, config, transport=transport)
            claims = validate_interpretation(payload, turn, self.state)
        except (GroundingError, ModelError, ValueError, OSError) as exc:
            self.state.accept(turn, 'clarification', [])
            validation = isinstance(exc, GroundingError)
            result = self.result(str(exc) if validation else
                                 '结构化对话理解暂不可用，未生成保存或撤回操作。普通本地康复查询仍可用。')
            result['extraction_status'] = 'needs_clarification' if validation else 'unavailable'
            result['mode_label'] = '引用核验未通过 · 未保存' if validation else '结构化对话理解暂不可用'
            return result
        act = payload['dialogue_act']
        self.state.accept(turn, act, claims)
        for claim in claims:
            if act == 'correction':
                if claim['certainty'] != 'certain' or claim['proposition']['polarity'] == 'hypothetical':
                    continue
                target = self.state.resolve('event', claim['relation']['target_event_id'])
                if target is None or not save_eligible(target):
                    continue
                record = (self.care_factory().get(self.scope, KIND, target['id'])
                          if target['record_revision'] is not None else None)
                if record is None or (record['status'] == 'ACTIVE' and record['evidence_method'] == 'SELF_REPORTED'):
                    self._propose('retract', target, record=record, correction=claim)
            elif save_eligible(claim):
                self._propose('save', claim)
        if not claims and act in {'chat', 'question', 'request'}:
            return None
        return self.result(statement_reply(claims, act) if act != 'correction' or self.pending else
                           '引用的内容不是可撤回的本人自报。请点击查看记录，按原话选择。', claims=claims, dialogue_act=act)

    def act(self, token):
        self.network = 'not_sent'
        if token == 'cancel':
            self.pending.clear()
            self._seals.clear()
            return self.result('已取消待确认操作。', receipt=dict(status='cancelled', text='没有新增或更改自报。'))
        if token not in self.pending:
            raise ValueError('确认已失效，请重新说明或查看自报记录')
        operation = self.pending[token]
        if (self._seals.get(token) != digest(operation) or operation['scope'] != self.scope
                or operation['conversation_id'] != self.state.conversation_id or operation['epoch'] != self.state.epoch):
            raise ValueError('确认内容或对话范围已变化，请重新核对')
        claim = operation['claim']
        if operation['operation'] == 'save':
            if not save_eligible(claim) or not self.state.resolve('event', claim['id']):
                raise ValueError('此解释不能保存为本人自报')
            target_id = claim['relation']['target_event_id']
            if operation['target_revision'] is not None:
                target = self.care_factory().get(self.scope, KIND, target_id)
                if not target or target['status'] != 'ACTIVE' or target['revision'] != operation['target_revision']:
                    raise ValueError('关联记录已更新，请重新核对')
            item = dict(id=claim['id'], claim=copy.deepcopy(claim), source_message_id=claim['source_message_id'],
                        status='ACTIVE', evidence_method='SELF_REPORTED', origin='AGENT_USER_STATEMENT',
                        created_utc=utc_now(), shared=False, remote_delivery='NOT_CONNECTED', corrections=[],
                        relations=[copy.deepcopy(claim['relation'])] if target_id else [],
                        consent=dict(method='explicit_button', at_utc=utc_now(), action_id=token))
            stored = self.care_factory().save(self.scope, KIND, item)
            self.state.saved(stored['id'], stored['revision'])
            status, note = 'saved', '已保存到本机自报记录；不是摄像头评估，未分享家属。'
        elif operation['record'] is None:
            if not self.state.resolve('event', claim['id']):
                raise ValueError('被引用的临时自述已失效')
            stored = dict(id=claim['id'], revision=0)
            self.state.invalidate(claim['id'])
            status, note = 'discarded', '已撤销这条未保存自述；没有改写任何数据库记录。'
        else:
            item = copy.deepcopy(operation['record'])
            if item['evidence_method'] != 'SELF_REPORTED' or item['status'] != 'ACTIVE':
                raise ValueError('只能撤回有效的本人自报')
            correction = operation['correction']
            item['status'] = 'RETRACTED'
            item['corrections'].append(dict(source_message_id=correction['source_message_id'],
                text=correction['raw_text'], at_utc=utc_now(), action_id=token, method='explicit_button',
                interpretation=copy.deepcopy(correction)))
            stored = self.care_factory().save(self.scope, KIND, item, expected_revision=item['revision'])
            self.state.invalidate(claim['id'])
            status, note = 'retracted', '已撤回这一条自报，保留原话与更正轨迹；原始评估和其他自报未修改。'
        del self.pending[token]
        del self._seals[token]
        receipt = dict(status=status, record_id=stored['id'], revision=stored['revision'],
                       source_message_id=claim['source_message_id'], text=note + '\n记录号：' + stored['id'])
        return self.result('已按你核对并确认的内容处理。', claims=[claim], receipt=receipt)
