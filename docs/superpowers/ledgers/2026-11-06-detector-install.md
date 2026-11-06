# SDD ledger — plan: docs/superpowers/plans/2026-11-06-detector-install.md
Spec: docs/superpowers/specs/2026-11-06-detector-install-design.md
Setup: Ruling: no worktree; work on branch feat/detector-install in the main checkout — Task 1, 2 and 6 need data/ (venv-det, det-runs, hznu), which is git-ignored and absent from a fresh worktree — cost if wrong: work shares the checkout with untracked tools/auto_rectify.py, which stays out of every commit.
Pre-flight:
- T2 produces readManifest/sha256File/compareDraft -> T3, T4, T5 consume the same names: consistent.
- T3 produces installDir/readSetup/installState/installedDetector(…,{allowPending}) -> T4 consumes installedDetector(repoRoot, env, {allowPending: true}): consistent after plan fix.
- T3 states none|ok|pending|outdated|incomplete -> T5 table uses the same five: consistent.
- T1 adds draft.device (python) ; T3 adds draft.model (node): different fields, no conflict.
Task 1: Ruling: only the runtime path (predict/detect_image) gets the explicit device; the benchmark/training calls (facade_yolo.py:201 spec command, silhouette.py, train_data.py) stay as they are — they run only on the GPU dev PC and never through the plugin — cost if wrong: those dev tools fail on a GPU-less PC, as they do today.
Task 1: Ruling: pick_device also requires torch.cuda.device_count() > 0 — with CUDA_VISIBLE_DEVICES="" torch 2.11 reports is_available() True and 0 devices, so the plan's is_available() alone still failed — cost if wrong: none found; GPU path checked by hand (13 els, cuda).
Task 1: complete (commits 579a88f..fbbd9fd, tests: npm test → OK (skipped=7))
Task 2: complete (commits fbbd9fd..0b408df, tests: npm test → OK (skipped=6))
Task 3: Ruling: the existing "helpers: defaults and detector discovery" test was left without a temp LOCALAPPDATA — installedDetector needs the repo's models.json, which that test's temp repo lacks, so a real install on the PC can never leak into it (it stayed green) — cost if wrong: that test would see a real install only if someone adds models.json to its temp dir.
Task 3: Ruling: installedDetector also returns `model` ("<version> <run+run>") and findDetector sets model "repo"/"custom" — the plan put the label in runDetector; runDetector only copies det.model — cost if wrong: none, same output.
Task 3: complete (commits 0b408df..3654fa6, tests: npm test → OK (skipped=6))
Task 4: Ruling: prereq checks run only for the steps that are needed (uv only if the venv must be built, gh only if a model must be downloaded, disk only if either) — the plan listed all prereqs first, but its own test "second run touches neither uv nor the release" needs them skipped — cost if wrong: a broken gh login is noticed only when a download is due.
Task 4: Ruling: setup() takes two extra injectables, detect (default runDetector) and freeBytes (default statfsSync on the nearest existing folder) — the plan said the self-test detector is "replaced by a fake" and disk must be testable — cost if wrong: none, defaults are the real ones.
Task 4: Ruling: the needed disk space adds the bytes of the models still to download to the 8 / 2 GB — cost if wrong: a few tens of MB stricter.
Task 4: complete (commits 3654fa6..23801fc, tests: npm test → OK (skipped=6))
Task 5: Ruling: detectorReport loads findDetector with a dynamic import — facade-detector.mjs already imports detector-install.mjs, and a static import back would make a cycle — cost if wrong: none.
Task 5: Ruling: with source "repo" (dev PC) the doctor still adds a pending/outdated/incomplete line when an install exists beside data/, but skips the python/models/gpu probe of an install not in use — cost if wrong: a dev PC does not see probe lines for an unused install.
Task 5: Ruling: the GPU probe also requires device_count() > 0, as in Task 1 — cost if wrong: none.
Task 5: complete (commits 23801fc..0dab247, tests: npm test → OK (skipped=6))
Task 6: Ruling: requirements pinned from importlib.metadata of data/venv-det (opencv-python 5.0.0.93, torchvision 0.26.0, psutil 7.2.2) — the plan copied module versions, and the real setup failed on opencv-python==5.0.0; test_requirements_pins RED→GREEN guards it — cost if wrong: none.
Task 6: real run — release models-2026.11.06 created with Filippo's ok (assets 40566828 / 19243354 bytes); setup into a separate LOCALAPPDATA: first run stopped at python (opencv pin, fixed), rerun rebuilt the half venv and finished (selftest ok); doctor from a clean clone without data/: three OK lines; installed vs data/ drafts identical on c_0075 (13 els) and c_0174 (192 els), on cuda and with RHINO_FACADE_DEVICE=cpu.
Task 6: complete (commits 0dab247..2ce9072, tests: npm test → OK (skipped=6))
Final review: fresh reviewer (opus). Verdict: ready with fixes; focus 1-4 hold, focus 5 only at plugin launch.
Final: fixed cached detector used while setup reruns — "an install that a rerun of the setup is replacing is not run…" RED→GREEN, suite JS 67/67 (1 skipped) + py 236 OK
Final: fixed rmSync on a venv in use crashing the setup — "a venv still in use … stops the setup with a clear message" RED→GREEN
Final: fixed Python probes without -I (re-graded Minor→Important: code in the cwd would run) — two "-I" tests RED→GREEN
Final: fixed gh missing reported as "not signed in" (re-graded Minor→Important: wrong guidance on a colleague's first setup) — "gh missing is reported as missing" RED→GREEN
Final: minor (deferred): doctor says "sha256 mismatch" for every incomplete cause (missing venv/file too)
Final: minor (deferred): selftest "fail" shows as "setup not finished"; the stored diff is not shown by the doctor
Final: minor (deferred): "outdated" prints "<" even when the install is newer than the plugin (downgrade)
Final: minor (deferred): old models/<version> folders are never removed (~60 MB per release)
Final: minor (deferred): device kept on a failed rebuild (covered today by the import probe)
Final: minor (deferred): two setups at once share models/.tmp and setup.json.tmp (no lock)
Final: Ruling: ";" in LOCALAPPDATA would split the weights list — pre-existing delimiter design, Windows user names with ";" are very rare — cost if wrong: detector hidden on such a PC.
Final: Ruling: 4 px self-test tolerance on other GPUs — identical drafts cuda/cpu on the reference PC; a colleague's first setup is the evidence — cost if wrong: a false selftest fail, visible with its diff.
Final: Ruling: uv/gh as .cmd shims — execFile without shell cannot start .cmd; official installers ship .exe — cost if wrong: "not found" on such a PC, fixed by the official installer.
Final: Ruling: hand-edited setup.json claiming ok is trusted at launch without hashing — by design (spec), the doctor re-hashes — cost if wrong: a tampered local file runs, needs local write access anyway.
