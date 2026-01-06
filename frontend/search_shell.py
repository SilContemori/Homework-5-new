from elasticsearch import Elasticsearch
from loguru import logger


class SearchShell:
    def __init__(self):
        self.es = Elasticsearch(
            "https://localhost:9200",
            basic_auth=("elastic", "+ETDg*f9nQCp-0Qho1Bb"),
            verify_certs=False
        )
        self.index_name = "papers_index"

    def search(self, query_text):
        # Cerchiamo nei campi titolo, abstract e autori
        body = {
            "query": {
                "multi_match": {
                    "query": query_text,
                    "fields": ["title", "abstract", "authors"]
                }
            }
        }

        # Eseguiamo la ricerca
        response = self.es.search(index=self.index_name, body=body)
        hits = response['hits']['hits']

        if not hits:
            print(f"\nNESSUN RISULTATO TROVATO PER: {query_text}")
            return

        print(f"\nTROVATI {len(hits)} RISULTATI:\n" + "=" * 50)
        for hit in hits:
            source = hit['_source']
            print(f"ID: {source['paper_id']}")
            print(f"TITOLO: {source['title']}")
            print(f"AUTORI: {', '.join(source['authors'])}")
            print(f"SCORE: {hit['_score']}")
            print("-" * 50)


if __name__ == "__main__":
    shell = SearchShell()
    print("--- BENVENUTO NELLA SHELL DI RICERCA ARXIV ---")
    while True:
        q = input("\nInserisci parola chiave (o 'esci' per chiudere): ")
        if q.lower() in ['esci', 'exit', 'quit']:
            break
        shell.search(q)