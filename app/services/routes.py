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

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'templates'))
templates = Jinja2Templates(directory=template_dir)

app = FastAPI()
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


def run_build_corpus_task(task_id: str):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        if config.SOURCE.lower() == "pubmed":
            logger.info("Initializing PubMed source...")
            source = PubmedSource()
        else:
            logger.info("Initializing ArXiv source...")
            source = ArxivSource()

        query = config.QUERY
        downloader = CorpusDownloader(source, max_workers=1, delay=1.5)

        logger.info(f"Avvio download corpus con query: {query} (Source: {config.SOURCE})")
        papers = downloader.build(query)

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        output_file = os.path.join(project_root, "corpus.json")

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
                "doi": p.doi
            }
            for p in papers
        ]

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(papers_data, f, indent=2, ensure_ascii=False)

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[CORPUS BUILD] Task COMPLETED. Paper salvati: {len(papers)}. Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "papers_count": len(papers),
            "output_file": output_file
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[CORPUS BUILD] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_extract_tables_task(task_id: str):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        corpus_file = os.path.join(project_root, "corpus.json")

        if not os.path.exists(corpus_file):
            logger.error("File corpus.json non trovato.")
            task_status[task_id]["status"] = "failed"
            task_status[task_id]["completed_at"] = datetime.now().isoformat()
            task_status[task_id]["error"] = "File corpus.json non trovato. Esegui prima /api/tasks/corpus/build"
            return

        num_tables = extract_detailed_tables(corpus_file)

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[EXTRACT TABLES] Task COMPLETED. Tabelle estratte: {num_tables}. Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "tables_count": num_tables
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[EXTRACT TABLES] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_extract_figures_task(task_id: str):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        corpus_file = os.path.join(project_root, "corpus.json")

        if not os.path.exists(corpus_file):
            logger.error("File corpus.json non trovato.")
            task_status[task_id]["status"] = "failed"
            task_status[task_id]["completed_at"] = datetime.now().isoformat()
            task_status[task_id]["error"] = "File corpus.json non trovato. Esegui prima /api/tasks/corpus/build"
            return

        total = extract_detailed_figures(corpus_file)

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[EXTRACT FIGURES] Task COMPLETED. Figure estratte: {total}. Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "figures_count": total
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[EXTRACT FIGURES] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_index_papers_task(task_id: str):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        corpus_file = os.path.join(project_root, "corpus.json")

        if not os.path.exists(corpus_file):
            logger.error("File corpus.json non trovato.")
            task_status[task_id]["status"] = "failed"
            task_status[task_id]["completed_at"] = datetime.now().isoformat()
            task_status[task_id]["error"] = "File corpus.json non trovato. Esegui prima /api/tasks/corpus/build"
            return

        indexer = DocumentIndexer()
        indexer.create_index(reset=True)
        indexer.index_data(corpus_file)

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[INDEX PAPERS] Task COMPLETED. Indicizzazione completata. Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "message": "Indicizzazione paper completata"
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[INDEX PAPERS] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_index_tables_task(task_id: str):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        tables_file = os.path.join(project_root, "tables_with_context.json")

        if not os.path.exists(tables_file):
            logger.error("File tables_with_context.json non trovato.")
            task_status[task_id]["status"] = "failed"
            task_status[task_id]["completed_at"] = datetime.now().isoformat()
            task_status[task_id]["error"] = "File tables_with_context.json non trovato. Esegui prima /api/tasks/extract/tables"
            return

        indexer = TablesIndexer()
        indexer.create_index(reset=True)
        indexer.index_from_json(tables_file)

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[INDEX TABLES] Task COMPLETED. Indicizzazione tabelle completata. Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "message": "Indicizzazione tabelle completata"
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[INDEX TABLES] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


def run_index_figures_task(task_id: str):
    start_dt = datetime.now()
    try:
        task_status[task_id]["status"] = "running"
        task_status[task_id]["started_at"] = start_dt.isoformat()

        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        figures_file = os.path.join(project_root, "figures_with_context.json")

        if not os.path.exists(figures_file):
            logger.error("File figures_with_context.json non trovato.")
            task_status[task_id]["status"] = "failed"
            task_status[task_id]["completed_at"] = datetime.now().isoformat()
            task_status[task_id]["error"] = "File figures_with_context.json non trovato. Esegui prima /api/tasks/extract/figures"
            return

        indexer = FiguresIndexer()
        indexer.create_index(reset=True)
        indexer.index_from_json(figures_file)

        duration = (datetime.now() - start_dt).total_seconds()
        logger.success(f"[INDEX FIGURES] Task COMPLETED. Indicizzazione figure completata. Durata: {duration:.2f}s")

        task_status[task_id]["status"] = "completed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["result"] = {
            "message": "Indicizzazione figure completata"
        }

    except Exception as e:
        duration = (datetime.now() - start_dt).total_seconds()
        logger.error(f"[INDEX FIGURES] Errore dopo {duration:.2f}s: {e}")
        task_status[task_id]["status"] = "failed"
        task_status[task_id]["completed_at"] = datetime.now().isoformat()
        task_status[task_id]["error"] = str(e)


@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name='index.html',
        context={
            'paper': None
        }
    )


