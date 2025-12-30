import json
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from loguru import logger

# 1. Definizione dei termini non informativi (Stop-words)
STOP_WORDS = set([
    'il', 'lo', 'la', 'i', 'gli', 'le', 'di', 'a', 'da', 'in', 'con', 'su', 
    'per', 'tra', 'fra', 'and', 'the', 'of', 'with', 'figure', 'figura', 
    'image', 'immagine', 'shown', 'shows', 'illustrates', 'presents'
])

def clean_text(text):
    """Pulisce il testo da spazi bianchi eccessivi e newline."""
    return re.sub(r'\s+', ' ', text).strip()

def get_informative_terms(text):
    """Estrae solo termini rilevanti (> 3 lettere e non stop-words)."""
    words = re.findall(r'\b\w{4,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS]

class FigureContextExtractor:
    def __init__(self, json_file):
        self.json_file = json_file
        self.output_dir = "../extracted_figures"
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        # Header per evitare blocchi durante il download delle immagini
        self.headers = {'User-Agent': 'Mozilla/5.0'}

    def extract(self):
        with open(self.json_file, 'r', encoding='utf-8') as f:
            papers = json.load(f)

        all_figures_data = []

        for paper in papers:
            if not paper.get('html_content'):
                continue
            
            soup = BeautifulSoup(paper['html_content'], 'lxml')
            paper_id = paper['paper_id']
            # Estraiamo i paragrafi per l'analisi del contesto
            paragraphs = [clean_text(p.get_text()) for p in soup.find_all('p') if len(p.get_text()) > 30]
            
            # Cerchiamo i contenitori standard delle figure (tag <figure> o div con classe figure)
            figure_wrappers = soup.find_all(['figure', 'div'], class_=re.compile(r'figure', re.I))
            
            for i, wrapper in enumerate(figure_wrappers):
                img_tag = wrapper.find('img')
                if not img_tag: 
                    continue
                
                # 1. Estrazione URL originale
                src = img_tag.get('src')
                img_url = urljoin(paper.get('html_url', ''), src)
                
                # 2. Estrazione CAPTION
                caption_tag = wrapper.find(['figcaption', 'span', 'div'], class_=re.compile(r'caption', re.I))
                caption = clean_text(caption_tag.get_text()) if caption_tag else f"Figure {i+1}"
                
                # 3. Estrazione MENTIONS (Paragrafi che citano la figura)
                # Identifichiamo il numero della figura (es. Fig. 1 -> "1")
                label_match = re.search(r'(?:Figure|Fig\.|Figura)\s*(\d+[\.\d+]*)', caption, re.I)
                label = label_match.group(1) if label_match else str(i+1)
                
                # Cerchiamo nel testo i riferimenti alla figura
                mentions = [p for p in paragraphs if re.search(rf'\b(Figure|Fig\.|Figura)\s*{label}\b', p, re.I)]
                
                # 4. Estrazione CONTEXT PARAGRAPHS (Basata su termini informativi)
                keywords = get_informative_terms(caption)
                context_paragraphs = []
                for p in paragraphs:
                    if p in mentions: 
                        continue # Evitiamo di duplicare le mentions nel contesto
                    
                    # Verifichiamo se il paragrafo contiene almeno 2 termini della caption
                    matches = [kw for kw in keywords if kw in p.lower()]
                    if len(matches) >= 2:
                        context_paragraphs.append(p)

                # Creazione del pacchetto dati per la figura
                figure_data = {
                    "paper_id": paper_id,
                    "paper_title": paper.get('title', ''),  # Titolo del paper
                    "figure_id": f"fig_{i}",
                    "url": img_url,
                    "caption": caption,
                    "mentions": mentions,
                    "context_paragraphs": context_paragraphs,
                    "local_filename": f"{paper_id.replace('/', '_')}_fig_{i}.png"
                }
                all_figures_data.append(figure_data)
                
            logger.info(f"Paper {paper_id}: Analizzate {len(figure_wrappers)} figure con dati di contesto.")

        # Salvataggio del database strutturato in JSON
        output_path = os.path.join(os.path.dirname(self.json_file), "figures_with_context.json")
        with open(output_path, "w", encoding='utf-8') as f:
            json.dump(all_figures_data, f, indent=4)

        return len(all_figures_data)

if __name__ == "__main__":
    extractor = FigureContextExtractor("../corpus.json")
    total = extractor.extract()
    print(f"\n--- ESTRAZIONE COMPLETATA ---")
    print(f"Totale figure processate: {total}")
    print(f"I dati di contesto sono pronti in: 'figures_with_context.json'")