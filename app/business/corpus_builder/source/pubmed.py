import time
import requests
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from typing import List

from bs4 import BeautifulSoup
from loguru import logger

from app.business.corpus_builder.models import Paper
from app.business.corpus_builder.source.base import DocumentSource
from app.config.config import config


class PubmedSource(DocumentSource):
    """Source per l'accesso ai paper di PubMed"""

    API_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    FETCH_URL: str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

    def search(self, query: str) -> List[Paper]:
        """esegue la ricerca su PubMed con paginazione."""
        papers = []
        retstart = 0
        batch_size = 200

        open_access_query = f"{query} AND free full text[filter]"

        logger.info("Starting PubMed search | query={}", open_access_query)

        while True:
            search_params = {
                'db': 'pubmed',
                'term': open_access_query,
                'retmax': batch_size,
                'retmode': 'xml',
                'retstart': retstart
            }

            try:
                logger.debug("Fetching IDs | retstart={}", retstart)

                search_response = requests.get(
                    self.API_URL,
                    params=search_params,
                    headers=config.HEADERS,
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

                fetch_response = requests.get(
                    self.FETCH_URL,
                    params=fetch_params,
                    headers=config.HEADERS,
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
        # PMID
        pmid_elem = article.find('.//PMID')
        pmid = pmid_elem.text if pmid_elem is not None else ""

        title_elem = article.find('.//ArticleTitle')
        title = title_elem.text if title_elem is not None else ""


        authors = []
        for author in article.findall('.//Author'):
            ln_elem = author.find('LastName')
            fn_elem = author.find('ForeName')
            inits_elem = author.find('Initials')

            if ln_elem is not None and inits_elem is not None:
                authors.append(f"{ln_elem.text} {inits_elem.text}")
            elif ln_elem is not None and fn_elem is not None:
                authors.append(f"{ln_elem.text} {fn_elem.text}")

        abstract_texts = article.findall('.//AbstractText')
        abstract = " ".join([t.text for t in abstract_texts if t.text])

        pub_date_elem = article.find('.//PubDate')
        pub_year = "1900"
        if pub_date_elem is not None:
            year_elem = pub_date_elem.find('Year')
            medline_date_elem = pub_date_elem.find('MedlineDate')
            if year_elem is not None:
                pub_year = year_elem.text
            elif medline_date_elem is not None:
                match = re.search(r'\d{4}', medline_date_elem.text)
                if match:
                    pub_year = match.group()

        try:
            published = datetime.strptime(pub_year, '%Y')
        except ValueError:
            published = datetime.now()

        doi_elem = article.find('.//ELocationID[@EIdType="doi"]')
        doi = doi_elem.text if doi_elem is not None else ""

        pmc_id = ""
        pmc_elem = article.find('.//ArticleIdList/ArticleId[@IdType="pmc"]')
        if pmc_elem is not None:
            pmc_id = pmc_elem.text

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

        url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{paper.pmc_id}/"
        logger.debug("Fetching PMC HTML | pmc_id={} | url={}", paper.pmc_id, url)

        try:
            r = requests.get(url, headers=config.HEADERS, timeout=20)
            if r.status_code != 200:
                logger.warning("Failed to fetch PMC page | status={}", r.status_code)
                return

            soup = BeautifulSoup(r.text, 'lxml')

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


            main_content = soup.find('main')
            if main_content:
                paper.html_content = str(main_content)
            else:
                paper.html_content = str(soup)

            logger.info("PMC HTML fetched successfully | pmc_id={}", paper.pmc_id)

        except Exception as e:
            logger.error("Error fetching PMC HTML for {}: {}", paper.pmc_id, e)