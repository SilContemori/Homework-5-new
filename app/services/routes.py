from fastapi import FastAPI, Request, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.templating import Jinja2Templates
from elasticsearch import Elasticsearch
import urllib3
import os
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger

from app.config.config import config
from app.business.corpus_builder.downloader import CorpusDownloader
from app.business.corpus_builder.source.arxiv import ArxivSource
from app.business.corpus_builder.source.pubmed import PubmedSource
from app.business.extractor.table_context_extractor import extract_detailed_tables
from app.business.extractor.figure_context_extractor import extract_detailed_figures
from app.business.indexer.elastic_indexer import DocumentIndexer
from app.business.indexer.index_advanced_tables import TablesIndexer
from app.business.indexer.index_advanced_figures import FiguresIndexer
from app.utils.format_date import format_date
from urllib.parse import parse_qs, urlparse
from scripts.index_all import index_unified_corpora

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
templates = Jinja2Templates(directory=template_dir)

tags_metadata = [
    {"name": "Ricerca & UI", "description": "Interfaccia web e ricerca full-text o booleana."},
    {"name": "Pipeline & Tasks", "description": "Download ed estrazione dati in background."},
    {"name": "Redirects", "description": "Gestione link interni agli articoli HTML (evita errori 404 verso PMC e arXiv)."},
]

app = FastAPI(
    title="Motore di Ricerca Paper Scientifici",
    description="API per la ricerca e gestione di articoli scientifici, tabelle e figure (arXiv e PubMed Central).",
    version="1.0.0",
    openapi_tags=tags_metadata,
)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
import warnings
warnings.filterwarnings("ignore", message=".*TLS with verify_certs=False.*")

task_status: Dict[str, Dict] = {}


def get_elasticsearch():
    es_config = {
        "hosts": [config.HOST_ELASTIC],
        "verify_certs": False
    }
    if config.PASSWORD_ELASTIC:
        es_config["basic_auth"] = ("elastic", config.PASSWORD_ELASTIC)
    return Elasticsearch(**es_config)


