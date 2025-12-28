import json
from config import QUERY
from corpus_builder.downloader import CorpusDownloader
from corpus_builder.source.arxiv import ArxivSource

if __name__ == "__main__":
    source = ArxivSource()
    downloader = CorpusDownloader(source)

    corpus = downloader.build(QUERY)

    with open("corpus.json", "w", encoding="utf-8") as f:
        json.dump([paper.__dict__ for paper in corpus],
                  f, indent=2, ensure_ascii=False)

    print(f"Creato corpus con {len(corpus)} documenti")
