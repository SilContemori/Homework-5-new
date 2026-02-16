"""
Esperimenti di valutazione del sistema di Information Retrieval.

Genera il ground truth automaticamente interrogando le API di ArXiv e PubMed
come "oracolo esterno", poi confronta i risultati con quelli di Elasticsearch.

Metriche calcolate: Precision@5, Precision@10, Recall@10, MAP, nDCG@10, MRR.
Misura anche i tempi di risposta per ogni query.

Uso:
    python -m experiments.evaluation
"""

import sys
import os
import json
import time
import math
import requests
import feedparser
import xml.etree.ElementTree as ET
from statistics import mean
from urllib.parse import quote

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from elasticsearch import Elasticsearch
import urllib3
from loguru import logger
from app.config.config import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ---------------------------------------------------------------------------
# Query di test per corpus
# ---------------------------------------------------------------------------

TEST_QUERIES = {
    "arxiv": {
        "api_query_format": "arxiv",
        "queries": {
            "fulltext": [
                "entity resolution",
                "record linkage",
                "entity matching",
                "data deduplication",
                "duplicate detection",
                "blocking methods entity",
            ],
            "boolean": [
                "entity OR resolution",
                "record AND linkage",
                "entity OR matching",
                "data AND deduplication",
                "duplicate AND detection",
                "blocking OR methods AND entity",
            ]
        }
    },
    "pubmed": {
        "api_query_format": "pubmed",
        "queries": {
            "fulltext": [
                "cancer risk coffee consumption",
                "glyphosate cancer risk",
                "ultra-processed foods cardiovascular risk",
                "coffee cancer epidemiology",
                "glyphosate exposure health",
                "processed food chronic disease",
            ],
            "boolean": [
                "cancer AND risk OR coffee AND consumption",
                "glyphosate AND cancer AND risk",
                "ultra-processed OR foods AND cardiovascular OR risk",
                "coffee AND cancer OR epidemiology",
                "glyphosate AND exposure AND health",
                "processed OR food AND chronic AND disease",
            ]
        }
    }
}

# Campi di ricerca per categoria (stessi usati in routes.py)
SEARCH_FIELDS = {
    "papers": ["title^2", "abstract", "authors", "html_content"],
    "tables": ["caption^3", "body", "mentions", "context_paragraphs"],
    "figures": ["caption^3", "mentions", "context_paragraphs"],
}

INDEX_NAMES = {
    "papers": "papers_index",
    "tables": "tables_index",
    "figures": "figures_index",
}

HEADERS = {"User-Agent": "AcademicSearchProject/1.0 (IR Evaluation)"}


# ---------------------------------------------------------------------------
# Generazione ground truth via API esterne
# ---------------------------------------------------------------------------

