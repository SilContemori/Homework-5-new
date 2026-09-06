import os
import sys
from loguru import logger

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from elasticsearch import Elasticsearch
import urllib3
import warnings
from app.config.config import config
from app.business.indexer.elastic_indexer import DocumentIndexer
from app.business.indexer.index_advanced_tables import TablesIndexer
from app.business.indexer.index_advanced_figures import FiguresIndexer

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings("ignore", message=".*TLS with verify_certs=False.*")


def clean_legacy_indices(es: Elasticsearch):
    legacy = ["image_db", "paper_db", "table_db"]
    for idx in legacy:
        if es.indices.exists(index=idx):
            es.indices.delete(index=idx)
            logger.info(f"eliminato indice legacy: {idx}")


def run_full_indexing():
    logger.info("avvio indicizzazione (pubmed + arxiv)")

    es_config = {
        "hosts": [config.HOST_ELASTIC],
        "verify_certs": False
    }
    if config.PASSWORD_ELASTIC:
        es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
    es = Elasticsearch(**es_config)

    clean_legacy_indices(es)

    # reset e creazione indici
    doc_indexer = DocumentIndexer(index_name="papers_index")
    doc_indexer.create_index(reset=True)

    table_indexer = TablesIndexer(index_name="tables_index")
    table_indexer.create_index(reset=True)

    figure_indexer = FiguresIndexer(index_name="figures_index")
    figure_indexer.create_index(reset=True)

    # indicizzazione pubmed
    pubmed_dir = os.path.join(project_root, "pubmed")
    pm_corpus = os.path.join(pubmed_dir, "corpus.json")
    pm_tables = os.path.join(pubmed_dir, "tables_with_context.json")
    pm_figures = os.path.join(pubmed_dir, "figures_with_context.json")

    logger.info("indicizzazione corpus pubmed...")
    if os.path.exists(pm_corpus):
        doc_indexer.index_data(pm_corpus, default_source="pubmed")
    if os.path.exists(pm_tables):
        table_indexer.index_from_json(pm_tables, default_source="pubmed")
    if os.path.exists(pm_figures):
        figure_indexer.index_from_json(pm_figures, default_source="pubmed")

    # indicizzazione arxiv
    arxiv_dir = os.path.join(project_root, "arxiv")
    ar_corpus = os.path.join(arxiv_dir, "corpus.json")
    ar_tables = os.path.join(arxiv_dir, "tables_with_context.json")
    ar_figures = os.path.join(arxiv_dir, "figures_with_context.json")

    logger.info("indicizzazione corpus arxiv...")
    if os.path.exists(ar_corpus):
        doc_indexer.index_data(ar_corpus, default_source="arxiv")
    if os.path.exists(ar_tables):
        table_indexer.index_from_json(ar_tables, default_source="arxiv")
    if os.path.exists(ar_figures):
        figure_indexer.index_from_json(ar_figures, default_source="arxiv")

    # verifica conteggi e stato cluster
    es.indices.refresh(index="papers_index,tables_index,figures_index")
    health = es.cluster.health()
    p_count = es.count(index="papers_index")["count"]
    t_count = es.count(index="tables_index")["count"]
    f_count = es.count(index="figures_index")["count"]

    logger.success(f"indicizzazione completata | stato: {health['status']} | papers: {p_count} | tabelle: {t_count} | figure: {f_count}")

    return {
        "status": health['status'].lower(),
        "papers": p_count,
        "tables": t_count,
        "figures": f_count
    }


index_unified_corpora = run_full_indexing


if __name__ == "__main__":
    run_full_indexing()
