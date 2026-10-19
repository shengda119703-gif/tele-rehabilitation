# PR #13 Host/UI initial read-only audit — 2026-10-17

Baseline: c3a5aaff; no source edits or synthetic executions occurred before saving this file. No production database or patient data accessed. Status PASS requires execution evidence and is not assigned solely from source reading.

## Initial scope matrix

| Node | Actual implementation and entry | Initial status | Initial gap |
|---|---|---|---|
| Desktop Host | app/product/backend.py ProductBackend._run → bridges/ankang/client.py AgentBridge.product → scripts/agent-bridge.cjs ProductService.request | PARTIAL | Real child/Host path exists; runtime feature is gated by ANKANG_SEMANTIC_ROUTING_ENABLED=1, needs synthetic runtime evidence |
| Personal scoped readers | app/rehab_read_tools.py RehabReadTools; ProductBackend installs trusted participant/source/context tools | PARTIAL | SQLite readers exist; no baseline synthetic execution yet |
| Preview/commit plan rename/add/remove/parameters | app/rehab_operation_tools.py _plan_change/_patch_plan → app/storage.py save_training_plan | PARTIAL | Real SQLite revision/audit path exists; doctor-publication mutation bypass below |
| Schedule create/change/remove | app/rehab_operation_tools.py _schedule_upsert/_schedule_remove → app/product/daily_store.py apply | FAIL | expected_existing compares before transaction; upsert returns only dailyReceipt, no persisted schedule ID |
| Cancel/confirmation/topic switch | src/runtime/semanticExecution.ts:80–101; src/rehab/programOperations.ts:242–271 | PARTIAL | Pending state in memory; confirmation/cancel path present, no baseline real Host test |
| Navigation | product_window.py:557–558; unified.js:867–879 consume agent.navigation | PARTIAL | UI consumer exists; semanticExecution.ts module branch reports module_not_connected; actual NLP navigation needs execution |
| Reminders | Registered operations in programOperations.ts:8–12 only plan.change and schedule upsert/remove | NOT IMPLEMENTED | No reminder operation in this semantic execution path; schedules are calendar records, not notification scheduling |
| Candidate adoption/save/display | ProductService.ts:301 localPlan; product_window.py:911–923; unified.js:844–853 | NOT IMPLEMENTED | Candidate detail text/Close only; no adoption, executable ID mapping, reviewed save, plan ID or revision |
| Paired mobile | mobile_rehab/unified.py SharedProduct.call binds desktop owner, shares backend; API source constrained | PARTIAL | Real shared backend path; no baseline browser runtime execution |
| Standalone mobile Python Host | mobile_rehab/product_host.cjs:10 new ProductService(store) | NOT IMPLEMENTED | No reads/model/operations/semantic flag wired to standalone Host |
| Standalone Android | android_offline/web/local-api.js:10–11 new ProductService(...) | FAIL | runtimeOptions object placed in rehabOperations constructor slot; flag ignored; no real operation port |
| Public web/cloud | Independent cloud source exists | UNVERIFIED | Public deployment not authorized; no deployment claim |
| Reopen durable plan/revision/order | Storage.save_training_plan + RehabReadTools.get_training_plan + UI existing plan readers | PARTIAL | Existing manual plans readable; newly generated candidate lacks save path |

## Initial defects retained for final report

**HUI-01 (P1): doctor-approved prescription can be modified under the old publication reference.** app/rehab_operation_tools.py:155–181 accepts any ACTIVE scoped plan. `_patch_plan` deep-copies doctor_publication and calls only validate_training_plan; app/training_plans.py:93–101 preserves publication reference; Storage.save_training_plan:233–247 blocks pending→active but permits ACTIVE doctor plan dose/action changes. Existing doctor adoption safeguards do not authorize altering an approved prescription. Repro: seed ACTIVE SYNTHETIC manual plan carrying syntactically valid doctor_publication, call plan.change commit true with target_reps changed; anticipated old behavior applies and retains old approval. Bounded fix: reject action/dose changes on published plans (rename can remain allowed), real SQLite regression proves no revision/data/audit change.

**HUI-02 (P2): schedule preview conflict check is outside the write transaction.** rehab_operation_tools.py:205–219 / 227–236 snapshots expected_existing, then DailyStore.apply opens a separate BEGIN IMMEDIATE. A concurrent writer between comparison and write can be overwritten or removed. Bounded fix: pass expected_existing to DailyStore and compare under same transaction; regression injects competing update after outer snapshot and before apply.

**HUI-03 (P2): schedule applied receipt does not identify saved record.** rehab_operation_tools.py:220–221 sets schedule=result from DailyStore.apply, which returns {'dailyReceipt':True} (daily_store.py:209). New schedule generated id is unavailable to caller; no readback occurs before success reply. Bounded fix: DailyStore return saved schedule value for daily.schedule; Host receipt includes it and readback test checks exact saved ID/state. Keep generic dailyReceipt compatibility.

**HUI-04 (P1/P2): standalone Android semantic options misplaced.** local-api.js:10–11 positional construction places runtimeOptions object at ninth slot, actually rehabOperations. ProductService constructor defines runtimeOptions at tenth slot (ProductService.ts:63–69). Semantic routing remains disabled. Root agent owns bounded caller fix.

**HUI-05 (blocking missing capability): plan generation stops before patient App adoption.** semanticExecution.ts:163–196 returns renderRehabDraft but no persistence; UI local candidate dialogs only show catalogue IDs/conditions/dose text. No explicit catalogue T-*→Python EXERCISE_IDS mapping or profession-reviewed adoption path. Do not build new App feature during bounded fixes; report NOT IMPLEMENTED. Therefore requested lumbar-disc natural-language→validated plan in patient App cannot pass.

## Proposed synthetic checks

Run pytest test_rehab_operation_tools.py, test_daily_store.py, test_rehab_read_tools.py using tmp_path under isolated test directory. Add integration checks: preview is read only; confirmed rename + parameters + add/remove increment revision and audit; stale revision rejects; source/owner scope rejects; reopened SQLite yields same state; doctor prescription immutable; create/change/remove schedule preview/commit exact receipts; race check atomic; cancel prevents write through Runtime (root/semantic agent owns runtime). Existing tests initially only exercise static _patch_plan, not true SQLite mutation.

No real camera/hardware, public deployment, installed APK, notification delivery, or clinical validation was checked in this initial audit. Those remain explicit execution/environment boundaries.

## Initial synthetic reproduction (after baseline aa8cf7b, before production fixes)

Command: validation-venv/Scripts/python.exe -m pytest tests/test_rehab_operation_tools.py -q, cwd rehab_codex_single_camera_v2_1.

Actual result: **11 failed, 5 passed in 1.43s**. Three failures were existing tests: `sample_plan()` supplied source_kind='LOCAL', rejected by unchanged scope validator before test body. This test fixture will be corrected to SYNTHETIC/TEST; validator will remain unchanged. Eight new failure cases:

- Published action/dose add/update/remove preview did not raise (3 cases).
- Direct Storage mutation with/without publication stripped did not raise (2 cases).
- Schedule receipt missing persisted ID (`KeyError: 'id'`, 1 case).
- Concurrent schedule replacement/removal injected after outer snapshot did not raise (2 cases). Both paths overwrote/deleted competing real SQLite state.

Successful initial new cases covered real SQLite rename/parameters/add/remove, revision+audit+reopen, owner/source isolation, and published plan rename. All data used isolated pytest tmp_path and participant SYNTHETIC-TEST-operation-owner; no model or camera used. Proposed fix tests do not fabricate clinical applicability.
