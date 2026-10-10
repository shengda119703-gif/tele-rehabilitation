from __future__ import annotations

import hashlib
import json
from pathlib import Path


def artifact_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def supports(card, request):
    checks = {'input_domain': 'unsupported_input_domain', 'schema_id': 'unsupported_schema',
              'coordinate_space': 'unsupported_coordinate_space', 'feature_version': 'unsupported_features'}
    for key, reason in checks.items():
        if request.get(key) != card.get(key):
            return False, reason
    for key, allowed in [('exercise_id', 'actions'), ('side', 'sides'),
                         ('camera_view', 'camera_views'), ('protocol_version', 'protocol_versions')]:
        if request.get(key) not in card.get(allowed, []):
            return False, 'unsupported_' + key
    if card.get('license_status') != 'verified_dataset_license':
        return False, 'unverified_license'
    if card.get('role') != 'rep_quality_candidate' or not card.get('after_end_only'):
        return False, 'unsupported_model_role'
    return True, None


class ShadowSequence:
    """Domain/epoch gate for a research-only candidate, never a repetition source.

    A predictor is injected by the offline harness. No heavy framework, model
    loading or automatic download runs on application import. Even in research
    mode its output is not a metric/rep/eligibility/cue authority.
    """
    def __init__(self, card, predictor, *, research_mode=False, max_steps=3000):
        self.card, self.predictor, self.research_mode = card, predictor, research_mode
        self.max_steps = max_steps
        self.context, self.frames, self.last_seq = None, [], -1
        self.overflow = False

    def begin(self, session_id, calibration_epoch):
        self.context = (session_id, calibration_epoch)
        self.frames, self.last_seq, self.overflow = [], -1, False

    def append(self, session_id, calibration_epoch, seq, feature):
        if (session_id, calibration_epoch) != self.context or seq <= self.last_seq:
            return False
        self.last_seq = seq
        if len(self.frames) >= self.max_steps:
            self.overflow = True
            return False
        self.frames.append(feature)
        return True

    def finish(self, session_id, calibration_epoch, request):
        ok, reason = supports(self.card, request)
        if not ok:
            return dict(status=reason, fallback='versioned_rules', authoritative=False)
        if not self.research_mode:
            return dict(status='offline_research_only', fallback='versioned_rules', authoritative=False)
        if (session_id, calibration_epoch) != self.context or self.overflow or not self.frames:
            return dict(status='unavailable_session_evidence', authoritative=False)
        result = self.predictor(self.frames)
        self.frames = []
        return dict(status='shadow_candidate', output=result, evidence_kind='predicted',
                    model_id=self.card['model_id'], authoritative=False,
                    cannot_modify=['completed_reps', 'plan_progress', 'eligibility', 'dosage', 'current_cue'])