def run_build_corpus_task(task_id: str, source: str = "all"):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        results = {}

        # pubmed
        if source.lower() in ("all", "pubmed"):
            logger.info("Initializing PubMed source...")
            pubmed_source = PubmedSource()
            downloader = CorpusDownloader(pubmed_source, max_workers=1, delay=1.5)
            pubmed_papers = downloader.build(config.QUERY_PUBMED)
            pubmed_dir = os.path.join(project_root, "pubmed")
            os.makedirs(pubmed_dir, exist_ok=True)
            pubmed_file = os.path.join(pubmed_dir, "corpus.json")
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
                    "pmc_id": p.pmc_id,
                    "doi": p.doi,
                    "source": "pubmed"
                }
                for p in pubmed_papers
            ]
            with open(pubmed_file, 'w', encoding='utf-8') as f:
                json.dump(papers_data, f, indent=2, ensure_ascii=False)
            results["pubmed_count"] = len(pubmed_papers)
            results["pubmed_file"] = pubmed_file

        # arxiv
        if source.lower() in ("all", "arxiv"):
            arxiv_file = os.path.join(project_root, "arxiv", "corpus.json")
            if not os.path.exists(arxiv_file):
                logger.info("arxiv/corpus.json non trovato, avvio pipeline_arxiv...")
                from scripts.pipeline_arxiv import run_arxiv_pipeline
                run_arxiv_pipeline(target_papers=500, max_workers=6)
            if os.path.exists(arxiv_file):
                with open(arxiv_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results["arxiv_count"] = len(data)
                results["arxiv_file"] = arxiv_file

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[CORPUS BUILD] Task COMPLETED. Risultati: {results}. Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = results

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[CORPUS BUILD] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_extract_tables_task(task_id: str, source: str = "all"):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        pubmed_corpus = os.path.join(project_root, "pubmed", "corpus.json")
        if not os.path.exists(pubmed_corpus):
            pubmed_corpus = os.path.join(project_root, "corpus.json")
        arxiv_corpus = os.path.join(project_root, "arxiv", "corpus.json")

        total_tables = 0
        details = {}

        if source.lower() in ("all", "pubmed") and os.path.exists(pubmed_corpus):
            n = extract_detailed_tables(pubmed_corpus)
            total_tables += n
            details["pubmed_tables"] = n

        if source.lower() in ("all", "arxiv") and os.path.exists(arxiv_corpus):
            n = extract_detailed_tables(arxiv_corpus)
            total_tables += n
            details["arxiv_tables"] = n

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[EXTRACT TABLES] Task COMPLETED. Tabelle estratte: {total_tables} ({details}). Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "tables_count": total_tables,
            "details": details
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[EXTRACT TABLES] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_extract_figures_task(task_id: str, source: str = "all"):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        pubmed_corpus = os.path.join(project_root, "pubmed", "corpus.json")
        if not os.path.exists(pubmed_corpus):
            pubmed_corpus = os.path.join(project_root, "corpus.json")
        arxiv_corpus = os.path.join(project_root, "arxiv", "corpus.json")

        total_figures = 0
        details = {}

        if source.lower() in ("all", "pubmed") and os.path.exists(pubmed_corpus):
            n = extract_detailed_figures(pubmed_corpus)
            total_figures += n
            details["pubmed_figures"] = n

        if source.lower() in ("all", "arxiv") and os.path.exists(arxiv_corpus):
            n = extract_detailed_figures(arxiv_corpus)
            total_figures += n
            details["arxiv_figures"] = n

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[EXTRACT FIGURES] Task COMPLETED. Figure estratte: {total_figures} ({details}). Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "figures_count": total_figures,
            "details": details
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[EXTRACT FIGURES] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_index_papers_task(task_id: str, source: str = "all"):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        pubmed_corpus = os.path.join(project_root, "pubmed", "corpus.json")
        if not os.path.exists(pubmed_corpus):
            pubmed_corpus = os.path.join(project_root, "corpus.json")
        arxiv_corpus = os.path.join(project_root, "arxiv", "corpus.json")

        indexer = DocumentIndexer()
        if source.lower() == "all":
            indexer.create_index(reset=True)
            if os.path.exists(pubmed_corpus):
                indexer.index_data(pubmed_corpus)
            if os.path.exists(arxiv_corpus):
                indexer.index_data(arxiv_corpus)
        elif source.lower() == "pubmed" and os.path.exists(pubmed_corpus):
            indexer.index_data(pubmed_corpus)
        elif source.lower() == "arxiv" and os.path.exists(arxiv_corpus):
            indexer.index_data(arxiv_corpus)

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[INDEX PAPERS] Task COMPLETED. Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "message": f"Indicizzazione paper ({source}) completata con successo."
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[INDEX PAPERS] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_index_tables_task(task_id: str, source: str = "all"):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        pubmed_tables = os.path.join(project_root, "pubmed", "tables_with_context.json")
        if not os.path.exists(pubmed_tables):
            pubmed_tables = os.path.join(project_root, "tables_with_context.json")
        arxiv_tables = os.path.join(project_root, "arxiv", "tables_with_context.json")

        indexer = TablesIndexer()
        if source.lower() == "all":
            indexer.create_index(reset=True)
            if os.path.exists(pubmed_tables):
                indexer.index_from_json(pubmed_tables)
            if os.path.exists(arxiv_tables):
                indexer.index_from_json(arxiv_tables)
        elif source.lower() == "pubmed" and os.path.exists(pubmed_tables):
            indexer.index_from_json(pubmed_tables)
        elif source.lower() == "arxiv" and os.path.exists(arxiv_tables):
            indexer.index_from_json(arxiv_tables)

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[INDEX TABLES] Task COMPLETED. Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "message": f"Indicizzazione tabelle ({source}) completata con successo."
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[INDEX TABLES] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_index_figures_task(task_id: str, source: str = "all"):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        pubmed_figures = os.path.join(project_root, "pubmed", "figures_with_context.json")
        if not os.path.exists(pubmed_figures):
            pubmed_figures = os.path.join(project_root, "figures_with_context.json")
        arxiv_figures = os.path.join(project_root, "arxiv", "figures_with_context.json")

        indexer = FiguresIndexer()
        if source.lower() == "all":
            indexer.create_index(reset=True)
            if os.path.exists(pubmed_figures):
                indexer.index_from_json(pubmed_figures)
            if os.path.exists(arxiv_figures):
                indexer.index_from_json(arxiv_figures)
        elif source.lower() == "pubmed" and os.path.exists(pubmed_figures):
            indexer.index_from_json(pubmed_figures)
        elif source.lower() == "arxiv" and os.path.exists(arxiv_figures):
            indexer.index_from_json(arxiv_figures)

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[INDEX FIGURES] Task COMPLETED. Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "message": f"Indicizzazione figure ({source}) completata con successo."
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[INDEX FIGURES] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_index_all_task(task_id: str):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        res = index_unified_corpora()

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[INDEX ALL] Task COMPLETED. Durata: {duration:.2f}s. Risultati: {res}")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = res

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[INDEX ALL] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


@app.get('/', response_class=HTMLResponse, tags=["Ricerca & UI"], summary="Home page", description="Pagina iniziale con form di ricerca.")
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name='index.html',
        context={
            'paper': None
        }
    )


