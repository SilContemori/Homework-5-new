import sys
import os

# Aggiungi il root del progetto al path per importare config
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from elasticsearch import Elasticsearch
import urllib3
from loguru import logger
from app.config.config import config

# Disabilita avvisi SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class SearchShell:
    def __init__(self):
        es_config = {
            "hosts": [config.HOST_ELASTIC],
            "verify_certs": False
        }
        if config.PASSWORD_ELASTIC:
            es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
        self.es = Elasticsearch(**es_config)
        self.index_name = "papers_index"

    def search(self, query_text, fields=None, mode="fulltext"):
        if fields is None:
            fields = ["title^2", "abstract", "authors", "html_content"]

        if mode == "boolean":
            body = {
                "query": {
                    "simple_query_string": {
                        "query": query_text,
                        "fields": fields,
                        "default_operator": "AND"
                    }
                }
            }
        else:
            body = {
                "query": {
                    "multi_match": {
                        "query": query_text,
                        "fields": fields,
                        "type": "best_fields"
                    }
                }
            }

        response = self.es.search(index=self.index_name, body=body)
        hits = response['hits']['hits']

        if not hits:
            print(f"\nNESSUN RISULTATO TROVATO PER: {query_text}")
            return

        print(f"\nTROVATI {len(hits)} RISULTATI:\n" + "=" * 50)
        for hit in hits:
            source = hit['_source']
            print(f"ID: {source.get('paper_id', hit['_id'])}")
            print(f"TITOLO: {source.get('title', 'N/A')}")
            authors = source.get('authors', [])
            if isinstance(authors, list):
                authors = ', '.join(authors)
            print(f"AUTORI: {authors}")
            print(f"DATA: {source.get('published', 'N/A')}")
            print(f"SCORE: {hit['_score']}")
            print("-" * 50)


if __name__ == "__main__":
    shell = SearchShell()
    print("--- BENVENUTO NELLA SHELL DI RICERCA ---")
    print("Modalita: 'b' per booleana (AND, OR, NOT), altrimenti full-text")
    print("Campi: 'c' per selezionare campi specifici\n")

    mode = "fulltext"
    fields = None

    while True:
        q = input("\nComando o query (esci/b/c/query): ").strip()
        if q.lower() in ['esci', 'exit', 'quit']:
            break
        elif q.lower() == 'b':
            mode = "boolean" if mode == "fulltext" else "fulltext"
            print(f"Modalita cambiata a: {mode}")
            if mode == "boolean":
                print("  Sintassi: AND, OR, NOT, \"frase esatta\"")
            continue
        elif q.lower() == 'c':
            print("\nCampi disponibili:")
            print("  1. title (Titolo)")
            print("  2. abstract (Abstract)")
            print("  3. authors (Autori)")
            print("  4. html_content (Testo completo)")
            print("  a. Tutti (default)")
            sel = input("Seleziona (es. '1,2' oppure 'a'): ").strip()
            field_map = {'1': 'title^2', '2': 'abstract', '3': 'authors', '4': 'html_content'}
            if sel.lower() == 'a' or not sel:
                fields = None
                print("  Uso tutti i campi.")
            else:
                fields = [field_map[s.strip()] for s in sel.split(',') if s.strip() in field_map]
                if not fields:
                    fields = None
                    print("  Selezione non valida, uso tutti i campi.")
                else:
                    print(f"  Campi selezionati: {fields}")
            continue

        shell.search(q, fields=fields, mode=mode)
