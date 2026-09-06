import time
import requests
import feedparser
import re
from urllib.parse import quote
from typing import List, Optional
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
        preprocessa l'HTML per fixare immagini, formule, CSS e altri elementi.
        """
        soup = BeautifulSoup(html, 'lxml')

        for script in soup.find_all('script', src=True):
            if 'mathjax' in script['src'].lower():
                script.decompose()

        head = soup.find('head')
        if head:
            mathjax_config = soup.new_tag('script')
            mathjax_config.string = """
            window.MathJax = {
                tex: {inlineMath: [['$', '$'], ['\\(', '\\)']]},
                svg: {fontCache: 'global'}
            };
            """
            head.insert(0, mathjax_config)

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
                    img['src'] = f"https://arxiv.org{src}"
                elif src.startswith(f"{paper_id}/"):
                    img['src'] = f"https://arxiv.org/html/{src}"
                else:
                    img['src'] = f"https://arxiv.org/html/{paper_id}/{src}"

            data_src = img.get('data-src', '')
            if data_src and not data_src.startswith('http'):
                if data_src.startswith('/'):
                    img['data-src'] = f"https://arxiv.org{data_src}"
                elif data_src.startswith(f"{paper_id}/"):
                    img['data-src'] = f"https://arxiv.org/html/{data_src}"
                else:
                    img['data-src'] = f"https://arxiv.org/html/{paper_id}/{data_src}"

        for obj in soup.find_all(['object', 'embed']):
            attr = 'data' if obj.name == 'object' else 'src'
            val = obj.get(attr, '')
            if val and not val.startswith('http') and not val.startswith('//'):
                if val.startswith('/'):
                    obj[attr] = f"https://arxiv.org{val}"
                elif val.startswith(f"{paper_id}/"):
                    obj[attr] = f"https://arxiv.org/html/{val}"
                else:
                    obj[attr] = f"https://arxiv.org/html/{paper_id}/{val}"

        for link in soup.find_all('link', href=True):
            href = link['href']
            if not href.startswith('http') and not href.startswith('//'):
                if href.startswith('/'):
                    link['href'] = f"https://arxiv.org{href}"
                elif href.startswith(f"{paper_id}/"):
                    link['href'] = f"https://arxiv.org/html/{href}"
                else:
                    link['href'] = f"https://arxiv.org/{href}"

        for script in soup.find_all('script', src=True):
            src = script['src']
            if not src.startswith('http') and not src.startswith('//'):
                if src.startswith('/'):
                    script['src'] = f"https://arxiv.org{src}"
                elif src.startswith(f"{paper_id}/"):
                    script['src'] = f"https://arxiv.org/html/{src}"
                else:
                    script['src'] = f"https://arxiv.org/{src}"

        for tag in soup.find_all(['header', 'footer', 'nav', 'dialog']):
            tag.decompose()

        junk_classes = [
            'ds-announcement', 'arxiv-html-header', 'arxiv-html-footer', 'ds-site-footer',
            'ltx_page_navbar', 'fixed-buttons-container', 'modal', 'modal-form', 'modal-dialog',
            'modal-header', 'modal-body', 'modal-footer'
        ]
        for class_name in junk_classes:
            for el in soup.find_all(class_=class_name):
                el.decompose()

        for link in soup.find_all('link', rel='stylesheet'):
            link.decompose()

        for a in soup.find_all('a', href=True):
            href = a['href'].strip()
            if href.startswith('/pdf/') or href.startswith('pdf/'):
                clean = href.lstrip('/').replace('pdf/', '')
                a['href'] = f"https://arxiv.org/pdf/{clean}.pdf"
                a['target'] = "_blank"
            elif href.startswith('/abs/') or href.startswith('abs/'):
                clean = href.lstrip('/').replace('abs/', '')
                a['href'] = f"https://arxiv.org/abs/{clean}"
                a['target'] = "_blank"

        main_content = (
            soup.find('article')
            or soup.find(class_='ltx_document')
            or soup.find(class_='ltx_page_content')
            or soup.find('main')
        )
        if main_content:
            return str(main_content)

        return str(soup)

    def search(self, query: str, limit: Optional[int] = None) -> List[Paper]:
        """
        Scarica i risultati disponibili per la query, ordinati per data recente
        (per massimizzare la disponibilità HTML ar5iv/arXiv).
        """
        papers = []
        start = 0
        batch_size = min(200, limit) if limit else 200

        while True:
            encoded_query = quote(query)
            url = (
                f"{self.API_URL}?search_query={encoded_query}&start={start}"
                f"&max_results={batch_size}&sortBy=submittedDate&sortOrder=descending"
            )
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
                        title=entry.title.strip().replace("\n", " "),
                        authors=[a.name for a in entry.authors],
                        abstract=entry.summary.strip().replace("\n", " "),
                        published=entry.published,
                        updated=entry.updated,
                        html_url=f"https://arxiv.org/html/{arxiv_id}",
                        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}.pdf"
                    )
                )
                if limit and len(papers) >= limit:
                    return papers

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

        time.sleep(config.DELAY)
