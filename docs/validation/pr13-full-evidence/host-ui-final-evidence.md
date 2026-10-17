# Host/UI bounded repairs and evidence — 2026-10-17

Initial source-only audit and all initial defects remain in work/host-ui-audit.md, frozen before production changes (root baseline commit aa8cf7b). Root owns consolidated commit and final whole-product verdict. This child made no commit and did not access production data or external model credentials.

## Changes owned by this audit

- `rehab_codex_single_camera_v2_1/app/rehab_operation_tools.py`: reject patient action/dose add/update/remove on a published doctor plan during preview; rename allowed. Send expected_existing into the real schedule write transaction. Upsert receipt now exposes actual saved schedule with generated ID.
- `rehab_codex_single_camera_v2_1/app/storage.py`: recheck doctor-publication and item immutability against the previous record under BEGIN IMMEDIATE. Direct callers cannot bypass the operation adapter by stripping the publication reference.
- `rehab_codex_single_camera_v2_1/app/product/daily_store.py`: compare schedule expected_existing within the same BEGIN IMMEDIATE transaction that saves/removes it; return persisted schedule value while preserving dailyReceipt compatibility. No schema migration.
- `rehab_codex_single_camera_v2_1/tests/test_rehab_operation_tools.py`: 14 new actual SQLite cases (17 total including 3 existing), isolated tmp_path and explicit SYNTHETIC/TEST scope. Correct existing fixture source_kind=LOCAL to SYNTHETIC because LOCAL was rejected by real validator; no validation weakening.

## Reproduction and retest

Python: `C:\Users\PC\Documents\Codex\2026-10-17\files-pasted-by-the-user-pr\work\validation-venv\Scripts\python.exe`.

1. Before production edits, `python -m pytest tests/test_rehab_operation_tools.py -q`: **11 failed / 5 passed** in 1.43s. Existing invalid LOCAL fixture accounts for 3; new defect reproductions account for 8: doctor action/dose (3), direct Storage bypass (2), missing schedule ID (1), outside-transaction race (2). This count preceded the later added simultaneous-confirmation case.
2. After repair, `python -m pytest tests/test_rehab_operation_tools.py tests/test_daily_store.py tests/test_care_host.py tests/test_saved_training_plans.py -q --junitxml=<outside-repo evidence path>`: **64 passed** in 3.54s. JUnit: work/host-ui-focused-junit.xml. Cwd: rehab_codex_single_camera_v2_1.
3. Earlier exploratory broader command additionally included test_rehab_read_tools.py and test_workbench_clients.py: **66 passed / 2 failed / 11 errors**, all 13 non-passes because `.bridge-build/runtime/index.js` had not yet been built, with explicit `Build the bridge first: npm run build:bridge` error. Root owns rerun after build; do not label those 13 as application defect or silently omit the initial environment result.
4. `git diff --check`: exit 0 (only line-ending warnings on concurrently modified TypeScript files).

The 64 passing focused tests cover true SQLite preview with unchanged record+audit, rename/parameter/add/remove commit, exact revision+audit increments, close/reopen persistence and live reader readback, stale revisions, cross-owner/source/context rejection, doctor prescription no-write + audit rollback, direct Storage bypass rejection, safe rename, schedule create/reschedule/remove exact receipt+reopen+audit, deterministic competing-write injection, and two concurrent threads racing to confirm the same preview (one winner/one conflict; winning schedule preserved). Care idempotency and physician adoption storage regression tests are included. This is real Host business storage evidence, with no Mock Host or clinical applicability claim.

## Independent safety review of other agents' changes (read only)

- `previewRehabProgramOperation` no longer sends stored plan/schedule tool results to external model. It selects reads from user semantic text, executes local reads, then returns uncertainty explaining that stored-record model consent/local resolver is absent. No new pending proposal is emitted. This preserves privacy while exposing the missing capability.
- `generateRehabCandidate` filters personal read results from model context, allowing only public card/guidance/algorithm results. Algorithm input remains based on user/model selection; it is not an individual assessment. `validateRehabPlan` always retains needs_review unless structurally rejected; model screening flags cannot establish professional review. Candidate rendering omits untrusted model summary/dose and makes review required clear.
- Pending state is cleared on topic/context change, invalid/failed semantic parse, safety action and reset. User confirmation cannot execute a previous topic's proposal through those paths.
- Navigation consumers already exist on desktop and web. New allowlisted ProductAgent navigation reconnects them. Reported terminal punctuation issue (`帮我打开康复计划页面。` fails exact regex while no final punctuation matches) to root + semantic owner; they own fix/retest.

## Remaining user-requested capability boundaries

- Natural-language modifications now fail closed: stage 7 NLP write chain is not fully implemented under current privacy contract, despite passing direct Host SQLite operations. Do not claim the patient's sentence→write loop passes.
- New model candidate→review→adopt→executable patient App plan remains NOT IMPLEMENTED. Catalogue T-* IDs lack a verified conversion/adoption path to Python executable exercise IDs. Candidate dialogs render details and Close only. Four/five action illustration cannot justify an actual executable plan count.
- Reminders lack an assistant operation/notification schedule; calendar entry creation is separate.
- Standalone Python mobile host has no semantic/model/read/operation ports; Android has no true operation port (constructor drift fix belongs to root). Paired mobile shares the real desktop backend but needs actual UI evidence from root.
- Public deployment, installed Android hardware, cameras, reminder delivery and clinical outcomes were not checked. No production DB modified, no main merge/deploy, no new adoption feature added.
