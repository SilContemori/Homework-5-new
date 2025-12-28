import time
import requests
import feedparser
from urllib.parse import quote
from typing import List
from loguru import logger

from corpus_builder.models import Paper
from corpus_builder.source.base import DocumentSource


class ArxivSource(DocumentSource):

    API_URL = "http://export.arxiv.org/api/query"
    HEADERS = {"User-Agent": "AcademicSearchProject/1.0"}
    DELAY = 3

    # def search(self, query: str) -> List[Paper]:
    #     try:
    #         encoded_query = quote(query)
    #         url = f"{self.API_URL}?search_query={encoded_query}&start=0"
    #         logger.debug(f"Search {url}")
    #         response = requests.get(url, headers=self.HEADERS, timeout=30)
    #         response.raise_for_status()
    #
    #         feed = feedparser.parse(response.text)
    #
    #         papers = []
    #         for entry in feed.entries:
    #             arxiv_id = entry.id.split("/abs/")[1]
    #
    #             papers.append(
    #                 Paper(
    #                     paper_id=arxiv_id,
    #                     title=entry.title.strip(),
    #                     authors=[a.name for a in entry.authors],
    #                     abstract=entry.summary.strip(),
    #                     published=getattr(entry, "published", None),
    #                     updated=getattr(entry, "updated", None),
    #                     html_url=f"https://ar5iv.org/html/{arxiv_id}",
    #                     pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf"
    #                 )
    #             )
    #
    #         return papers
    #
    #     except Exception as e:
    #         print(f"Errore durante il fetch da arXiv: {e}")
    #         return []

    def search(self, query: str) -> List[Paper]:
        """
        Scarica tutti i risultati disponibili per la query, facendo paginazione.
        """
        papers = []
        start = 0
        batch_size = 200  # massimo consigliato da arXiv
        while True:
            encoded_query = quote(query)
            url = f"{self.API_URL}?search_query={encoded_query}&start={start}&max_results={batch_size}"
            response = requests.get(url, headers=self.HEADERS, timeout=30)
            response.raise_for_status()
            feed = feedparser.parse(response.text)
            if not feed.entries:
                break

            for entry in feed.entries:
                arxiv_id = entry.id.split("/abs/")[1]
                papers.append(
                    Paper(
                        paper_id=arxiv_id,
                        title=entry.title.strip(),
                        authors=[a.name for a in entry.authors],
                        abstract=entry.summary.strip(),
                        published=entry.published,
                        updated=entry.updated,
                        html_url=f"https://ar5iv.org/html/{arxiv_id}",
                        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    )
                )
            start += batch_size
            time.sleep(self.DELAY)  # per non essere bannati

        return papers

    def fetch_html(self, paper: Paper) -> None:
        if not paper.html_url:
            logger.debug(
                "Skipping HTML fetch | paper_id={} | reason=no_html_url",
                paper.paper_id
            )
            return

        logger.debug(
            "Fetching HTML content | paper_id={} | url={}",
            paper.paper_id,
            paper.html_url
        )

        try:
            start_ts = time.time()
            r = requests.get(paper.html_url, headers=self.HEADERS, timeout=20)
            elapsed = time.time() - start_ts

            if r.status_code == 200 and "<html" in r.text.lower():
                paper.html_content = r.text
                logger.debug(
                    "HTML fetch OK | paper_id={} | elapsed={:.2f}s",
                    paper.paper_id,
                    elapsed
                )
            else:
                paper.html_content = None
                logger.warning(
                    "HTML fetch invalid content | paper_id={} | status={}",
                    paper.paper_id,
                    r.status_code
                )

        except requests.RequestException as e:
            paper.html_content = None
            logger.error(
                "HTML fetch failed | paper_id={} | error={}",
                paper.paper_id,
                e
            )

        logger.debug(
            "Sleeping after fetch | seconds={}",
            self.DELAY
        )
        time.sleep(self.DELAY)
