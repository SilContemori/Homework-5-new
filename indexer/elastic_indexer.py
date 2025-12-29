import json
from elasticsearch import Elasticsearch, helpers
from loguru import logger
import urllib3
from config import config

# Disabilita warning SSL (solo in locale)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class DocumentIndexer:
    def __init__(self):
        # Usiamo le tue credenziali scoperte prima
        self.es = Elasticsearch(
            config.HOST_ELASTIC,
            basic_auth=("elastic", config.PASSWORD_ELASTC),
            verify_certs=False  # Necessario perché siamo in locale senza certificati veri
        )
        self.index_name = "papers_index"

    def create_index(self):
        """Crea la struttura (mapping) chiesta dal prof"""
        mapping = {
            "mappings": {
                "properties": {
                    "paper_id": {"type": "keyword"},
                    "title": {"type": "text", "analyzer": "english"},
                    "authors": {"type": "text"},
                    "published": {"type": "date"},
                    "abstract": {"type": "text", "analyzer": "english"},
                    "html_content": {"type": "text"} # Questo conterrà il testo completo
                }
            }
        }
        if not self.es.indices.exists(index=self.index_name):
            self.es.indices.create(index=self.index_name, body=mapping)
            logger.info(f"Indice '{self.index_name}' creato con successo.")
        else:
            logger.info(f"L'indice '{self.index_name}' esiste già.")

    def index_data(self, json_file):
        """Legge il file JSON e sposta tutto su Elasticsearch"""
        with open(json_file, 'r', encoding='utf-8') as f:
            papers = json.load(f)

        actions = [
            {
                "_index": self.index_name,
                "_id": p['paper_id'],
                "_source": p
            }
            for p in papers
        ]

        success, _ = helpers.bulk(self.es, actions)
        logger.info(f"Indicizzati correttamente {success} documenti su Elasticsearch.")

if __name__ == "__main__":
    #1. connessione a elastc seach
    indexer = DocumentIndexer()
    #2. creazione indice con una strutttura mapping ben definita (prendendo i paper dal file json)
    indexer.create_index()
    #3. indicizzazione dei file dentro elastic search
    indexer.index_data("../corpus.json")