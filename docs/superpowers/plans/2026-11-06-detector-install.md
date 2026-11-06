# Detector installabile — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `detect_facade` funziona su un PC dello studio dopo `claude plugin install` e
`node scripts/setup.mjs`, con i pesi della release GitHub verificati via sha256.

**Architecture:** Un modulo nuovo `scripts/detector-install.mjs` contiene tutta la logica pura
(percorsi, lettura di `models.json` e `setup.json`, sha256, confronto delle bozze, righe del
doctor). `facade-detector.mjs` lo usa per cercare il detector in tre posti, `setup.mjs` per
installarlo, `doctor.mjs` per riferire. `facade_yolo.py` sceglie il dispositivo in modo esplicito.

**Tech Stack:** Node ≥18 (ESM, `node:test`), Python 3.12 (`unittest`), `uv`, `gh`, Ultralytics YOLO.

**Spec:** `docs/superpowers/specs/2026-11-06-detector-install-design.md`

## Global Constraints

- Cartella di installazione: `%LOCALAPPDATA%\claude-rhino\` (`venv\`, `models\<version>\`, `cfg\`, `setup.json`).
- Release: `models-2026.11.06`; versione modelli `2026.11.06`; predefinito `["parts2m", "parts11s"]`.
- Versioni bloccate: Python 3.12, torch 2.11.0 (+cu128 / +cpu), ultralytics 8.4.202, numpy 2.5.4, opencv-python 5.0.0, Pillow 12.3.0, psutil.
- GPU: driver NVIDIA con versione principale ≥ 570; `--cpu` salta il controllo. Spazio libero minimo 8 GB (2 GB con `--cpu`).
- Prova finale: stesse classi e conteggi di `expected.json`, ogni box entro 4 px.
- Nessun processo figlio passa per una shell (`execFile`, `shell: false`); ogni percorso è un solo argomento.
- Il setup cancella solo dentro `%LOCALAPPDATA%\claude-rhino\`, non chiude processi, non tocca variabili d'ambiente globali.
- Inferenza sempre con `YOLO_OFFLINE=1`.
- Invariati: nome e schema di `detect_facade`, `checkImage`, `checkConf`, timeout 120 s, output massimo 2 MB, variabili `RHINO_FACADE_PYTHON` / `RHINO_FACADE_WEIGHTS`.
- Release su GitHub, commit, push e PR solo dopo l'ok esplicito di Filippo.

## Review Focus

1. Nome utente Windows con spazi o accenti (`C:\Users\Filippo Visentin\…`): ogni comando deve ricevere il percorso intatto come un solo argomento. Test in Task 3 e Task 4.
2. Setup interrotto a metà download (un file parziale in `models\.tmp\`): il rilancio cancella il parziale e riscarica, senza mai usarlo. Test in Task 4.
3. `setup.json` scritto a mano, troncato o di uno schema vecchio: trattato come assente, nessun crash né al lancio del plugin né nel doctor. Test in Task 3 e Task 5.
4. Allegato elencato in `models.json` ma assente nella release (`gh` esce con errore): il setup si ferma con il nome dell'allegato e non scrive `verified` per quel file. Test in Task 4.
5. Setup in corso mentre Claude usa il detector: il setup scrive `selftest: "pending"` prima di toccare venv o pesi, e il detector ignora l'installazione finché `selftest` non torna `"ok"`. Test in Task 3 e Task 4.

---

### Task 1: dispositivo esplicito in `facade_yolo.py`

**Files:**
- Modify: `tools/facade_yolo.py` (`predict`, righe ~309-332; `detect_image`, righe ~349-358)
- Test: `tests/test_facade_device.py`

**Interfaces:**
- Produces: `pick_device(env=os.environ, cuda=None) -> int | str` (`0` oppure `"cpu"`); `detect_image(...)` restituisce anche `"device": "cuda" | "cpu"`.

- [ ] **Step 1: Scrivi il test che fallisce**

```python
class PickDevice(unittest.TestCase):
    def test_gpu_when_cuda(self):      self.assertEqual(FY.pick_device({}, cuda=True), 0)
    def test_cpu_without_cuda(self):   self.assertEqual(FY.pick_device({}, cuda=False), "cpu")
    def test_env_forces_cpu(self):     self.assertEqual(FY.pick_device({"RHINO_FACADE_DEVICE": "cpu"}, cuda=True), "cpu")
    def test_env_cuda_without_gpu_falls_back(self):
        self.assertEqual(FY.pick_device({"RHINO_FACADE_DEVICE": "cuda"}, cuda=False), "cpu")
    def test_bad_env_ignored(self):    self.assertEqual(FY.pick_device({"RHINO_FACADE_DEVICE": "x"}, cuda=True), 0)