def fetch_arxiv_relevant_ids(query, max_results=50):
    """Interroga l'API ArXiv e restituisce un set di arxiv_id rilevanti."""
    # Rimuovi gli operatori booleani per la query API
    clean_query = query.replace(" AND ", " ").replace(" OR ", " ").replace(" NOT ", " ")
    terms = clean_query.split()
    arxiv_query = " AND ".join(f"all:{term}" for term in terms)
    encoded_query = quote(arxiv_query)
    url = f"http://export.arxiv.org/api/query?search_query={encoded_query}&start=0&max_results={max_results}"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            if response.status_code == 429:
                wait = 10 * (attempt + 1)
                logger.warning(f"ArXiv 429 rate limit, attendo {wait}s (tentativo {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            response.raise_for_status()
            feed = feedparser.parse(response.text)

            ids = set()
            for entry in feed.entries:
                arxiv_id = entry.id.split("/abs/")[-1]
                ids.add(arxiv_id)

            logger.debug(f"ArXiv API: query='{query}' -> {len(ids)} risultati")
            return ids

        except Exception as e:
            logger.error(f"Errore ArXiv API: {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
            else:
                return set()
    return set()


def fetch_pubmed_relevant_ids(query, max_results=500):
    """Interroga l'API PubMed e restituisce un set di PMID rilevanti."""
    # Rimuovi gli operatori booleani per la query API
    clean_query = query.replace(" AND ", " ").replace(" OR ", " ").replace(" NOT ", " ")
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        'db': 'pubmed',
        'term': f"{clean_query} AND free full text[filter]",
        'retmax': max_results,
        'retmode': 'xml'
    }

    try:
        response = requests.get(search_url, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ids = set()
        for id_elem in root.findall('.//Id'):
            ids.add(id_elem.text)

        logger.debug(f"PubMed API: query='{query}' -> {len(ids)} risultati")
        return ids

    except Exception as e:
        logger.error(f"Errore PubMed API: {e}")
        return set()


def fetch_relevant_ids(query, api_format):
    """Dispatcher: chiama l'API corretta in base al corpus."""
    if api_format == "arxiv":
        return fetch_arxiv_relevant_ids(query, max_results=50)
    else:
        return fetch_pubmed_relevant_ids(query, max_results=500)


def build_corpus_ground_truth(es, api_ids, api_format):
    """Filtra il ground truth tenendo solo i paper presenti nel corpus.

    Restituisce un set contenente sia PMID che PMC ID dei paper rilevanti
    che esistono effettivamente nell'indice papers_index.
    Questo evita di penalizzare il sistema per paper che non ha nel corpus.
    """
    if not api_ids:
        return set()

    id_list = list(api_ids)

    # Cerca nel papers_index i paper che hanno un ID corrispondente
    # (come paper_id/PMID oppure come pmc_id)
    body = {
        "query": {
            "bool": {
                "should": [
                    {"terms": {"paper_id": id_list}},
                    {"terms": {"pmc_id": id_list}},
                ],
                "minimum_should_match": 1
            }
        },
        "size": len(id_list),
        "_source": ["paper_id", "pmc_id"]
    }

    res = es.search(index="papers_index", body=body)

    # Costruisci un set con ENTRAMBI gli ID (PMID + PMC ID) per ogni paper trovato
    # cosi' il confronto funziona sia per papers (che usano PMID)
    # sia per figure (che usano PMC ID come paper_id)
    ground_truth = set()
    for hit in res["hits"]["hits"]:
        pid = hit["_source"].get("paper_id", "")
        pmc = hit["_source"].get("pmc_id", "")
        if pid:
            ground_truth.add(pid)
        if pmc:
            ground_truth.add(pmc)

    return ground_truth


# ---------------------------------------------------------------------------
# Metriche IR
# ---------------------------------------------------------------------------

def precision_at_k(retrieved_ids, relevant_ids, k):
    if k == 0:
        return 0.0
    top_k = retrieved_ids[:k]
    return sum(1 for doc_id in top_k if doc_id in relevant_ids) / k


def recall_at_k(retrieved_ids, relevant_ids, k):
    if not relevant_ids:
        return 0.0
    top_k = retrieved_ids[:k]
    return sum(1 for doc_id in top_k if doc_id in relevant_ids) / len(relevant_ids)


def average_precision(retrieved_ids, relevant_ids):
    if not relevant_ids:
        return 0.0
    hits = 0
    sum_precisions = 0.0
    for i, doc_id in enumerate(retrieved_ids):
        if doc_id in relevant_ids:
            hits += 1
            sum_precisions += hits / (i + 1)
    return sum_precisions / len(relevant_ids)


def reciprocal_rank(retrieved_ids, relevant_ids):
    for i, doc_id in enumerate(retrieved_ids):
        if doc_id in relevant_ids:
            return 1.0 / (i + 1)
    return 0.0


def dcg_at_k(retrieved_ids, relevant_ids, k):
    dcg = 0.0
    for i, doc_id in enumerate(retrieved_ids[:k]):
        rel = 1.0 if doc_id in relevant_ids else 0.0
        dcg += rel / math.log2(i + 2)
    return dcg


def ndcg_at_k(retrieved_ids, relevant_ids, k):
    dcg = dcg_at_k(retrieved_ids, relevant_ids, k)
    ideal_ids = list(relevant_ids)[:k]
    idcg = dcg_at_k(ideal_ids, relevant_ids, k)
    if idcg == 0:
        return 0.0
    return dcg / idcg


# ---------------------------------------------------------------------------
# Elasticsearch
# ---------------------------------------------------------------------------

def get_elasticsearch():
    es_config = {
        "hosts": [config.HOST_ELASTIC],
        "verify_certs": False
    }
    if config.PASSWORD_ELASTIC:
        es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
    return Elasticsearch(**es_config)


def execute_query(es, index_name, query_text, fields, mode, size=100):
    """Esegue una query ES e restituisce (lista di _id, tempo in ms, hits raw)."""
    if mode == "boolean":
        body = {
            "query": {
                "simple_query_string": {
                    "query": query_text,
                    "fields": fields,
                    "default_operator": "AND"
                }
            },
            "size": size
        }
    else:
        body = {
            "query": {
                "multi_match": {
                    "query": query_text,
                    "fields": fields,
                    "type": "best_fields"
                }
            },
            "size": size
        }

    start = time.perf_counter()
    res = es.search(index=index_name, body=body)
    elapsed_ms = (time.perf_counter() - start) * 1000

    hits = res["hits"]["hits"]
    return hits, elapsed_ms


def get_paper_ids_from_hits(hits, category):
    """Estrae gli ID da confrontare con il ground truth.
    Per papers: usa paper_id o _id.
    Per tables/figures: usa paper_id (per verificare appartenenza a paper rilevanti).
    """
    if category == "papers":
        return [
            hit["_source"].get("paper_id") or hit["_source"].get("pmc_id") or hit["_id"]
            for hit in hits
        ]
    else:
        # Per tabelle e figure, l'ID rilevante e' il paper_id di appartenenza
        return [hit["_source"].get("paper_id", "") for hit in hits]


# ---------------------------------------------------------------------------
# Valutazione
# ---------------------------------------------------------------------------

def evaluate_single_query(es, query_text, category, mode, relevant_paper_ids):
    """Valuta una singola query su una categoria e modalita'."""
    index_name = INDEX_NAMES[category]
    fields = SEARCH_FIELDS[category]

    hits, elapsed_ms = execute_query(es, index_name, query_text, fields, mode)
    retrieved_ids = get_paper_ids_from_hits(hits, category)

    # Debug: mostra i primi 5 ID estratti da ES vs ground truth
    matched = [rid for rid in retrieved_ids[:10] if rid in relevant_paper_ids]
    logger.debug(f"[{category}/{mode}] Retrieved IDs (top 5): {retrieved_ids[:5]}")
    logger.debug(f"[{category}/{mode}] Matched with GT: {matched}")

    result = {
        "query": query_text,
        "category": category,
        "mode": mode,
        "num_retrieved": len(retrieved_ids),
        "num_relevant_in_ground_truth": len(relevant_paper_ids),
        "response_time_ms": round(elapsed_ms, 2),
        "precision_at_5": round(precision_at_k(retrieved_ids, relevant_paper_ids, 5), 4),
        "precision_at_10": round(precision_at_k(retrieved_ids, relevant_paper_ids, 10), 4),
        "recall_at_10": round(recall_at_k(retrieved_ids, relevant_paper_ids, 10), 4),
        "average_precision": round(average_precision(retrieved_ids, relevant_paper_ids), 4),
        "reciprocal_rank": round(reciprocal_rank(retrieved_ids, relevant_paper_ids), 4),
        "ndcg_at_10": round(ndcg_at_k(retrieved_ids, relevant_paper_ids, 10), 4),
    }

    # Top 3 risultati per analisi qualitativa
    top_results = []
    for hit in hits[:3]:
        src = hit["_source"]
        info = {"_id": hit["_id"], "score": round(hit["_score"], 4)}
        if category == "papers":
            info["title"] = src.get("title", "N/A")[:100]
            info["relevant"] = (src.get("paper_id") or src.get("pmc_id") or hit["_id"]) in relevant_paper_ids
        else:
            info["caption"] = src.get("caption", "N/A")[:100]
            info["paper_id"] = src.get("paper_id", "N/A")
            info["relevant"] = src.get("paper_id", "") in relevant_paper_ids
        top_results.append(info)
    result["top_results"] = top_results

    return result


def print_query_result(result):
    """Stampa i risultati di una singola query."""
    marker = "FT" if result["mode"] == "fulltext" else "BL"
    print(f"    [{marker}] \"{result['query']}\"")
    print(f"        Risultati: {result['num_retrieved']} | GT rilevanti: {result['num_relevant_in_ground_truth']} | Tempo: {result['response_time_ms']:.1f}ms")
    print(f"        P@5={result['precision_at_5']:.4f}  P@10={result['precision_at_10']:.4f}  R@10={result['recall_at_10']:.4f}")
    print(f"        AP={result['average_precision']:.4f}   nDCG@10={result['ndcg_at_10']:.4f}   RR={result['reciprocal_rank']:.4f}")

    # Top 3 qualitativo
    for i, tr in enumerate(result["top_results"], 1):
        rel = "V" if tr.get("relevant") else "X"
        label = tr.get("title") or tr.get("caption", "N/A")
        print(f"        #{i} [{rel}] (score={tr['score']:.2f}) {label}")


def select_corpus():
    """Chiede all'utente quale corpus valutare."""
    available = list(TEST_QUERIES.keys())
    print("\nQuale sistema vuoi valutare?")
    for i, name in enumerate(available, 1):
        n_queries_ft = len(TEST_QUERIES[name]["queries"]["fulltext"])
        n_queries_bl = len(TEST_QUERIES[name]["queries"]["boolean"])
        print(f"  {i}. {name} ({n_queries_ft} query fulltext, {n_queries_bl} query boolean)")

    choice = input("\nScegli (numero): ").strip()
    try:
        idx = int(choice)
        if 1 <= idx <= len(available):
            return available[idx - 1]
    except ValueError:
        pass
    print("Scelta non valida.")
    sys.exit(1)


def run_evaluation():
    """Esegue la valutazione completa."""
    print("=" * 70)
    print("  VALUTAZIONE SPERIMENTALE - GROUND TRUTH AUTOMATICO VIA API")
    print("=" * 70)

    corpus_name = select_corpus()
    print(f"\nCorpus selezionato: {corpus_name.upper()}")

    es = get_elasticsearch()
    if not es.ping():
        print("\nERRORE: Impossibile connettersi a Elasticsearch.")
        sys.exit(1)
    print(f"Elasticsearch: OK ({config.HOST_ELASTIC})")

    corpus_config = TEST_QUERIES[corpus_name]
    api_format = corpus_config["api_query_format"]
    queries_by_mode = corpus_config["queries"]

    print(f"\n{'=' * 70}")
    print(f"  CORPUS: {corpus_name.upper()}")
    print(f"{'=' * 70}")

    corpus_results = {}

    # Per ogni modalità (fulltext e boolean)
    for mode in ["fulltext", "boolean"]:
        queries = queries_by_mode[mode]

        print(f"\n{'=' * 70}")
        print(f"  MODALITÀ: {mode.upper()}")
        print(f"{'=' * 70}")

        # Per ogni query nella modalità corrente
        for query_text in queries:
            print(f"\n  Query: \"{query_text}\"")
            print(f"  Recupero ground truth da API {api_format.upper()}...")

            api_ids = fetch_relevant_ids(query_text, api_format)
            print(f"  -> {len(api_ids)} paper rilevanti trovati dall'API")

            if not api_ids:
                print(f"  [!] Nessun risultato dall'API, skip questa query")
                time.sleep(1)
                continue

            # Filtra: tieni solo i paper che esistono nel corpus
            relevant_ids = build_corpus_ground_truth(es, api_ids, api_format)
            n_unique_papers = len(relevant_ids)
            print(f"  -> {len(relevant_ids)} ID rilevanti presenti nel corpus (~{n_unique_papers} paper unici)")

            if not relevant_ids:
                print(f"  [!] Nessun paper dell'API trovato nel corpus, skip")
                time.sleep(1)
                continue

            # Valuta su tutte le categorie con la modalità corrente
            for category in ["papers", "tables", "figures"]:
                index_name = INDEX_NAMES[category]
                if not es.indices.exists(index=index_name):
                    print(f"    [{category}] Indice non trovato, skip")
                    continue

                key = f"{corpus_name}_{category}"
                if key not in corpus_results:
                    corpus_results[key] = []

                result = evaluate_single_query(
                    es, query_text, category, mode, relevant_ids
                )
                corpus_results[key].append(result)
                print_query_result(result)

            # Rate limit tra le query API (ArXiv richiede almeno 3s, usiamo 5s per sicurezza)
            time.sleep(5)

    # ---------------------------------------------------------------------------
    # Riepilogo finale
    # ---------------------------------------------------------------------------
    print(f"\n{'=' * 70}")
    print(f"  RIEPILOGO FINALE")
    print(f"{'=' * 70}")

    summary = {}
    print(f"\n  Corpus: {corpus_name.upper()}")
    summary[corpus_name] = {}

    for key, results in corpus_results.items():
        category = key.split("_", 1)[1]

        # Separa per modalita'
        for mode in ["fulltext", "boolean"]:
            mode_results = [r for r in results if r["mode"] == mode]
            if not mode_results:
                continue

            map_val = mean([r["average_precision"] for r in mode_results])
            ndcg_val = mean([r["ndcg_at_10"] for r in mode_results])
            mrr_val = mean([r["reciprocal_rank"] for r in mode_results])
            avg_p5 = mean([r["precision_at_5"] for r in mode_results])
            avg_p10 = mean([r["precision_at_10"] for r in mode_results])
            avg_time = mean([r["response_time_ms"] for r in mode_results])

            mode_label = "FT" if mode == "fulltext" else "BL"
            print(f"    {category:8s} [{mode_label}]: MAP={map_val:.4f} | nDCG@10={ndcg_val:.4f} | MRR={mrr_val:.4f} | P@5={avg_p5:.4f} | P@10={avg_p10:.4f} | Tempo={avg_time:.1f}ms")

            summary[corpus_name][f"{category}_{mode}"] = {
                "MAP": round(map_val, 4),
                "mean_nDCG_at_10": round(ndcg_val, 4),
                "MRR": round(mrr_val, 4),
                "mean_P_at_5": round(avg_p5, 4),
                "mean_P_at_10": round(avg_p10, 4),
                "avg_response_time_ms": round(avg_time, 2),
                "num_queries": len(mode_results)
            }

    # Salva risultati completi
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(output_dir, "evaluation_results.json")

    full_output = {
        "summary": summary,
        "detailed_results": {
            corpus_name: {
                key: results for key, results in corpus_results.items()
            }
        }
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(full_output, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 70}")
    print(f"  Risultati salvati in: {output_file}")
    print(f"{'=' * 70}\n")


if __name__ == "__main__":
    run_evaluation()