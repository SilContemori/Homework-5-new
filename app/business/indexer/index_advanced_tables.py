import os
import json
from elasticsearch import Elasticsearch, helpers
from loguru import logger
from app.config.config import config
import urllib3
import warnings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message=".*TLS with verify_certs=False.*")


class TablesIndexer:
    def __init__(self, index_name="tables_index"):
        self.index_name = index_name
        es_config = {
            "hosts": [config.HOST_ELASTIC],
            "verify_certs": False
        }
        if config.PASSWORD_ELASTIC:
            es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
        self.es = Elasticsearch(**es_config)

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
                    "pmid": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "paper_title": {"type": "text", "analyzer": "english"},
                    "table_id": {"type": "keyword"},
                    "table_number": {"type": "integer"},
                    "element_id": {"type": "keyword"},
                    "caption": {"type": "text", "analyzer": "english"},
                    "body": {"type": "text", "analyzer": "english"},
                    "mentions": {"type": "text", "analyzer": "english"},
                    "context_paragraphs": {"type": "text", "analyzer": "english"}
                }
            }
        }

        self.es.indices.create(index=self.index_name, body=mapping)
        logger.success(f"Indice '{self.index_name}' creato con mapping ottimizzato.")

    def index_from_json(self, json_file, default_source=None):
        with open(json_file, encoding="utf-8") as f:
            tables = json.load(f)

        if not tables:
            logger.warning("Nessuna tabella trovata nel file JSON.")
            return 0

        actions = []
        for idx, table in enumerate(tables):
            paper_ref = table.get("pmc_id") or table.get("paper_id") or "doc"
            elem_id = table.get("element_id") or ""
            table_num = table.get("table_number", idx + 1)

            t_id = f"{paper_ref}_table_{table_num}_{idx}"
            if elem_id:
                t_id += f"_{elem_id}"

            source = table.get("source") or default_source
            if not source:
                source = "pubmed" if (table.get("pmc_id") or table.get("pmid")) else "arxiv"

            actions.append({
                "_index": self.index_name,
                "_id": t_id,
                "_source": {
                    "paper_id": str(table.get("paper_id", "")),
                    "pmc_id": str(table.get("pmc_id", "")),
                    "pmid": str(table.get("pmid", "")),
                    "source": source,
                    "paper_title": table.get("paper_title", ""),
                    "table_id": table.get("table_id") or f"table_{table_num}_{idx}",
                    "table_number": table_num,
                    "element_id": elem_id,
                    "caption": table.get("caption", ""),
                    "body": table.get("body", ""),
                    "mentions": table.get("mentions", []),
                    "context_paragraphs": table.get("context_paragraphs", [])
                }
            })

        success, _ = helpers.bulk(self.es, actions)
        logger.success(f"Indicizzate correttamente {success} tabelle in '{self.index_name}'.")
        return success


if __name__ == "__main__":
    indexer = TablesIndexer()
    indexer.create_index(reset=True)
    json_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "tables_with_context.json"
    )
    if os.path.exists(json_path):
        indexer.index_from_json(json_path)