@app.get('/search', response_class=HTMLResponse, tags=["Ricerca & UI"], summary="Cerca", description="Esegue la ricerca su paper, tabelle o figure con filtri e logica booleana.")
async def search(request: Request):
    
    raw_query_string = request.url.query
    parsed_params = parse_qs(raw_query_string, keep_blank_values=True)
    
    q = parsed_params.get('q', [None])[0]
    category = parsed_params.get('category', ['papers'])[0]
    source_filter = parsed_params.get('source', ['all'])[0].strip().lower()
    try:
        size = int(parsed_params.get('size', [10])[0])
    except ValueError:
        size = 10

    logics = parsed_params.get('logic', []) or parsed_params.get('logic[]', [])
    fields = parsed_params.get('field', []) or parsed_params.get('field[]', [])
    operators = parsed_params.get('operator', []) or parsed_params.get('operator[]', [])
    values = parsed_params.get('value', []) or parsed_params.get('value[]', [])

    try:
        size = int(parsed_params.get('size', [10])[0])
        size = max(1, min(size, 100))
    except (ValueError, TypeError):
        size = 10

    if category not in ['papers', 'tables', 'figures', 'images']:
        category = 'papers'

    if category == 'papers':
        index_name = "papers_index"
        default_fallback = "abstract"
    elif category == 'tables':
        index_name = "tables_index"
        default_fallback = "caption"
    else:
        index_name = "figures_index"
        default_fallback = "caption"

    body = {}
    query_display_parts = []

    if q and q.strip():
        if category == 'tables':
            search_fields = ["caption^5", "body^4", "mentions^2", "context_paragraphs^0.2"]
        elif category in ['figures', 'images']:
            search_fields = ["caption^5", "mentions^3", "context_paragraphs^0.2"]
        else:
            search_fields = ["title^3", "abstract^2", "full_text", "authors"]

        clean_q = q.strip()
        is_boolean = any(op in clean_q for op in [" AND ", " OR ", " NOT "])
        if is_boolean:
            body = {
                "query": {
                    "query_string": {
                        "query": clean_q,
                        "fields": search_fields,
                        "default_operator": "AND"
                    }
                },
                "size": size
            }
        else:
            body = {
                "query": {
                    "multi_match": {
                        "query": clean_q,
                        "fields": search_fields
                    }
                },
                "size": size
            }

    elif values:
        groups = []
        current_and_group = []
        must_nots = []

        keyword_fields = {"paper_id", "pmc_id", "pmid", "element_id", "url"}
        non_fuzzy_fields = {"paper_id", "pmc_id", "pmid", "element_id", "url", "table_number", "figure_number", "published"}

        for i in range(len(values)):
            val = values[i] if isinstance(values[i], str) else ""
            if not val or not val.strip():
                continue

            f = fields[i] if i < len(fields) else ""
            op = operators[i] if i < len(operators) else "match"
            log = logics[i].upper().strip() if i < len(logics) and logics[i] else ("WHERE" if i == 0 else "AND")

            if not f or f == "Campo...":
                if category == 'tables':
                    cond = {
                        "multi_match": {
                            "query": val.strip(),
                            "fields": ["caption^5", "body^4", "mentions^2", "context_paragraphs^0.2"]
                        }
                    }
                elif category in ['figures', 'images']:
                    cond = {
                        "multi_match": {
                            "query": val.strip(),
                            "fields": ["caption^5", "mentions^3", "context_paragraphs^0.2"]
                        }
                    }
                else:
                    cond = {
                        "multi_match": {
                            "query": val.strip(),
                            "fields": ["title^3", "abstract^2", "full_text", "authors"]
                        }
                    }
            else:
                search_field = f
                if search_field == "alt":
                    search_field = "caption"

                clean_val = val.strip()
                if op == "phrase":
                    cond = {"match_phrase": {search_field: clean_val}}
                elif op == "term":
                    if search_field in {"table_number", "figure_number"} and clean_val.isdigit():
                        cond = {"term": {search_field: int(clean_val)}}
                    else:
                        term_val = clean_val if search_field in keyword_fields else clean_val.lower()
                        cond = {"term": {search_field: term_val}}
                else:
                    cond = {"match": {search_field: clean_val}}

            field_label = f if (f and f != "Campo...") else "tutti i campi"
            query_display_parts.append(f"{log} {field_label} ({op}) '{val.strip()}'")

            if log == "NOT":
                must_nots.append(cond)
            elif log == "OR":
                if current_and_group:
                    groups.append(current_and_group)
                current_and_group = [cond]
            else:
                current_and_group.append(cond)

        if current_and_group:
            groups.append(current_and_group)

        if groups or must_nots:
            if len(groups) <= 1:
                bool_clause = {}
                if groups:
                    bool_clause["must"] = groups[0]
                elif must_nots:
                    bool_clause["must"] = [{"match_all": {}}]
                if must_nots:
                    bool_clause["must_not"] = must_nots
                body = {
                    "query": {
                        "bool": bool_clause
                    },
                    "size": size
                }
            else:
                should_clauses = []
                for g in groups:
                    if len(g) == 1:
                        should_clauses.append(g[0])
                    else:
                        should_clauses.append({"bool": {"must": g}})

                bool_clause = {
                    "should": should_clauses,
                    "minimum_should_match": 1
                }
                if must_nots:
                    bool_clause["must_not"] = must_nots
                body = {
                    "query": {
                        "bool": bool_clause
                    },
                    "size": size
                }

    if not body:
        return templates.TemplateResponse(
            request=request,
            name='index.html',
            context={
                'error': "Inserisci almeno un valore di ricerca valido."
            }
        )

    if body and source_filter in ['arxiv', 'pubmed']:
        inner_query = body.get("query", {"match_all": {}})
        if "bool" in inner_query:
            if "filter" in inner_query["bool"]:
                inner_query["bool"]["filter"].append({"term": {"source": source_filter}})
            else:
                inner_query["bool"]["filter"] = [{"term": {"source": source_filter}}]
        else:
            body["query"] = {
                "bool": {
                    "must": [inner_query],
                    "filter": [{"term": {"source": source_filter}}]
                }
            }

    try:
        es = get_elasticsearch()
        if category in ['tables', 'figures', 'images'] and 'min_score' not in body:
            body['min_score'] = 4.0
        res = es.search(index=index_name, body=body)
        hits = res['hits']['hits']
    except Exception as e:
        error_msg = f"Errore durante la ricerca in '{index_name}': {str(e)}.<br><small>Assicurati che il servizio Elasticsearch sia avviato in WSL e che i dati siano indicizzati.</small>"
        return templates.TemplateResponse(
            request=request,
            name='index.html',
            context={
                'error': error_msg
            }
        )

    query_display = q.strip() if (q and q.strip()) else " ".join(query_display_parts)
    if not query_display:
        query_display = "Filtri applicati"
    if source_filter in ['arxiv', 'pubmed']:
        query_display += f" [{source_filter.upper()}]"

    return templates.TemplateResponse(
        request=request,
        name='results.html',
        context={
            'hits': hits,
            'category': category,
            'query': query_display,
            'source': source_filter
        }
    )


