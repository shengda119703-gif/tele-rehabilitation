"""Conservative local claim acceptance and consent-bound self-report operations.

Adapted from Ankang understanding/elderTurn/correction, not its clinical rules.
No clinical store, camera, model or task executor is available to this module.
"""
from __future__ import annotations

import copy
import re
from datetime import datetime, timedelta
from uuid import uuid4

from .agent_privacy import parse_privacy_intent
from .silver_store import scope_key
from .domain import utc_now

KIND = 'agent_self_report'
SYMPTOMS = r'头晕|胸闷|不舒服|疲劳|乏力|无力|麻木|恶心|气短|摔倒|跌倒|(?:头|肩|腰|腿|膝|手|脚|背|胸|肚子)(?:疼|痛)|疼痛|很累|有点累'
FAMILY = r'妈妈|母亲|我妈|爸爸|父亲|我爸|家人|家里人|老伴|爱人|丈夫|妻子|老公|老婆|儿子|女儿|爷爷|奶奶|外公|外婆|哥哥|姐姐|弟弟|妹妹|他|她'
CORRECTION = r'说错|讲错|更正|纠正|撤回.*(?:自报|自述|说的)|撤销.*(?:自报|自述|说的)'
LABELS = {'self': '本人', 'family': '家人/他人', 'unknown': '未知',
          'current': '今天/现在', 'past': '过去', 'future': '将来',
          'occurred': '发生', 'negated': '否定', 'hypothetical': '假设', 'uncertain': '不确定'}


def parse_statements(text, message_id, now=None):
    """Bounded symptom vocabulary; no guessed subject/date or cross-turn carryover.

    Unknown constructions are not admissible. Multiple predicates in one clause
    with mixed polarity deliberately require separate restatement.
    """
    now = now or datetime.now().astimezone()
    rows = []
    subject, time_scope, event_date = 'unknown', 'unknown', None
    for clause in filter(None, re.split(r'[，,。；;！!\n]|(?:但是|不过|而且|然后)', text)):
        clause = clause.strip()
        matches = list(re.finditer(SYMPTOMS, clause))
        if not matches:
            continue
        family = bool(re.search(FAMILY, clause))
        # Remove possessive kinship before counting an explicit "我".
        self_text = re.sub(r'我(?:的)?(?:妈妈|母亲|妈|爸爸|父亲|爸|家人|老伴|爱人|丈夫|妻子|老公|老婆|儿子|女儿)', '', clause)
        explicit_self = bool(re.search(r'我|本人', self_text))
        if family or explicit_self:
            subject = 'unknown' if family and explicit_self else 'family' if family else 'self'
            # A new subject cannot inherit another person's event time.
            time_scope, event_date = 'unknown', None
        if re.search(r'昨天|昨晚|前天|以前|过去|上周|去年|曾经|刚才', clause):
            time_scope = 'past'
            days = 2 if '前天' in clause else 1 if re.search(r'昨天|昨晚', clause) else 0 if '刚才' in clause else None
            event_date = (now.date()-timedelta(days=days)).isoformat() if days is not None else None
        elif re.search(r'明天|以后|将来|下周', clause):
            time_scope, event_date = 'future', None
        elif re.search(r'今天|现在|此刻|目前', clause):
            time_scope, event_date = 'current', now.date().isoformat()
        uncertain = re.search(r'可能|也许|好像|似乎|不确定|不清楚|不知道|是不是|是否|吗|[？?]|听说|说我|不是没|并非不|不能说没', clause)
        hypothetical = re.search(r'如果|假如|假设|万一|要是', clause)
        negated = re.search(r'没|没有|未|不再|不会|不曾|并非|不是|不怎么|不太|不(?=头晕|胸闷|疼|痛|累|疲劳|乏力|恶心|气短|摔倒|跌倒)', clause)
        status = 'hypothetical' if hypothetical else 'uncertain' if uncertain else 'negated' if negated else 'occurred'
        if status == 'occurred':
            # Positive acceptance is a small grammar, not a keyword match.
            # Quotation, questions about symptoms, recovery, and unfamiliar
            # syntax stay uncertain even if a known symptom occurs in them.
            remainder = re.sub(SYMPTOMS, '', clause)
            remainder = re.sub(FAMILY, '', remainder)
            remainder = re.sub(r'我自己|本人|我|今天|现在|此刻|目前|昨天|昨晚|前天|以前|过去|上周|去年|曾经|刚才|明天|以后|将来|下周', '', remainder)
            remainder = re.sub(r'请|帮|记录|记下|保存|一下|有一点|有点|一点|有些|感觉|觉得|一直|突然|确实|真的|还是|仍然|开始|出现|有|很|也|都|和|跟|与|又|了|啊|呀|呢|的|[\s、]', '', remainder)
            if remainder:
                status = 'uncertain'
        # Contradictory / mixed-time clauses must never produce current facts.
        if (re.search(r'昨天|以前|过去|刚才', clause) and re.search(r'今天|现在', clause)):
            time_scope, event_date = 'unknown', None
            status = 'uncertain'
        for match in matches:
            rows.append(dict(id=uuid4().hex, source_message_id=message_id, text=clause,
                             symptom=match.group(), subject=subject, time_scope=time_scope,
                             event_date=event_date, status=status, certainty='explicit' if status == 'occurred' else 'not_accepted',
                             received_utc=now.isoformat(), time_text=clause,
                             admissible=(subject == 'self' and time_scope in ('current', 'past') and status == 'occurred')))
    return rows


