import os
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
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "url": {"type": "keyword"},
                    "paper_id": {"type": "keyword"},
                    "pmc_id": {"type": "keyword"},
                    "pmid": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "paper_title": {"type": "text", "analyzer": "english"},
                    "figure_id": {"type": "keyword"},
                    "table_id": {"type": "keyword"},  # Alias richiesto dal punto 7 della traccia
                    "figure_number": {"type": "integer"},
                    "element_id": {"type": "keyword"},
                    "caption": {"type": "text", "analyzer": "english"},
                    "mentions": {"type": "text", "analyzer": "english"},
                    "context_paragraphs": {"type": "text", "analyzer": "english"}
                }
            }
        }

        self.es.indices.create(index=self.index_name, body=mapping)
        logger.success(f"Indice '{self.index_name}' creato con mapping ottimizzato.")

    def index_from_json(self, json_file, default_source=None):
        with open(json_file, encoding="utf-8") as f:
            figures = json.load(f)

        if not figures:
            logger.warning("Nessuna figura trovata nel JSON.")
            return 0

        actions = []
        for idx, fig in enumerate(figures):
            link_id = fig.get("pmc_id") or fig.get("paper_id") or "unk"
            fig_id = fig.get("figure_id", f"fig_{idx}")

            source = fig.get("source") or default_source
            if not source:
                source = "pubmed" if (fig.get("pmc_id") or fig.get("pmid")) else "arxiv"

            actions.append({
                "_index": self.index_name,
                "_id": f"{link_id}_{fig_id}_{idx}",
                "_source": {
                    "url": fig.get("url", ""),
                    "paper_id": str(link_id),
                    "pmc_id": str(fig.get("pmc_id", "")),
                    "pmid": str(fig.get("pmid", fig.get("paper_id", ""))),
                    "source": source,
                    "paper_title": fig.get("paper_title", ""),
                    "figure_id": fig_id,
                    "table_id": fig_id,  # Mantiene conformità pedante al testo del requisito 7
                    "figure_number": fig.get("figure_number", 1),
                    "element_id": fig.get("element_id", ""),
                    "caption": fig.get("caption", ""),
                    "mentions": fig.get("mentions", []),
                    "context_paragraphs": fig.get("context_paragraphs", [])
                }
            })

        success, _ = helpers.bulk(self.es, actions)
        logger.success(f"Indicizzate correttamente {success} figure in '{self.index_name}'.")
        return success


if __name__ == "__main__":
    indexer = FiguresIndexer()
    indexer.create_index(reset=True)
    json_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "figures_with_context.json"
    )
    if os.path.exists(json_path):
        indexer.index_from_json(json_path)