@app.get('/paper/table/{table_path:path}', tags=["Redirects"], summary="Redirect tabella PMC", description="Reindirizza alla tabella su PubMed Central.")
async def redirect_paper_table(table_path: str):
    element_id = table_path.strip("/").split("/")[-1]
    logger.info(f"Fallback redirect requested for table element_id: {element_id}")
    try:
        es = get_elasticsearch()
        res = es.search(
            index="tables_index",
            body={
                "query": {
                    "bool": {
                        "should": [
                            {"term": {"element_id": element_id}},
                            {"term": {"table_id": element_id}},
                            {"wildcard": {"element_id": f"*{element_id}*"}}
                        ]
                    }
                },
                "size": 1
            }
        )
        if res['hits']['hits']:
            src = res['hits']['hits'][0]['_source']
            pmc_id = src.get('pmc_id')
            if pmc_id:
                return RedirectResponse(
                    url=f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc_id}/table/{element_id}/",
                    status_code=302
                )
    except Exception as e:
        logger.warning(f"Error redirecting table {table_path}: {e}")

    return RedirectResponse(url="https://pmc.ncbi.nlm.nih.gov/", status_code=302)


@app.get('/paper/figure/{figure_path:path}', tags=["Redirects"], summary="Redirect figura PMC", description="Reindirizza alla figura su PubMed Central.")
async def redirect_paper_figure(figure_path: str):
    fig_id = figure_path.strip("/").split("/")[-1]
    logger.info(f"Fallback redirect requested for figure: {fig_id}")
    try:
        es = get_elasticsearch()
        res = es.search(
            index="figures_index",
            body={
                "query": {
                    "bool": {
                        "should": [
                            {"term": {"figure_id": fig_id}},
                            {"term": {"element_id": fig_id}},
                            {"wildcard": {"figure_id": f"*{fig_id}*"}}
                        ]
                    }
                },
                "size": 1
            }
        )
        if res['hits']['hits']:
            src = res['hits']['hits'][0]['_source']
            pmc_id = src.get('pmc_id')
            if pmc_id:
                return RedirectResponse(
                    url=f"https://pmc.ncbi.nlm.nih.gov/articles/{pmc_id}/figure/{fig_id}/",
                    status_code=302
                )
    except Exception as e:
        logger.warning(f"Error redirecting figure {figure_path}: {e}")

    return RedirectResponse(url="https://pmc.ncbi.nlm.nih.gov/", status_code=302)


