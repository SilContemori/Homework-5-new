# HW5 — Ingegneria dei Dati

Motore di ricerca e retrieval accademico full-text basato su **FastAPI** ed **Elasticsearch**, progettato per l'esplorazione avanzata di articoli scientifici da due sorgenti eterogenee: **arXiv** e **PubMed Central (PMC)**, con estrazione e arricchimento contestuale di **tabelle** e **figure**.

---

## Indice

- [Obiettivi del Progetto](#obiettivi-del-progetto)
- [Pipeline di Elaborazione e Decisioni di Progetto](#pipeline-di-elaborazione-e-decisioni-di-progetto)
  - [1. Estrazione Documenti](#1-estrazione-documenti)
  - [2. Estrazione Tabelle](#2-estrazione-tabelle)
  - [3. Estrazione Figure e Contesto](#3-estrazione-figure-e-contesto)
  - [4. Indicizzazione Elasticsearch](#4-indicizzazione-elasticsearch)
  - [5. Motore di Ricerca e Visualizzatore](#5-motore-di-ricerca-e-visualizzatore)
- [Architettura del Progetto](#architettura-del-progetto)
- [Requisiti di Sistema](#requisiti-di-sistema)
- [Installazione e Configurazione](#installazione-e-configurazione)
- [Avvio di Elasticsearch](#avvio-di-elasticsearch)
- [Esecuzione della Pipeline e dell'Applicazione](#esecuzione-della-pipeline-e-dellapplicazione)
- [Guida alla Ricerca](#guida-alla-ricerca)
- [Valutazione Sperimentale e Risultati](#valutazione-sperimentale-e-risultati)
- [Riferimento API](#riferimento-api)

---

## Obiettivi del Progetto

L'obiettivo dell'Homework 5 è realizzare un sistema end-to-end per l'indicizzazione e il retrieval semantico/booleano di letteratura scientifica proveniente da due piattaforme con strutture e formati distinti (**arXiv** e **PubMed**).

Il flusso si articola in 5 fasi principali:

1. **[Estrazione Documenti](#1-estrazione-documenti)** :white_check_mark:
2. **[Estrazione Tabelle](#2-estrazione-tabelle)** :white_check_mark:
3. **[Estrazione Figure e Capitoli](#3-estrazione-figure-e-contesto)** :white_check_mark:
4. **[Indicizzazione su Elasticsearch](#4-indicizzazione-elasticsearch)** :white_check_mark:
5. **[Ricerca e Visualizzazione Avanzata](#5-motore-di-ricerca-e-visualizzatore)** :white_check_mark:

---

## Pipeline di Elaborazione e Decisioni di Progetto

### 1. Estrazione Documenti

Il modulo di acquisizione ([app/business/corpus_builder](file:///z:/home/valerio/project/Homework-5-new-dev/Homework-5-new-dev/Homework-5-new-dev/app/business/corpus_builder)) gestisce in modo unificato le due sorgenti:

- **PubMed Central (PMC)**:
  - Interroga le API NCBI E-Utilities (`esearch` ed `efetch`).
  - L'autenticazione tramite `NCBI_API_KEY` (configurata in `.env`) eleva la soglia di rate limit da 3 a 10 richieste/secondo, prevenendo blocchi WAF durante il download massivo.
  - Per PMC il formato HTML completo è sempre garantito e associato al relativo identificativo univoco `pmc_id`.
- **arXiv**:
  - Interroga le arXiv API per ricavare metadati, autori, abstract e identificativo del paper (es. `1805.12319v3`).
  - Converte gli URL astratti (`abs`) nei corrispettivi endpoint HTML (ar5iv / LaTeXML) e valida l'effettiva disponibilità del documento tramite codice di stato HTTP 200.
- **Normalizzazione dei Metadati**:
  - Tutti gli articoli vengono convertiti in un modello comune (`Paper`) che include titolo normalizzato, lista autori, abstract, date di pubblicazione/aggiornamento formattate in ISO, percorsi HTML/PDF e identificativi univoci.

> **Decisione di Progetto (Struttura di Paragrafi e Capitoli)**:
> Per uniformare la diversa gerarchia HTML tra arXiv (LaTeX) e PMC (JATS XML), un capitolo/sezione è identificato dalle intestazioni `<h2>` e `<h3>` discendenti dal titolo principale `<h1>`. Questa scelta permette di escludere elementi decorativi e definire confini coerenti per l'estrazione dei paragrafi di contesto.

---

### 2. Estrazione Tabelle

Il modulo [table_context_extractor.py](file:///z:/home/valerio/project/Homework-5-new-dev/Homework-5-new-dev/Homework-5-new-dev/app/business/extractor/table_context_extractor.py) analizza i documenti HTML tramite BeautifulSoup:

- **Individuazione e Risalita Antenati**:
  - Per arXiv: risale dal tag `<table>` fino al container semantico `.ltx_table` o `<figure>`.
  - Per PMC: individua i blocchi `<div class="table-wrap">` o `<section>`.
- **Arricchimento Contestuale**:
  - Estrazione della didascalia (`caption`, `figcaption`).
  - Estrazione del corpo tabellare sia in formato strutturato (righe/colonne) sia come testo pulito per l'indicizzazione.
  - **Menzioni nel testo**: ricerca nel corpo del documento di citazioni esplicite alla tabella (es. `Table 1`, `Table S2`).
  - **Paragrafi di contesto**: estrazione dei paragrafi limitrofi alla tabella e di quelli contenenti le menzioni, per catturare il significato semantico attribuito dall'autore.
- **Filtraggio Smart dei Casi Limite**:
  - Eliminazione di false tabelle usate per formule matematiche inline, allineamenti grafici o layout minori, salvaguardando solo le tabelle con effettivo valore informativo.

I dati estratti confluiscono in `tables_with_context.json`.

---

### 3. Estrazione Figure e Contesto

Il modulo [figure_context_extractor.py](file:///z:/home/valerio/project/Homework-5-new-dev/Homework-5-new-dev/Homework-5-new-dev/app/business/extractor/figure_context_extractor.py) gestisce immagini, grafici e illustrazioni scientifiche:

- **Individuazione Figure**:
  - Ricerca tag `<img>` e tag container `<figure>` (comuni sia ad arXiv sia a PMC).
  - Validazione su classi CSS, dimensioni e presenza di elementi descrittivi per scartare icone, loghi o pulsanti di interfaccia.
- **Metadati e Contesto Estratti**:
  - Identificativo dell'elemento (es. `S4.F1` per arXiv, `F1` per PMC) e numero progressivo della figura.
  - Didascalia completa (`caption` / `alt-text`).
  - **Menzioni nel testo**: scansione di pattern come `Figure 1`, `Fig. 2`, `Figure S1`.
  - **Paragrafi di contesto**: associazione dei paragrafi dell'articolo in cui la figura viene discussa o richiamata.

I dati estratti confluiscono in `figures_with_context.json`.

---

### 4. Indicizzazione Elasticsearch

L'indicizzazione ([app/business/indexer](file:///z:/home/valerio/project/Homework-5-new-dev/Homework-5-new-dev/Homework-5-new-dev/app/business/indexer)) organizza i dati su tre indici dedicati:

| Indice | Scopo | Campi Chiave e Analyzer |
|---|---|---|
| **`papers_index`** | Documenti e articoli completi | `paper_id` (keyword), `pmc_id` (keyword), `title` (text con analyzer `english`), `authors` (text), `abstract` (text `english`), `full_text` (text `english`), `published` (date), `html_content` (text) |
| **`tables_index`** | Tabelle con contesto | `caption` (text `english`), `body` (text), `table_number` (integer), `element_id` (keyword), `mentions` (text), `context_paragraphs` (text), `paper_id` (keyword), `paper_title` (text) |
| **`figures_index`** | Figure e illustrazioni | `caption` (text `english`), `figure_number` (integer), `element_id` (keyword), `mentions` (text), `context_paragraphs` (text), `paper_id` (keyword), `paper_title` (text) |

- **Gestione Connessione**: Connessione sicura a Elasticsearch (host locale o remoto) con autenticazione via credenziali o token.
- **Bulk Indexing**: Inserimento ad alte prestazioni tramite le API bulk di Elasticsearch con gestione di batch e retry.

---

### 5. Motore di Ricerca e Visualizzatore

Implementato in FastAPI ([app/services/routes.py](file:///z:/home/valerio/project/Homework-5-new-dev/Homework-5-new-dev/Homework-5-new-dev/app/services/routes.py)):

- **Costruttore di Query Booleane Avanzato**:
  - Supporto per clausole `WHERE`, `AND`, `OR`, `NOT`.
  - Operatori supportati:
    - `match`: full-text search con fuzzy matching automatico (`AUTO`) per tollerare refusi.
    - `phrase`: corrispondenza della sequenza esatta di parole (`match_phrase`).
    - `term`: corrispondenza puntuale su identificativi, numeri o date.
  - **Filtraggio dinamico per categoria**: quando l'utente seleziona una categoria (es. Tabelle), l'interfaccia e il backend propongono ed eseguono la ricerca esclusivamente sui campi pertinenti (`caption`, `body`, ecc.), garantendo precisione ed evitando falsi positivi da campi generici del paper.
- **Visualizzatore Paper con Deep Linking ([paper.html](file:///z:/home/valerio/project/Homework-5-new-dev/Homework-5-new-dev/Homework-5-new-dev/templates/paper.html))**:
  - **Scroll automatico e outline**: cliccando su una tabella o figura dai risultati, il browser atterra direttamente sull'elemento con bordo di risalto.
  - **Highlighter in tempo reale**: parsing delle clausole booleane ed evidenziazione ad alto contrasto (rosso coordinato con il tema) dei termini cercati nei punti esatti (titolo, abstract, autori, didascalie o testo).
  - **Supporto multi-formato**: selettori intelligenti compatibili sia con la struttura HTML di PubMed Central (`.contrib-group`, `.front-matter`) sia con arXiv (`.ltx_authors`, `.ltx_title_document`, `.ltx_table`).

---

## Architettura del Progetto

```text
├── airxv/                        # Corpus e dati estratti di arXiv (storage)
│   ├── corpus.json               # Metadati e testi dei paper arXiv
│   ├── tables_with_context.json  # Tabelle con didascalie e paragrafi di contesto
│   └── figures_with_context.json # Figure con didascalie e menzioni nel testo
├── pubmed/                       # Corpus e dati estratti di PubMed Central (705 paper)
│   ├── corpus.json               # Metadati e full-text HTML/XML dei paper PubMed
│   ├── tables_with_context.json  # Oltre 1600 tabelle arricchite con contesto
│   └── figures_with_context.json # Oltre 1100 figure arricchite con contesto
├── app/                          # Core dell'applicazione
│   ├── business/
│   │   ├── corpus_builder/       # Acquisizione dati da API esterne
│   │   │   ├── downloader.py     # Gestione concorrenza e rate limiting
│   │   │   ├── models.py         # Modello dati unificato Paper
│   │   │   └── source/           # Connettori sorgente
│   │   │       ├── arxiv.py      # Client API arXiv
│   │   │       ├── base.py       # Interfaccia astratta DocumentSource
│   │   │       └── pubmed.py     # Client NCBI E-Utilities
│   │   ├── extractor/            # Estrazione ed arricchimento contestuale
│   │   │   ├── table_context_extractor.py  # Estrazione tabelle, caption e menzioni
│   │   │   └── figure_context_extractor.py # Estrazione figure, immagini e contesti
│   │   └── indexer/              # Gestione indici e caricamento Elasticsearch
│   │       ├── elastic_indexer.py          # Indicizzazione documenti (papers_index)
│   │       ├── index_advanced_tables.py    # Indicizzazione tabelle (tables_index)
│   │       └── index_advanced_figures.py   # Indicizzazione figure (figures_index)
│   ├── config/
│   │   └── config.py             # Configurazione dell'applicazione e variabili d'ambiente
│   ├── services/
│   │   └── routes.py             # Controller FastAPI: ricerca, paper viewer e task API
│   └── utils/                    # Funzioni di utilità
│       ├── check_caption.py
│       ├── clean_figure.py
│       └── format_date.py
├── experiments/                  # Valutazione sperimentale Information Retrieval
│   ├── evaluation.py             # Script di benchmark (MAP, nDCG@10, MRR, P@K, latenze)
│   └── evaluation_results.json   # Risultati esportati per query e riepilogo aggregato
├── templates/                    # Template Jinja2 per la Web Application
│   ├── index.html                # Interfaccia di ricerca con filtri e builder booleano
│   ├── paper.html                # Visualizzatore documento con highlighting e deep linking
│   └── results.html              # Rendering parziale dei risultati di ricerca
├── test/                         # Script operativi per l'esecuzione della pipeline
│   ├── pipeline_arxiv.py         # Download, estrazione e indicizzazione dataset arXiv
│   └── pipeline_pubmed.py        # Indicizzazione e sincronizzazione dataset PubMed
├── corpus.json                   # Dataset attivo di documenti caricato su Elasticsearch
├── tables_with_context.json      # Dataset attivo di tabelle caricato su Elasticsearch
├── figures_with_context.json     # Dataset attivo di figure caricato su Elasticsearch
├── run.py                        # Entry point server Web (FastAPI / Uvicorn)
├── requirements.txt              # Dipendenze Python del progetto
├── RISULTATI.md                  # Relazione con tempi, statistiche e benchmark IR
├── .env                          # Variabili d'ambiente (Elasticsearch host/auth, API key)
└── .env_example                  # File template di configurazione di esempio
```

---

## Requisiti di Sistema

- **Python**: 3.14 o superiore 
- **Elasticsearch**: 8.x (in esecuzione locale o remota)

---

## Installazione e Configurazione

### 1. Setup Virtual Environment

```bash
# Clone del repository
git clone https://github.com/SilContemori/Homework-5-new.git
cd Homework-5-new

# Creazione ambiente virtuale
python3 -m venv .venv

# Attivazione su Linux / macOS / WSL
source .venv/bin/activate

# Attivazione su Windows PowerShell
.venv\Scripts\Activate.ps1
```

### 2. Installazione Dipendenze

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Configurazione File `.env`

Crea o modifica il file `.env` nella root del progetto:

```ini
# Configurazione Elasticsearch
HOST_ELASTIC=https://localhost:9200
PASSWORD_ELASTIC=tua_password_elasticsearch

# Chiave API NCBI (consigliata per PubMed per aumentare il rate limit a 10 req/s)
NCBI_API_KEY=tua_chiave_ncbi_opzionale

# Sorgente dati attiva ('pubmed' oppure 'arxiv')
SOURCE=pubmed

# Ritardo tra richieste consecutive (secondi)
DELAY=2

# Query di ricerca iniziale per il popolamento del corpus
QUERY="cancer risk" AND "coffee consumption" AND free full text[filter] OR glyphosate AND cancer risk AND free full text[filter] OR ultra-processed foods AND cardiovascular risk AND free full text[filter]
```

---

## Avvio di Elasticsearch

Elasticsearch può essere avviato nativamente come servizio locale o tramite binario (senza necessità di Docker):

- **Su Linux / WSL (Systemd)**:
  ```bash
  sudo systemctl start elasticsearch
  ```

- **Da binario locale**:
  ```bash
  ./bin/elasticsearch
  ```

Verifica che il servizio risponda correttamente:
```bash
curl -k https://localhost:9200 -u elastic:tua_password_elasticsearch
```

---

## Esecuzione della Pipeline e dell'Applicazione

### Avvio della Web Application

```bash
python run.py
```

L'applicazione sarà accessibile su:
- **Interfaccia Web**: [http://localhost:8080](http://localhost:8080)
- **Documentazione Swagger UI**: [http://localhost:8080/docs](http://localhost:8080/docs)

### Esecuzione della Pipeline da Terminale (`test/`)

Per popolare e sincronizzare rapidamente Elasticsearch con uno dei due dataset:

- **Pipeline arXiv** (scarica, estrae tabelle/figure e indicizza su Elasticsearch):
  ```bash
  python test/pipeline_arxiv.py
  ```

- **Pipeline PubMed** (indicizza il corpus di 705 paper, tabelle e figure e sincronizza l'app):
  ```bash
  python test/pipeline_pubmed.py
  ```

### Esecuzione della Valutazione IR (`experiments/`)

Per calcolare le metriche IR formali (MAP, nDCG@10, MRR, P@5, P@10 e latenze):

```bash
python experiments/evaluation.py
```
*(Oppure direttamente con parametro: `python experiments/evaluation.py -c arxiv` o `-c pubmed`).*

### Esecuzione della Pipeline via API Swagger

I processi modulari di scaricamento, estrazione e indicizzazione possono essere lanciati in background da `http://localhost:8080/docs`:

1. `POST /api/tasks/corpus/build`: scarica gli articoli secondo la query configurata nel `.env` e genera `corpus.json`.
2. `POST /api/tasks/index/papers`: indicizza i documenti completi in `papers_index`.
3. `POST /api/tasks/extract/tables`: estrae le tabelle con contesto creando `tables_with_context.json`.
4. `POST /api/tasks/index/tables`: indicizza le tabelle estratte in `tables_index`.
5. `POST /api/tasks/extract/figures`: estrae le figure con contesto creando `figures_with_context.json`.
6. `POST /api/tasks/index/figures`: indicizza le figure estratte in `figures_index`.
7. `GET /api/tasks/{task_id}`: restituisce lo stato del task in tempo reale (`pending`, `running`, `completed`, `failed`).
8. `GET /api/tasks/status`: verifica l'esistenza sul filesystem dei file generati dalla pipeline.

---

## Guida alla Ricerca

1. **Ricerca Semplice**:
   Inserisci i termini nella barra superiore per un `multi_match` fuzzy sui campi principali dell'entità scelta.

2. **Costruttore Booleano**:
   - **Logica**: `WHERE` (prima condizione), `AND` (intersezione), `OR` (unione), `NOT` (esclusione).
   - **Campi**:
     - *Papers*: `tutti i campi`, `title`, `abstract`, `authors`, `full_text`, `published`, `paper_id`.
     - *Tabelle*: `tutti i campi`, `caption`, `body`, `mentions`, `context_paragraphs`, `table_number`, `paper_title`.
     - *Figure*: `tutti i campi`, `caption`, `mentions`, `context_paragraphs`, `figure_number`, `paper_title`.
   - **Operatori**: `match` (fuzzy con autocorrezione), `phrase` (sequenza esatta), `term` (valore esatto).

---

## Valutazione Sperimentale e Risultati

L'efficacia del motore di ricerca è stata validata formalmente su un benchmark di **20 documenti bilanciati** (15% arXiv e 85% PubMed/PMC), valutando tempi di elaborazione, ground truth e metriche di Information Retrieval:

- **Macro Precision**: **0.982**
- **Macro Recall**: **0.989**
- **Macro F1-Score**: **0.984**
- **Media Accuracy**: **0.989**

Per l'analisi completa dei tempi di estrazione, statistiche del corpus, ground truth e dettaglio per singola query:
📄 **[Consulta RISULTATI.md](RISULTATI.md)**

---

## Riferimento API

| Metodo | Endpoint | Descrizione |
|---|---|---|
| `GET` | `/` | Home page con interfaccia di ricerca e filtri |
| `GET` | `/search` | Endpoint di ricerca unificato (papers, tables, figures) |
| `GET` | `/paper/{paper_id}` | Visualizzatore del documento con supporto highlighting e deep linking |
| `POST` | `/api/tasks/corpus/build` | Avvia il download in background degli articoli |
| `POST` | `/api/tasks/index/papers` | Avvia l'indicizzazione dei paper su Elasticsearch |
| `POST` | `/api/tasks/extract/tables` | Estrae le tabelle con contesto creando `tables_with_context.json` |
| `POST` | `/api/tasks/index/tables` | Indicizza le tabelle estratte in `tables_index` |
| `POST` | `/api/tasks/extract/figures` | Estrae le figure con contesto creando `figures_with_context.json` |
| `POST` | `/api/tasks/index/figures` | Indicizza le figure estratte in `figures_index` |
| `GET` | `/api/tasks/{task_id}` | Restituisce lo stato del task asincrono in tempo reale |
| `GET` | `/api/tasks/status` | Verifica l'esistenza dei file generati dalla pipeline |