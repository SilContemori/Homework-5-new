import json
from elasticsearch import Elasticsearch, helpers
from loguru import logger
from config import config
import urllib3

# Disabilita warning SSL (solo in locale)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TablesIndexer:
    def __init__(self, index_name="tables_index"):
        self.index_name = index_name
        self.es = Elasticsearch(
            config.HOST_ELASTIC,
            basic_auth=("elastic", config.PASSWORD_ELASTC),
            verify_certs=False
        )

    def create_index(self, reset=False):
        """
        Crea l'indice delle tabelle.
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
                    "paper_id": {"type": "keyword"},
                    "paper_title": {"type": "text", "analyzer": "standard"},
                    "table_id": {"type": "keyword"},
                    "table_number": {"type": "integer"},
                    "caption": {"type": "text", "analyzer": "standard"},
                    "body": {"type": "text", "analyzer": "standard"},
                    "mentions": {"type": "text", "analyzer": "standard"},
                    "context_paragraphs": {"type": "text", "analyzer": "standard"}
                }
            }
        }

        self.es.indices.create(index=self.index_name, body=mapping)
        logger.success(f"Indice '{self.index_name}' creato con successo.")

    def index_from_json(self, json_file):
        """
        Indicizza le tabelle da un file JSON.
        Usa _id composito per evitare collisioni.
        """

        with open(json_file, encoding="utf-8") as f:
            tables = json.load(f)

        if not tables:
            logger.warning("Nessuna tabella trovata nel file JSON.")
            return

        actions = [
            {
                "_index": self.index_name,
                "_id": f"{table['paper_id']}_table_{table['table_index']}",
                "_source": {
                    "paper_id": table["paper_id"],
                    "paper_title": table.get("paper_title", ""),
                    "table_id": f"table_{table['table_index']}",
                    "table_number": table['table_index'] + 1,
                    "caption": table.get("caption", ""),
                    "body": table.get("body", ""),
                    "mentions": table.get("mentions", []),
                    "context_paragraphs": table.get("context_paragraphs", [])
                }
            }
            for table in tables
        ]

        success, _ = helpers.bulk(self.es, actions)
        logger.success(f"Indicizzate correttamente {success} tabelle.")


if __name__ == "__main__":
    import os
    # 1. connessione a elastic search
    indexer = TablesIndexer()
    # 2. creazione indice con una strutttura mapping ben definita (prendendo i paper dal file json)
    indexer.create_index(reset=True)
    # 3. indicizzazione delle tabelle dentro elastic search
    json_path = os.path.join(os.path.dirname(__file__), "..", "tables_with_context.json")
    indexer.index_from_json(json_path)
