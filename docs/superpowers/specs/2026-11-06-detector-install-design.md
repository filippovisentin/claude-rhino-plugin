# Detector installabile sui PC dello studio

Data: 2026-11-06 · Stato: in revisione · Branch: `feat/detector-install`

## Obiettivo

Il plugin `rhino` si installa sul PC di un collega e `detect_facade` funziona con i modelli
YOLO addestrati da Filippo, senza la cartella `data/` del suo PC.

**Successo:** su un PC che non ha mai visto il progetto, dopo `claude plugin install` e un solo
comando di setup, `node scripts/doctor.mjs` mostra le righe del detector in `OK` e
`detect_facade` sulla foto di prova restituisce la bozza attesa (stesso numero di elementi per
classe, ogni box entro 4 px dal riferimento).

## Contesto

- Utenti: studio e colleghi, uso interno, repository GitHub privato
  (`filippovisentin/claude-rhino-plugin`); l'accesso si gestisce da GitHub.
- PC: Windows con GPU NVIDIA, simili a quello di riferimento (RTX 5070 Ti Laptop, driver 596.36).
- Oggi `scripts/facade-detector.mjs` cerca Python in `data/venv-det` e pesi in
  `data/det-runs/<run>/weights/best.pt` dentro la cartella del plugin. `data/` è in `.gitignore`,
  e la cartella del plugin installato viene sostituita a ogni aggiornamento.
- Modello predefinito: `parts2m` (YOLO11m, 41 MB) fuso con `parts11s` (YOLO11s, 19 MB).
- Misura del 2026-11-06 sulla foto hznu c_0075, entrambi i modelli: GPU 0,09 s per foto dopo il
  primo avvio, CPU 0,37 s, box identici (29 e 18).
- Bug trovato: con la GPU nascosta `detect_facade` fallisce (`AssertionError: Invalid device id`),
  perché Ultralytics riprende dai pesi il dispositivo usato in addestramento.

## Fuori ambito

Cosa riconosce il modello, la catena foto→3D (raddrizzamento automatico, MoGe), la pulizia di
`tools/`, macOS. Ciascuno avrà la sua specifica.

## Decisioni

| Tema | Decisione |
|---|---|
| Distribuzione pesi | Allegati di una GitHub Release del repo privato, scaricati con `gh` |
| Integrità | `models.json` nel repo con sha256 di ogni file; un file non verificato non viene mai usato |
| Python | Creato da `uv` in una cartella utente stabile, versioni bloccate |
| Dispositivo | GPU (torch CUDA 12.8) di default; `--cpu` opzionale; ripiego automatico su CPU a runtime |
| Licenza modelli | `MODELS-LICENSE.md`: solo uso interno (Ultralytics AGPL-3.0, dataset non commerciali) |

## Dove sta cosa

**Nel repository**
- `models.json`: modello predefinito e file.
  ```json
  {
    "version": "2026.11.06",
    "release": "models-2026.11.06",
    "default": ["parts2m", "parts11s"],
    "files": {
      "parts2m":  {"asset": "parts2m.pt",  "sha256": "<64 hex>", "bytes": 40566828},
      "parts11s": {"asset": "parts11s.pt", "sha256": "<64 hex>", "bytes": 19243354}
    }
  }
  ```
  Gli sha256 si calcolano dai `best.pt` attuali quando si crea la release.
- `requirements-detector.txt` (GPU) e `requirements-detector-cpu.txt`: versioni bloccate uguali
  al venv di riferimento: Python 3.12, torch 2.11.0 (+cu128 o +cpu), ultralytics 8.4.202,
  numpy 2.5.4, opencv-python 5.0.0, Pillow 12.3.0, psutil.
- `scripts/setup.mjs`: il setup.
- `tests/fixtures/detector/`: una foto di prova (hznu c_0075 ridotta a 1280 px, CC BY 4.0, con
  attribuzione) e `expected.json`, la bozza prodotta dal PC di riferimento.
