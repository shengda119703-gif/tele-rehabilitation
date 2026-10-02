import type { CareTask, Finding } from '../types';
import { createTaskFromFinding, updateTaskStatus } from '../engine/tasks';

/** Extracted from useCareTasks; completed finding tasks survive reconciliation. */
export function reconcileCareTasks(current: CareTask[], findings: Finding[], today: string): CareTask[] {
  const actionable = findings.filter((finding) => finding.severity === 'alert' || finding.severity === 'urgent');
  const currentFindingIds = new Set(findings.map((finding) => finding.id));
  const next = current.filter(
    (task) => !task.sourceFindingId || currentFindingIds.has(task.sourceFindingId) || task.status === 'completed',
  );
  for (const finding of actionable.slice(0, 2)) {
    const task = createTaskFromFinding(finding, today);
    if (task && !next.some((item) => item.id === task.id)) next.push(task);
  }
  return next;
}

export function shouldCreateMedicationCheck(tasks: CareTask[], today: string): boolean {
  return !tasks.some((task) => task.kind === 'medication_check' && task.dueDate === today);
}

export function ensureMedicationTask(
  current: CareTask[],
  today: string,
  medications: string[],
  createdAt?: string,
): CareTask[] {
  if (!shouldCreateMedicationCheck(current, today)) return current;
  const medList = medications.length ? medications.map((m) => `• ${m}`).join('\n') : '• （暂无录入的药物）';
  return [
    ...current,
    {
      id: `task-medication-${today}`,
      title: '💊 今天的药',
      description: `${medList}\n\n按原来的医生方案服用；不要自行加倍或调整药量。`,
      dueDate: today,
      status: 'pending',
      createdAt: createdAt ?? `${today}T08:00:00`,
      kind: 'medication_check',
    },
  ];
}

export function changeTaskStatus(tasks: CareTask[], id: string, status: CareTask['status']): CareTask[] {
  return tasks.map((task) => (task.id === id ? updateTaskStatus(task, status) : task));
}
