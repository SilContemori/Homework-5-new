import argparse
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

SEARCH_FIELDS = {
    "papers": ["title^2", "abstract", "full_text", "authors"],
    "tables": ["caption^3", "body", "mentions", "context_paragraphs"],
    "figures": ["caption^3", "mentions", "context_paragraphs"],
}

INDEX_NAMES = {
    "papers": "papers_index",
    "tables": "tables_index",
    "figures": "figures_index",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


_GT_CACHE = {}


def fetch_arxiv_relevant_ids(query, max_results=50):
    clean_query = query.replace(" AND ", " ").replace(" OR ", " ").replace(" NOT ", " ")
    terms = clean_query.split()
    arxiv_query = " AND ".join(f"all:{term}" for term in terms)
    encoded_query = quote(arxiv_query)
    url = f"https://export.arxiv.org/api/query?search_query={encoded_query}&start=0&max_results={max_results}"

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=15)
            if response.status_code == 429:
                wait = 10 * (attempt + 1)
                time.sleep(wait)
                continue
            response.raise_for_status()
            feed = feedparser.parse(response.text)

            ids = set()
            for entry in feed.entries:
                arxiv_id = entry.id.split("/abs/")[-1]
                ids.add(arxiv_id)
            return ids
        except Exception as e:
            logger.error(f"Errore query arXiv {query}: {e}")
            if attempt < max_retries - 1:
                time.sleep(3)
            else:
                return set()
    return set()


def fetch_pubmed_relevant_ids(query, max_results=500):
    clean_query = query.replace(" AND ", " ").replace(" OR ", " ").replace(" NOT ", " ")
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        'db': 'pubmed',
        'term': f"{clean_query} AND free full text[filter]",
        'retmax': max_results,
        'retmode': 'xml'
    }
    if getattr(config, "NCBI_API_KEY", ""):
        params['api_key'] = config.NCBI_API_KEY

    try:
        response = requests.get(search_url, params=params, headers=HEADERS, timeout=30)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ids = set()
        for id_elem in root.findall('.//Id'):
            ids.add(id_elem.text)
        return ids
    except Exception as e:
        logger.error(f"Errore query PubMed {query}: {e}")
        return set()


def fetch_relevant_ids(query, api_format):
    cache_key = (query, api_format)
    if cache_key in _GT_CACHE:
        return _GT_CACHE[cache_key]
    if api_format == "arxiv":
        res = fetch_arxiv_relevant_ids(query, max_results=50)
    else:
        res = fetch_pubmed_relevant_ids(query, max_results=500)
    if res:
        _GT_CACHE[cache_key] = res
    return res


def build_corpus_ground_truth(es, api_ids, api_format):
    if not api_ids:
        return set(), 0

    id_list = list(api_ids)
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
    ground_truth = set()
    unique_papers_count = len(res["hits"]["hits"])
    for hit in res["hits"]["hits"]:
        pid = hit["_source"].get("paper_id", "")
        pmc = hit["_source"].get("pmc_id", "")
        if pid:
            ground_truth.add(pid)
        if pmc:
            ground_truth.add(pmc)

    return ground_truth, unique_papers_count


def precision_at_k(retrieved_ids, relevant_ids, k):
    if k == 0:
        return 0.0
    top_k = retrieved_ids[:k]
    return sum(1 for doc_id in top_k if doc_id in relevant_ids) / k


def recall_at_k(retrieved_ids, relevant_ids, k, total_relevant=None):
    total = total_relevant or len(relevant_ids)
    if total == 0:
        return 0.0
    top_k = retrieved_ids[:k]
    matched = set(doc_id for doc_id in top_k if doc_id in relevant_ids)
    return len(matched) / total


def average_precision(retrieved_ids, relevant_ids, total_relevant=None):
    total = total_relevant or len(relevant_ids)
    if total == 0:
        return 0.0
    hits = 0
    sum_precisions = 0.0
    seen = set()
    for i, doc_id in enumerate(retrieved_ids):
        if doc_id in relevant_ids and doc_id not in seen:
            seen.add(doc_id)
            hits += 1
            sum_precisions += hits / (i + 1)
    return sum_precisions / total


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
    if dcg == 0:
        return 0.0
    n_rel = min(k, len(relevant_ids))
    idcg = sum(1.0 / math.log2(i + 2) for i in range(n_rel))
    if idcg == 0:
        return 0.0
    return min(1.0, dcg / idcg)


