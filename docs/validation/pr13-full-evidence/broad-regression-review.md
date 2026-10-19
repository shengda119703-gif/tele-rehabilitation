# Broad regression classification (read only)

Reviewed 2026-10-17. Current HEAD `e4539938788f6c8217fa9011bba8f6d82e5d6dd5`; initial PR head `c3a5aaff28dc6f58699f63fe3a7233e5895e9b12`; local `origin/main` `8f1fc2c706504f4119fb9bad984ab9ded87aa86d`. No source edits, test changes or reruns performed for this review.

## R02 — broad desktop product suite: FAIL, unresolved contract/UI failures

Actual log `work/product-python-tests.txt`: **18 failed, 129 passed, 2 skipped in 123.72s**. Keep all failures in final report. Individual failing IDs and evidence:

| Exact test ID (prefix `rehab_codex_single_camera_v2_1/tests/`) | Actual failure | Classification |
|---|---|---|
| test_product_visual.py::test_published_116_button_contract_and_native_connections | KeyError assistantImage | Retained button audit expects an absent action ID; source/test contract mismatch |
| test_product_ux.py::test_live_turn_receipt_and_keyboard_send_preserve_next_draft | record_disclosure.isVisible() false | Receipt expectation conflicts with unconditional hide below |
| test_product_ux.py::test_quick_question_does_not_erase_unsent_draft_and_no_record_receipt_is_honest | Expected 本轮不记录, actual 正在理解与处理记录，请稍候… | Receipt expectation conflicts with unconditional hide/no replacement |
| test_product_ux.py::test_navigation_marker_settles_after_rapid_keyboard_navigation | animation Running after 200ms | Test waits 200ms; actual SelectionRail animation duration is 300ms (product_motion.py:22), timing contract mismatch |
| test_product_module_paths.py::test_health_metric_details_save_back_refresh_and_clear_on_owner_switch | Expected saved weight event, events empty (IndexError) | Unresolved actual UI button/save path failure; root cause not proved by this log |
| test_product_module_paths.py::test_today_medication_detail_operations_use_original_task_and_chat | Expected assistant page, remained medication | Unresolved medication shortcut/navigation contract failure |
| test_product_completion.py::test_paths_5_7_member_permissions_notification_detail_business | notifications.rowCount()==0 | Test expects chat-derived notification after health facts; current chat read-only contract does not create those facts |
| test_product_completion.py::test_loading_duplicate_error_empty_disabled_and_button_audit | 本地候选计划 button lacks actionId | Definite unclassified UI control: product_assistant.py:105 adds button without action metadata |
| test_product_care_controls.py::test_visible_confirmation_performs_no_write_until_click_and_returns_actual_receipt | care.prepare throws Agent 代操作已下架，请在对应页面手动处理。 | Retired API expectation; cannot execute proposed flow |
| test_product_care_controls.py::test_cancel_and_scope_change_cannot_execute_old_controls | same care.prepare error | Retired API expectation |
| test_product_care_controls.py::test_agent_module_navigation_uses_existing_gate_and_does_not_command_runtime | Expected medication page, remained assistant | Offline fixture disables model; semantic navigation requires valid semantic turn; old offline module path unavailable |
| test_product_care_controls.py::test_completed_receipt_does_not_promote_another_pending_operation | same care.prepare error | Retired API expectation |
| test_product_care_controls.py::test_scope_switch_immediately_closes_confirmation_and_refreshes_current_scope[source_kind-REPLAY_FILE] | same care.prepare error | Retired API expectation |
| test_product_care_controls.py::test_scope_switch_immediately_closes_confirmation_and_refreshes_current_scope[usage-TEST] | same care.prepare error | Retired API expectation |
| test_product_care_controls.py::test_confirmation_dialog_labels_receive_central_theme_palette[light] | same care.prepare error | Retired API expectation |
| test_product_care_controls.py::test_confirmation_dialog_labels_receive_central_theme_palette[dark] | same care.prepare error | Retired API expectation |
| test_product_assistant.py::test_medication_shortcut_edits_draft_only_and_explicit_send_keeps_privacy | StopIteration locating product-201 | Expected medication starter control/action absent |
| test_product_assistant.py::test_conversation_chrome_keeps_errors_receipts_and_contextual_assistant | Expected visible receipt/disclosure, actual hidden | Receipt expectation conflicts with unconditional hide |

