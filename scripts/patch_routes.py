import re

path = '/home/valerio/project/Homework-5-new/app/services/routes.py'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update run_build_corpus_task pubmed_file path
old_task = '''            pubmed_source = PubmedSource()
            downloader = CorpusDownloader(pubmed_source, max_workers=1, delay=1.5)
            pubmed_papers = downloader.build(config.QUERY_PUBMED)
            pubmed_file = os.path.join(project_root, 