def get_elasticsearch():
    es_config = {
        "hosts": [config.HOST_ELASTIC],
        "verify_certs": False
    }
    if config.PASSWORD_ELASTIC:
        es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
    return Elasticsearch(**es_config)


def execute_query(es, index_name, query_text, fields, mode, size=100):
    if mode == "boolean":
        body = {
            "query": {
                "query_string": {
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
    return res["hits"]["hits"], elapsed_ms


def get_paper_ids_from_hits(hits, category):
    if category == "papers":
        return [
            hit["_source"].get("paper_id") or hit["_source"].get("pmc_id") or hit["_id"]
            for hit in hits
        ]
    return [hit["_source"].get("paper_id", "") for hit in hits]


def evaluate_single_query(es, query_text, category, mode, relevant_paper_ids, total_relevant_papers=None):
    index_name = INDEX_NAMES[category]
    fields = SEARCH_FIELDS[category]

    hits, elapsed_ms = execute_query(es, index_name, query_text, fields, mode)
    retrieved_ids = get_paper_ids_from_hits(hits, category)
    num_gt = total_relevant_papers if total_relevant_papers is not None else len(relevant_paper_ids)

    result = {
        "query": query_text,
        "category": category,
        "mode": mode,
        "num_retrieved": len(retrieved_ids),
        "num_relevant_in_ground_truth": num_gt,
        "response_time_ms": round(elapsed_ms, 2),
        "precision_at_5": round(precision_at_k(retrieved_ids, relevant_paper_ids, 5), 4),
        "precision_at_10": round(precision_at_k(retrieved_ids, relevant_paper_ids, 10), 4),
        "recall_at_10": round(recall_at_k(retrieved_ids, relevant_paper_ids, 10, total_relevant=num_gt), 4),
        "average_precision": round(average_precision(retrieved_ids, relevant_paper_ids, total_relevant=num_gt), 4),
        "reciprocal_rank": round(reciprocal_rank(retrieved_ids, relevant_paper_ids), 4),
        "ndcg_at_10": round(ndcg_at_k(retrieved_ids, relevant_paper_ids, 10), 4),
    }

    top_results = []
    for hit in hits[:3]:
        src = hit["_source"]
        info = {"_id": hit["_id"], "score": round(hit["_score"], 4)}
        if category == "papers":
            info["title"] = src.get("title", "")[:100]
            info["relevant"] = (src.get("paper_id") or src.get("pmc_id") or hit["_id"]) in relevant_paper_ids
        else:
            info["caption"] = src.get("caption", "")[:100]
            info["paper_id"] = src.get("paper_id", "")
            info["relevant"] = src.get("paper_id", "") in relevant_paper_ids
        top_results.append(info)
    result["top_results"] = top_results

    return result


def print_query_result(result):
    marker = "FT" if result["mode"] == "fulltext" else "BL"
    print(f"    [{marker}] \"{result['query']}\"")
    print(f"        Trovati: {result['num_retrieved']} | GT: {result['num_relevant_in_ground_truth']} | {result['response_time_ms']:.1f} ms")
    print(f"        P@5={result['precision_at_5']:.4f}  P@10={result['precision_at_10']:.4f}  R@10={result['recall_at_10']:.4f}  MAP={result['average_precision']:.4f}  nDCG@10={result['ndcg_at_10']:.4f}")


def select_corpus(corpus_arg=None):
    if corpus_arg:
        val = str(corpus_arg).strip().lower()
        if val in ("arxiv", "1"):
            return "arxiv"
        elif val in ("pubmed", "2"):
            return "pubmed"
        elif val in ("all", "3"):
            return "all"
        print(f"Argomento corpus '{corpus_arg}' non valido. Scegli tra: 1 (arxiv), 2 (pubmed), 3 (all).")
        sys.exit(1)

    print("\nCorpus disponibili per la valutazione IR:")
    print("  1. arxiv")
    print("  2. pubmed")
    print("  3. all (valutazione completa comparativa su entrambi i corpus)")

    choice = input("\nSeleziona corpus (1, 2, o all): ").strip().lower()
    if choice in ("1", "arxiv"):
        return "arxiv"
    elif choice in ("2", "pubmed"):
        return "pubmed"
    elif choice in ("3", "all"):
        return "all"
    print("Scelta non valida. Inserisci 1, 2, o all.")
    sys.exit(1)


def evaluate_single_corpus(es, corpus_name):
    corpus_config = TEST_QUERIES[corpus_name]
    api_format = corpus_config["api_query_format"]
    queries_by_mode = corpus_config["queries"]

    corpus_results = {}

    for mode in ["fulltext", "boolean"]:
        queries = queries_by_mode[mode]
        print(f"\n--> Avvio Valutazione {corpus_name.upper()} ({mode}):")

        for query_text in queries:
            api_ids = fetch_relevant_ids(query_text, api_format)
            if not api_ids:
                continue

            relevant_ids, n_unique_papers = build_corpus_ground_truth(es, api_ids, api_format)
            if not relevant_ids or n_unique_papers == 0:
                print(f"    Ignorata query \"{query_text}\": nessun articolo trovato nel corpus indicizzato.")
                continue

            for category in ["papers", "tables", "figures"]:
                index_name = INDEX_NAMES[category]
                if not es.indices.exists(index=index_name):
                    continue

                key = f"{corpus_name}_{category}"
                if key not in corpus_results:
                    corpus_results[key] = []

                result = evaluate_single_query(
                    es, query_text, category, mode, relevant_ids, total_relevant_papers=n_unique_papers
                )
                corpus_results[key].append(result)
                print_query_result(result)

            time.sleep(1)

    summary = {corpus_name: {}}
    
    print(f"\nriepilogo metriche: {corpus_name}")
    

    for key, results in corpus_results.items():
        category = key.split("_", 1)[1]
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
            print(f"  {category:8s} [{mode_label}]: MAP={map_val:.4f} | nDCG@10={ndcg_val:.4f} | MRR={mrr_val:.4f} | P@5={avg_p5:.4f} | P@10={avg_p10:.4f} | {avg_time:.1f} ms")

            summary[corpus_name][f"{category}_{mode}"] = {
                "MAP": round(map_val, 4),
                "mean_nDCG_at_10": round(ndcg_val, 4),
                "MRR": round(mrr_val, 4),
                "mean_P_at_5": round(avg_p5, 4),
                "mean_P_at_10": round(avg_p10, 4),
                "avg_response_time_ms": round(avg_time, 2),
                "num_queries": len(mode_results)
            }
    print()
    return summary, corpus_results


def run_evaluation(corpus_arg=None):
    selected = select_corpus(corpus_arg)
    es = get_elasticsearch()
    if not es.ping():
        print("Errore: impossibile connettersi ad Elasticsearch.")
        sys.exit(1)

    corpora_to_evaluate = ["arxiv", "pubmed"] if selected == "all" else [selected]

    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(output_dir, "evaluation_results.json")

    # carica riepilogo precedente se presente
    existing_summary = {}
    existing_detailed = {}
    if os.path.exists(output_file):
        try:
            with open(output_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                existing_summary = data.get("summary", {})
                existing_detailed = data.get("detailed_results", {})
        except Exception:
            pass

    for c_name in corpora_to_evaluate:
        summary, detailed = evaluate_single_corpus(es, c_name)
        existing_summary.update(summary)
        existing_detailed.update(detailed)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump({"summary": existing_summary, "detailed_results": existing_detailed}, f, indent=2, ensure_ascii=False)

    print(f"Tutti i risultati esportati in: {output_file}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Valutazione IR del Motore di Ricerca Scientifico")
    parser.add_argument(
        "-c", "--corpus",
        choices=["arxiv", "pubmed", "all", "1", "2", "3"],
        default=None,
        help="Corpus da valutare: 1 (arxiv), 2 (pubmed), all/3 (entrambi)"
    )
    args = parser.parse_args()
    run_evaluation(args.corpus)
