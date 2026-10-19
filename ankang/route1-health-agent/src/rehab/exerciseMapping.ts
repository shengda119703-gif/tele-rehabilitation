/**
 * Explicit bridge from the public rehabilitation knowledge cards (T-*) to the
 * app's executable movement registry (snake_case exercise IDs).
 *
 * This is a technical compatibility map only, not clinical clearance.
 * Unknown/unmapped cards must not be auto-adopted into an app plan.
 */
export interface ExecutableActionMapping {
  knowledge_action_id: string;
  app_exercise_id: string;
  match_basis: string;
  limitations: string[];
}

const mappings: readonly ExecutableActionMapping[] = [
  {
    knowledge_action_id: 'T-LOW-003',
    app_exercise_id: 'knee_extension',
    match_basis: 'Both describe seated/open-chain knee extension; app uses a 2D projection contract.',
    limitations: [
      'Not evidence of post-operative or diagnosis-specific suitability.',
      'Use only after the current knee range, load and stop conditions are reviewed.',
      'Knowledge-card dose is not automatically converted to app target reps/sets.',
    ],
  },
  {
    knowledge_action_id: 'T-LOW-017',
    app_exercise_id: 'sit_to_stand',
    match_basis: 'Both describe graded sit-to-stand movement.',
    limitations: [
      'Chair height, hand support and companion needs remain user-specific.',
      'Knowledge-card dose is not automatically converted to app target reps/sets.',
      'This mapping does not establish individual fall-risk or weight-bearing clearance.',
    ],
  },
];

const byKnowledgeId = new Map(mappings.map(item => [item.knowledge_action_id, item]));

export function mapKnowledgeActionToApp(knowledgeActionId: string): ExecutableActionMapping | null {
  return byKnowledgeId.get(knowledgeActionId) ?? null;
}

export function listExecutableActionMappings(): readonly ExecutableActionMapping[] {
  return mappings.map(item => ({...item, limitations:[...item.limitations]}));
}
