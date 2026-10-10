"""Pure derived report. The repository alone owns immutable training facts."""
from __future__ import annotations

from .compatibility import comparison_contract

REPORT_INPUT_FIELDS = ('session_id', 'source_epoch', 'frozen_plan', 'source',
                       'snapshot', 'end_reason', 'feedback_status', 'feedback_revision')


def build_report(item):
    snapshot = item['snapshot']
    contract = comparison_contract(item)
    return dict(session_id=item['session_id'], end_reason=item['end_reason'],
                completed_reps=snapshot['completed'], visual_evidence=snapshot,
                source=item['source'], frozen_plan=item['frozen_plan'],
                feedback_status=item['feedback_status'],
                interpretation='observed_training_facts_not_diagnosis',
                protocol_compatibility=contract,
                evidence_fingerprint=contract['evidence_fingerprint'])
