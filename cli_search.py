#!/usr/bin/env python3
import sys
import os
import argparse
from typing import List, Dict, Any, Optional

# aggiungi root al path
project_root = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, project_root)

from elasticsearch import Elasticsearch
import urllib3
import warnings
from app.config.config import config
from scripts.index_all import run_full_indexing

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message=".*TLS with verify_certs=False.*")


def get_elasticsearch() -> Elasticsearch:
    es_config = {
        "hosts": [config.HOST_ELASTIC],
        "verify_certs": False,
        "request_timeout": 30
    }
    if config.PASSWORD_ELASTIC:
        es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
    return Elasticsearch(**es_config)


INDEX_MAP = {
    "papers": "papers_index",
    "tables": "tables_index",
    "figures": "figures_index",
    "images": "figures_index"
}

SEARCH_FIELDS = {
    "papers": ["title^3", "abstract^2", "full_text", "authors"],
    "tables": ["caption^3", "body^2", "mentions^1.5", "context_paragraphs"],
    "figures": ["caption^3", "mentions^2", "context_paragraphs"]
}


def build_es_query(
    category: str,
    query_text: str,
    field: Optional[str] = None,
    mode: str = "fulltext",
    source: Optional[str] = None,
    size: int = 10
) -> Dict[str, Any]:
    index_name = INDEX_MAP.get(category, "papers_index")
    fields = SEARCH_FIELDS.get(category, SEARCH_FIELDS["papers"])

    if field and field.lower() not in ["all", "tutti", "campo...", ""]:
        target_fields = [field]
    else:
        target_fields = fields

    if mode == "boolean":
        query_clause = {
            "query_string": {
                "query": query_text,
                "fields": target_fields,
                "default_operator": "AND"
            }
        }
    elif mode == "phrase":
        if len(target_fields) == 1:
            query_clause = {"match_phrase": {target_fields[0]: query_text}}
        else:
            query_clause = {
                "multi_match": {
                    "query": query_text,
                    "fields": target_fields,
                    "type": "phrase"
                }
            }
    elif mode == "term":
        clean_field = target_fields[0]
        if clean_field in ["table_number", "figure_number"] and query_text.isdigit():
            query_clause = {"term": {clean_field: int(query_text)}}
        elif clean_field in ["paper_id", "pmc_id", "pmid", "element_id", "url", "source"]:
            query_clause = {"term": {clean_field: query_text}}
        elif clean_field in ["title", "authors"]:
            query_clause = {"term": {f"{clean_field}.keyword": query_text}}
        else:
            query_clause = {"match_phrase": {clean_field: query_text}}
    else:
        # ricerca full-text
        if len(target_fields) == 1:
            query_clause = {"match": {target_fields[0]: query_text}}
        else:
            query_clause = {
                "multi_match": {
                    "query": query_text,
                    "fields": target_fields,
                    "type": "best_fields"
                }
            }

    # filtro per sorgente
    if source and source.lower() in ["arxiv", "pubmed"]:
        body = {
            "query": {
                "bool": {
                    "must": [query_clause],
                    "filter": [{"term": {"source": source.lower()}}]
                }
            },
            "size": size
        }
    else:
        body = {
            "query": query_clause,
            "size": size
        }

    return body


def execute_search(es: Elasticsearch, category: str, body: Dict[str, Any]):
    index_name = INDEX_MAP.get(category, "papers_index")
    if not es.indices.exists(index=index_name):
        print(f"\n[!] Errore: l'indice '{index_name}' non esiste in Elasticsearch. Esegui prima l'indicizzazione.")
        return []
    res = es.search(index=index_name, body=body)
    return res["hits"]["hits"]


def print_results(hits: List[Dict[str, Any]], category: str):
    print(f"\ntrovati {len(hits)} risultati per [{category.lower()}]:")
    
    if not hits:
        print("  Nessun risultato trovato. Prova con termini diversi o operatori più permissivi.")
        return

    for i, hit in enumerate(hits, 1):
        score = hit.get("_score", 0.0)
        src = hit.get("_source", {})
        source_label = src.get("source", "N/A").upper()

        print(f"\n[{i}] Score: {score:.4f} | ID: {hit['_id']} | Sorgente: {source_label}")

        if category == "papers":
            title = src.get("title", "Senza titolo")
            authors = src.get("authors", [])
            auth_str = authors if isinstance(authors, str) else ", ".join(authors) if authors else "N/A"
            abstract = src.get("abstract", "")
            print(f"    Titolo:  {title}")
            print(f"    Autori:  {auth_str}")
            if src.get("published"):
                print(f"    Data:    {src.get('published')[:10]}")
            if abstract:
                print(f"    Abstract: {abstract[:220]}...")
            if src.get("doi"):
                print(f"    DOI:     https://doi.org/{src.get('doi')}")

        elif category == "tables":
            p_title = src.get("paper_title", "N/A")
            t_num = src.get("table_number", "N/A")
            caption = src.get("caption", "Nessuna caption")
            body = src.get("body", "")
            mentions = src.get("mentions", [])
            context = src.get("context_paragraphs", [])

            print(f"    Paper:    {p_title}")
            print(f"    Tabella:  Tabella {t_num} (ID: {src.get('table_id')})")
            print(f"    Caption:  {caption}")
            if body:
                print(f"    Corpo:    {body[:180]}...")
            if mentions:
                print(f"    Menzioni nel testo ({len(mentions)}): \"{mentions[0][:150]}...\"")
            if context:
                print(f"    Contesto estratto ({len(context)} paragrafi): \"{context[0][:150]}...\"")

        elif category in ["figures", "images"]:
            p_title = src.get("paper_title", "N/A")
            f_num = src.get("figure_number", "N/A")
            caption = src.get("caption", "Nessuna caption")
            url = src.get("url", "")
            mentions = src.get("mentions", [])
            context = src.get("context_paragraphs", [])

            print(f"    Paper:    {p_title}")
            print(f"    Figura:   Figura {f_num} (ID: {src.get('figure_id')})")
            print(f"    Caption:  {caption}")
            print(f"    URL:      {url}")
            if mentions:
                print(f"    Menzioni ({len(mentions)}): \"{mentions[0][:150]}...\"")
            if context:
                print(f"    Contesto ({len(context)}): \"{context[0][:150]}...\"")

        

