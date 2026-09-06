import argparse
import os
import sys
import json
from loguru import logger

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, project_root)

from app.config.config import config
from app.utils.format_date import format_date
from app.business.corpus_builder.source.pubmed import PubmedSource
from app.business.corpus_builder.downloader import CorpusDownloader
from app.business.extractor.table_context_extractor import extract_detailed_tables
from app.business.extractor.figure_context_extractor import extract_detailed_figures
from app.business.indexer.elastic_indexer import DocumentIndexer
from app.business.indexer.index_advanced_tables import TablesIndexer
from app.business.indexer.index_advanced_figures import FiguresIndexer


def run_pubmed_pipeline(
    download: bool = False,
    extract: bool = False,
    index: bool = True,
    query: str = None,
    limit: int = None,
    workers: int = 4
):
    logger.info('Avvio pipeline PubMed')
    pubmed_dir = os.path.join(project_root, 'pubmed')
    os.makedirs(pubmed_dir, exist_ok=True)
    corpus_file = os.path.join(pubmed_dir, 'corpus.json')
    tables_file = os.path.join(pubmed_dir, 'tables_with_context.json')
    figures_file = os.path.join(pubmed_dir, 'figures_with_context.json')

    if download:
        target_query = query or config.QUERY_PUBMED
        logger.info(f'Download PubMed da API NCBI (query={target_query[:80]}...)')
        source = PubmedSource()
        downloader = CorpusDownloader(source, max_workers=workers, delay=config.DELAY)
        papers = downloader.build(target_query)
        if limit and len(papers) > limit:
            papers = papers[:limit]

        papers_data = [
            {
                'paper_id': p.paper_id,
                'title': p.title,
                'authors': p.authors,
                'abstract': p.abstract,
                'published': format_date(p.published),
                'updated': format_date(p.updated),
                'html_url': p.html_url,
                'pdf_url': p.pdf_url,
                'html_content': p.html_content,
                'pmc_id': p.pmc_id,
                'doi': p.doi,
                'source': 'pubmed'
            }
            for p in papers
        ]
        with open(corpus_file, 'w', encoding='utf-8') as f:
            json.dump(papers_data, f, indent=2, ensure_ascii=False)
        logger.info(f'Salvati {len(papers_data)} articoli in {corpus_file}')

    if not os.path.exists(corpus_file):
        logger.error(f'File non trovato: {corpus_file}. Esegui con --download per scaricarlo.')
        sys.exit(1)

    if extract:
        logger.info('Estrazione tabelle da PubMed...')
        num_t = extract_detailed_tables(corpus_file)
        logger.info(f'Tabelle estratte da PubMed: {num_t}')

        logger.info('Estrazione figure da PubMed...')
        num_f = extract_detailed_figures(corpus_file)
        logger.info(f'Figure estratte da PubMed: {num_f}')

    if index:
        logger.info('Indicizzazione documenti PubMed...')
        doc_indexer = DocumentIndexer(index_name='papers_index')
        doc_indexer.index_data(corpus_file, default_source='pubmed')

        if os.path.exists(tables_file):
            logger.info('Indicizzazione tabelle PubMed...')
            table_indexer = TablesIndexer(index_name='tables_index')
            table_indexer.index_from_json(tables_file, default_source='pubmed')

        if os.path.exists(figures_file):
            logger.info('Indicizzazione figure PubMed...')
            figure_indexer = FiguresIndexer(index_name='figures_index')
            figure_indexer.index_from_json(figures_file, default_source='pubmed')

    logger.success('Pipeline PubMed completata con successo.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Pipeline PubMed')
    parser.add_argument('--download', '-d', action='store_true', help='Scarica gli articoli da PubMed / PMC')
    parser.add_argument('--query', '-q', default=None, help='Query personalizzata per PubMed')
    parser.add_argument('--limit', '-l', type=int, default=None, help='Limite numero articoli')
    parser.add_argument('--workers', '-w', type=int, default=4, help='Worker concorrenti per download HTML')
    parser.add_argument('--extract', '-e', action='store_true', help='Esegui estrazione tabelle e figure con contesto')
    parser.add_argument('--index', '-i', action='store_true', help='Esegui indicizzazione su Elasticsearch')
    args = parser.parse_args()

    do_download = args.download
    do_extract = args.extract
    if args.download and not args.extract and not args.index:
        do_index = False
    elif args.extract and not args.index:
        do_index = False
    else:
        do_index = args.index or (not args.download and not args.extract)

    run_pubmed_pipeline(
        download=do_download,
        extract=do_extract,
        index=do_index,
        query=args.query,
        limit=args.limit,
        workers=args.workers
    )
