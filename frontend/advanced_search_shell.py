from elasticsearch import Elasticsearch
import urllib3
import os

# Disabilita avvisi SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Connessione
es = Elasticsearch(
    "https://localhost:9200",
    basic_auth=("elastic", "+ETDg*f9nQCp-0Qho1Bb"),
    verify_certs=False
)

def search_papers(query):
    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["title^2", "abstract", "authors", "full_text"],
                "type": "best_fields"
            }
        }
    }
    res = es.search(index="papers_index", body=body)
    print(f"\n--- Trovati {res['hits']['total']['value']} Documenti ---")
    for hit in res['hits']['hits']:
        print(f"ID: {hit['_source']['paper_id']} | Titolo: {hit['_source']['title'][:80]}...")

def search_tables(query):
    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["caption^3", "body", "mentions", "context_paragraphs"],
                "type": "best_fields"
            }
        }
    }
    res = es.search(index="tables_index", body=body)
    print(f"\n--- Trovate {res['hits']['total']['value']} Tabelle ---")
    for hit in res['hits']['hits']:
        print(f"Paper: {hit['_source']['paper_id']} | Caption: {hit['_source']['caption'][:100]}")

def search_figures(query):
    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["caption^3", "mentions", "context_paragraphs"],
                "type": "best_fields"
            }
        }
    }
    res = es.search(index="figures_index", body=body)
    print(f"\n--- Trovate {res['hits']['total']['value']} Figure ---")
    for hit in res['hits']['hits']:
        print(f"Paper: {hit['_source']['paper_id']} | Caption: {hit['_source']['caption'][:100]}")
        print(f"URL: {hit['_source']['url']}")

def main():
    print("=== SISTEMA DI RICERCA AVANZATA (Homework-5) ===")
    while True:
        print("\nCosa vuoi cercare?")
        print("1. Documenti (Paper)")
        print("2. Tabelle")
        print("3. Figure")
        print("q. Esci")
        
        scelta = input("\nInserisci scelta: ")
        if scelta.lower() == 'q': break
        
        query = input("Inserisci parole chiave (es. 'entity matching performance'): ")
        
        if scelta == '1': search_papers(query)
        elif scelta == '2': search_tables(query)
        elif scelta == '3': search_figures(query)
        else: print("Scelta non valida.")

if __name__ == "__main__":
    main()