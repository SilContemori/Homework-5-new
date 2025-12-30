import json
from config import config
from corpus_builder.downloader import CorpusDownloader
from corpus_builder.source.arxiv import ArxivSource

# Extractor
from extractor.table_context_extractor import extract_detailed_tables
from extractor.figure_context_extractor import FigureContextExtractor

# Indexer
from indexer.elastic_indexer import DocumentIndexer
from indexer.index_advanced_tables import TablesIndexer
from indexer.index_advanced_figures import FiguresIndexer

if __name__ == "__main__":
    # ========== 1. CREAZIONE CORPUS ==========
    print("=== FASE 1: Creazione corpus documenti ===")
    source = ArxivSource()
    downloader = CorpusDownloader(source)

    corpus = downloader.build(config.QUERY)

    with open("corpus.json", "w", encoding="utf-8") as f:
        json.dump([paper.__dict__ for paper in corpus],
                  f, indent=2, ensure_ascii=False)

    print(f"Creato corpus con {len(corpus)} documenti\n")

    # ========== 2. ESTRAZIONE TABELLE ==========
    print("=== FASE 2: Estrazione tabelle con contesto ===")
    num_tables = extract_detailed_tables("corpus.json")
    print(f"Estratte {num_tables} tabelle\n")

    # ========== 3. ESTRAZIONE FIGURE ==========
    print("=== FASE 3: Estrazione figure con contesto ===")
    fig_extractor = FigureContextExtractor("corpus.json")
    num_figures = fig_extractor.extract()
    print(f"Estratte {num_figures} figure\n")

    # ========== 4. INDICIZZAZIONE PAPER ==========
    print("=== FASE 4: Indicizzazione paper su Elasticsearch ===")
    doc_indexer = DocumentIndexer()
    doc_indexer.create_index()
    doc_indexer.index_data("corpus.json")

    # ========== 5. INDICIZZAZIONE TABELLE ==========
    print("\n=== FASE 5: Indicizzazione tabelle su Elasticsearch ===")
    table_indexer = TablesIndexer()
    table_indexer.create_index(reset=True)
    table_indexer.index_from_json("tables_with_context.json")

    # ========== 6. INDICIZZAZIONE FIGURE ==========
    print("\n=== FASE 6: Indicizzazione figure su Elasticsearch ===")
    fig_indexer = FiguresIndexer()
    fig_indexer.create_index(reset=True)
    fig_indexer.index_from_json("figures_with_context.json")

    print("\n=== PIPELINE COMPLETATA ===")
    print("Tutte le fasi sono state eseguite con successo!")