```
Più un test saltato se `ultralytics` non si importa: con `CUDA_VISIBLE_DEVICES=""` in un sottoprocesso, `detect-image` su `tests/fixtures/detector/c_0075.jpg` (Task 2; finché non esiste usa `skipUnless(os.path.exists(...))`) con i pesi di `data/det-runs` esce con codice 0 e stampa `"device":"cpu"`.

- [ ] **Step 2:** `python -m unittest tests.test_facade_device -v` → FAIL (`pick_device` non esiste).
- [ ] **Step 3: Implementa** `pick_device`: `cuda=None` significa `torch.cuda.is_available()` (import di torch dentro la funzione). `predict` passa `device=pick_device()` a ogni `.predict(...)`; `detect_image` aggiunge `"device": "cpu" if dev == "cpu" else "cuda"`.
- [ ] **Step 4:** stesso comando → PASS. Poi verifica a mano: `CUDA_VISIBLE_DEVICES= data/venv-det/Scripts/python.exe tools/facade_yolo.py detect-image data/hznu/all_adjust_zhedang/c_0075.jpg "data/det-runs/parts2m/weights/best.pt;data/det-runs/parts11s/weights/best.pt" 0.25` → JSON con 13 elementi e `"device":"cpu"` (prima del fix: `AssertionError: Invalid device id`).
- [ ] **Step 5:** `npm test` tutto verde; commit `Pick the detector's device explicitly so it runs without a GPU`.

### Task 2: manifest, requirements, licenza, fixture e helper puri

**Files:**
- Create: `models.json`, `requirements-detector.txt`, `requirements-detector-cpu.txt`, `MODELS-LICENSE.md`
- Create: `tests/fixtures/detector/c_0075.jpg`, `tests/fixtures/detector/expected.json`, `tests/fixtures/detector/README.md`
- Create: `scripts/detector-install.mjs`
- Test: `tests/detector-install.test.mjs`

**Interfaces:**
- Produces (in `scripts/detector-install.mjs`):
  - `readManifest(repoRoot: string) -> {version, release, default: string[], files: {[run]: {asset, sha256, bytes}}} | null` (null se manca o non valido: `version`/`release` stringhe non vuote, `default` non vuoto, ogni run di `default` in `files`, sha256 di 64 caratteri esadecimali minuscoli, `bytes` intero positivo);
  - `sha256File(path: string) -> Promise<string>` (hex minuscolo, a stream);
  - `compareDraft(actual: object, expected: object, tol = 4) -> string[]` (vuoto se uguali: conteggi per classe `k` uguali, e accoppiando per classe in ordine di `box`, ogni coordinata entro `tol`; ogni differenza è una riga leggibile).

- [ ] **Step 1: Test che falliscono** in `tests/detector-install.test.mjs`:
  - `readManifest` sul `models.json` vero del repo: `version === "2026.11.06"`, `release === "models-2026.11.06"`, `default` uguale a `["parts2m","parts11s"]`;
  - su una cartella temporanea: file assente → `null`; JSON troncato → `null`; sha256 di 63 caratteri → `null`; run di `default` assente da `files` → `null`;
  - `sha256File` su un file con contenuto `"abc"` → `"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"`;
  - `compareDraft(e, e)` → `[]`; un box spostato di 5 px → una riga che contiene la classe; un elemento in meno → una riga con i due conteggi.