**Attribution evidence:** `git diff --name-only` and `--numstat` against BOTH initial PR head and local origin/main returned no changes for `app/ui/` and `tests/test_product*`. `product_assistant.py:210–211` contains `refresh_record_review(...): record_receipt.hide();record_disclosure.hide()`, directly explaining three visibility/receipt failures; same source exists in both compared revisions. `ProductService.ts` care.* rejection is also present in both `git show origin/main:...` (line 286) and `git show c3a5aaff:...` (line 302). Both also already install the read-only rehabAssistant. These are demonstrated source/test expectation conflicts present at the compared source revisions; **this review did not execute their historical test suites**, so do not say “main already had 18 failures” or claim all 18 measured failures were preexisting. ProductService/session semantic code did change in this audit/PR; full runtime attribution of remaining UI assertions has not been isolated. No failures were removed or weakened.

## R03 — mobile real-model suite: UNVERIFIED capability, four actual failed tests

Actual log `work/mobile-python-retest.txt`: **4 failed, 121 passed, 2 skipped in 18.41s**. Maintain failed-test count alongside environment classification.

| Exact failing test ID | Actual evidence | Classification |
|---|---|---|
| mobile_rehab/tests/test_extensions.py::test_real_local_model_live_empty_frame_no_false_counts | Real worker IPC returns 实时分析中断, API raises 503 | Model execution failed; worker hides underlying exception. Missing configured weights is the strongly supported cause (same VisionWorker path); generic log alone does not expose its exact exception |
| mobile_rehab/tests/test_mobile.py::test_fitness_mode_real_model_empty_video | Child traceback reaches VisionWorker._load:36, missing YOLO11n-pose weights | Explicit missing model prerequisite |
| mobile_rehab/tests/test_mobile.py::test_real_capture_model_and_empty_report | Same missing-weight traceback | Explicit missing model prerequisite |
| mobile_rehab/tests/test_unified.py::test_real_blank_video_saves_under_desktop_owner_and_keeps_source | Expected done, actual failed; its retained isolated analysis.log shows same missing-weight traceback | Explicit missing model prerequisite confirmed by generated job log |

The fourth test's synthetic-only retained child log was read at `C:/Users/PC/AppData/Local/Temp/pytest-of-PC/pytest-10/test_real_blank_video_saves_un0/phone/jobs/95256875151043abdcafdd26fd390c65/bb2d018b029745b28c70e3c5f44010a7/analysis.log`: its last exception is “尚未配置本地 YOLO11n-pose 权重，程序不会自动下载”. No patient directory was accessed.

`Test-Path rehab_codex_single_camera_v2_1/assets/models/yolo11n-pose.pt` returned **False**. `VisionWorker` defaults to that exact path (vision.py:18), rejects missing local weights before loading or downloading anything (vision.py:34–36). `git diff --name-only`/`--numstat` against both compared revisions returned no changes for vision.py, mobile_rehab/live.py, analyzer.py, fitness_analyzer.py and mobile_rehab/tests. Thus tested inference has a demonstrated absent local prerequisite; there is no evidence these four errors were introduced by the PR13 Host/semantic repairs. Historical suite runs were not performed, and no real-model inference PASS is claimed. Do not download models or substitute fabricated pose results to turn these tests green.

No production database, model key, token, UI source or test expectation was modified. This classification leaves R02 open and R03 environment-blocked, while preserving every actual test failure.
