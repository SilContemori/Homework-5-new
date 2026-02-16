import sys
import os

# Aggiungi il root del progetto al path per importare config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from elasticsearch import Elasticsearch
import urllib3
from app.config.config import config

# Disabilita avvisi SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def get_elasticsearch():
    es_config = {
        "hosts": [config.HOST_ELASTIC],
        "verify_certs": False
    }
    if config.PASSWORD_ELASTIC:
        es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
    return Elasticsearch(**es_config)


# Campi disponibili per categoria
FIELDS_BY_CATEGORY = {
    "papers": {
        "1": ("title", "Titolo", 2),
        "2": ("abstract", "Abstract", 1),
        "3": ("authors", "Autori", 1),
        "4": ("html_content", "Testo completo", 1),
    },
    "tables": {
        "1": ("caption", "Caption", 3),
        "2": ("body", "Body", 1),
        "3": ("mentions", "Mentions", 1),
        "4": ("context_paragraphs", "Context paragraphs", 1),
    },
    "figures": {
        "1": ("caption", "Caption", 3),
        "2": ("mentions", "Mentions", 1),
        "3": ("context_paragraphs", "Context paragraphs", 1),
    }
}

INDEX_NAMES = {
    "papers": "papers_index",
    "tables": "tables_index",
    "figures": "figures_index"
}


def select_fields(category):
    """Permette all'utente di scegliere su quali campi cercare."""
    fields_info = FIELDS_BY_CATEGORY[category]

    print("\nCampi disponibili:")
    for key, (field, label, boost) in fields_info.items():
        print(f"  {key}. {label} ({field})")
    print(f"  a. Tutti i campi (default)")

    scelta = input("\nSeleziona campi (es. '1,3' oppure 'a' per tutti): ").strip()

    if not scelta or scelta.lower() == 'a':
        # Tutti i campi con boost
        return [f"{f}^{b}" if b > 1 else f for _, (f, _, b) in fields_info.items()]

    selected = []
    for s in scelta.split(','):
        s = s.strip()
        if s in fields_info:
            field, _, boost = fields_info[s]
            selected.append(f"{field}^{boost}" if boost > 1 else field)

    if not selected:
        print("Selezione non valida, uso tutti i campi.")
        return [f"{f}^{b}" if b > 1 else f for _, (f, _, b) in fields_info.items()]

    return selected


def select_search_mode():
    """Permette all'utente di scegliere la modalità di ricerca."""
    print("\nModalità di ricerca:")
    print("  1. Full-text (default) - ricerca per rilevanza")
    print("  2. Booleana - supporta AND, OR, NOT, frasi \"...\"")

    scelta = input("\nSeleziona modalità (1/2): ").strip()
    return "boolean" if scelta == "2" else "fulltext"


def build_query(query_text, fields, mode):
    """Costruisce la query Elasticsearch in base alla modalità."""
    if mode == "boolean":
        return {
            "query": {
                "simple_query_string": {
                    "query": query_text,
                    "fields": fields,
                    "default_operator": "AND"
                }
            },
            "size": 20
        }
    else:
        return {
            "query": {
                "multi_match": {
                    "query": query_text,
                    "fields": fields,
                    "type": "best_fields"
                }
            },
            "size": 20
        }


def search_papers(es, query_text, fields, mode):
    body = build_query(query_text, fields, mode)
    res = es.search(index="papers_index", body=body)
    total = res['hits']['total']['value']
    hits = res['hits']['hits']

    print(f"\n--- Trovati {total} Documenti (mostrati {len(hits)}) ---")
    for hit in hits:
        src = hit['_source']
        print(f"  ID: {src.get('paper_id', hit['_id'])} | Score: {hit['_score']:.2f}")
        print(f"  Titolo: {src.get('title', 'N/A')[:100]}")
        authors = src.get('authors', [])
        if isinstance(authors, list):
            authors = ', '.join(authors)
        print(f"  Autori: {authors[:80]}")
        print(f"  Data: {src.get('published', 'N/A')}")
        print("-" * 60)


def search_tables(es, query_text, fields, mode):
    body = build_query(query_text, fields, mode)
    res = es.search(index="tables_index", body=body)
    total = res['hits']['total']['value']
    hits = res['hits']['hits']

    print(f"\n--- Trovate {total} Tabelle (mostrate {len(hits)}) ---")
    for hit in hits:
        src = hit['_source']
        print(f"  Paper: {src.get('paper_id', 'N/A')} | Table: {src.get('table_id', 'N/A')} | Score: {hit['_score']:.2f}")
        print(f"  Caption: {src.get('caption', 'N/A')[:120]}")
        print("-" * 60)


def search_figures(es, query_text, fields, mode):
    body = build_query(query_text, fields, mode)
    res = es.search(index="figures_index", body=body)
    total = res['hits']['total']['value']
    hits = res['hits']['hits']

    print(f"\n--- Trovate {total} Figure (mostrate {len(hits)}) ---")
    for hit in hits:
        src = hit['_source']
        print(f"  Paper: {src.get('paper_id', 'N/A')} | Figure: {src.get('figure_id', 'N/A')} | Score: {hit['_score']:.2f}")
        print(f"  Caption: {src.get('caption', 'N/A')[:120]}")
        print(f"  URL: {src.get('url', 'N/A')}")
        print("-" * 60)


def main():
    es = get_elasticsearch()

    print("=" * 60)
    print("  SISTEMA DI RICERCA AVANZATA (Homework-5)")
    print("  Supporta: full-text, booleana (AND, OR, NOT, \"frasi\")")
    print("=" * 60)

    while True:
        print("\nCosa vuoi cercare?")
        print("  1. Documenti (Paper)")
        print("  2. Tabelle")
        print("  3. Figure")
        print("  q. Esci")

        scelta = input("\nInserisci scelta: ").strip()
        if scelta.lower() == 'q':
            break

        category_map = {'1': 'papers', '2': 'tables', '3': 'figures'}
        category = category_map.get(scelta)
        if not category:
            print("Scelta non valida.")
            continue

        # Selezione campi
        fields = select_fields(category)
        print(f"  Campi selezionati: {fields}")

        # Selezione modalità di ricerca
        mode = select_search_mode()

        if mode == "boolean":
            print("\n  Sintassi booleana: usa AND, OR, NOT, \"frase esatta\", (raggruppamento)")
            print("  Esempio: \"entity resolution\" AND (blocking OR matching) NOT survey")

        query = input("\nInserisci query: ").strip()
        if not query:
            print("Query vuota, riprova.")
            continue

        search_fn = {'papers': search_papers, 'tables': search_tables, 'figures': search_figures}
        search_fn[category](es, query, fields, mode)


if __name__ == "__main__":
    main()
