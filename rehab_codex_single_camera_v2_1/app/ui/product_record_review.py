"""Read-only explanation of existing Agent Runtime receipts; never interprets input."""
from .product_widgets import escape, display_time

SUBJECTS={'self':'本人','spouse':'配偶','father':'父亲','mother':'母亲','family_other':'其他家人','unknown':'人物待确认'}
CLAIM_STATES={'occurred':'已发生','negated':'否定','hypothetical':'假设','uncertain':'不确定','near_miss':'险些发生'}
TIME_SCOPES={'today':'今天','yesterday':'昨天','lastNight':'昨晚','historical':'过去','unknown':'时间待确认'}


def record_review(turn):
    """Return plain receipt + escaped details from the actual completed turn."""
    understanding=turn.get('understanding') or {}
    plan=turn.get('appliedChanges') or {}
    persistence=(turn.get('persistence') or {}).get('status')
    events=plan.get('eventsToAppend') or []
    family=plan.get('familyEventsToAppend') or []
    private=(turn.get('reply') or {}).get('persisted') is False
    if private:
        title='本轮不记录 · 这段对话不保存到本机记录'
    elif persistence not in ('saved','loaded'):
        title='记录尚未确认保存 · 请核对本机状态'
    elif understanding.get('clarificationQuestion'):
        title='需要你补充确认 · 请回答管家的澄清问题'
    elif plan.get('correction'):
        title='更正请求已处理 · 请核对更新后的记录'
    elif events or family:
        title=f'已保存到本机 · 本人健康 {len(events)} 项 / 家人情况 {len(family)} 项'
    else:
        title='管家已回复 · 本轮没有新增健康事实'
    details=['<h3>管家如何理解这段表达</h3>']
    for claim in understanding.get('claims') or []:
        meaning=' · '.join((SUBJECTS.get(claim.get('subject'),'人物待确认'),
            CLAIM_STATES.get(claim.get('status'),'状态待确认'),TIME_SCOPES.get(claim.get('timeScope'),'时间待确认')))
        details.append('<p><b>'+escape(meaning)+'</b><br>'+escape(claim.get('text',''))+
                       ('<br>事件日期：'+escape(claim['eventDate']) if claim.get('eventDate') else '')+'</p>')
    if not understanding.get('claims'):details.append('<p>本轮没有结构化健康事实；请以管家回复和已保存记录为准。</p>')
    question=understanding.get('clarificationQuestion')
    if question:details.append('<p>待确认：'+escape(question)+'</p>')
    details.append('<h3>实际记录结果</h3><p>'+escape(title)+'</p>')
    for event in ([] if private else events):
        value=event.get('observation') or event.get('measurement') or event.get('labResult') or {}
        text=value.get('text') or ' '.join(str(value.get(k,'')) for k in ('metric','name','value','unit')).strip()
        details.append('<p>'+escape(text)+'<br>'+escape(display_time(event.get('timestamp')))+'</p>')
    details.append('<p>否定、假设、人物和时间不明确的表达不等于本人已发生事实。需要更正时直接在输入区说明原话与正确情况；处理结果以更新后的健康记录为准。</p>')
    details.append('<p>本机保存不等于已共享或送达家属。共享范围仍由原授权与审计决定。</p>')
    return title,''.join(details)
