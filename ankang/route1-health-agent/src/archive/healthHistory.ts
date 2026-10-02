import type { CareTask, DayRecord, ElderProfile, FamilyHealthEvent, Finding, MetricKey } from '../types';
import { materializeHealthData, type HealthEvent } from '../pipeline/events';
import { buildFamilyProjection } from '../family/projection';
import type { FamilyState } from '../family/FamilyPersistence';
import { computeBaseline, recentMean, diffDays } from '../engine/baseline';
import { buildWeeklyReport } from '../engine/report';
import { requireFamilyAccess, type OwnerScope, type Viewer } from './ArchiveService';
export function readHealthHistory(
  scope: OwnerScope,
  profile: ElderProfile,
  events: HealthEvent[],
  familyEvents: FamilyHealthEvent[],
  findings: Finding[],
  tasks: CareTask[],
  family: FamilyState,
  today: string,
  viewer: Viewer = 'self',
) {
  requireFamilyAccess(scope, viewer, family);
  const projection = buildFamilyProjection(family, {
    ownerId: scope.ownerId,
    findings,
    tasks,
    familyEvents,
    measurements: [],
    selfEvents: events,
  });
  const health = materializeHealthData(viewer === 'self' ? events : projection.selfEvents);
  const visibleFindings = viewer === 'self' ? findings : projection.findings;
  return {
    ownerId: scope.ownerId,
    profile: viewer === 'self' ? structuredClone(profile) : { name: profile.name },
    ...health,
    familyEvents: structuredClone(viewer === 'self' ? familyEvents : projection.familyEvents),
    findings: structuredClone(visibleFindings),
    report: buildWeeklyReport(
      health.records,
      health.observations,
      visibleFindings,
      today,
      viewer === 'self' ? tasks : projection.tasks,
    ),
  };
}
/** Same ProfileView trend computation, extracted without changing windows/thresholds. */
export function metricTrend(records: DayRecord[], key: MetricKey, today: string) {
  const values = records.map((record) => record.metrics[key] ?? null);
  const baseline = computeBaseline(records, key, { endDate: today, excludeDays: 3 });
  const recent = recentMean(records, key, today, 3);
  let deltaText: string | null = null;
  if (baseline && recent !== null && Math.abs(baseline.mean) > 1e-9) {
    const delta = (recent - baseline.mean) / Math.abs(baseline.mean);
    if (Math.abs(delta) >= 0.05)
      deltaText = `最近3天比平时${delta > 0 ? '高' : '低'} ${Math.abs(Math.round(delta * 100))}%`;
  }
  return { values, baseline, recent, deltaText };
}
export function familyReportWindow(
  records: DayRecord[],
  findings: Finding[],
  events: FamilyHealthEvent[],
  today: string,
  offset: number,
) {
  const end = new Date(today + 'T12:00:00');
  end.setDate(end.getDate() - offset * 7);
  const start = new Date(end);
  start.setDate(start.getDate() - 6);
  const key = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const startDate = key(start),
    endDate = key(end);
  const inWeek = (date: string) => date.slice(0, 10) >= startDate && date.slice(0, 10) <= endDate;
  return {
    startDate,
    endDate,
    weekRecords: records.filter((r) => inWeek(r.date)),
    weekFindings: findings.filter((f) => inWeek(f.date)),
    weekEvents: events.filter((e) => inWeek(e.timestamp)),
  };
}
export function recentObservations<T extends { date: string }>(observations: T[], today: string) {
  return observations.filter((o) => diffDays(o.date, today) >= 0 && diffDays(o.date, today) < 7);
}

export function summarizeMetric(records: DayRecord[], key: MetricKey) {
  const values = records
    .map((r) => r.metrics[key])
    .filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  return values.length
    ? {
        count: values.length,
        mean: values.reduce((a, b) => a + b, 0) / values.length,
        min: Math.min(...values),
        max: Math.max(...values),
      }
    : null;
}
