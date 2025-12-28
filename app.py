from flask import Flask, render_template, request
from elasticsearch import Elasticsearch
import urllib3
from config import config

app = Flask(__name__)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

es = Elasticsearch(
    config.HOST_ELASTIC,
    basic_auth=("elastic", config.PASSWORD_ELASTC),
    verify_certs=False  # Necessario perché siamo in locale senza certificati veri
)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search')
def search():
    query = request.args.get('q')
    category = request.args.get('category', 'papers') # Default: papers
    
    if not query:
        return render_template('index.html')

    if category == 'papers':
        index_name = "papers_index"
        search_fields = ["title^2", "abstract", "authors", "full_text"]
    elif category == 'tables':
        index_name = "tables_index"
        search_fields = ["caption^3", "body", "mentions", "context_paragraphs"]
    else: # figures
        index_name = "figures_index"
        search_fields = ["caption^3", "mentions", "context_paragraphs"]

    body = {
        "query": {
            "multi_match": {
                "query": query,
                "fields": search_fields,
                "type": "best_fields"
            }
        },
        "size": 20
    }

    res = es.search(index=index_name, body=body)
    hits = res['hits']['hits']
    
    return render_template('results.html', hits=hits, category=category, query=query)

if __name__ == '__main__':
    app.run(debug=True, port=5000)