def describe(claim):
    return f"{claim['symptom']} · {LABELS[claim['subject']]} · {LABELS[claim['time_scope']]} · {LABELS[claim['status']]}" + (
        f" · {claim['event_date']}" if claim['event_date'] else '')


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

    def result(self, text, *, claims=(), receipt=None, record_summary=''):
        return dict(scope=copy.deepcopy(self.scope), version='agent-statements-1', at=utc_now(),
                    text=text, main_text=text, source_label='本机理解 / 本人自报',
                    mode='local', mode_label='本机结构化自述 · 未联网', shareable=False,
                    actions=[], evidence=[], tools=[], local_text='', understanding=copy.deepcopy(list(claims)),
                    evidence_summary='\n'.join(describe(c) for c in claims),
                    receipt=receipt or dict(status='not_saved', text='未写入自报记录。'),
                    record_summary=record_summary,
                    proposed_actions=[dict(id=k, label=v['label'], summary=v['summary'],
                                           operation=v['operation'], requires_confirmation=True)
                                      for k, v in self.pending.items()],
                    privacy_notice='本轮未发送给 DeepSeek；自报仅在明确确认后保存到本机，未分享家属。',
                    privacy_status=dict(network='not_sent', family='not_shared'),
                    delivery_status='NOT_CONNECTED')

    def propose(self, operation, claim, *, record=None, correction_message=None, correction_text=''):
        token = uuid4().hex
        summary = describe(claim) + '\n原话：' + claim['text']
        label = (('确认保存' if operation == 'save' else '确认撤回') + '：' + claim['symptom']
                 + '（' + LABELS[claim['time_scope']] + ' · ' + (claim['event_date'] or '日期未明确') + '）')
        self.pending[token] = dict(operation=operation, claim=copy.deepcopy(claim),
                                   record=copy.deepcopy(record), correction_message=correction_message,
                                   correction_text=correction_text,
                                   label=label, summary=summary)

    def turn(self, text, *, now=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 500:
            raise ValueError('请输入 1–500 字的问题')
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
        claims = parse_statements(text, message_id, now)
        if re.search(CORRECTION, text):
            # Explicit family/ambiguous correction cannot retract self facts.
            if re.search(FAMILY, text):
                return self.result('这次更正涉及家人或主体不明确，请查看自报记录，按原话选择对应的一条。', claims=claims)
            tags = {c['symptom'] for c in claims}
            targets = [c for c in previous if c['admissible'] and (not tags or c['symptom'] in tags)]
            for claim in targets:
                record = self.care_factory().get(self.scope, KIND, claim['id'])
                if record is None or record['status'] == 'ACTIVE':
                    self.propose('retract', claim, record=record, correction_message=message_id, correction_text=text)
            return self.result('请核对下面的原话，选择要撤回的具体自报；其他自报和原始评估不变。'
                               if self.pending else '刚才那条消息没有可更正的本人自报，未更改任何记录。'
                               '若要更正较早记录，请点“查看自报记录”选择具体一条。', claims=claims)
        self.last_claims = copy.deepcopy(claims)
        if not claims:
            return None
        for claim in claims:
            if claim['admissible']:
                self.propose('save', claim)
        text_reply = ('我把你的话分成了下面的自述，请核对人物、时间和是否发生。'
                      '只有点击对应的“确认保存”才会入库；也可以取消或重新说明。')
        if not self.pending:
            text_reply = ('这句话没有形成可保存的本人明确自报。家人的情况、否定、假设和不确定表达不会记成本人不适。'
                          '如需记录，请分别说明“谁、什么时候、实际发生了什么”。')
        if any(c['subject'] == 'self' and c['time_scope'] == 'current' and c['status'] in ('occurred', 'uncertain') for c in claims):
            text_reply += '如果你现在确有不适，请先暂停训练。'
        return self.result(text_reply, claims=claims)

    def act(self, token):
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
            if not (claim['admissible'] and claim['subject'] == 'self' and claim['status'] == 'occurred'
                    and claim['time_scope'] in ('current', 'past')):
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
