# TEMPI DI INDICIZZAZIONE ED ESTRAZIONE
Tempi misurati dai log del framework (Loguru + Elasticsearch 8.x + FastAPI):

> **Nota sui tempi di acquisizione**: Il download del corpus PubMed da remoto (705 articoli full-text) ha richiesto circa 30 minuti a causa del rate limiting delle API NCBI e del delay prudenziale di sicurezza (1.5-2.0s a richiesta) per prevenire blocchi IP/WAF. La successiva indicizzazione locale su Elasticsearch ha richiesto invece appena ~26 secondi complessivi.

## PUBMED (Corpus Completo — 705 Paper)

### 1. Documenti (papers_index)
```text
2026-09-04 20:06:06.657 | INFO     | app.business.indexer.elastic_indexer:create_index:25 - Indice 'papers_index' eliminato.
2026-09-04 20:06:07.063 | SUCCESS  | app.business.indexer.elastic_indexer:create_index:45 - Indice 'papers_index' creato.
2026-09-04 20:06:28.062 | SUCCESS  | app.business.indexer.elastic_indexer:index_data:72 - Indicizzati correttamente 705 documenti su Elasticsearch.
```
- Tempo di indicizzazione: **20.99 secondi**

### 2. Tabelle (tables_index)
```text
2026-09-04 20:06:28.159 | INFO     | app.business.indexer.index_advanced_tables:create_index:25 - Indice 'tables_index' eliminato.
2026-09-04 20:06:28.319 | SUCCESS  | app.business.indexer.index_advanced_tables:create_index:49 - Indice 'tables_index' creato con successo.
2026-09-04 20:06:31.379 | SUCCESS  | app.business.indexer.index_advanced_tables:index_from_json:86 - Indicizzate correttamente 1674 tabelle.
```
- Tempo di indicizzazione: **3.06 secondi**

### 3. Figure / Immagini (figures_index)
```text
2026-09-04 20:06:31.474 | INFO     | app.business.indexer.index_advanced_figures:create_index:25 - Indice 'figures_index' eliminato.
2026-09-04 20:06:31.639 | SUCCESS  | app.business.indexer.index_advanced_figures:create_index:49 - Indice 'figures_index' creato.
2026-09-04 20:06:33.464 | SUCCESS  | app.business.indexer.index_advanced_figures:index_from_json:88 - Indicizzate correttamente 1179 figure.
```
- Tempo di indicizzazione: **1.82 secondi**

- **Tempo totale indicizzazione PubMed**: **25.87 secondi**

---

## ARXIV (Dataset di Test)

### 1. Documenti (papers_index)
```text
2026-09-04 20:12:10.832 | INFO     | app.business.indexer.elastic_indexer:create_index:25 - Indice 'papers_index' eliminato.
2026-09-04 20:12:10.969 | SUCCESS  | app.business.indexer.elastic_indexer:create_index:45 - Indice 'papers_index' creato.
2026-09-04 20:12:11.233 | SUCCESS  | app.business.indexer.elastic_indexer:index_data:72 - Indicizzati correttamente 3 documenti su Elasticsearch.
```
- Tempo di indicizzazione: **0.26 secondi**

### 2. Tabelle (tables_index)
```text
2026-09-04 20:12:11.317 | INFO     | app.business.indexer.index_advanced_tables:create_index:25 - Indice 'tables_index' eliminato.
2026-09-04 20:12:11.491 | SUCCESS  | app.business.indexer.index_advanced_tables:create_index:49 - Indice 'tables_index' creato con successo.
2026-09-04 20:12:11.505 | SUCCESS  | app.business.indexer.index_advanced_tables:index_from_json:86 - Indicizzate correttamente 11 tabelle.
```
- Tempo di indicizzazione: **0.01 secondi**

### 3. Figure / Immagini (figures_index)
```text
2026-09-04 20:12:11.582 | INFO     | app.business.indexer.index_advanced_figures:create_index:25 - Indice 'figures_index' eliminato.
2026-09-04 20:12:11.756 | SUCCESS  | app.business.indexer.index_advanced_figures:create_index:49 - Indice 'figures_index' creato.
2026-09-04 20:12:11.774 | SUCCESS  | app.business.indexer.index_advanced_figures:index_from_json:88 - Indicizzate correttamente 21 figure.
```
- Tempo di indicizzazione: **0.02 secondi**

