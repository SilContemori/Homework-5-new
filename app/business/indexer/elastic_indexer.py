import json
from elasticsearch import Elasticsearch, helpers
from loguru import logger
import urllib3
import warnings
from app.config.config import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message=".*TLS with verify_certs=False.*")

class DocumentIndexer:
    def __init__(self):
        es_config = {
            "hosts": [config.HOST_ELASTIC],
            "verify_certs": False,
            "request_timeout": 60
        }
        if config.PASSWORD_ELASTIC:
            es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
        self.es = Elasticsearch(**es_config)
        self.index_name = "papers_index"

    def create_index(self, reset=False):
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
                    "published": {"type": "date", "ignore_malformed": True},
                    "abstract": {"type": "text", "analyzer": "english"},
                    "full_text": {"type": "text", "analyzer": "english"},
                    "html_content": {"type": "text"}
                }
            }
        }
        self.es.indices.create(index=self.index_name, body=mapping)
        logger.success(f"Indice '{self.index_name}' creato.")

    def index_data(self, json_file):
        import re
        from bs4 import BeautifulSoup

        with open(json_file, 'r', encoding='utf-8') as f:
            papers = json.load(f)

        actions = []
        for p in papers:
            doc = dict(p)
            if not doc.get("full_text"):
                if doc.get("html_content"):
                    soup = BeautifulSoup(doc["html_content"], 'lxml')
                    doc["full_text"] = re.sub(r'\s+', ' ', soup.get_text()).strip()
                else:
                    doc["full_text"] = doc.get("abstract", "")

            doc_id = doc.get('pmc_id') or doc.get('paper_id')
            actions.append({
                "_index": self.index_name,
                "_id": doc_id,
                "_source": doc
            })

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