@app.get('/search', response_class=HTMLResponse)
async def search(request: Request):
    from urllib.parse import parse_qs, urlparse
    
    raw_query_string = request.url.query
    parsed_params = parse_qs(raw_query_string, keep_blank_values=True)
    
    q = parsed_params.get('q', [None])[0]
    category = parsed_params.get('category', ['papers'])[0]
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
            search_fields = ["caption^2", "body"]
        elif category in ['figures', 'images']:
            search_fields = ["caption"]
        else:
            search_fields = ["title^2", "abstract", "full_text", "authors"]

        body = {
            "query": {
                "multi_match": {
                    "query": q.strip(),
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
                            "fields": ["caption^2", "body"]
                        }
                    }
                elif category in ['figures', 'images']:
                    cond = {
                        "multi_match": {
                            "query": val.strip(),
                            "fields": ["caption"]
                        }
                    }
                else:
                    cond = {
                        "multi_match": {
                            "query": val.strip(),
                            "fields": ["title^2", "abstract", "full_text", "authors"]
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

    try:
        es = get_elasticsearch()
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

    return templates.TemplateResponse(
        request=request,
        name='results.html',
        context={
            'hits': hits,
            'category': category,
            'query': query_display
        }
    )


@app.get('/paper/table/{table_path:path}')
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


@app.get('/paper/figure/{figure_path:path}')
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


@app.get('/articles/{path:path}')
async def redirect_pmc_articles(path: str):
    logger.info(f"Fallback redirecting /articles/{path} to PMC...")
    return RedirectResponse(url=f"https://pmc.ncbi.nlm.nih.gov/articles/{path}", status_code=302)


@app.get('/pmc/articles/{path:path}')
async def redirect_pmc_full_articles(path: str):
    logger.info(f"Fallback redirecting /pmc/articles/{path} to PMC...")
    return RedirectResponse(url=f"https://pmc.ncbi.nlm.nih.gov/articles/{path}", status_code=302)


@app.get('/instance/{path:path}')
async def redirect_pmc_instance(path: str):
    logger.info(f"Fallback redirecting /instance/{path} to PMC...")
    return RedirectResponse(url=f"https://pmc.ncbi.nlm.nih.gov/articles/instance/{path}", status_code=302)


@app.get('/about/{path:path}')
@app.get('/about')
async def redirect_pmc_about(path: str = ""):
    logger.info(f"Fallback redirecting /about/{path} to PMC...")
    suffix = f"/{path}" if path else ""
    return RedirectResponse(url=f"https://pmc.ncbi.nlm.nih.gov/about{suffix}", status_code=302)


@app.get('/pmc/about/{path:path}')
@app.get('/pmc/about')
async def redirect_pmc_about_nested(path: str = ""):
    logger.info(f"Fallback redirecting /pmc/about/{path} to PMC...")
    suffix = f"/{path}" if path else ""
    return RedirectResponse(url=f"https://pmc.ncbi.nlm.nih.gov/about{suffix}", status_code=302)


@app.get('/pdf/{path:path}')
async def redirect_arxiv_pdf(path: str):
    clean_path = path.strip('/')
    if not clean_path.endswith('.pdf'):
        clean_path += '.pdf'
    logger.info(f"Redirecting /pdf/{path} to https://arxiv.org/pdf/{clean_path}")
    return RedirectResponse(url=f"https://arxiv.org/pdf/{clean_path}", status_code=302)


@app.get('/abs/{path:path}')
async def redirect_arxiv_abs(path: str):
    clean_path = path.strip('/')
    logger.info(f"Redirecting /abs/{path} to https://arxiv.org/abs/{clean_path}")
    return RedirectResponse(url=f"https://arxiv.org/abs/{clean_path}", status_code=302)


@app.get('/paper/{paper_id}', response_class=HTMLResponse)
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


@app.post("/api/tasks/corpus/build")
async def build_corpus(background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "corpus/build",
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_build_corpus_task, task_id)

    return JSONResponse({
        "status": "accepted",
        "message": "Task avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/extract/tables")
async def extract_tables(background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "extract/tables",
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_extract_tables_task, task_id)

    return JSONResponse({
        "status": "accepted",
        "message": "Task avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/extract/figures")
async def extract_figures(background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "extract/figures",
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_extract_figures_task, task_id)

    return JSONResponse({
        "status": "accepted",
        "message": "Task avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/index/papers")
async def index_papers(background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "index/papers",
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_index_papers_task, task_id)

    return JSONResponse({
        "status": "accepted",
        "message": "Task avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/index/tables")
async def index_tables(background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "index/tables",
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_index_tables_task, task_id)

    return JSONResponse({
        "status": "accepted",
        "message": "Task avviato in background",
        "task_id": task_id
    })


@app.post("/api/tasks/index/figures")
async def index_figures(background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    task_status[task_id] = {
        "task_type": "index/figures",
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }

    background_tasks.add_task(run_index_figures_task, task_id)

    return JSONResponse({
        "status": "accepted",
        "message": "Task avviato in background",
        "task_id": task_id
    })


@app.get("/api/tasks/status")
async def get_tasks_status():
    base_dir = os.path.join(os.path.dirname(__file__), "..", "..")
    base_dir = os.path.abspath(base_dir)

    files_status = {
        "corpus.json": os.path.exists(os.path.join(base_dir, "corpus.json")),
        "tables_with_context.json": os.path.exists(os.path.join(base_dir, "tables_with_context.json")),
        "figures_with_context.json": os.path.exists(os.path.join(base_dir, "figures_with_context.json"))
    }

    return JSONResponse({
        "status": "success",
        "files": files_status
    })


@app.get("/api/tasks/{task_id}")
async def get_task_by_id(task_id: str):
    if task_id not in task_status:
        return JSONResponse({
            "status": "not_found",
            "message": f"Task '{task_id}' non trovato."
        }, status_code=404)
    return JSONResponse(task_status[task_id])