import time
import requests
import feedparser
import re
from urllib.parse import quote
from typing import List
from loguru import logger
from bs4 import BeautifulSoup

from app.business.corpus_builder.models import Paper
from app.business.corpus_builder.source.base import DocumentSource
from app.config.config import config


class ArxivSource(DocumentSource):

    API_URL = "http://export.arxiv.org/api/query"

    @staticmethod
    def _preprocess_html(html: str, paper_id: str) -> str:
        """
        Preprocessa l'HTML per fixare immagini, formule, CSS e altri elementi.
        """
        soup = BeautifulSoup(html, 'lxml')

        for script in soup.find_all('script', src=True):
            if 'mathjax' in script['src'].lower():
                script.decompose()

        head = soup.find('head')
        if head:
            mathjax_config = soup.new_tag('script')
            mathjax_config.string = '''
            window.MathJax = {
                tex: {inlineMath: [['$', '$'], ['\\(', '\\)']]},
                svg: {fontCache: 'global'}
            };
            '''
            head.insert(0, mathjax_config)

            # MathJax v3
            mathjax = soup.new_tag(
                'script',
                src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js",
                attrs={"async": "async"}
            )
            head.insert(1, mathjax)

        for img in soup.find_all('img'):
            src = img.get('src', '')
            if src and not src.startswith('http') and not src.startswith('//'):
                if src.startswith('/'):
                    img['src'] = f"https://ar5iv.org{src}"
                else:
                    img['src'] = f"https://ar5iv.org/html/{paper_id}/{src}"

            data_src = img.get('data-src', '')
            if data_src and not data_src.startswith('http'):
                if data_src.startswith('/'):
                    img['data-src'] = f"https://ar5iv.org{data_src}"
                else:
                    img['data-src'] = f"https://ar5iv.org/html/{paper_id}/{data_src}"

        for link in soup.find_all('link', href=True):
            href = link['href']
            if not href.startswith('http') and not href.startswith('//'):
                if href.startswith('/'):
                    link['href'] = f"https://ar5iv.org{href}"
                else:
                    link['href'] = f"https://ar5iv.org/{href}"

        for script in soup.find_all('script', src=True):
            src = script['src']
            if not src.startswith('http') and not src.startswith('//'):
                if src.startswith('/'):
                    script['src'] = f"https://ar5iv.org{src}"
                else:
                    script['src'] = f"https://ar5iv.org/{src}"

        for svg in soup.find_all('svg'):
            for svg_img in svg.find_all('image', href=True):
                href = svg_img['href']
                if not href.startswith('http') and not href.startswith('//'):
                    if href.startswith('/'):
                        svg_img['href'] = f"https://ar5iv.org{href}"
                    else:
                        svg_img['href'] = f"https://ar5iv.org/html/{paper_id}/{href}"

        return str(soup)

    def search(self, query: str) -> List[Paper]:
        """
        Scarica tutti i risultati disponibili per la query, facendo paginazione.
        """
        papers = []
        start = 0
        batch_size = 200
        while True:
            encoded_query = quote(query)
            url = f"{self.API_URL}?search_query={encoded_query}&start={start}&max_results={batch_size}"
            response = requests.get(url, headers=config.HEADERS, timeout=30)
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
            time.sleep(config.DELAY)

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
            r = requests.get(paper.html_url, headers=config.HEADERS, timeout=20)
            elapsed = time.time() - start_ts

            if r.status_code == 200 and "<html" in r.text.lower():
                # Preprocessa l'HTML per fixare immagini, formule e CSS
                paper.html_content = self._preprocess_html(r.text, paper.paper_id)
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
            config.DELAY
        )
        time.sleep(config.DELAY)