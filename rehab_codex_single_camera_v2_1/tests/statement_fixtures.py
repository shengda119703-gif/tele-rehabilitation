"""Explicit synthetic interpretations. Imported only by tests/offline QA."""
import json

from app.agent_conversation import ModelConfig
from app.agent_statements import StatementSession as ProductionSession

CONFIG = ModelConfig('https://api.deepseek.com', 'deepseek-flash', 'synthetic-not-a-key', True)


def source(text, kind='current', rid='current'):
    return dict(kind=kind, id=rid, quote=text)


def statement(text, *, subject='self', time='current', polarity='affirmed', certainty='certain',
              proposition=None, relation='none', target=None):
    proposition = proposition or text
    return dict(raw_text=text, evidence_span=text,
                subject=dict(value=subject, source=None if subject == 'unknown' else source(text)),
                time_reference=dict(value=time, source=None if time == 'unknown' else source(text)),
                proposition=dict(text=proposition, polarity=polarity, source=source(proposition)),
                certainty=certainty, context_refs=[dict(kind='event', id=target)] if target else [],
                relation=dict(type=relation, target=dict(kind='event', id=target) if target else None))


def interpretation(text, *, act='new_report', target=None, **kwargs):
    relation = {'correction':'corrects', 'state_change':'updates', 'follow_up':'elaborates'}.get(act, 'none')
    return dict(dialogue_act=act, statements=[statement(text, relation=relation, target=target, **kwargs)])


# Expected provider interpretations of pre-existing UI examples, not a parser.
CASES = {
    '昨天妈妈头晕': dict(subject='family', time='past', proposition='头晕'),
    '我今天没头晕': dict(polarity='negated', proposition='头晕'),
    '我头晕': dict(time='unknown', proposition='头晕'),
    '头晕': dict(subject='unknown', time='unknown'),
    '腿疼': dict(subject='unknown', time='unknown'),
    '我腿疼': dict(time='unknown', proposition='腿疼'),
    '我今天头晕': dict(proposition='头晕'),
    '我今天腿疼': dict(proposition='腿疼'),
    '我昨天头晕': dict(time='past', proposition='头晕'),
    '妈妈今天腿疼': dict(subject='family', proposition='腿疼'),
    '如果我现在头晕': dict(polarity='hypothetical', proposition='头晕'),
    '如果我今天头晕': dict(polarity='hypothetical', proposition='头晕'),
    '我现在可能头晕': dict(certainty='uncertain', proposition='头晕'),
    '我今天可能头晕': dict(certainty='uncertain', proposition='头晕'),
    '我明天头晕': dict(time='future', proposition='头晕'),
    '我今天发烧': dict(proposition='发烧'),
    '我今天咳嗽': dict(proposition='咳嗽'),
    '我今天睡不好': dict(proposition='睡不好'),
    '我今天没睡好': dict(proposition='没睡好'),
    '我今天胃口不好': dict(proposition='胃口不好'),
    '我今天没胃口': dict(proposition='没胃口'),
    '我今天不舒服': dict(proposition='不舒服'),
    '我今天心情差': dict(proposition='心情差'),
    '我今天头有点沉': dict(proposition='头有点沉'),
    '昨天摔了一跤': dict(subject='unknown', time='past', proposition='摔了一跤'),
    '我昨天摔了一跤': dict(time='past', proposition='摔了一跤'),
    '妈妈今天发烧': dict(subject='family', proposition='发烧'),
    '如果明天发烧': dict(subject='unknown', time='future', polarity='hypothetical', proposition='发烧'),
    '我今天没有咳嗽': dict(polarity='negated', proposition='咳嗽'),
}


def transport(config, messages):
    packet = json.loads(messages[-1]['content'])
    text = packet['current']['raw_text']
    events = packet['context']['events']
    if text in ('我刚才说错了', '我刚才说错了，没有头晕'):
        focus = packet['context']['focus']
        targets = ([e for e in events if e['proposition']['text'] == '头晕'][-1:]
                   if text == '我刚才说错了，没有头晕' else [e for e in events if e['id'] == focus])
        result = dict(dialogue_act='correction', statements=[statement(text, relation='corrects', target=e['id']) for e in targets])
    elif text in ('我今天头晕，我今天腿疼', '我昨天头晕，妈妈今天腿疼'):
        result = dict(dialogue_act='new_report', statements=[])
        for part in text.split('，'):
            item = statement(text, **CASES[part])
            item['evidence_span'] = part
            result['statements'].append(item)
    else:
        result = interpretation(text, **CASES[text])
    return json.dumps(result, ensure_ascii=False)


class StatementSession(ProductionSession):
    def turn(self, text, **kwargs):
        # Historical UI tests use this explicit read command helper.
        if text == '查看自报记录':
            return self.list_records()
        kwargs.setdefault('config', CONFIG)
        kwargs.setdefault('transport', transport)
        return super().turn(text, **kwargs)