- [ ] **Step 2:** `node --test tests/detector-install.test.mjs` → FAIL.
- [ ] **Step 3: File di dati.**
  - `models.json` come nella spec, con `bytes` 40566828 e 19243354 e sha256 calcolati da `data/det-runs/parts2m/weights/best.pt` e `data/det-runs/parts11s/weights/best.pt` (`sha256sum`).
  - `requirements-detector.txt`: prima riga `--extra-index-url https://download.pytorch.org/whl/cu128`, poi `torch==2.11.0+cu128`, `ultralytics==8.4.202`, `numpy==2.5.4`, `opencv-python==5.0.0`, `Pillow==12.3.0`, `psutil`. La variante `-cpu` usa `.../whl/cpu` e `torch==2.11.0+cpu`.
  - `MODELS-LICENSE.md`: i pesi sono solo per uso interno allo studio; derivano da Ultralytics (AGPL-3.0) e da dataset tra cui LabelMeFacade, eTRIMS e ADE20K (ricerca, non commerciale); il codice del plugin resta MIT.
  - Fixture: `c_0075.jpg` da `data/hznu/all_adjust_zhedang/c_0075.jpg`, ridotta a lato lungo 1280 px (Pillow, `LANCZOS`, qualità JPEG 90); `README.md` della fixture con fonte e licenza (hznu_facade, CC BY 4.0, doi 10.17632/k387xkyc5f.1); `expected.json` è l'output di `detect-image` di questa foto con i due pesi di `data/det-runs`, conf 0.25, sul PC di riferimento (GPU).
- [ ] **Step 4: Implementa** le tre funzioni. Step 2 → PASS.
- [ ] **Step 5:** `npm test` verde; commit `Add the model manifest, pinned requirements, model licence and detector fixture`.

### Task 3: ricerca del detector installato

**Files:**
- Modify: `scripts/detector-install.mjs`, `scripts/facade-detector.mjs` (`findDetector` righe ~43-55, `runDetector` righe ~79-96)
- Test: `tests/detector-install.test.mjs`, `tests/facade-detector.test.mjs`

**Interfaces:**
- Consumes: `readManifest` (Task 2).
- Produces:
  - `installDir(env = process.env) -> string`: `join(env.LOCALAPPDATA || join(homedir(), "AppData", "Local"), "claude-rhino")`;
  - `readSetup(dir: string) -> object | null` (null se manca o se non è un oggetto con `version` stringa e `verified` oggetto);
  - `installState(repoRoot, env) -> {state: "none" | "ok" | "pending" | "outdated" | "incomplete", manifest, setup, dir}`;
  - `installedDetector(repoRoot, env, {allowPending = false} = {}) -> {python, weights, configDir, version} | null`: solo con `state === "ok"` (con `allowPending` basta che tutto il resto sia a posto, qualunque sia `selftest`; lo usa solo il selftest del setup), cioè `setup.version === manifest.version`, `setup.selftest === "ok"`, ogni run di `manifest.default` con `setup.verified[run] === manifest.files[run].sha256` e il file `models/<version>/<asset>` esistente, e `venv/Scripts/python.exe` (o `bin/python`) esistente. `weights` = asset del predefinito uniti con `delimiter`, nell'ordine di `default`; `configDir` = `<dir>/cfg`;
  - `findDetector(repoRoot, env)` restituisce anche `source: "env" | "installed" | "repo"` e `version: string | null`. Ordine: (1) se è impostata `RHINO_FACADE_PYTHON` o `RHINO_FACADE_WEIGHTS` vale la logica attuale con `source: "env"`; (2) `installedDetector`; (3) la logica attuale su `data/` con `source: "repo"`.
  - `runDetector` imposta sempre `YOLO_OFFLINE=1` e aggiunge alla bozza `model`: `"<version> <run+run>"` per `installed`, `"repo"` o `"custom"` per gli altri.

