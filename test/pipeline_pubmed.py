import os
import sys
import shutil
from loguru import logger

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from app.business.indexer.elastic_indexer import DocumentIndexer
from app.business.indexer.index_advanced_tables import TablesIndexer
from app.business.indexer.index_advanced_figures import FiguresIndexer


def run_pubmed_pipeline():
    logger.info("Avvio pipeline PubMed")

    pubmed_dir = os.path.join(project_root, "pubmed")
    corpus_file = os.path.join(pubmed_dir, "corpus.json")
    tables_file = os.path.join(pubmed_dir, "tables_with_context.json")
    figures_file = os.path.join(pubmed_dir, "figures_with_context.json")

    if not os.path.exists(corpus_file):
        logger.error(f"File non trovato: {corpus_file}")
        sys.exit(1)

    shutil.copyfile(corpus_file, os.path.join(project_root, "corpus.json"))
    if os.path.exists(tables_file):
        shutil.copyfile(tables_file, os.path.join(project_root, "tables_with_context.json"))
    if os.path.exists(figures_file):
        shutil.copyfile(figures_file, os.path.join(project_root, "figures_with_context.json"))

    doc_indexer = DocumentIndexer()
    doc_indexer.create_index(reset=True)
    doc_indexer.index_data(corpus_file)

    table_indexer = TablesIndexer()
    table_indexer.create_index(reset=True)
    if os.path.exists(tables_file):
        table_indexer.index_from_json(tables_file)

    figure_indexer = FiguresIndexer()
    figure_indexer.create_index(reset=True)
    if os.path.exists(figures_file):
        figure_indexer.index_from_json(figures_file)

    logger.success("Pipeline completata con successo")


if __name__ == "__main__":
    run_pubmed_pipeline()