- `MODELS-LICENSE.md`.

**Su GitHub**: release `models-2026.11.06` con `parts2m.pt` e `parts11s.pt`.

**Sul PC dell'utente**, `%LOCALAPPDATA%\claude-rhino\` (sopravvive agli aggiornamenti del plugin):
- `venv\`: il Python;
- `models\<version>\`: i pesi verificati;
- `cfg\`: cartella di configurazione di Ultralytics (`YOLO_CONFIG_DIR`);
- `setup.json`: cosa è installato.
  ```json
  {"version": "2026.11.06", "device": "cuda", "python": "...\\venv\\Scripts\\python.exe",
   "verified": {"parts2m": "<sha256>", "parts11s": "<sha256>"},
   "selftest": "ok", "date": "2026-11-06T12:00:00Z"}
  ```

## Setup (`node scripts/setup.mjs [--cpu]`)

Ogni passo controlla prima se è già a posto e in quel caso lo salta. Rilanciare il setup è
sempre sicuro.

1. **Controlli, senza installare nulla.** Ognuno, se fallisce, stampa la causa e il comando
   per risolverla, poi si ferma:
   - `nvidia-smi` presente e driver con versione principale ≥ 570 (minimo per CUDA 12.8).
     Saltato con `--cpu`;
   - `uv` nel `PATH` (se manca, indica il comando di installazione ufficiale senza eseguirlo);
   - `gh auth status` riuscito e accesso alla release (`gh release view <release>`);
   - almeno 8 GB liberi sul disco di `%LOCALAPPDATA%` (2 GB con `--cpu`).
2. **Python.** `uv venv --python 3.12 venv`, poi `uv pip install -r requirements-detector[-cpu].txt`
   (per la GPU con l'indice PyTorch cu128). Un venv che non importa `torch` e `ultralytics`
   viene cancellato e ricreato; si cancella solo dentro `%LOCALAPPDATA%\claude-rhino\`.
3. **Pesi.** Per ogni file non ancora verificato: `gh release download <release> -p <asset>`
   in `models\.tmp\`, sha256 calcolato e confrontato con `models.json`, poi spostato in
   `models\<version>\`. Se lo sha256 non coincide il file viene cancellato e il setup si ferma.
4. **Prova finale.** Il detector gira sulla foto di prova; esito `ok` se coincide con
   `expected.json` (stesse classi e conteggi, box entro 4 px), altrimenti `fail` con le differenze.
5. **`setup.json`** viene scritto alla fine di ogni passo riuscito, così un'interruzione lascia
   traccia di cosa è già fatto.

Il setup non chiude processi, non modifica impostazioni di sistema o variabili d'ambiente globali
e non installa programmi fuori da `%LOCALAPPDATA%\claude-rhino\`.

## Detector (`scripts/facade-detector.mjs`, `tools/facade_yolo.py`)

- **Ordine di ricerca**, vince il primo completo:
  1. `RHINO_FACADE_PYTHON` e `RHINO_FACADE_WEIGHTS` (come oggi);
  2. `%LOCALAPPDATA%\claude-rhino\` se `setup.json` esiste, la sua `version` coincide con
     `models.json` e ogni file del modello predefinito è in `verified` con lo sha256 di
     `models.json`;
  3. `data/venv-det` e `data/det-runs` del repo (PC di sviluppo, come oggi).
  Una versione installata più vecchia non viene usata: il tool resta nascosto e il doctor lo segnala.
- **Dispositivo:** `facade_yolo.py` passa sempre `device` a `predict`: `0` se
  `torch.cuda.is_available()`, altrimenti `"cpu"`. Una variabile `RHINO_FACADE_DEVICE`
  (`cuda`/`cpu`) lo può forzare.
- **Ambiente del processo:** `YOLO_CONFIG_DIR` sulla cartella `cfg` scelta e `YOLO_OFFLINE=1`,
  così nessuna inferenza scarica file.
- **Risultato:** la bozza resta uguale, con due campi in più: `device` (`cuda`/`cpu`) e
  `model` (`version` più i nomi dei run, oppure `custom` con le variabili d'ambiente).
- Restano invariati: nome e schema del tool, validazione dell'immagine, un solo argomento,
  timeout di 120 s, limite di output di 2 MB.

## Doctor

Tre righe dopo quelle esistenti, con i livelli già usati (`OK`, `WARN`, `FAIL`, `INFO`):

| Stato | Riga |
|---|---|
| Setup mai fatto e nessun `data/` | `INFO detector not installed (optional): node scripts/setup.mjs` |
| Python a posto | `OK detector python <percorso> (torch <ver> <cuda/cpu>)` |
| Modelli verificati e aggiornati | `OK detector models <default> <version>, sha256 verified` |
| Modelli più vecchi di `models.json` | `WARN detector models <installata> < <richiesta>: node scripts/setup.mjs` |
| sha256 non coincide | `FAIL detector models <file> sha256 mismatch: node scripts/setup.mjs` |
| GPU vista da torch | `OK detector gpu <nome>, driver <ver>` |
| GPU assente o non vista | `WARN detector gpu not available, running on CPU` |
| In uso `data/` del repo | `INFO detector using repo data/ (development)` |

Il controllo della GPU usa il Python del detector con un timeout di 30 s. La skill `rhino-doctor`
riceve queste righe nella tabella delle correzioni.

## Errori

- Rete assente durante il setup: il passo fallisce con un messaggio; quello che era già verificato
  resta valido.
- `gh` senza accesso al repo: il messaggio chiede di farsi aggiungere al repository.
- Driver troppo vecchio: indica di aggiornare il driver NVIDIA oppure di usare `--cpu`.
- Detector che fallisce a runtime: come oggi, l'errore torna a Claude nel risultato del tool;
  Claude legge la foto senza bozza.

## Test

**Automatici** (`npm test`, nessun download, nessuna GPU richiesta):
- ordine di ricerca nei tre casi, con cartelle finte e `LOCALAPPDATA` puntato a una cartella
  temporanea;
- `models.json` e `setup.json` mancanti, malformati, con versione diversa o sha256 diverso:
  il tool resta nascosto;
- setup: passi già completi saltati; sha256 sbagliato porta a file cancellato ed errore; con
  `gh`, `uv` e `nvidia-smi` sostituiti da script finti;
- doctor: ogni riga della tabella;
- `facade_yolo.py`: con la GPU nascosta usa la CPU e restituisce `device: "cpu"`
  (test Python, saltato se `ultralytics` non c'è).

**Reali, sul PC di riferimento:**
1. setup completo con `LOCALAPPDATA` puntato a una cartella separata (il `venv-det` esistente non
   viene toccato);
2. `doctor` tutto `OK`;
3. `detect_facade` sulla foto di prova uguale a `expected.json`, e uguale al risultato con `data/`;
4. stessa cosa con `RHINO_FACADE_DEVICE=cpu`.

**Collaudo di un collega**, fatto da Filippo con una lista di 5 passi nel README:
accesso al repo, `gh auth login`, installazione del plugin, setup, doctor e una foto.

## Azioni che richiedono un ok esplicito

- Creare la release `models-2026.11.06` e caricare i pesi sul GitHub privato.
- Commit, push e pull request.

## Ordine di lavoro previsto

1. Correzione del dispositivo in `facade_yolo.py` (indipendente, risolve il bug).
2. `models.json`, file requirements, `MODELS-LICENSE.md`, fixture con `expected.json`.
3. Ricerca dei percorsi in `facade-detector.mjs`.
4. `setup.mjs`.
5. Doctor e skill `rhino-doctor`.
6. Release dei pesi (dopo l'ok), prova reale, README.
