# SDD ledger — plan: docs/superpowers/plans/2026-11-06-runtime-tools.md
Spec: docs/superpowers/specs/2026-11-06-runtime-tools-design.md
Setup: Ruling: same checkout, branch feat/runtime-tools from feat/detector-install — data/ needed for real checks — cost if wrong: none.
Pre-flight: T1 facade_detect -> T2 (facade_yolo re-exports), T5 (script path); T4 modelRuns/installedDetector.scene -> T5 RHINO_SCENE_WEIGHTS; T3 photo_tools -> T5 overlay/crop map: consistent.
Task 1: complete (commits 49d3898..1e4c259, tests: npm test → OK (skipped=6))
Task 2: Ruling: the local training scripts data/*.ps1 (not in git) were updated in place, 23 paths tools\train_data.py / train_report.py -> tools\dev\... — otherwise the next night training would fail on a missing file — cost if wrong: none; a plain path prefix, reversible.
Task 2: Ruling: dev tools put both tools/dev and tools on sys.path (sys.path[:0] = [HERE, TOOLS]) so they import facade_detect/rectify from the runtime folder — cost if wrong: none.
Task 2: complete (commits 1e4c259..37447b0, tests: npm test → OK (skipped=6))
Task 3: Ruling: overlay also accepts a detect_facade draft ({els}) besides a spec, and facade_bench now imports COLORS/expand_px/facade_part/px_boxes from photo_tools instead of keeping copies — cost if wrong: none.
Task 3: complete (commits 37447b0..5312ebd, tests: npm test → OK (skipped=6))
Task 4: complete (commits 5312ebd..fbdb433, tests: npm test → OK (skipped=6))
Task 5: complete (commits fbdb433..8dcacf8, tests: npm test → OK (skipped=6))
Task 6: complete (commits 8dcacf8..7c8070a, tests: npm test → OK (skipped=6))
Final review: fresh reviewer (opus). Verdict: ready with fixes; focus 1-5 hold.
Final: fixed silhouette compare --calib failing under run-tool's -I (import photo3d) — test_silhouette_finds_photo3d_under_python_I RED→GREEN, suite JS 77/77 + py 252 OK
Final: fixed docs still naming old tools/ paths (re-graded Minor→Important: copy-paste commands fail, incl. solid_audit exec and README scenarios) — test_no_doc_points_at_a_moved_tool_old_path RED→GREEN
Final: Ruling: "run-tool ignores det.ready()" not fixed — run-tool is a new process per call and findDetector reads setup.json at that moment, so a pending install is already refused; only a millisecond window between lookup and spawn remains — cost if wrong: one failed tool call during a setup rerun.
Final: minor (deferred): crop --size 0 or negative is not rejected
Final: minor (deferred): overlay on a malformed draft box shows a traceback (exit still non-zero)
Final: minor (deferred): a version bump re-downloads unchanged models and leaves the old models/<version> folder
Final: Ruling: release models-2026.11.07 exists (created with Filippo's ok, 3 assets, sizes match models.json) — reviewer could not check it read-only.
Task 7: real run — release models-2026.11.07 created with Filippo's ok (3 assets, sizes match); setup from a clean clone without data/ into a separate LOCALAPPDATA: exit 0, 3 models verified, selftest ok; doctor from the clone: three OK lines incl. scene2; run-tool rectify / overlay (13 boxes) / crop / silhouette mask on the fixture: all exit 0 with their files. silhouette compare --calib not run for real (needs a Rhino mesh); its import under -I is covered by a test.
Task 7: complete (commits 7c8070a..758593b, tests: npm test → OK (skipped=6))
