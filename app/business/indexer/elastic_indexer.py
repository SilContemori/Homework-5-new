import os
import json
import re
from elasticsearch import Elasticsearch, helpers
from loguru import logger
import urllib3
import warnings
from bs4 import BeautifulSoup
from app.config.config import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message=".*TLS with verify_certs=False.*")


class DocumentIndexer:
    def __init__(self, index_name="papers_index"):
        es_config = {
            "hosts": [config.HOST_ELASTIC],
            "verify_certs": False,
            "request_timeout": 60
        }
        if config.PASSWORD_ELASTIC:
            es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
        self.es = Elasticsearch(**es_config)
        self.index_name = index_name

    def create_index(self, reset=False):
        if self.es.indices.exists(index=self.index_name):
            if reset:
                self.es.indices.delete(index=self.index_name)
                logger.info(f"Indice '{self.index_name}' eliminato.")
            else:
                logger.info(f"Indice '{self.index_name}' esiste già.")
                return

        mapping = {
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "paper_id": {"type": "keyword"},
                    "pmc_id": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        "analyzer": "english",
                        "fields": {
                            "keyword": {"type": "keyword", "ignore_above": 256}
                        }
                    },
                    "authors": {
                        "type": "text",
                        "analyzer": "standard",
                        "fields": {
                            "keyword": {"type": "keyword", "ignore_above": 256}
                        }
                    },
                    "published": {"type": "date", "ignore_malformed": True},
                    "abstract": {"type": "text", "analyzer": "english"},
                    "full_text": {"type": "text", "analyzer": "english"},
                    "html_content": {"type": "text", "index": False}
                }
            }
        }
        self.es.indices.create(index=self.index_name, body=mapping)
        logger.success(f"Indice '{self.index_name}' creato con mapping ottimizzato.")

    def index_data(self, json_file, default_source=None):
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

            # rileva sorgente
            if not doc.get("source"):
                if default_source:
                    doc["source"] = default_source
                elif doc.get("pmc_id") or (doc.get("paper_id", "").isdigit()):
                    doc["source"] = "pubmed"
                else:
                    doc["source"] = "arxiv"

            doc_id = doc.get('pmc_id') or doc.get('paper_id') or f"{doc['source']}_{len(actions)}"
            actions.append({
                "_index": self.index_name,
                "_id": str(doc_id),
                "_source": doc
            })

        success, _ = helpers.bulk(self.es, actions)
        logger.success(f"Indicizzati correttamente {success} documenti in '{self.index_name}'.")
        return success


if __name__ == "__main__":
    indexer = DocumentIndexer()
    indexer.create_index(reset=True)
    json_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "corpus.json"
    )
    if os.path.exists(json_path):
        indexer.index_data(json_path)
