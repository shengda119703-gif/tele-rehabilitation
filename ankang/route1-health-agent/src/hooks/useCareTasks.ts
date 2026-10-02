import { useEffect, useState } from 'react';
import type { CareTask, Finding } from '../types';
import { buildInitialTasks } from '../engine/tasks';
import { changeTaskStatus, ensureMedicationTask, reconcileCareTasks } from '../runtime/careTasks';
export { shouldCreateMedicationCheck } from '../runtime/careTasks';

interface UseCareTasksOptions {
  findings: Finding[];
  today: string;
}

export function useCareTasks({ findings, today }: UseCareTasksOptions) {
  // Instance-owned: a remounted/new App must not inherit another session's tasks.
  const [tasks, setTasks] = useState<CareTask[]>(() => buildInitialTasks(today));
  useEffect(() => {
    window.localStorage.removeItem('ankang-route1-tasks-v2');
  }, []);
  useEffect(() => {
    setTasks((current) => reconcileCareTasks(current, findings, today));
  }, [findings, today]);
  function updateStatus(taskId: string, status: CareTask['status']) {
    setTasks((current) => changeTaskStatus(current, taskId, status));
  }
  function ensureMedicationCheck(medications: string[], createdAt?: string) {
    setTasks((current) => ensureMedicationTask(current, today, medications, createdAt));
  }
  return { tasks, updateStatus, ensureMedicationCheck };
}
