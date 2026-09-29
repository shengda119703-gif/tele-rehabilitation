"""Consent-bound self-report operations using validated open model extraction.

Adapted from Ankang understanding/elderTurn/correction, not its clinical rules.
No clinical store, camera or task executor is available to this module.
"""
from __future__ import annotations

import copy
import re
from uuid import uuid4

from .agent_privacy import parse_privacy_intent
from .silver_store import scope_key
from .domain import utc_now
from .agent_conversation import ModelError
from .agent_extraction import FAMILY, ExtractionError, extract_statements, revalidate_claim

KIND = 'agent_self_report'
LOCAL_QUERIES = {'今天该练什么', '今天练什么', '我的评估结果', '查看历史记录',
                 '今天不想训练', '查看训练计划', '查看身体档案', '继续'}
CORRECTION = r'说错|讲错|更正|纠正|撤回.*(?:自报|自述|说的)|撤销.*(?:自报|自述|说的)'
LABELS = {'self': '本人', 'family': '家人/他人', 'unknown': '未知',
          'current': '今天/现在', 'past': '过去', 'future': '将来',
          'occurred': '发生', 'negated': '否定', 'hypothetical': '假设', 'uncertain': '不确定'}


def concept_text(claim):
    """Read compatibility only; legacy records are never re-parsed or rewritten."""
    return claim.get('concept', claim.get('symptom', claim.get('text', '自述')))


def describe(claim):
    return f"{concept_text(claim)} · {LABELS[claim['subject']]} · {LABELS[claim['time_scope']]} · {LABELS[claim['status']]}" + (
        f" · {claim['event_date']}" if claim['event_date'] else '')


def time_label(claim):
    """Presentation only: never resolves an unknown time or changes admission."""
    scope = claim['time_scope']
    if scope == 'unknown':
        return '时间待确认'
    words = {'current': ('现在', '此刻', '目前', '今天'),
             'past': ('前天', '昨晚', '昨天', '刚才', '上周', '去年', '以前', '过去'),
             'future': ('明天', '以后', '将来', '下周')}[scope]
    return next((word for word in words if word in claim['time_text']),
                {'current': '今天/现在', 'past': '之前', 'future': '将来'}[scope])


def brief_claim(claim):
    parts = [{'self': '本人', 'family': '家人', 'unknown': '人物待确认'}[claim['subject']],
             time_label(claim), concept_text(claim)]
    if claim['status'] != 'occurred':
        parts.append(LABELS[claim['status']])
    return ' · '.join(parts)


def statement_reply(claims):
    """Respond to known dimensions and ask only for the next missing dimension.

    This function cannot change claims or authorize persistence.
    """
    replies, accepted = [], []
    for claim in claims:
        subject, status, concept = claim['subject'], claim['status'], concept_text(claim)
        when = '' if claim['time_scope'] == 'unknown' else time_label(claim)
        who = (re.search(FAMILY, claim['text']).group() if subject == 'family'
               and re.search(FAMILY, claim['text']) else '家人')
        if subject == 'unknown':
            line = f'你提到的{concept}，是你本人还是家人的情况？'
        elif status == 'hypothetical':
            line = f'你说的{concept}是一个假设，不会记录成已经发生。'
            if subject == 'family':
                line += '这也不会记到你的本人自报记录里。'
        elif status == 'negated':
            line = f'明白，你说的是“{claim["text"]}”。'
            line += ('这是家人的情况，不会记到你的本人自报记录里。' if subject == 'family'
                     else '这不会记录成你的不适。')
        elif status == 'uncertain':
            line = f'关于{who if subject == "family" else "你"}{when}提到的{concept}，我还不能确定这件事是否实际发生。'
            line += ('这是家人的情况，不会记到你的本人自报记录里。' if subject == 'family'
                     else '你能确认是否确实发生了吗？')
        elif subject == 'family':
            line = f'明白，你说的是{who}{when}{concept}。这是家人的情况，不会记到你的本人自报记录里。'
        elif claim['time_scope'] == 'unknown':
            line = f'你是说现在正在{concept}，还是之前发生过{concept}？'
        elif claim['time_scope'] == 'future':
            line = f'你说的是将来的{concept}，不会记录成已经发生。'
        elif claim['admissible']:
            accepted.append(f'{when}{concept}')
            continue
        else:
            line = '这条自述还需要你核对，暂不保存。'
        if line not in replies:
            replies.append(line)
    if accepted:
        replies.insert(0, '你说自己' + '，'.join(dict.fromkeys(accepted)) + '。请核对下面的原话，逐条点击“确认保存”后才会记录。')
    if any(c['subject'] == 'self' and c['time_scope'] == 'current'
           and c['status'] in ('occurred', 'uncertain') for c in claims):
        replies.append('如果你现在确有不适，请先暂停训练。')
    return '\n'.join(replies)


