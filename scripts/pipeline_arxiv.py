import argparse
import os
import sys
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from loguru import logger

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)

from app.config.config import config
from app.business.corpus_builder.source.arxiv import ArxivSource
from app.utils.format_date import format_date
from app.business.extractor.table_context_extractor import extract_detailed_tables
from app.business.extractor.figure_context_extractor import extract_detailed_figures

TRACK_QUERIES = [
    ("Group A (Entity Resolution)", 'ti:"entity resolution" OR abs:"entity resolution" OR ti:"entity matching" OR abs:"entity matching"'),
    ("Group B (Text-to-SQL)", 'ti:"text-to-sql" OR abs:"text-to-sql" OR ti:"natural language to sql" OR abs:"natural language to sql"'),
    ("Group C (Speech Recognition)", 'ti:"automatic speech recognition" OR abs:"automatic speech recognition" OR ti:"speech to text" OR abs:"speech to text"'),
    ("Group D (Text to Speech)", 'ti:"text to speech" OR abs:"text to speech"'),
    ("Studenti Lavoratori (Query Processing/Optimization)", 'ti:"query processing" OR abs:"query processing" OR ti:"query optimization" OR abs:"query optimization"'),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}


def fetch_candidates_for_query(query_str: str, max_candidates: int = 200):
    candidates = []
    start = 0
    batch_size = min(100, max_candidates)

    while start < max_candidates:
        encoded = urllib.parse.quote(query_str)
        url = (
            f"https://export.arxiv.org/api/query?search_query={encoded}&start={start}"
            f"&max_results={batch_size}&sortBy=submittedDate&sortOrder=descending"
        )
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                xml_data = resp.read()
            tree = ET.fromstring(xml_data)
            entries = tree.findall("{http://www.w3.org/2005/Atom}entry")
            if not entries:
                break

            for entry in entries:
                id_elem = entry.find("{http://www.w3.org/2005/Atom}id")
                if id_elem is None or "/abs/" not in id_elem.text:
                    continue
                arxiv_id = id_elem.text.split("/abs/")[1]
                title_elem = entry.find("{http://www.w3.org/2005/Atom}title")
                title = title_elem.text.strip().replace("\n", " ") if title_elem is not None else ""

                authors = []
                for a in entry.findall("{http://www.w3.org/2005/Atom}author"):
                    name_el = a.find("{http://www.w3.org/2005/Atom}name")
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                summary_elem = entry.find("{http://www.w3.org/2005/Atom}summary")
                abstract = summary_elem.text.strip().replace("\n", " ") if summary_elem is not None else ""

                pub_elem = entry.find("{http://www.w3.org/2005/Atom}published")
                published = pub_elem.text if pub_elem is not None else ""

                upd_elem = entry.find("{http://www.w3.org/2005/Atom}updated")
                updated = upd_elem.text if upd_elem is not None else ""

                candidates.append({
                    "paper_id": arxiv_id,
                    "title": title,
                    "authors": authors,
                    "abstract": abstract,
                    "published": format_date(published),
                    "updated": format_date(updated),
                    "html_url": f"https://arxiv.org/html/{arxiv_id}",
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                    "pmc_id": "",
                    "doi": "",
                    "source": "arxiv"
                })

            start += len(entries)
            if len(entries) < batch_size:
                break
            time.sleep(2.0)
        except Exception as e:
            logger.error(f"Errore query arXiv API: {e}")
            break

    return candidates


def download_html(candidate: dict):
    paper_id = candidate["paper_id"]
    url = candidate["html_url"]
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 200 and "<html" in r.text.lower():
            candidate["html_content"] = ArxivSource._preprocess_html(r.text, paper_id)
            return candidate
    except Exception:
        pass
    return None


def run_arxiv_pipeline(
    query: str = None,
    target_papers: int = 500,
    max_workers: int = 6
):
    logger.info(f"Avvio pipeline arXiv (target HTML: {target_papers})")

    seen_ids = set()
    all_candidates = []

    if query:
        logger.info(f"Ricerca candidati per query personalizzata: {query}")
        all_candidates = fetch_candidates_for_query(query, max_candidates=target_papers * 2)
    else:
        for group_name, query_str in TRACK_QUERIES:
            if len(all_candidates) >= target_papers * 2:
                break
            logger.info(f"Ricerca candidati per {group_name}...")
            cands = fetch_candidates_for_query(query_str, max_candidates=160)
            added = 0
            for c in cands:
                if c["paper_id"] not in seen_ids:
                    seen_ids.add(c["paper_id"])
                    all_candidates.append(c)
                    added += 1
            logger.info(f"Aggiunti {added} candidati da {group_name}. Totale: {len(all_candidates)}")
            time.sleep(1.0)

    logger.info(f"Download HTML parallelo ({max_workers} workers) per {len(all_candidates)} candidati...")
    valid_papers = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_html, c): c["paper_id"] for c in all_candidates}
        for future in as_completed(futures):
            res = future.result()
            if res:
                valid_papers.append(res)
                if len(valid_papers) % 25 == 0 or len(valid_papers) >= target_papers:
                    logger.info(f"Progress: {len(valid_papers)}/{target_papers} HTML scaricati")
            if len(valid_papers) >= target_papers:
                break

    arxiv_dir = os.path.join(project_root, "arxiv")
    os.makedirs(arxiv_dir, exist_ok=True)
    corpus_file = os.path.join(arxiv_dir, "corpus.json")

    with open(corpus_file, "w", encoding="utf-8") as f:
        json.dump(valid_papers, f, indent=2, ensure_ascii=False)
    logger.info(f"Salvati {len(valid_papers)} paper validi in {corpus_file}")

    num_tables = extract_detailed_tables(corpus_file)
    logger.info(f"Tabelle estratte da arXiv: {num_tables}")
    num_figures = extract_detailed_figures(corpus_file)
    logger.info(f"Figure estratte da arXiv: {num_figures}")

    logger.success("Pipeline arXiv completata con successo.")
    return len(valid_papers), num_tables, num_figures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline ArXiv")
    parser.add_argument("--query", "-q", default=None, help="Query per arXiv")
    parser.add_argument("--limit", "-l", type=int, default=500, help="Numero target di paper con HTML reale")
    parser.add_argument("--workers", "-w", type=int, default=6, help="Numero worker concorrenti")
    args = parser.parse_args()
    run_arxiv_pipeline(query=args.query, target_papers=args.limit, max_workers=args.workers)