def interactive_menu():
    print("""
          motore di ricerca - shell interattiva
    ricerca su documenti, tabelle e figure (arxiv e pubmed)
""")
    es = get_elasticsearch()
    if not es.ping():
        print("[!] Errore: Impossibile connettersi ad Elasticsearch su " + config.HOST_ELASTIC)
        sys.exit(1)

    while True:
        print("""
seleziona modalita:
  1. cerca documenti (papers)
  2. cerca tabelle (tables)
  3. cerca figure (figures)
  4. ricerca booleana (and, or, not)
  5. re-indicizza database (index_all)
  6. esci
""")
        choice = input("Scelta [1-6]: ").strip()
        if choice == "6" or choice.lower() in ["q", "exit", "quit"]:
            print("Chiusura CLI. Arrivederci!")
            break

        if choice == "5":
            print("\n--> Avvio re-indicizzazione unificata in corso...")
            run_full_indexing()
            continue

        cat_map = {"1": "papers", "2": "tables", "3": "figures", "4": "papers"}
        if choice not in cat_map:
            print("Scelta non valida.")
            continue

        if choice == "4":
            print("\nricerca booleana")
            sub_cat = input("Su quale entità vuoi cercare? (1: papers, 2: tables, 3: figures) [1]: ").strip()
            cat = {"2": "tables", "3": "figures"}.get(sub_cat, "papers")
            query_str = input("Inserisci query booleana (es. \"cancer AND risk NOT diet\"): ").strip()
            if not query_str:
                continue
            mode = "boolean"
            field = "all"
        else:
            cat = cat_map[choice]
            query_str = input(f"\nInserisci termini di ricerca per [{cat.upper()}]: ").strip()
            if not query_str:
                continue

            print("\nCampi specifici opzionali (premi Invio per cercare su tutti i campi):")
            if cat == "papers":
                print("  Disponibili: title, abstract, authors, full_text, published, paper_id")
            elif cat == "tables":
                print("  Disponibili: caption, body, mentions, context_paragraphs, paper_title, table_number")
            else:
                print("  Disponibili: caption, mentions, context_paragraphs, paper_title, figure_number, url")

            field = input("Campo specifico (Invio per tutti): ").strip()
            mode_choice = input("Tipo corrispondenza (1: Full-text, 2: Frase esatta phrase, 3: Termine esatto term) [1]: ").strip()
            mode = {"2": "phrase", "3": "term"}.get(mode_choice, "fulltext")

        src_choice = input("Filtro sorgente (1: Tutti i corpus, 2: solo arXiv, 3: solo PubMed) [1]: ").strip()
        source = {"2": "arxiv", "3": "pubmed"}.get(src_choice, "all")

        size_input = input("Numero massimo risultati [5]: ").strip()
        size = int(size_input) if size_input.isdigit() else 5

        body = build_es_query(cat, query_str, field=field, mode=mode, source=source, size=size)
        hits = execute_search(es, cat, body)
        print_results(hits, cat)


def main():
    parser = argparse.ArgumentParser(description="CLI di Ricerca Accademica (HW5 Ingegneria dei Dati)")
    parser.add_argument("-c", "--category", choices=["papers", "tables", "figures"], default="papers", help="Entità su cui cercare")
    parser.add_argument("-q", "--query", type=str, default=None, help="Termini di ricerca")
    parser.add_argument("-f", "--field", type=str, default=None, help="Campo specifico su cui cercare")
    parser.add_argument("-m", "--mode", choices=["fulltext", "phrase", "term", "boolean"], default="fulltext", help="Modalità di matching")
    parser.add_argument("-s", "--source", choices=["all", "arxiv", "pubmed"], default="all", help="Filtro per corpus")
    parser.add_argument("-n", "--size", type=int, default=5, help="Numero massimo di risultati da mostrare")
    parser.add_argument("-i", "--interactive", action="store_true", help="Avvia in modalità shell interattiva")
    parser.add_argument("--index-all", action="store_true", help="Esegui indicizzazione unificata completa su Elasticsearch")

    args = parser.parse_args()

    if args.index_all:
        run_full_indexing()
        sys.exit(0)

    if args.interactive or not args.query:
        interactive_menu()
    else:
        es = get_elasticsearch()
        if not es.ping():
            print("[!] Errore: Elasticsearch non raggiungibile su " + config.HOST_ELASTIC)
            sys.exit(1)
        body = build_es_query(args.category, args.query, field=args.field, mode=args.mode, source=args.source, size=args.size)
        hits = execute_search(es, args.category, body)
        print_results(hits, args.category)


if __name__ == "__main__":
    main()
