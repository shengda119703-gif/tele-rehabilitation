# Rehab audit initial baseline (read-only)
Baseline: c3a5aaff, PR #13 target branch. No real patient DB or model calls performed by this audit.

## Initial node matrix
- Stage 4A: PARTIAL. Python RehabReadTools reads current plans, assessments, history from real Storage, bound by participant/source/context. No registered personal-restrictions/profile reader. Real execution not yet verified.
- Stage 4B: PARTIAL. Catalogue is real full 185-card resource, exact ID/name matching exists; oral synonyms limited. Search returns max 3. Tools include conditions, candidate dose and content; explicit sourceRefs not returned in workflow projection.
- Stage 4C: PARTIAL. searchGuidance maps fixed keywords to one full section; 疼痛/痛/退阶/专业协助 cases need deterministic coverage. Source content includes referenced boundaries. Real UI not yet verified.
- Stage 4D: PARTIAL. run_plan_algorithm calls actual localPlan, but supplies model goal/region/equipment/restrictions/level without trusted provenance. Host forces screeningConfirmed false. localPlan has 5 starter mappings and max 3 actions, no lumbar/back starter mapping, reviewRequired always true.
- Stage 5: PARTIAL. rehabAnswerTask separates guidance/progress/question/plan generation. Read-only replies are local source excerpts; progress emits raw record JSON and does not analyze trends. Multi-round plan state is absent; downstream models receive current turn only, not prior user inputs.
- Stage 6: FAIL. validateRehabPlan can mark passed from model screening=true, no restrictions and an arbitrary complete training card even when no algorithm requested or no card retrieved. Does not enforce card eligibility, level/equipment compatibility, required assessment/trial/pro review, unique IDs or nonempty candidate list. localPlan.reviewRequired=true not propagated when status=draft. Model-generated restrictions may omit user disease. All are untrusted fields.
- Stage 8: FAIL. Mixed rehab/program branch exists and blocks needs_review, but trusts false passed. Personal read receipts are serialized to external model in both candidate analysis and operation planning, without dedicated consent. Urgent handling precedes operations, though pending-operation invalidation needs separate audit.
- Stage 9: NOT IMPLEMENTED for full requested NLP -> reviewed candidate -> adoption -> new plan -> patient display flow. New candidate path explicitly stops at text. Registered operations only change existing plans or schedules. No create/adopt tool, review receipt linkage or knowledge-card T-* to executable snake_case action mapping in this flow. Existing cloud clinician candidate+publication path is separate and manual.

## Definite defects and file references
1. P1 unauthorized stored personal record transmission: workflow.ts generateRehabCandidate lines 298-309 sends tool_results wholesale; programOperations.ts buildPlan lines 181-189 also sends real read receipts. Existing rehabTools.ts and semanticExecution.ts explicitly preserve records locally.
2. P1 false applicability PASS: workflow.ts validateRehabPlan lines 181-230 relies on model candidate fields, accepts arbitrary real training IDs and unchecked screening; runRehabWorkflow lines 340-365 only compares algorithm IDs if planner chose to call it. localPlan assistant.ts lines 12-35 always reviewRequired=true but workflow only escalates status needs_review.
3. P2 read API mismatch: programOperations.ts line 224 calls input.reads.read('rehab.get_training_plan', {}) although RehabToolPort.read takes RehabCall object. Real bridge passes malformed name; TypeScript compilation expected to catch. Operation model then receives failed receipt and can guess IDs.
4. P2 output formatting: workflow renderers use literal \\n; readOnly progress uses JSON.stringify records including internal fields. User-facing guard may replace successful candidate response because it contains raw keys/reply claims. Needs runtime repro.
5. P2 pain lookup: searchGuidance keyword table has 酸痛/不适 but no 疼痛/痛 as direct match; direct pain queries can miss all guidance. Needs focused deterministic test.

