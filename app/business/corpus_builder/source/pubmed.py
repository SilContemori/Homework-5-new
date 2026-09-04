import time
import requests
import xml.etree.ElementTree as ET
import re
import shutil
import subprocess
from datetime import datetime
from typing import List

from bs4 import BeautifulSoup
from loguru import logger
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from app.business.corpus_builder.models import Paper
from app.business.corpus_builder.source.base import DocumentSource
from app.config.config import config


class PubmedSource(DocumentSource):
    """Source per l'accesso ai paper di PubMed"""

    API_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    FETCH_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(config.HEADERS)
        retry = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def search(self, query: str) -> List[Paper]:
        """esegue la ricerca su PubMed con paginazione."""
        papers = []
        retstart = 0
        batch_size = 200

        if "free full text[filter]" not in query.lower():
            open_access_query = f"({query}) AND free full text[filter]"
        else:
            open_access_query = query

        logger.info("Starting PubMed search | query={}", open_access_query)

        while True:
            search_params = {
                'db': 'pubmed',
                'term': open_access_query,
                'retmax': batch_size,
                'retmode': 'xml',
                'retstart': retstart
            }
            if config.NCBI_API_KEY:
                search_params['api_key'] = config.NCBI_API_KEY

            try:
                logger.debug("Fetching IDs | retstart={}", retstart)

                search_response = self.session.get(
                    self.API_URL,
                    params=search_params,
                    timeout=30
                )
                search_response.raise_for_status()

                search_root = ET.fromstring(search_response.content)
                ids = [id_elem.text for id_elem in search_root.findall('.//Id')]

                if not ids:
                    logger.debug("No more IDs found | ending pagination")
                    break

                fetch_params = {
                    'db': 'pubmed',
                    'id': ','.join(ids),
                    'retmode': 'xml'
                }
                if config.NCBI_API_KEY:
                    fetch_params['api_key'] = config.NCBI_API_KEY

                fetch_response = self.session.get(
                    self.FETCH_URL,
                    params=fetch_params,
                    timeout=30
                )
                fetch_response.raise_for_status()
                fetch_root = ET.fromstring(fetch_response.content)
                logger.debug("Fetching details for {} papers", len(ids))

                for article in fetch_root.findall('.//PubmedArticle'):
                    try:
                        paper = self._parse_pubmed_article(article)
                        if paper:
                            papers.append(paper)
                    except Exception as e:
                        logger.warning("Error parsing single PubMed article: {}", e)

                if len(ids) < batch_size:
                    break

                retstart += batch_size
                time.sleep(config.DELAY)

            except requests.RequestException as e:
                logger.error("PubMed request failed | error={}", e)
                break
            except ET.ParseError as e:
                logger.error("Failed to parse XML response | error={}", e)
                break

        logger.info("PubMed search completed | total_papers={}", len(papers))
        return papers

    def _parse_pubmed_article(self, article: ET.Element) -> Paper:
        """ Estrae i dati da un singolo elemento XML <PubmedArticle>."""
        pmid = article.findtext('.//MedlineCitation/PMID', default="")

        title = article.findtext('.//ArticleTitle', default="")

        authors = []
        for author in article.findall('.//AuthorList/Author'):
            last_name = author.findtext('LastName', default="")
            fore_name = author.findtext('ForeName', default="")
            if last_name or fore_name:
                authors.append(f"{fore_name} {last_name}".strip())

        abstract_texts = article.findall('.//Abstract/AbstractText')
        abstract = " ".join([elem.text for elem in abstract_texts if elem.text])

        pub_date = article.find('.//Journal/JournalIssue/PubDate')
        year = pub_date.findtext('Year') if pub_date is not None else None
        month = pub_date.findtext('Month') if pub_date is not None else "01"
        day = pub_date.findtext('Day') if pub_date is not None else "01"

        if year:
            try:
                published = datetime.strptime(f"{year}-{month}-{day}", "%Y-%b-%d")
            except ValueError:
                try:
                    published = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
                except ValueError:
                    published = datetime.strptime(f"{year}", "%Y")
        else:
            published = datetime.now()

        doi = ""
        pmc_id = ""

        article_ids = article.findall('.//PubmedData/ArticleIdList/ArticleId')
        for aid in article_ids:
            id_type = aid.get('IdType')
            if id_type == 'doi' and not doi:
                doi = aid.text or ""
            elif id_type == 'pmc' and not pmc_id:
                raw_pmc = aid.text or ""
                pmc_id = raw_pmc if raw_pmc.startswith("PMC") else f"PMC{raw_pmc}"

        return Paper(
            paper_id=pmid,
            title=title.strip(),
            authors=authors,
            abstract=abstract.strip(),
            published=published,
            updated=published,
            html_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            pdf_url="",
            doi=doi,
            pmc_id=pmc_id
        )

    def fetch_html(self, paper: Paper) -> None:
        """
        Scarica l'HTML completo da PMC e risolve le immagini (PMC Moderno).
        Usa logica avanzata per data-srcset (risolve definitivamente i rettangoli bianchi).
        """
        if not paper.pmc_id:
            logger.debug("Skipping HTML fetch | paper_id={} | reason=no_pmc_id", paper.paper_id)
            return

        url = f"https://pmc.ncbi.nlm.nih.gov/articles/{paper.pmc_id}/"
        logger.debug("Fetching PMC HTML | pmc_id={} | url={}", paper.pmc_id, url)

        html_text = None
        try:
            r = self.session.get(url, timeout=20)
            if r.status_code == 200 and "recaptcha" not in r.text.lower() and "challengepage" not in r.text.lower():
                html_text = r.text
            else:
                logger.warning(
                    "Session fetch warning for {} (status={}, captcha={}) | trying curl fallback",
                    paper.pmc_id,
                    r.status_code,
                    "recaptcha" in r.text.lower() or "challengepage" in r.text.lower()
                )
        except Exception as e:
            logger.warning("Session fetch failed for {}: {} | trying curl fallback", paper.pmc_id, e)

        if not html_text:
            curl_bin = shutil.which("curl.exe") or shutil.which("curl")
            if curl_bin:
                try:
                    res = subprocess.run(
                        [curl_bin, "-s", "-L", "-A", config.HEADERS.get("User-Agent", ""), url],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="ignore",
                        timeout=30
                    )
                    if res.returncode == 0 and res.stdout and "recaptcha" not in res.stdout.lower() and "challengepage" not in res.stdout.lower():
                        html_text = res.stdout
                except Exception as e:
                    logger.debug("curl fallback failed for {}: {}", paper.pmc_id, e)

        if not html_text:
            logger.warning("Failed to fetch PMC page | pmc_id={}", paper.pmc_id)
            return

        try:
            soup = BeautifulSoup(html_text, 'lxml')

            for tag in soup.find_all(['header', 'footer', 'nav']):
                tag.decompose()

            pmc_junk_classes = [
                'main-header', 'top-links', 'jig-ncbi-pager', 'pmc-sidebar',
                'fm-meta', 'bottom-content', 'footer-content', 'accesskeys-container',
                'skip-nav', 'top-nav'
            ]
            for class_name in pmc_junk_classes:
                for el in soup.find_all(class_=class_name):
                    el.decompose()

            for img in soup.find_all('img'):
                real_src = img.get('data-srcset') or img.get('original') or img.get('src')

                if not real_src:
                    continue

                real_src = real_src.split(',')[0].split(' ')[0].strip()

                if not real_src.startswith('http'):
                    if real_src.startswith('/'):
                        img['src'] = f"https://www.ncbi.nlm.nih.gov{real_src}"
                    else:
                        img['src'] = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{paper.pmc_id}/{real_src}"
                else:
                    img['src'] = real_src

                if 'data-src' in img.attrs: del img['data-src']
                if 'data-srcset' in img.attrs: del img['data-srcset']

            for script in soup.find_all('script'):
                script.decompose()

            main_content = soup.find('main') or soup.find('article')
            if main_content:
                paper.html_content = str(main_content)
            elif not ("recaptcha" in soup.text.lower() or "challenge" in soup.text.lower()):
                paper.html_content = str(soup)
            else:
                logger.warning("PMC page is a captcha challenge | pmc_id={}", paper.pmc_id)
                paper.html_content = None
                return

            logger.info("PMC HTML fetched successfully | pmc_id={}", paper.pmc_id)

        except Exception as e:
            logger.error("Error parsing PMC HTML for {}: {}", paper.pmc_id, e)