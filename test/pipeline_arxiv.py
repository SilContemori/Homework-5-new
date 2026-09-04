import os
import sys
import json
from loguru import logger

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from app.config.config import config
from app.business.corpus_builder.source.arxiv import ArxivSource
from app.business.corpus_builder.downloader import CorpusDownloader
from app.utils.format_date import format_date
from app.business.extractor.table_context_extractor import extract_detailed_tables
from app.business.extractor.figure_context_extractor import extract_detailed_figures
from app.business.indexer.elastic_indexer import DocumentIndexer
from app.business.indexer.index_advanced_tables import TablesIndexer
from app.business.indexer.index_advanced_figures import FiguresIndexer


def run_arxiv_pipeline(
    query: str = 'all:"entity resolution" OR all:"entity matching" OR all:"record linkage" OR all:"data deduplication"',
    max_papers: int = 50
):
    logger.info(f"Avvio pipeline arXiv (query: {query}, max: {max_papers})")

    source = ArxivSource()
    import feedparser
    import urllib.parse
    encoded = urllib.parse.quote(query)
    url = f"{source.API_URL}?search_query={encoded}&start=0&max_results={max_papers}"
    feed = feedparser.parse(url)
    
    from app.business.corpus_builder.models import Paper
    papers_to_fetch = []
    for entry in feed.entries:
        aid = entry.id.split("/abs/")[1]
        papers_to_fetch.append(
            Paper(
                paper_id=aid,
                title=entry.title.strip().replace("\n", " "),
                authors=[a.name for a in entry.authors],
                abstract=entry.summary.strip().replace("\n", " "),
                published=entry.published,
                updated=entry.updated,
                html_url=f"https://arxiv.org/html/{aid}",
                pdf_url=f"https://arxiv.org/pdf/{aid}.pdf"
            )
        )
    logger.info(f"Trovati {len(papers_to_fetch)} paper.")

    downloaded_papers = []
    for p in papers_to_fetch:
        logger.info(f"Scaricamento HTML: {p.paper_id}")
        source.fetch_html(p)
        downloaded_papers.append(p)

    corpus_file = os.path.join(project_root, "corpus.json")
    papers_data = [
        {
            "paper_id": p.paper_id,
            "title": p.title,
            "authors": p.authors,
            "abstract": p.abstract,
            "published": format_date(p.published),
            "updated": format_date(p.updated),
            "html_url": p.html_url,
            "pdf_url": p.pdf_url,
            "html_content": p.html_content,
            "pmc_id": "",
            "doi": getattr(p, "doi", "") or ""
        }
        for p in downloaded_papers
    ]

    with open(corpus_file, "w", encoding="utf-8") as f:
        json.dump(papers_data, f, indent=2, ensure_ascii=False)
    logger.info(f"Salvati {len(papers_data)} paper in corpus.json")

    num_tables = extract_detailed_tables(corpus_file)
    logger.info(f"Tabelle estratte: {num_tables}")
    num_figures = extract_detailed_figures(corpus_file)
    logger.info(f"Figure estratte: {num_figures}")

    doc_indexer = DocumentIndexer()
    doc_indexer.create_index(reset=True)
    doc_indexer.index_data(corpus_file)

    table_indexer = TablesIndexer()
    table_indexer.create_index(reset=True)
    tables_file = os.path.join(project_root, "tables_with_context.json")
    if os.path.exists(tables_file):
        table_indexer.index_from_json(tables_file)

    figure_indexer = FiguresIndexer()
    figure_indexer.create_index(reset=True)
    figures_file = os.path.join(project_root, "figures_with_context.json")
    if os.path.exists(figures_file):
        figure_indexer.index_from_json(figures_file)

    logger.success("Pipeline completata con successo")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Pipeline ArXiv")
    parser.add_argument(
        "--query",
        "-q",
        default='all:"entity resolution" OR all:"entity matching" OR all:"record linkage" OR all:"data deduplication"',
        help="Query per arXiv"
    )
    parser.add_argument("--limit", "-l", type=int, default=50, help="Numero massimo di paper da scaricare")
    args = parser.parse_args()
    run_arxiv_pipeline(query=args.query, max_papers=args.limit)
