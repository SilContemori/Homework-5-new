from typing import List
from app.business.corpus_builder.models import Paper
from app.business.corpus_builder.source.base import DocumentSource
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import time


class CorpusDownloader:

    def __init__(self, source: DocumentSource, max_workers: int = 5, delay: float = 0.0):
        """
        max_workers: numero di thread paralleli
        delay: delay tra le richieste per evitare ban (solo per thread singoli)
        """
        self.source = source
        self.max_workers = max_workers
        self.delay = delay

    def build(self, query: str) -> List[Paper]:
        papers = self.source.search(query)

        def fetch(paper):
            self.source.fetch_html(paper)
            if self.delay > 0:
                time.sleep(self.delay)
            return paper

        results = []
        if self.max_workers <= 1:
            for p in tqdm(papers, total=len(papers), desc="Fetching HTML"):
                self.source.fetch_html(p)
                results.append(p)
                if self.delay > 0:
                    time.sleep(self.delay)
            return results

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(fetch, p) for p in papers]

            for f in tqdm(as_completed(futures), total=len(futures), desc="Fetching HTML"):
                results.append(f.result())

        return results
