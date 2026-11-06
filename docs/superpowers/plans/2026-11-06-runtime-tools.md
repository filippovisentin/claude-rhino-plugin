# Strumenti runtime — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** ogni comando che la skill fa eseguire a Claude funziona sul PC di un collega dopo il setup; gli strumenti di sviluppo stanno in `tools/dev/`.

**Architecture:** il rilevamento esce da `facade_yolo.py` in `tools/facade_detect.py`; gli script di sviluppo vanno in `tools/dev/`; `scripts/run-tool.mjs` lancia gli strumenti runtime col Python del detector; `scene2` entra in `models.json` e nella release.

**Tech Stack:** Node ≥18 (`node:test`), Python 3.12 (`unittest`), Ultralytics, Pillow, OpenCV.

**Spec:** `docs/superpowers/specs/2026-11-06-runtime-tools-design.md`

## Global Constraints

- Strumenti ammessi da `run-tool`: `rectify`, `photo3d`, `silhouette`, `overlay`, `crop` (nient'altro).
- Processi figli senza shell, Python con `-I`, `YOLO_OFFLINE=1`; argomenti passati intatti uno per uno.
- `models.json`: `version` `2026.11.07`, `release` `models-2026.11.07`, `default` `["parts2m","parts11s"]`, `scene` `["scene2"]`.
- Nessun cambiamento di comportamento del rilevamento: la bozza di `tests/fixtures/detector/c_0075.jpg` resta uguale a `expected.json`.
- Release su GitHub, push e merge solo con l'ok di Filippo.
- Ogni test esistente resta verde dopo ogni task (`npm test`).

## Review Focus

1. `run-tool` chiamato con un nome di strumento costruito per uscire dall'elenco (`../dev/train_data`, `rectify.py`, stringa vuota): rifiutato senza avviare nulla. Test in Task 5.
2. Script di `tools/dev/` lanciati dalla cartella del repo o da un'altra: trovano `data/`, `rhino/` e i moduli di `tools/`. Test in Task 2.
3. Installazione `2026.11.06` (senza `scene2`) dopo l'aggiornamento del plugin: `outdated`, il detector usa `data/` o resta nascosto, il setup la porta a `2026.11.07`. Test in Task 4.
4. `crop` con box fuori dalla foto o invertito: errore chiaro, nessun file scritto. Test in Task 3.
5. `silhouette` con `RHINO_SCENE_WEIGHTS` che punta a un file inesistente: ricade su `data/` come oggi. Test in Task 4.

---

### Task 1: `tools/facade_detect.py`

**Files:** Create `tools/facade_detect.py`; Modify `tools/facade_yolo.py`, `scripts/facade-detector.mjs` (percorso dello script), `scripts/detector-install.mjs` se cita lo script, `tests/test_facade_device.py`, `tests/test_fuse_boxes.py`, `tests/test_detect_shapes.py` (import), test JS che controllano `facade_yolo.py` come script del detector.

**Interfaces:** Produces `facade_detect` con i simboli elencati nella spec e `main(argv)` per `detect-image PHOTO WEIGHTS CONF`. `findDetector(...).script` = `tools/facade_detect.py`.

- [ ] Test che fallisce `tests/test_facade_detect.py`: in un sottoprocesso `python -I -c "import sys; sys.path.insert(0,'tools'); import facade_detect; print('facade_bench' in sys.modules)"` stampa `False`; `facade_detect.pick_device`, `fuse_boxes`, `detect_image` esistono. JS: `findDetector` restituisce uno `script` che termina con `facade_detect.py`.
- [ ] RED; sposta i simboli (spostamento, non riscrittura); `facade_yolo.py` fa `from facade_detect import *` più i nomi privati usati (`_iou`, `_hood`, `_expose`, `_MODELS`) e il suo `main` delega `detect-image` a `facade_detect.main`.
- [ ] GREEN; verifica a mano: `data/venv-det/Scripts/python.exe -I tools/facade_detect.py detect-image tests/fixtures/detector/c_0075.jpg "<parts2m>;<parts11s>" 0.25` → `compareDraft` con `expected.json` = `[]`.
- [ ] `npm test` verde; commit `Split the runtime detector out of facade_yolo into facade_detect`.

### Task 2: `tools/dev/`

**Files:** `git mv` in `tools/dev/` di: `facade_bench.py`, `facade_yolo.py`, `train_data.py`, `train_report.py`, `ensemble_report.py`, `facade_report.py`, `photo_bench.py`, `clean_pick.py`, `facade_refine.py`, `fuzz_specs.py`, `glass_read.py`, `solid_audit.py`, `scenarios/`; `git add tools/dev/auto_rectify.py` (da `tools/auto_rectify.py`, con la nota del risultato in testa). Modify: i test che li importano; `data/*.ps1` non sono in git e non si toccano (Ruling se servono).

**Interfaces:** in ogni script spostato, `HERE = dirname(abspath(__file__))`, `TOOLS = dirname(HERE)`, `ROOT = dirname(TOOLS)`; `sys.path[:0] = [HERE, TOOLS]` dove prima c'era `sys.path.insert(0, HERE)`.

- [ ] Test che fallisce `tests/test_dev_layout.py`: ogni script dell'elenco esiste in `tools/dev/` e non in `tools/`; `tools/` contiene solo `rectify.py`, `photo3d.py`, `silhouette.py`, `export_mesh.py`, `facade_regular.py`, `facade_detect.py`, `photo_tools.py` (aggiunto nel Task 3: il test lo ammette se esiste) più `dev/`; `facade_bench.ROOT` è la radice del repo; `python -I tools/dev/train_data.py sources` lanciato con cwd = una cartella temporanea esce con 0.
- [ ] RED; sposta e correggi radici e percorsi; aggiorna gli import dei test.
- [ ] GREEN; `npm test` verde; commit `Move training, benchmark and experiment tools to tools/dev`.

### Task 3: `tools/photo_tools.py`

**Interfaces:** `overlay(photo, spec_path, out) -> None` (riusa il disegno di `facade_bench.overlay`, spostando in `photo_tools` la parte che disegna e lasciando a `facade_bench.overlay(fid, pred)` solo la scelta dei file); `crop(photo, box, out, size=768) -> {"origin": [x0, y0], "scale": s}`; `main(argv)`.

- [ ] Test che fallisce `tests/test_photo_tools.py` (Pillow; immagine sintetica 400×300): `crop` di `[100,50,200,150]` scrive un file con lato lungo 768 e restituisce `origin [100,50]`, `scale 7.68`; box invertito o fuori dalla foto → `ValueError`, nessun file; `overlay` con una spec facade `px` di due finestre scrive un'immagine 400×300; la riga di comando stampa il JSON di `crop`.
- [ ] RED → implementa → GREEN; `npm test` verde; commit `Add overlay and crop for any photo`.

### Task 4: `scene2` in manifest, setup, doctor e silhouette

**Files:** `models.json`, `scripts/detector-install.mjs`, `scripts/setup.mjs`, `tools/silhouette.py`, `tests/detector-install.test.mjs`, `tests/setup.test.mjs`, `tests/test_silhouette.py`.

**Interfaces:** `modelRuns(manifest) -> string[]` = `[...default, ...(scene ?? [])]` in `detector-install.mjs`, usato da `installState`, `installedDetector`, setup e doctor; `installedDetector(...).scene` = percorso di `scene[0]` o `null`; `silhouette.scene_weights(env=os.environ) -> str` (variabile se il file esiste, altrimenti la logica attuale).

- [ ] Test che falliscono: manifest con `scene` letto, `scene` con run assente da `files` → `null`; installazione senza `scene2` verificato → `incomplete`/`pending`; `installedDetector().scene` termina con `scene2.pt`; doctor `models parts2m+parts11s+scene2 2026.11.07, sha256 verified`; setup scarica tre file; installazione `2026.11.06` con manifest `2026.11.07` → `outdated`; `scene_weights` con variabile su file esistente → quel file, su file inesistente → la logica attuale.
- [ ] RED → implementa; `models.json` con sha256 e bytes di `data/det-runs/scene2/weights/best.pt` → GREEN; `npm test` verde; commit `Ship the scene model with the detector install`.

### Task 5: `scripts/run-tool.mjs`

**Interfaces:** `TOOLS` (mappa nome → `[script, ...argomenti fissi]`); `toolCommand(repoRoot, env, tool, args) -> {python, args, env} | {error}`; CLI che usa `spawn` con `stdio: "inherit"`, `shell: false`, ed esce col codice del figlio (2 per errori propri).

- [ ] Test che falliscono `tests/run-tool.test.mjs`: `rectify` → `args` = `["-I", <repo>/tools/rectify.py, ...args]`; `overlay` → `[..., photo_tools.py, "overlay", ...]`; `../dev/train_data`, `rectify.py`, `""`, `__proto__` → `{error}` con l'elenco; nessun detector → `{error}` che contiene `node scripts/setup.mjs`; argomento `C:\Users\Filippo Visentì\a b.jpg` intatto; `env.YOLO_OFFLINE === "1"`; con un'installazione con `scene`, `env.RHINO_SCENE_WEIGHTS` termina con `scene2.pt`; la CLI su tool sconosciuto esce con 2 senza avviare Python.
- [ ] RED → implementa → GREEN; `npm test` verde; commit `Add run-tool: the runtime tools with the detector's Python`.

### Task 6: skill, README, docstring

- [ ] `skills/rhino-model/SKILL.md`: i comandi di `rectify`, `photo3d`, `silhouette`, `overlay`, `crop` col prefisso `node "<plugin>/scripts/run-tool.mjs"`; `overlay`/`crop` su qualsiasi foto; `tools/dev/facade_bench.py errors` come riferimento di misura. Verifica: `grep -n "python \"<plugin>\|python tools/" skills/rhino-model/SKILL.md` → nessuna riga.
- [ ] README: comandi di sviluppo con `tools/dev/`, paragrafo su `run-tool`; docstring di `silhouette.py`, `photo3d.py`, `rectify.py` col nuovo comando.
- [ ] `npm test` verde; commit `Point the skill and docs at run-tool and tools/dev`.

### Task 7: release, prova reale

- [ ] **Chiedere l'ok**, poi `gh release create models-2026.11.07` con `parts2m.pt`, `parts11s.pt`, `scene2.pt`; verifica dimensioni con `models.json`.
- [ ] Setup reale con `LOCALAPPDATA` separato; clone pulito; da lì `run-tool rectify` (foto di prova, quattro angoli qualsiasi validi), `overlay` (con `expected.json` come spec non serve: usa una spec facade `px` di prova), `crop`, `silhouette mask` su `data/hznu/all_adjust_zhedang/c_0075.jpg` → ognuno esce con 0 e scrive il file. Doctor: tre `OK` con `scene2` nella riga models.
- [ ] Ledger con l'esito; cartelle di prova cancellate solo con l'ok.
