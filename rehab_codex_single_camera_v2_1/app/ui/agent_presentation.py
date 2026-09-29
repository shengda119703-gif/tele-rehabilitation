"""Presentation only; the original result remains intact for details/audit."""
from ..agent_privacy import parse_privacy_intent
from ..agent_statements import brief_claim

WRITE_RECEIPTS = {'saved', 'retracted', 'discarded', 'cancelled'}


def without_record_ids(value):
    return '\n'.join(line for line in value.splitlines() if not line.startswith('记录号：'))


def present_result(result, user_text=''):
    claims = result.get('understanding', [])
    receipt = result.get('receipt', {})
    explicit_privacy = result.get('privacy_intent', 'none') != 'none' or parse_privacy_intent(user_text) != 'none'
    return dict(
        assistant=result.get('main_text', result['text']),
        local_text=result.get('local_text', ''),
        secondary='；'.join(dict.fromkeys(brief_claim(c) for c in claims)),
        receipt_text=without_record_ids(receipt.get('text', '')) if receipt.get('status') in WRITE_RECEIPTS else '',
        privacy_notice=result.get('privacy_notice', '') if explicit_privacy else '',
        record_summary=without_record_ids(result.get('record_summary', '')),
        evidence_summary=(result.get('evidence_summary', '') if not claims
                          and result.get('evidence_summary') != result.get('local_text') else ''),
        pending_summary='',
    )