class StatementSession:
    """Owned by one dialog and scope, on the existing optional-service queue.

    The UI receives opaque action tokens, never executable model instructions.
    Save/retract commands can only use a currently displayed, locally made token.
    """
    def __init__(self, scope, care_factory):
        self.scope = scope_key(scope)
        self.care_factory = care_factory
        self.pending = {}
        self.last_claims = []
        self.network = 'not_sent'

    def result(self, text, *, claims=(), receipt=None, record_summary=''):
        return dict(scope=copy.deepcopy(self.scope), version='agent-statements-2', at=utc_now(),
                    text=text, main_text=text, source_label='用户原话 · 本机核对',
                    mode='local', mode_label=('DeepSeek 抽取 · 本机核对' if self.network != 'not_sent' else '本机自报操作 · 未联网'), shareable=False,
                    actions=[], evidence=[], tools=[], local_text='', understanding=copy.deepcopy(list(claims)),
                    evidence_summary='\n'.join(describe(c) for c in claims),
                    receipt=receipt or dict(status='not_saved', text='未写入自报记录。'),
                    record_summary=record_summary,
                    proposed_actions=[dict(id=k, label=v['label'], summary=v['summary'],
                                           operation=v['operation'], requires_confirmation=True)
                                      for k, v in self.pending.items()],
                    privacy_notice=('本轮未发送给 DeepSeek；' if self.network == 'not_sent' else '本轮文字已按授权提交 DeepSeek 抽取（服务失败时可能已发送）；')
                                   + '自报仅在明确确认后保存到本机，未分享家属。',
                    privacy_status=dict(network=self.network, family='not_shared'),
                    delivery_status='NOT_CONNECTED')

    def propose(self, operation, claim, *, record=None, correction_message=None, correction_text=''):
        token = uuid4().hex
        summary = describe(claim) + '\n原话：' + claim['text']
        label = (('确认保存' if operation == 'save' else '确认撤回') + '：' + concept_text(claim)
                 + '（' + LABELS[claim['time_scope']] + ' · ' + (claim['event_date'] or '日期未明确') + '）')
        self.pending[token] = dict(operation=operation, claim=copy.deepcopy(claim),
                                   record=copy.deepcopy(record), correction_message=correction_message,
                                   correction_text=correction_text,
                                   label=label, summary=summary)

    def turn(self, text, *, now=None, config=None, transport=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise ValueError('请输入 1–500 字的问题')
        self.network = 'not_sent'
        previous = self.last_claims
        self.last_claims = []
        self.pending.clear()
        # Privacy dominates all acceptance, correction, and recall operations.
        if parse_privacy_intent(text) != 'none':
            return None
        message_id = uuid4().hex
        if text.strip() == '查看自报记录':
            records = self.care_factory().records(self.scope, KIND)
            lines = []
            for record in records[:30]:
                state = '已撤回' if record['status'] == 'RETRACTED' else '已保存'
                lines.append(f"{state} · {describe(record['claim'])}\n原话：{record['claim']['text']}\n记录号：{record['id']} · 版本 {record['revision']}")
                if record['status'] == 'ACTIVE':
                    self.propose('retract', record['claim'], record=record, correction_message=message_id,
                                 correction_text='查看自报记录后，逐条确认撤回')
            return self.result('这里是当前用户、来源和情境下的本机自报记录（最近 30 条，含撤回）。'
                               '它们不是摄像头评估；可按原话选择要撤回的一条。',
                               record_summary='\n\n'.join(lines) or '尚无已保存自报。',
                               receipt=dict(status='read', text='只读查看；没有修改记录。'))
        if re.search(CORRECTION, text):
            # Explicit family/ambiguous correction cannot retract self facts.
            if re.search(FAMILY, text):
                return self.result('这次更正涉及家人或主体不明确，请查看自报记录，按原话选择对应的一条。', claims=[])
            # Exact quoted concept matching only; the model cannot select a record.
            tags = {concept_text(c) for c in previous if concept_text(c) in text}
            targets = [c for c in previous if c['admissible'] and (not tags or concept_text(c) in tags)]
            for claim in targets:
                record = self.care_factory().get(self.scope, KIND, claim['id'])
                if record is None or record['status'] == 'ACTIVE':
                    self.propose('retract', claim, record=record, correction_message=message_id, correction_text=text)
            return self.result('请核对下面的原话，选择要撤回的具体自报；其他自报和原始评估不变。'
                               if self.pending else '刚才那条消息没有可更正的本人自报，未更改任何记录。'
                               '若要更正较早记录，请点“查看自报记录”选择具体一条。', claims=[])
        # Exact read-only commands work without a model; this is not a health-word router.
        if text.strip() in LOCAL_QUERIES:
            return None
        try:
            if config is not None:
                config.validate()
                self.network = 'may_have_been_sent'
            claims = extract_statements(text, message_id, config, now=now, transport=transport)
        except ExtractionError as exc:
            result = self.result(str(exc))
            result['extraction_status'] = 'needs_clarification'
            result['mode_label'] = '结构化抽取未通过本机核对 · 未保存'
            return result
        except (ModelError, ValueError, OSError):
            result = self.result('结构化自报理解暂不可用，未生成保存操作。请连接 DeepSeek 或稍后重试；普通本地康复查询仍可用。')
            result['extraction_status'] = 'unavailable'
            result['mode_label'] = '结构化自报理解暂不可用 · 本地查询仍可用'
            return result
        self.last_claims = copy.deepcopy(claims)
        if not claims:
            return None
        for claim in claims:
            if claim['admissible']:
                self.propose('save', claim)
        return self.result(statement_reply(claims), claims=claims)

    def act(self, token):
        self.network = 'not_sent'
        if token == 'cancel':
            self.pending.clear()
            self.last_claims = []
            return self.result('已取消待确认操作。', receipt=dict(status='cancelled', text='没有新增或更改自报。'))
        if token not in self.pending:
            raise ValueError('确认已失效，请重新说明或查看自报记录')
        operation = self.pending[token]
        claim = operation['claim']
        if operation['operation'] == 'save':
            # Revalidate local admission, rather than trust UI payloads or LLM text.
            if not revalidate_claim(claim):
                raise ValueError('此陈述不能保存为本人自报')
            item = dict(id=claim['id'], claim=copy.deepcopy(claim), source_message_id=claim['source_message_id'],
                        status='ACTIVE', evidence_method='SELF_REPORTED', origin='AGENT_USER_STATEMENT',
                        created_utc=utc_now(), shared=False, remote_delivery='NOT_CONNECTED', corrections=[],
                        consent=dict(method='explicit_button', at_utc=utc_now(), action_id=token))
            stored = self.care_factory().save(self.scope, KIND, item)
            status, note = 'saved', '已保存到本机自报记录；不是摄像头评估，未分享家属。'
        elif operation['record'] is None:
            stored = dict(id=claim['id'], revision=0)
            status, note = 'discarded', '已撤销这条未保存自述；没有改写任何数据库记录。'
        else:
            item = copy.deepcopy(operation['record'])
            if item['evidence_method'] != 'SELF_REPORTED' or item['status'] != 'ACTIVE':
                raise ValueError('只能撤回有效的本人自报')
            item['status'] = 'RETRACTED'
            item['corrections'].append(dict(source_message_id=operation['correction_message'],
                                             text=operation['correction_text'],
                                             at_utc=utc_now(), action_id=token, method='explicit_button'))
            stored = self.care_factory().save(self.scope, KIND, item, expected_revision=item['revision'])
            status, note = 'retracted', '已撤回这一条自报，保留原话与更正轨迹；原始评估和其他自报未修改。'
        del self.pending[token]
        if status in ('retracted', 'discarded'):
            self.last_claims = [c for c in self.last_claims if c['id'] != claim['id']]
        receipt = dict(status=status, record_id=stored['id'], revision=stored['revision'],
                       source_message_id=claim['source_message_id'], text=note + '\n记录号：' + stored['id'])
        return self.result('已处理你确认的这一条。更正后的新情况请重新说明，再单独确认保存。'
                           if status != 'saved' else '已按你核对并确认的内容记录。', claims=[claim], receipt=receipt)
