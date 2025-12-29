import json
from elasticsearch import Elasticsearch, helpers
from loguru import logger
import urllib3
from config import config

# Disabilita warning SSL (solo in locale)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class FiguresIndexer:
    def __init__(self, index_name="figures_index"):
        self.index_name = index_name
        self.es = Elasticsearch(
            config.HOST_ELASTIC,
            basic_auth=("elastic", config.PASSWORD_ELASTC),
            verify_certs=False  # Necessario perché siamo in locale senza certificati veri
        )

    def create_index(self, reset=False):
        """
        Crea l'indice delle figure.
        Se reset=True, elimina l'indice esistente.
        """

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
                    "paper_title": {"type": "text", "analyzer": "standard"},
                    "figure_id": {"type": "keyword"},
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

        actions = [
            {
                "_index": self.index_name,
                "_id": f"{fig['paper_id']}_{fig['figure_id']}",
                "_source": {
                    "url": fig["url"],
                    "paper_id": fig["paper_id"],
                    "paper_title": fig.get("paper_title", ""),
                    "figure_id": fig["figure_id"],
                    "caption": fig["caption"],
                    "mentions": fig["mentions"],
                    "context_paragraphs": fig.get("context_paragraphs", [])
                }
            }
            for fig in figures
        ]

        success, _ = helpers.bulk(self.es, actions)
        logger.success(f"Indicizzate correttamente {success} figure.")


if __name__ == "__main__":
    # 1. connessione a elastic search
    indexer = FiguresIndexer()
    #2. creazione indice con una strutttura mapping ben definita (prendendo i paper dal file json)
    indexer.create_index(reset=True)
    # 3. indicizzazione delle immagini dentro elastic search
    indexer.index_from_json("../figures_with_context.json")