## Actual call chains (static)
ProductBackend worker -> AgentBridge.product -> agent-bridge.cjs ProductService.request(chat.send) -> AgentRuntime -> RuntimeSession.processTurn -> understandSemanticTurn (LLM #1) -> executeSemanticTurn.
Plan: executeSemanticTurn rehab plan_generation -> runRehabWorkflow -> selectRehabTools (LLM #2) -> executeCall -> readRehabReceipt -> Python host_tools -> RehabReadTools -> Storage(readonly); searchCards/searchGuidance/localPlan are real local functions -> generateRehabCandidate (LLM #3, currently sends private data) -> validateRehabPlan -> renderRehabDraft -> chat text. No plan persistence.
Guidance/question: executeSemanticTurn -> runRehabReadOnlyAnswer -> searchCards/searchGuidance -> source excerpts -> reply. No second LLM.
Progress: runRehabReadOnlyAnswer -> 3 readRehabReceipt calls -> Python scoped readers -> local raw excerpts; no external analysis.
Mixed: existing safety first -> runRehabWorkflow -> requires status passed -> previewRehabProgramOperation -> selectReads (LLM #4) -> read plan/schedule -> buildPlan (LLM #5, currently sends private data) -> Python preview -> store pending -> confirmation -> Python commit -> Storage.save_training_plan or DailyStore.apply.
Independent cloud path: rehab_workflow.py profile -> existing nonsynthetic assessments + grant -> deterministic starter cards max 3 -> PENDING_REVIEW -> DOCTOR_ADMIN-only review status. Doctor separately creates/publishes executable plan; patient separately adopts. Not connected to runRehabWorkflow candidate.

## Focused test suggestions
- Capture model requests with synthetic stored marker; plan and operation prompts must never contain marker, raw record, settings, schedule or participant scope. Real DB bridge test separately after baseline.
- Validate arbitrary known card with no search, screening=true, level=null/missing assessments; must never passed. Algorithm draft with reviewRequired=true must stay needs_review. Omitted lumbar restriction must not grant acceptance.
- Reject unknown/assessment/incomplete IDs, mismatched algorithm IDs, duplicate/empty candidate actions and invented dose; preserve no_match/needs_review.
- Fix true RehabCall object and assert real bridge plan read succeeds before model receives its local status.
- Cover common oral Chinese names, exact ID, unknown action, pain/rest/progression/pro assistance guidance.
- Check T-* candidates cannot be inserted into executable plan without verified mapping; report full new-plan flow not implemented.

## Executed initial deterministic repro (2026-10-17)
Command: node work/rehab-baseline-repro.cjs <installed-typescript> <agent-root>; transpileModule loads actual source modules without changing source. This is deterministic/mock-model evidence, not real DeepSeek or Host.
- arbitrary_known_card_validation: passed (expected needs_review/rejected) => FAIL reproduced.
- empty_candidate_validation: passed (expected rejected) => FAIL reproduced.
- unretrieved_candidate_validation: passed (expected rejected) => FAIL reproduced.
- stored_marker_sent_to_model: true (expected false) => FAIL reproduced, SYNTHETIC marker only.
- pain_guidance_found: false => missing common query reproduced.
- lumbar_algorithm: no_match => lumbar starter filtering NOT IMPLEMENTED.

## Bounded repair and focused retest (after frozen baseline aa8cf7b)
Changed files: src/rehab/workflow.ts, src/rehab/programOperations.ts, src/rehab/assistant.ts, tests/rehab-acceptance-boundary.test.ts.
- Fixed stored receipt externalization: candidate model receives only explicit public tool allowlist. Personal read data remains local. Program-operation model planning that depended on sending stored plans/schedules was removed; NLP modification now fails closed with manual-page guidance. Existing direct Host APIs remain present. This is a deliberate capability limitation, not a completed NLP write flow.
- Fixed false applicability pass: generic model candidate cannot prove individual eligibility or clinical approval, therefore always needs_review; empty, duplicate, unknown/incomplete/assessment and unretrieved candidate actions reject. localPlan.reviewRequired is propagated. No new clinician approval flow or weakened source conditions.
- Removed arbitrary model summary/reasons from draft display; deterministic candidate wording cannot claim training clearance or saving.
- Fixed wrong read method signature and TS number narrowing/strict arguments parameter errors.
- Improved read-only report labels (reuses describeLocalRehabReceipt), failed-all-read status, actual newlines and common pain lookup.
- npm run typecheck: PASS.
- node node_modules/typescript/bin/tsc -p tsconfig.test.json plus focused Node test files: 18 tests, 18 PASS, 0 FAIL (10 new boundary cases and 8 existing rehab cases).
- A test harness initially omitted .test-build/package.json type=commonjs and then matched static prompt word participant_id; both harness/test assertion issues corrected before final 18/18 run, no safety standard weakened.

## Remaining exact blocking positions
Lumbar plan request cannot create a patient App plan: localPlan has no lumbar starter; model parameters have no trusted individual-source resolver; generic candidates retain needs_review; no actual professional review receipt is linked to candidate adoption; T-* knowledge cards have no verified executable-ID mapping in NLP path; no new-plan create/adopt persistence tool exists; no candidate-to-patient-plan UI connection exists. Ordinary confirmation cannot resolve these missing nodes.
Whole workflow tool-selection/analysis remains current-turn-based. First semantic pass has context but downstream candidate tool planner lacks a persisted plan-profile state. Multi-turn equipment correction and subsequent adoption need evidence, cannot be asserted passed.

## Final screening correction and runner review
- Restored the existing direct local-plan UI checkbox contract: localPlan rejects screeningConfirmed=false (the product regression already required this). Workflow does not use a model flag as trusted confirmation: it passes false, calls the real function, and returns structured needs_review/trusted_screening_not_available with no generated algorithm items. Public searched-card candidates remain review-only. Trusted individual parameter/confirmation resolver is still NOT IMPLEMENTED.
- Final npm typecheck + test TS compile + focused 18 tests: 18 PASS / 0 FAIL after this correction.
- Reviewed and patched root-owned real-model runner tools/qa/pr13-full-live.cjs: required openSession now, close sessions, sanitize credential in saved traces, dynamic stored-record marker gate, understanding status separated from full behavior status, no full-flow PASS from schema-only checks, route expectations documented as broad screening rather than clinical proof. Node --check PASS. Root owns the actual live run and raw initial failed harness evidence.
- No real model credentials or real patient data were used by this subagent. All model stubs and record markers above are SYNTHETIC/TEST. Final full-suite/live/UI results must come from root's authoritative run.