@app.get('/articles/{path:path}', tags=["Redirects"], summary="Redirect articolo PMC", description="Reindirizza i link relativi agli articoli su PubMed Central.")
async def redirect_pmc_articles(path: str):
    logger.info(f"Fallback redirecting /articles/{path} to PMC...")
    return RedirectResponse(url=f"https://pmc.ncbi.nlm.nih.gov/articles/{path}", status_code=302)


@app.get('/pmc/articles/{path:path}', tags=["Redirects"], summary="Redirect articolo PMC", description="Reindirizza i link relativi /pmc/articles/ a PubMed Central.")
async def redirect_pmc_full_articles(path: str):
    logger.info(f"Fallback redirecting /pmc/articles/{path} to PMC...")
    return RedirectResponse(url=f"https://pmc.ncbi.nlm.nih.gov/articles/{path}", status_code=302)


@app.get('/instance/{path:path}', tags=["Redirects"], summary="Redirect istanze PMC", description="Reindirizza link interni PMC.")
async def redirect_pmc_instance(path: str):
    logger.info(f"Fallback redirecting /instance/{path} to PMC...")
    return RedirectResponse(url=f"https://pmc.ncbi.nlm.nih.gov/articles/instance/{path}", status_code=302)


@app.get('/about/{path:path}', tags=["Redirects"], summary="Redirect About PMC", description="Reindirizza alla pagina About di PMC.")
@app.get('/about', tags=["Redirects"], summary="Redirect About PMC", description="Reindirizza alla pagina About di PMC.")
async def redirect_pmc_about(path: str = ""):
    logger.info(f"Fallback redirecting /about/{path} to PMC...")
    suffix = f"/{path}" if path else ""
    return RedirectResponse(url=f"https://pmc.ncbi.nlm.nih.gov/about{suffix}", status_code=302)


