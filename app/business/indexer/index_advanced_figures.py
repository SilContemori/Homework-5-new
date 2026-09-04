import json
from elasticsearch import Elasticsearch, helpers
from loguru import logger
import urllib3
import warnings
from app.config.config import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message=".*TLS with verify_certs=False.*")


class FiguresIndexer:
    def __init__(self, index_name="figures_index"):
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
            "mappings": {
                "properties": {
                    "url": {"type": "keyword"},
                    "paper_id": {"type": "keyword"},
                    "pmc_id": {"type": "keyword"},
                    "pmid": {"type": "keyword"},
                    "paper_title": {"type": "text", "analyzer": "standard"},
                    "figure_id": {"type": "keyword"},
                    "figure_number": {"type": "integer"},
                    "element_id": {"type": "keyword"},
                    "caption": {"type": "text", "analyzer": "standard"},
                    "mentions": {"type": "text", "analyzer": "standard"},
                    "context_paragraphs": {"type": "text", "analyzer": "standard"}
                }
            }
        }

        self.es.indices.create(index=self.index_name, body=mapping)
        logger.success(f"Indice '{self.index_name}' creato.")

    def index_from_json(self, json_file):
        """
        Indicizza le figure da un file JSON.
        Usa un _id composito (paper_id + figure_id)
        per evitare collisioni.
        """

        with open(json_file, encoding="utf-8") as f:
            figures = json.load(f)

        if not figures:
            logger.warning("Nessuna figura trovata nel JSON.")
            return

        actions = []
        for fig in figures:
            link_id = fig.get("pmc_id") or fig.get("paper_id") or "unk"

            actions.append({
                "_index": self.index_name,
                "_id": f"{link_id}_{fig['figure_id']}",
                "_source": {
                    "url": fig["url"],
                    "paper_id": link_id,
                    "paper_title": fig.get("paper_title", ""),
                    "figure_id": fig["figure_id"],
                    "figure_number": fig.get("figure_number", 1),
                    "element_id": fig.get("element_id", ""),
                    "caption": fig["caption"],
                    "mentions": fig.get("mentions", []),
                    "context_paragraphs": fig.get("context_paragraphs", []),
                    "pmc_id": fig.get("pmc_id", ""),
                    "pmid": fig.get("pmid", fig.get("paper_id", ""))
                }
            })

        success, _ = helpers.bulk(self.es, actions)
        logger.success(f"Indicizzate correttamente {success} figure.")

if __name__ == "__main__":
    import os
    indexer = FiguresIndexer()
    indexer.create_index(reset=True)
    json_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "figures_with_context.json"
    )
    indexer.index_from_json(json_path)
