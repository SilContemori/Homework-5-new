import json
from elasticsearch import Elasticsearch, helpers
from loguru import logger
import urllib3
from app.config.config import config

# Disabilita warning SSL (solo in locale)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class DocumentIndexer:
    def __init__(self):
        es_config = {
            "hosts": [config.HOST_ELASTIC],
            "verify_certs": False
        }
        if config.PASSWORD_ELASTIC:
            es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
        self.es = Elasticsearch(**es_config)
        self.index_name = "papers_index"

    def create_index(self, reset=False):
        """Crea la struttura (mapping) chiesta dal prof"""
        if self.es.indices.exists(index=self.index_name):
            if reset:
                self.es.indices.delete(index=self.index_name)
                logger.info(f"Indice '{self.index_name}' eliminato.")
            else:
                logger.info(f"Indice '{self.index_name}' esiste già.")
                return

        mapping = {
            "mappings": {
                "properties": {
                    "paper_id": {"type": "keyword"},
                    "pmc_id": {"type": "keyword"},
                    "title": {"type": "text", "analyzer": "english"},
                    "authors": {"type": "text"},
                    "published": {"type": "date"},
                    "abstract": {"type": "text", "analyzer": "english"},
                    "html_content": {"type": "text"} #
                }
            }
        }
        self.es.indices.create(index=self.index_name, body=mapping)
        logger.success(f"Indice '{self.index_name}' creato.")

    def index_data(self, json_file):
        """Legge il file JSON e sposta tutto su Elasticsearch"""
        with open(json_file, 'r', encoding='utf-8') as f:
            papers = json.load(f)

        actions = [
            {
                "_index": self.index_name,
                "_id": p.get('pmc_id') or p.get('paper_id'),
                "_source": p
            }
            for p in papers
        ]

        success, _ = helpers.bulk(self.es, actions)
        logger.success(f"Indicizzati correttamente {success} documenti su Elasticsearch.")

if __name__ == "__main__":
    import os
    indexer = DocumentIndexer()
    indexer.create_index(reset=True)
    json_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "corpus.json"
    )
    indexer.index_data(json_path)