@app.get('/pmc/about/{path:path}', tags=["Redirects"], summary="Redirect About PMC", description="Reindirizza alla pagina About di PMC.")
@app.get('/pmc/about', tags=["Redirects"], summary="Redirect About PMC", description="Reindirizza alla pagina About di PMC.")
async def redirect_pmc_about_nested(path: str = ""):
    logger.info(f"Fallback redirecting /pmc/about/{path} to PMC...")
    suffix = f"/{path}" if path else ""
    return RedirectResponse(url=f"https://pmc.ncbi.nlm.nih.gov/about{suffix}", status_code=302)


@app.get('/pdf/{path:path}', tags=["Redirects"], summary="Redirect PDF arXiv", description="Reindirizza al PDF originale su arXiv.")
async def redirect_arxiv_pdf(path: str):
    clean_path = path.strip('/')
    if not clean_path.endswith('.pdf'):
        clean_path += '.pdf'
    logger.info(f"Redirecting /pdf/{path} to https://arxiv.org/pdf/{clean_path}")
    return RedirectResponse(url=f"https://arxiv.org/pdf/{clean_path}", status_code=302)


@app.get('/abs/{path:path}', tags=["Redirects"], summary="Redirect Abstract arXiv", description="Reindirizza alla pagina abstract su arXiv.")
async def redirect_arxiv_abs(path: str):
    clean_path = path.strip('/')
    logger.info(f"Redirecting /abs/{path} to https://arxiv.org/abs/{clean_path}")
    return RedirectResponse(url=f"https://arxiv.org/abs/{clean_path}", status_code=302)


@app.get('/paper/{paper_id}', response_class=HTMLResponse, tags=["Ricerca & UI"], summary="Visualizza paper", description="Mostra il testo HTML del paper ed evidenzia tabelle o figure cercate.")
async def view_paper(
        request: Request,
        paper_id: str,
        query: Optional[str] = Query(None),
        category: Optional[str] = Query(None),
        table: Optional[int] = Query(None),
        figure: Optional[str] = Query(None),
        figure_id: Optional[str] = Query(None),
        element_id: Optional[str] = Query(None)
):
    resolved_figure = figure or figure_id
    logger.info(f"Requesting paper ID: {paper_id} | table: {table} | figure: {resolved_figure} | element_id: {element_id}")

    es = get_elasticsearch()
    paper = None

    try:
        res = es.search(
            index="papers_index",
            body={
                "query": {
                    "bool": {
                        "should": [
                            {"term": {"_id": paper_id}},
                            {"term": {"paper_id": paper_id}},
                            {"term": {"pmc_id": paper_id}},
                            {"term": {"pmc_id": paper_id.upper()}},
                            {"term": {"arxiv_id": paper_id}},
                            {"prefix": {"paper_id": paper_id}},
                            {"wildcard": {"pmc_id": f"*{paper_id}*"}}
                        ]
                    }
                },
                "size": 1
            }
        )

        if res['hits']['hits']:
            paper = res['hits']['hits'][0]['_source']
        else:
            logger.warning(f"Paper ID {paper_id} not found directly in papers_index.")

    except Exception as e:
        logger.error(f"Errore ricerca ES: {e}")

    if not paper:
        error_msg = f"Paper '{paper_id}' non trovato nell'indice. <br> <small>Prova a reindicizzare i papers.</small>"
        logger.error(f"Paper definitively not found: {paper_id}")
        return templates.TemplateResponse(
            request=request,
            name='index.html',
            context={
                'error': error_msg
            }
        )

    return templates.TemplateResponse(
        request=request,
        name='paper.html',
        context={
            'paper': paper,
            'query': query,
            'category': category,
            'table_number': table,
            'figure_id': resolved_figure,
            'element_id': element_id
        }
    )


