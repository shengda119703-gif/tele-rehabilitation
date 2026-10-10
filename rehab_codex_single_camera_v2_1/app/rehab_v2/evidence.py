from __future__ import annotations

from dataclasses import dataclass, field
import math

from ..quality import PoseAnalyzer
from .protocols import protocol


@dataclass(frozen=True)
class MetricEvidence:
    value: float | None
    unit: str
    valid: bool
    reason: str | None
    evidence_kind: str
    observed_at_s: float | None
    computed_at_s: float
    age_ms: float
    required_joints: tuple[str, ...]

    def observable(self, max_age_ms):
        return (self.valid and self.evidence_kind in ('observed', 'filtered')
                and self.value is not None and math.isfinite(self.value)
                and self.observed_at_s is not None and math.isfinite(self.observed_at_s)
                and math.isfinite(self.computed_at_s)
                and math.isfinite(self.age_ms) and 0 <= self.age_ms <= max_age_ms
                and self.computed_at_s >= self.observed_at_s
                and abs((self.computed_at_s-self.observed_at_s)*1000-self.age_ms) < .001)


@dataclass(frozen=True)
class EvidenceFrame:
    seq: int
    time_s: float
    source_epoch: str
    track_key: str | None
    schema_id: str
    model_manifest_id: str
    size: tuple[int, int]
    metrics: dict[str, MetricEvidence]
    observation_status: str
    source_ref: str = 'internal-replay'
    coordinate_space: str = 'raw_image_pixels'
    time_basis: str = 'mapped_source_seconds'
    reasons: tuple[str, ...] = field(default_factory=tuple)


class EvidenceAdapter:
    """Reuse the legacy anatomical selection and causal EMA; no future samples.

    Processing age must be supplied by the owning process, in a mapped source
    clock. No subtraction of monotonic clocks received from another process.
    """
    def __init__(self, exercise_id, side='left', *, max_gap_s=.5):
        self.spec = protocol(exercise_id, side)
        self.max_gap_s = max_gap_s
        self.analyzer = PoseAnalyzer(side=side, exercise_id=None,
                                     max_gap=max_gap_s, tau=.12)
        self.last_signature = None

    def analyze(self, pose, *, processing_age_ms=0., time_basis='mapped_source_seconds'):
        if (not math.isfinite(processing_age_ms) or processing_age_ms < 0
                or time_basis not in ('mapped_source_seconds', 'nominal_video_seconds', 'opencv_media_pts')):
            raise ValueError('invalid_processing_age_or_time_basis')
        signature = (pose.context, pose.model_manifest_id, pose.size, pose.schema_id,
                     pose.coordinate_space, pose.keypoint_order_version)
        if signature != self.last_signature:
            self.analyzer = PoseAnalyzer(side=self.spec['side'], exercise_id=None, max_gap=self.max_gap_s, tau=.12)
            self.last_signature = signature
        observation = self.analyzer.analyze(pose)
        joints = {self.spec['metric']: self.spec['required_joints'],
                  **self.spec['optional_quality_metrics']}
        metrics = {}
        for name, required in joints.items():
            metric = observation.metrics.get(name)
            valid = metric is not None and metric.valid
            metrics[name] = MetricEvidence(
                metric.value if valid else None, 'degree', bool(valid),
                metric.reason if metric else 'metric_not_provided', 'filtered',
                pose.time_s if valid else None, pose.time_s + processing_age_ms / 1000,
                processing_age_ms, tuple(required))
        return EvidenceFrame(pose.seq, pose.time_s, pose.context.epoch, observation.track_key,
                             pose.schema_id, pose.model_manifest_id, pose.size, metrics,
                             observation.status, pose.context.source_ref, pose.coordinate_space,
                             time_basis, tuple(observation.reasons))
