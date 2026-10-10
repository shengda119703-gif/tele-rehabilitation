from __future__ import annotations

from ..domain import digest


def comparison_contract(item):
    """Comparable measurement meaning is separate from this session's identity.

    Concrete video hashes/run IDs/starting times are evidence identity. Absolute
    projected angles do not depend on a different comfortable starting angle;
    a relative excursion does. This is not anatomical ROM comparability.
    """
    snapshot = item['snapshot'] or {}
    spec = snapshot.get('protocol', item['frozen_plan'].get('protocol', {}))
    measurement = snapshot.get('measurement_contract', {})
    signature = measurement.get('signature') or []
    domain = dict(schema_id=signature[1] if len(signature) >= 5 else None,
                  model_manifest_id=signature[2] if len(signature) >= 5 else None,
                  time_basis=signature[4] if len(signature) >= 5 else None,
                  coordinate_space=measurement.get('coordinate_space'),
                  preprocess_version=measurement.get('preprocess_version'))
    common = dict(protocol_version=spec.get('protocol_version'), exercise_id=spec.get('exercise_id'),
        metric=spec.get('metric'), metric_version=spec.get('metric_version'), unit=spec.get('unit'),
        reference_axis=spec.get('baseline_reference'), source_kind=item['source']['source_kind'],
        usage_context=item['source']['usage_context'], view=spec.get('view'), side=spec.get('side'),
        domain=domain)
    baseline = snapshot.get('baseline')
    relative = dict(common, baseline=(dict(raw_value=baseline['raw_value'], unit=baseline['unit'],
        reference=baseline['reference']) if baseline else None))
    return dict(version='rehab-comparison-1', absolute_metric=common, relative_excursion=relative,
        target_definition=spec.get('target_definition'),
        scope='same_projected_metric_not_clinical_anatomical_ROM',
        evidence_fingerprint=digest(dict(session_id=item['session_id'], source_epoch=item['source_epoch'],
            frozen_plan=item['frozen_plan'], source=item['source'], snapshot=snapshot)))


def comparable(left, right, *, measure='absolute_metric'):
    if measure not in ('absolute_metric', 'relative_excursion'):
        raise ValueError('unsupported_comparison_measure')
    a, b = comparison_contract(left)[measure], comparison_contract(right)[measure]
    if any(value is None for value in a.values()) or any(value is None for value in a['domain'].values()):
        return dict(comparable=False, reason='missing_measurement_contract', clinical_comparable=False)
    if any(value is None for value in b.values()) or any(value is None for value in b['domain'].values()):
        return dict(comparable=False, reason='missing_measurement_contract', clinical_comparable=False)
    changes = [key for key in a if a[key] != b[key]]
    return dict(comparable=not changes, reason='compatible' if not changes else 'contract_changed',
                changed_fields=changes, clinical_comparable=False)