@app.post("/api/tasks/corpus/build", tags=["Pipeline & Tasks"], summary="Download corpus", description="Scarica i paper da PubMed o arXiv.")
async def build_corpus(
    background_tasks: BackgroundTasks,
    source: str = Query("all", description="Sorgente: 'all', 'arxiv' o 'pubmed'")
):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "corpus/build",
        "source": source,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_build_corpus_task, task_id, source)

    return JSONResponse({
        "status": "accepted",
        "message": f"Task corpus build ({source}) avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/extract/tables", tags=["Pipeline & Tasks"], summary="Estrai tabelle", description="Estrae tabelle e contesti dai paper.")
async def extract_tables(
    background_tasks: BackgroundTasks,
    source: str = Query("all", description="Sorgente: 'all', 'arxiv' o 'pubmed'")
):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "extract/tables",
        "source": source,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_extract_tables_task, task_id, source)

    return JSONResponse({
        "status": "accepted",
        "message": f"Task estrazione tabelle ({source}) avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/extract/figures", tags=["Pipeline & Tasks"], summary="Estrai figure", description="Estrae figure e didascalie dai paper.")
async def extract_figures(
    background_tasks: BackgroundTasks,
    source: str = Query("all", description="Sorgente: 'all', 'arxiv' o 'pubmed'")
):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "extract/figures",
        "source": source,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_extract_figures_task, task_id, source)

    return JSONResponse({
        "status": "accepted",
        "message": f"Task estrazione figure ({source}) avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/index/papers", tags=["Pipeline & Tasks"], summary="Indicizza paper", description="Indicizza i paper su Elasticsearch.")
async def index_papers(
    background_tasks: BackgroundTasks,
    source: str = Query("all", description="Sorgente: 'all', 'arxiv' o 'pubmed'")
):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "index/papers",
        "source": source,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_index_papers_task, task_id, source)

    return JSONResponse({
        "status": "accepted",
        "message": f"Task indicizzazione paper ({source}) avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/index/tables", tags=["Pipeline & Tasks"], summary="Indicizza tabelle", description="Indicizza le tabelle su Elasticsearch.")
async def index_tables(
    background_tasks: BackgroundTasks,
    source: str = Query("all", description="Sorgente: 'all', 'arxiv' o 'pubmed'")
):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "index/tables",
        "source": source,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_index_tables_task, task_id, source)

    return JSONResponse({
        "status": "accepted",
        "message": f"Task indicizzazione tabelle ({source}) avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/index/figures", tags=["Pipeline & Tasks"], summary="Indicizza figure", description="Indicizza le figure su Elasticsearch.")
async def index_figures(
    background_tasks: BackgroundTasks,
    source: str = Query("all", description="Sorgente: 'all', 'arxiv' o 'pubmed'")
):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "index/figures",
        "source": source,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_index_figures_task, task_id, source)

    return JSONResponse({
        "status": "accepted",
        "message": f"Task indicizzazione figure ({source}) avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/index/all", tags=["Pipeline & Tasks"], summary="Indicizza tutto", description="Indicizza tutti i paper, tabelle e figure di entrambe le fonti.")
async def index_all_unified(background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "index/all",
        "source": "all",
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_index_all_task, task_id)

    return JSONResponse({
        "status": "accepted",
        "message": "Task indicizzazione unificata (tutti i corpora, tabelle e figure) avviato in background",
        "task_id": task_id
    })


@app.get("/api/tasks/status", tags=["Pipeline & Tasks"], summary="Stato dataset", description="Controlla se i file JSON esistono su disco.")
async def get_tasks_status():
    base_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    base_dir = os.path.abspath(base_dir)

    files_status = {
        "pubmed/corpus.json": os.path.exists(os.path.join(base_dir, "pubmed", "corpus.json")),
        "pubmed/tables_with_context.json": os.path.exists(os.path.join(base_dir, "pubmed", "tables_with_context.json")),
        "pubmed/figures_with_context.json": os.path.exists(os.path.join(base_dir, "pubmed", "figures_with_context.json")),
        "arxiv/corpus.json": os.path.exists(os.path.join(base_dir, "arxiv", "corpus.json")),
        "arxiv/tables_with_context.json": os.path.exists(os.path.join(base_dir, "arxiv", "tables_with_context.json")),
        "arxiv/figures_with_context.json": os.path.exists(os.path.join(base_dir, "arxiv", "figures_with_context.json"))
    }

    return JSONResponse({
        "status": "success",
        "files": files_status
    })


@app.get("/api/tasks/{task_id}", tags=["Pipeline & Tasks"], summary="Stato task", description="Controlla lo stato di avanzamento di un task in background.")
async def get_task_by_id(task_id: str):
    if task_id not in task_status:
        return JSONResponse({
            "status": "not_found",
            "message": f"Task '{task_id}' non trovato."
        }, status_code=404)
    return JSONResponse(task_status[task_id])