- **Tempo totale indicizzazione arXiv**: **0.29 secondi**

# STATISTICHE DEL CORPUS

708 paper totali (705 PubMed / PMC + 3 arXiv)
	705 PubMed / PMC (99.6%)
	3 arXiv (0.4%)

1685 tabelle con contesto in totale
	circa 2.4 tabelle per paper
	1674 PubMed / PMC
	11 arXiv

1200 figure con contesto in totale
	circa 1.7 figure per paper
	1179 PubMed / PMC
	21 arXiv

# CAMPIONE
20 Documenti estratti randomicamente mantenendo equilibrio tra le sorgenti:
15% arXiv -> 3 doc
85% PubMed / PMC -> 17 doc

## ARXIV:
	A) http://arxiv.org/html/1208.1927v1 - CrowdER: Crowdsourcing Entity Resolution
	B) http://arxiv.org/html/1710.00597v6 - DeepER -- Deep Entity Resolution
	C) http://arxiv.org/html/1805.12319v3 - Skyblocking for Entity Resolution

## PUBMED / PMC:
	D) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13518480 - Ultra-Processed Foods and Metabolic Dysfunction: Mechanisms, Health Consequences, and Clinical Implications
	E) 42634376 - A systematic review to critically appraise methodological rigor and validate health outcomes
	F) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13482330 - Nutrition Transition, Processed Foods, and Cardiometabolic Risk
	G) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13487355 - The Hidden Burden of Water-Binding Additives in Meat Products
	H) 42563602 - Adherence to the world cancer prevention recommendations in cohort studies
	I) 42557022 - Diet and Atherosclerosis Prevention: Rethinking the Significance
	J) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13425132 - Not all ultra-processed foods are created equal: a review
	K) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13415102 - Unhealthy Diets, Unhealthy Futures: How Modern Eating Patterns Shape Chronic Disease
	L) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13414525 - Non-HDL Cholesterol as a Practical Gatekeeper for Adolescent Atherosclerosis
	M) 42482054 - Circulating metabolomic signatures of ultra-processed and minimally processed foods
	N) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13363947 - Additives with Emerging Health Concerns in Ultra-Processed Snacks
	O) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13334127 - Muscle toxicity reports in FAERS: a disproportionality analysis
	P) 42377342 - Dietary sodium intake: evidence, controversies and practical management
	Q) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13296373 - Ultra-processed food consumption across early life: implications for cardiometabolic health
	R) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13304886 - The Mediterranean Diet as a Sustainable Dietary Pattern: A Scoping Review
	S) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13298066 - Excess Weight and Dyslipidemia in Indigenous Populations
	T) https://www.ncbi.nlm.nih.gov/pmc/articles/PMC13284789 - The Global Obesity Epidemic: Epidemiology, Health Burden and Preventive Strategies

# LISTA DI QUERY
## QUERY PER PAPER:
	1) Titolo match "entity resolution"
	2) Titolo phrase "Ultra-Processed Foods and Metabolic Dysfunction"
	3) Abstract match "cardiovascular"
	4) Abstract match "cancer"
	5) Titolo match booleano AND "diet" AND "prevention"
	6) Titolo match booleano NOT "diet" AND NOT "prevention"
	7) Autori match "Ebraheem"
	8) Autori match "Wang"
	9) Titolo match "obesity"
	10) Data pubblicazione prima del "2026-01-01"

## QUERY PER IMMAGINI:
	1) Caption phrase "figure 1"
	2) Mentions match "figure"

## QUERY PER TABELLE:
	1) Caption phrase "table 1"
	2) Mentions match "table"

# GROUND TRUTH:
## QUERY PER PAPER:
	1) [3/20] : A, B, C
	2) [1/20] : D
	3) [14/20] : D, E, F, G, I, J, K, L, M, N, O, P, Q, T
	4) [3/20] : D, H, P
	5) [1/20] : I
	6) [4/20] : D, K, P, R
	7) [1/20] : B
	8) [4/20] : A, C, M, O
	9) [1/20] : T
	10) [3/20] : A, B, C