- [ ] **Step 1: Test che falliscono**, con `LOCALAPPDATA` puntato a una cartella temporanea il cui nome contiene uno spazio e una lettera accentata (`"Filippo Visentì"`):
  - nessun `setup.json` → `installState().state === "none"`, `installedDetector() === null`;
  - installazione completa e coerente → `findDetector().source === "installed"`, `weights` termina con `parts2m.pt` + `delimiter` + `.../parts11s.pt`, e il percorso contiene lo spazio intatto;
  - `setup.json` troncato (`"{\"version\""`) → `state "none"`, nessuna eccezione;
  - `selftest: "pending"` → `state "pending"`, `installedDetector() === null`;
  - `setup.version` `"2026.10.01"` → `state "outdated"`; se esiste `data/` del repo, `findDetector().source === "repo"`;
  - `verified.parts11s` diverso da `models.json` → `state "incomplete"`;
  - con `RHINO_FACADE_PYTHON` e `RHINO_FACADE_WEIGHTS` impostate e installazione valida → `source "env"`;
  - `runDetector` con `run` finto: l'oggetto `env` passato contiene `YOLO_OFFLINE: "1"`, e la bozza restituita ha `model === "2026.11.06 parts2m+parts11s"` per un detector `installed`.
  - Il test esistente "helpers: defaults and detector discovery" deve restare verde dopo aver aggiunto `LOCALAPPDATA` temporaneo vuoto al suo `env`.
- [ ] **Step 2:** `node --test tests/detector-install.test.mjs tests/facade-detector.test.mjs` → FAIL.
- [ ] **Step 3: Implementa** le funzioni. `findDetector` resta sincrono e non calcola sha256 (si fida di `setup.json`; il doctor ricalcola).
- [ ] **Step 4:** stesso comando → PASS; `npm test` verde.
- [ ] **Step 5:** commit `Find the detector installed in LOCALAPPDATA before the repo's data folder`.

### Task 4: `scripts/setup.mjs`

**Files:**
- Create: `scripts/setup.mjs`
- Test: `tests/setup.test.mjs`

**Interfaces:**
- Consumes: `installDir`, `readManifest`, `readSetup`, `sha256File`, `compareDraft` (Task 2-3); `runDetector` (`facade-detector.mjs`).
- Produces: `setup({repoRoot, env, cpu = false, exec, log}) -> Promise<{ok: boolean, step: string, message: string}>`. `exec(file, args, opts) -> Promise<{code, stdout, stderr}>` è iniettabile (di default `execFile` promisificato, `shell: false`, `windowsHide: true`, che non lancia eccezioni sul codice di uscita). La CLI (`node scripts/setup.mjs [--cpu]`) chiama `setup`, stampa i messaggi e esce con 0/1; parte solo quando il modulo è eseguito direttamente.

`setup.json` ha i campi `version`, `device` (`"cuda"`/`"cpu"`), `python` (percorso), `verified` (`{run: sha256}`), `selftest` (`"pending"`/`"ok"`/`"fail"`), `date` (ISO 8601) ed eventualmente `diff` (righe di `compareDraft`). Passi, ciascuno saltato se già a posto, con `setup.json` riscritto dopo ogni passo riuscito (scrittura in un file temporaneo e poi `rename`):
1. `prereqs`: `nvidia-smi --query-gpu=name,driver_version --format=csv,noheader` (versione principale ≥ 570; saltato con `cpu`); `uv --version`; `gh auth status`; `gh release view <release> --repo filippovisentin/claude-rhino-plugin`; spazio libero con `fs.statfsSync` sulla cartella esistente più vicina a `installDir` (8 GB, o 2 GB con `cpu`; se `statfsSync` non esiste il controllo viene saltato con un messaggio).
2. `python`: prima di toccare il venv scrive `selftest: "pending"`. Il venv è a posto se `<venv python> -c "import torch, ultralytics"` esce con 0 e `setup.device` coincide con la modalità richiesta. Altrimenti cancella `venv` (solo dentro `installDir`), poi `uv venv --python 3.12 <dir>/venv` e `uv pip install --python <venv python> --index-strategy unsafe-best-match -r <repoRoot>/requirements-detector[-cpu].txt`.
3. `models`: scrive `selftest: "pending"` se manca qualcosa. Per ogni run di `default` non verificato: svuota `models/.tmp`, `gh release download <release> --repo filippovisentin/claude-rhino-plugin -p <asset> -D <dir>/models/.tmp`, confronta lo sha256; se coincide sposta il file in `models/<version>/<asset>` e scrive `verified[run]`; altrimenti cancella il file e si ferma con `step: "models"`.
4. `selftest`: crea il detector con `installedDetector(repoRoot, env, {allowPending: true})`, esegue `runDetector` su `tests/fixtures/detector/c_0075.jpg` e lo confronta con `expected.json` con `compareDraft`; scrive `selftest: "ok"` oppure `"fail"` più le differenze.
5. Messaggio finale: versione, dispositivo e `node scripts/doctor.mjs`.

