from fastapi import FastAPI, Request, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.templating import Jinja2Templates
from elasticsearch import Elasticsearch
import urllib3
import os
import json
import uuid
from datetime import datetime
from typing import Dict
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
        downloader = CorpusDownloader(source, max_workers=5, delay=3.0)

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

        # CORRETTO: Chiamata alla funzione, non alla classe
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


# frontend
@app.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        'index.html',
        {
            'request': request,
            'paper': None
        }
    )


@app.get('/search', response_class=HTMLResponse)
async def search(
        request: Request,
        q: str = Query(None),
        category: str = Query('papers')
):
    if not q:
        return templates.TemplateResponse('index.html', {'request': request})

    if category == 'papers':
        index_name = "papers_index"
        search_fields = ["title^2", "abstract", "authors", "html_content"]
    elif category == 'tables':
        index_name = "tables_index"
        search_fields = ["caption^3", "body", "mentions", "context_paragraphs"]
    else:
        index_name = "figures_index"
        search_fields = ["caption^3", "mentions", "context_paragraphs"]

    body = {
        "query": {
            "multi_match": {
                "query": q,
                "fields": search_fields,
                "type": "best_fields"
            }
        },
        "size": 20
    }

    try:
        es = get_elasticsearch()
        res = es.search(index=index_name, body=body)
        hits = res['hits']['hits']
    except Exception as e:
        error_msg = f"Errore di connessione a Elasticsearch: {str(e)}"
        return templates.TemplateResponse(
            'index.html',
            {
                'request': request,
                'error': error_msg
            }
        )

    return templates.TemplateResponse(
        'results.html',
        {
            'request': request,
            'hits': hits,
            'category': category,
            'query': q
        }
    )


@app.get('/paper/{paper_id}', response_class=HTMLResponse)
async def view_paper(
        request: Request,
        paper_id: str,
        query: str = Query(None),
        category: str = Query(None),
        table: int = Query(None),
        figure_id: str = Query(None)
):
    """mostra l'HTML completo del paper"""

    logger.info(f"Requesting paper with ID: {paper_id}")

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
                            {"term": {"arxiv_id": paper_id}}
                        ]
                    }
                },
                "size": 1
            }
        )

        if res['hits']['hits']:
            paper = res['hits']['hits'][0]['_source']
        else:
            logger.warning(f"Paper ID {paper_id} not found directly. Trying fallback...")

    except Exception as e:
        logger.error(f"Errore ricerca ES: {e}")

    if not paper:
        error_msg = f"Paper '{paper_id}' non trovato nell'indice. <br> <small>Prova a reindicizzare i papers.</small>"
        logger.error(f"Paper definitively not found: {paper_id}")
        return templates.TemplateResponse(
            'index.html',
            {
                'request': request,
                'error': error_msg
            }
        )

    return templates.TemplateResponse(
        'paper.html',
        {
            'request': request,
            'paper': paper,
            'query': query,
            'category': category,
            'table_number': table,
            'figure_id': figure_id
        }
    )

# avviare i task

@app.post("/api/tasks/corpus/build")
async def build_corpus(background_tasks: BackgroundTasks):
    """costruzione del corpus scaricando i paper."""
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