# Strumenti runtime funzionanti ovunque, strumenti di sviluppo separati

Data: 2026-11-06 · Stato: in revisione · Branch: `feat/runtime-tools` (da `feat/detector-install`, PR #5)

## Obiettivo

Tutto quello che la skill `rhino-model` dice a Claude di eseguire funziona sul PC di un collega che
ha fatto `node scripts/setup.mjs`. Gli strumenti di addestramento, benchmark ed esperimenti sono
separati in `tools/dev/` e restano utilizzabili sul PC di Filippo.

**Successo:** da una copia pulita del repo (senza `data/`) con un'installazione fatta dal setup,
`node scripts/run-tool.mjs rectify|overlay|crop|silhouette mask` riescono sulla foto di prova; la
suite di test resta verde dopo lo spostamento; la skill non nomina più strumenti che richiedono
`data/`.

## Problemi di oggi

- La skill lancia `python "<plugin>/tools/rectify.py"`: sul PC di un collega non è detto che
  `python` abbia numpy e Pillow; quello del setup sì, ma Claude non sa dov'è.
- `silhouette.py mask` usa il modello `scene2` (o `scene11s`) da `data/det-runs`: non è nella release.
- `facade_bench.py overlay/crop` lavorano solo su foto del dataset CMP (`data/`).
- `facade_yolo.py` mescola il rilevamento usato dal plugin e la costruzione dei dataset, e importa
  il benchmark `facade_bench.py` a livello di modulo.
- 12 dei 19 script di `tools/` servono solo per addestrare, misurare o sperimentare.

## Disposizione

**`tools/` (runtime):** `rectify.py`, `photo3d.py`, `silhouette.py`, `export_mesh.py`,
`facade_regular.py`, e due nuovi:
- `facade_detect.py`: il rilevamento estratto da `facade_yolo.py` senza cambiare il comportamento:
  `NAMES`, `REVIEW`, `ORDER`, `PALETTE_FROM`, `_iou`, `_hood`, `draft_elements`, `fuse_boxes`,
  `pick_device`, `predict`, `facade_px`, `detect_image`, `dominant`, `sample_palette`, `_expose`, e la
  riga di comando `detect-image PHOTO WEIGHTS CONF`. Non importa `facade_bench`.
- `photo_tools.py`: `overlay PHOTO SPEC.json OUT.jpg` (i box `px` della spec disegnati sulla foto, come
  `facade_bench overlay` ma per qualsiasi foto) e `crop PHOTO x0 y0 x1 y1 OUT.jpg [--size 768]`
  (ritaglio ingrandito; stampa `{"origin":[x0,y0],"scale":s}` così px = origin + pixel del ritaglio / s).

**`tools/dev/` (sviluppo):** `facade_bench.py`, `facade_yolo.py` (dataset, `detect` per id, `compare`;
importa e riesporta tutto da `facade_detect`), `train_data.py`, `train_report.py`,
`ensemble_report.py`, `facade_report.py`, `photo_bench.py`, `clean_pick.py`, `facade_refine.py`,
`fuzz_specs.py`, `glass_read.py`, `solid_audit.py`, `scenarios/`, e `auto_rectify.py` committato con in
testa il risultato: "MoGe-2: 3,47° mediana contro 1,55° dei 4 angoli su 3 foto hznu; instabile con la
risoluzione; non collegato al plugin".

Ogni script spostato calcola la radice del repo un livello più su e mette in `sys.path` sia
`tools/dev` sia `tools`. I comandi documentati cambiano solo il percorso (`python tools/dev/train_data.py …`).

## `scripts/run-tool.mjs`

`node "<plugin>/scripts/run-tool.mjs" <tool> [args…]`

| tool | esegue |
|---|---|
| `rectify` | `tools/rectify.py args…` |
| `photo3d` | `tools/photo3d.py args…` |
| `silhouette` | `tools/silhouette.py args…` |
| `overlay` | `tools/photo_tools.py overlay args…` |
| `crop` | `tools/photo_tools.py crop args…` |

- Qualsiasi altro `tool` → uscita 2 con l'elenco ammesso; nessun processo avviato.
- Python: quello di `findDetector(repoRoot)` (variabili, installazione, `data/`). Se non c'è → uscita 2
  con `run node scripts/setup.mjs first`.
- Avvio con `execFile`/`spawn` senza shell, `-I`, argomenti passati intatti uno per uno, output e
  codice di uscita del figlio inoltrati.
- Ambiente: `YOLO_OFFLINE=1`, `YOLO_CONFIG_DIR` del detector, `RHINO_SCENE_WEIGHTS` col modello
  scene installato (se c'è).
- Funzione testabile: `toolCommand(repoRoot, env, tool, args) -> {python, args, env} | {error}`.

## Modello `scene2` nella release

- `models.json`: `version` `2026.11.07`, `release` `models-2026.11.07`, nuovo campo
  `"scene": ["scene2"]`, e `files.scene2` (asset `scene2.pt`, sha256 e bytes dal `best.pt` attuale).
- `readManifest`: `scene` facoltativo; se c'è, array di run tutti presenti in `files` e validi.
- Setup, `installState`, `installedDetector` e doctor trattano `[...default, ...scene]` come i modelli
  da scaricare e verificare. `installedDetector` restituisce anche `scene` (percorso del file o `null`).
  La riga del doctor diventa `models parts2m+parts11s+scene2 2026.11.07, sha256 verified`.
- `silhouette.py`: se `RHINO_SCENE_WEIGHTS` punta a un file esistente lo usa, altrimenti la logica di
  oggi su `data/det-runs/scene2|scene11s`.
- Nuova release `models-2026.11.07` con `parts2m.pt`, `parts11s.pt`, `scene2.pt`: **solo dopo l'ok**.
  Le installazioni `2026.11.06` diventano `outdated` e il setup riscarica i tre file.

## Skill e documentazione

- `skills/rhino-model/SKILL.md`: `rectify`, `silhouette`, `photo3d`, `overlay`, `crop` con il prefisso
  `node "<plugin>/scripts/run-tool.mjs"`; `overlay`/`crop` su qualsiasi foto; gli errori sistematici
  restano citati come misura, con il percorso `tools/dev/facade_bench.py`.
- README: comandi di sviluppo con `tools/dev/`; una riga su `run-tool`.
- Docstring di `silhouette.py` e `photo3d.py` col nuovo comando.

## Test

- Tutti i test esistenti verdi dopo lo spostamento (con i percorsi di import aggiornati).
- `run-tool`: tool ammessi e mappa; tool sconosciuto rifiutato senza avvio; nessun Python → messaggio
  setup; percorso con spazio e accento intatto; `shell` mai attivo; `-I` presente;
  `RHINO_SCENE_WEIGHTS` impostato con un'installazione che ha `scene`.
- `photo_tools`: `crop` produce l'immagine e stampa origin/scale coerenti; `overlay` produce un'immagine
  della stessa dimensione della foto.
- `facade_detect` senza `facade_bench`: `import facade_detect` non importa `facade_bench`.
- Manifest con `scene`: lettura, verifica, stato, doctor; setup che scarica anche `scene2`.
- `silhouette` usa `RHINO_SCENE_WEIGHTS`.
- Reale (dopo la release): setup in cartella separata; da una copia pulita `run-tool rectify`,
  `overlay`, `crop` sulla foto di prova e `silhouette mask` su una foto hznu.

## Fuori ambito

Cosa riconoscono i modelli; nuovi automatismi foto→3D; tool MCP nuovi.