## QUERY PER IMMAGINI:
	1) [12/20] : B, C, D, G, J, K, N, O, Q, R, S, T
	2) [6/20] : B, C, N, O, S, T

## QUERY PER TABELLE:
	1) [10/20] : B, C, D, G, J, N, O, Q, R, S
	2) [10/20] : B, C, D, G, J, N, O, Q, R, S

# RISPOSTE:
## QUERY PER PAPER:
	1) [3/20] : A, B, C
		TP: 3, FP: 0
		TN: 17, FN: 0
	2) [1/20] : D
		TP: 1, FP: 0
		TN: 19, FN: 0
	3) [13/20] : D, E, F, G, I, J, K, L, M, N, O, Q, T -> manca P (usa solo acronimo CVD invece del termine esteso nell'abstract)
		TP: 13, FP: 0
		TN: 6, FN: 1
	4) [3/20] : D, H, P
		TP: 3, FP: 0
		TN: 17, FN: 0
	5) [1/20] : I
		TP: 1, FP: 0
		TN: 19, FN: 0
	6) [4/20] : D, K, P, R
		TP: 4, FP: 0
		TN: 16, FN: 0
	7) [1/20] : B
		TP: 1, FP: 0
		TN: 19, FN: 0
	8) [4/20] : A, C, M, O
		TP: 4, FP: 0
		TN: 16, FN: 0
	9) [1/20] : T
		TP: 1, FP: 0
		TN: 19, FN: 0
	10) [4/20] : A, B, C, (!F) -> paper F con formato data preprint antecedente al range
		TP: 3, FP: 1
		TN: 16, FN: 0

## QUERY PER IMMAGINI:
	1) [11/20] : B, C, D, G, J, K, N, O, Q, R, T -> manca S per etichetta sintetica non standard
		TP: 11, FP: 0
		TN: 8, FN: 1
	2) [6/20] : B, C, N, O, S, T
		TP: 6, FP: 0
		TN: 14, FN: 0

## QUERY PER TABELLE:
	1) [10/20] : B, C, D, G, J, N, O, Q, R, S
		TP: 10, FP: 0
		TN: 10, FN: 0
	2) [10/20] : B, C, D, G, J, N, O, Q, R, S
		TP: 10, FP: 0
		TN: 10, FN: 0

# RISULTATI
## QUERY PER PAPER
| Query | TP | FP | FN | Precision | Recall | F1   | Accuracy |
| ----- | -- | -- | -- | --------- | ------ | ---- | -------- |
| 1     | 3  | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |
| 2     | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |
| 3     | 13 | 0  | 1  | 1.00      | 0.93   | 0.96 | 0.95     |
| 4     | 3  | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |
| 5     | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |
| 6     | 4  | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |
| 7     | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |
| 8     | 4  | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |
| 9     | 1  | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |
| 10    | 3  | 1  | 0  | 0.75      | 1.00   | 0.86 | 0.95     |

Macro-average (Paper)
Precision = 0.975
Recall = 0.993
F1 = 0.982
Accuracy = 0.990

## QUERY PER IMMAGINI
| Query | TP | FP | FN | Precision | Recall | F1   | Accuracy |
| ----- | -- | -- | -- | --------- | ------ | ---- | -------- |
| 1     | 11 | 0  | 1  | 1.00      | 0.92   | 0.96 | 0.95     |
| 2     | 6  | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |

Macro-average
Precision = 1.000
Recall = 0.958
F1 = 0.978
Accuracy = 0.975

## QUERY PER TABELLE
| Query | TP | FP | FN | Precision | Recall | F1   | Accuracy |
| ----- | -- | -- | -- | --------- | ------ | ---- | -------- |
| 1     | 10 | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |
| 2     | 10 | 0  | 0  | 1.00      | 1.00   | 1.00 | 1.00     |

Macro-average 
Precision = 1.000
Recall = 1.000
F1 = 1.000
Accuracy = 1.000

# RISULTATI FINALI 
Precision	0.982
Recall	0.989
F1-score	0.984
Accuracy = 0.989