- [ ] **Step 1: Test che falliscono**, con `exec` finto (una tabella comando → risultato) e `LOCALAPPDATA` temporaneo con spazio e accento. Il finto `gh release download` scrive nell'argomento dopo `-D` un file con contenuto fisso; `models.json` di prova punta al suo sha256.
  - tutto a posto → `ok: true`, `setup.json` con `verified` per entrambi i run e `selftest: "ok"` (il `runDetector` del selftest è sostituito da un finto che restituisce `expected.json`);
  - secondo lancio → nessuna chiamata a `uv` né a `gh release download` (controlla il registro delle chiamate);
  - driver `"566.03"` → `{ok: false, step: "prereqs"}` con `570` nel messaggio; con `cpu: true` lo stesso driver passa e il file usato è `requirements-detector-cpu.txt`;
  - `gh` che scarica contenuto sbagliato → `{ok: false, step: "models"}`, nessun file in `models/<version>/`, `verified` senza quel run;
  - `gh release download` che esce con 1 → `{ok: false, step: "models"}` con il nome dell'allegato nel messaggio;
  - un file parziale già presente in `models/.tmp/parts2m.pt` → rimosso prima del download, mai spostato;
  - dopo un fallimento in `models`, `setup.json` ha `selftest: "pending"`;
  - ogni percorso arriva a `exec` come un elemento intero di `args` (contiene lo spazio e l'accento);
  - nessuna chiamata a `exec` ha `shell: true`.
- [ ] **Step 2:** `node --test tests/setup.test.mjs` → FAIL.
- [ ] **Step 3: Implementa** `setup.mjs`.
- [ ] **Step 4:** stesso comando → PASS; `npm test` verde.
- [ ] **Step 5:** commit `Add the detector setup: pinned Python by uv, verified weights from the release, self-test`.

### Task 5: doctor e skill `rhino-doctor`

**Files:**
- Modify: `scripts/detector-install.mjs`, `scripts/doctor.mjs` (blocco 4b, righe ~49-52), `skills/rhino-doctor/SKILL.md` (riga `detector` della tabella)
- Test: `tests/detector-install.test.mjs`

**Interfaces:**
- Consumes: `installState`, `findDetector`, `sha256File`.
- Produces: `detectorReport(repoRoot, env, exec) -> Promise<Array<{status: "ok"|"warn"|"fail"|"info", check: "detector", detail: string}>>`. `doctor.mjs` chiama `report(...)` per ogni riga.

Righe (testo esatto dopo `detector `):

| Caso | status | detail |
|---|---|---|
| `source "repo"` | info | `using repo data/ (development): <weights>` |
| `source "env"` | info | `using RHINO_FACADE_PYTHON / RHINO_FACADE_WEIGHTS: <weights>` |
| nessun detector, `state "none"` | info | `not installed (optional): node scripts/setup.mjs` |
| `state "pending"` | warn | `setup not finished: node scripts/setup.mjs` |
| `state "outdated"` | warn | `models <installata> < <richiesta>: node scripts/setup.mjs` |
| `state "incomplete"` o sha256 su disco diverso | fail | `models <file> sha256 mismatch: node scripts/setup.mjs` |
| installato | ok | `python <percorso> (torch <ver> <cuda/cpu>)` |
| installato, sha256 ricalcolati uguali | ok | `models <run+run> <version>, sha256 verified` |
| GPU vista da torch | ok | `gpu <nome>, driver <ver>` |
| GPU non vista | warn | `gpu not available, running on CPU` |

Python e GPU si leggono con una sola chiamata al Python del detector, timeout 30 s:
`-c "import json,torch;c=torch.cuda.is_available();print(json.dumps([torch.__version__,c,torch.cuda.get_device_name(0) if c else None]))"`; il driver da `nvidia-smi` come nel setup. Se la chiamata fallisce o scade → `fail` `python <percorso> does not start: node scripts/setup.mjs`.

- [ ] **Step 1: Test che falliscono:** una riga per caso della tabella, con `exec` finto e cartelle temporanee; `setup.json` troncato → riga `info … not installed`, nessuna eccezione.
- [ ] **Step 2:** `node --test tests/detector-install.test.mjs` → FAIL.
- [ ] **Step 3: Implementa** `detectorReport`; in `doctor.mjs` sostituisci il blocco 4b; nella skill sostituisci la riga `detector` con una riga per stato (`not installed`, `setup not finished`, `models … <`, `sha256 mismatch`, `does not start`, `running on CPU`) e la correzione relativa (rilanciare il setup; `--cpu`; aggiornare il driver NVIDIA; chiedere l'accesso al repo).
- [ ] **Step 4:** test PASS; `npm test` verde; `node scripts/doctor.mjs` sul PC di riferimento mostra `[INFO] detector using repo data/ (development): …`.
- [ ] **Step 5:** commit `Report the installed detector in the doctor`.

### Task 6: release dei pesi, prova reale, README

**Files:**
- Modify: `README.md` (sezione "Local facade detector" e una nuova "Setting up a colleague's PC")

- [ ] **Step 1 — chiedere l'ok a Filippo**, poi:
  `gh release create models-2026.11.06 --repo filippovisentin/claude-rhino-plugin --title "Facade models 2026.11.06" --notes "parts2m + parts11s. Internal use only, see MODELS-LICENSE.md."`, poi `gh release upload` dei due file copiati come `parts2m.pt` e `parts11s.pt`. Verifica: `gh release view models-2026.11.06 --json assets` mostra due allegati con i `bytes` di `models.json`.
- [ ] **Step 2 — Setup reale in una cartella separata** (il `venv-det` non viene toccato), nel rispetto dei limiti di memoria (una cosa alla volta, RAM libera ≥ 6 GB):
  `LOCALAPPDATA="C:/Users/filip/AppData/Local/Temp/claude-rhino-trial" node scripts/setup.mjs` → esce con 0 e l'ultima riga riporta `2026.11.06` e `cuda`.
- [ ] **Step 3 — Doctor da una copia pulita:** `git clone . C:/Users/filip/AppData/Local/Temp/claude-rhino-clone` (il clone non ha `data/`, che è in `.gitignore`), poi da lì `LOCALAPPDATA="C:/Users/filip/AppData/Local/Temp/claude-rhino-trial" node scripts/doctor.mjs` → tre righe `OK` (`python`, `models`, `gpu`). Il clone si cancella solo con l'ok di Filippo.
- [ ] **Step 4 — Confronto:** `detect_facade` dal detector installato e da `data/` sulla foto di prova → `compareDraft` restituisce `[]`. Ripeti con `RHINO_FACADE_DEVICE=cpu` → `[]`, `device: "cpu"`.
- [ ] **Step 5 — README:** sezione detector aggiornata (setup, `--cpu`, dove finiscono i file, licenza modelli) e lista di 5 passi per un collega: 1) farsi aggiungere al repo; 2) `gh auth login`; 3) installare il plugin; 4) `node scripts/setup.mjs` dalla cartella del plugin; 5) `node scripts/doctor.mjs` con tre `OK`, poi una foto a Claude.
- [ ] **Step 6:** `npm test` verde; commit `Document the detector setup for studio PCs`. Push e PR solo dopo l'ok di Filippo.
