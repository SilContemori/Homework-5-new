import json
import os
import re
from bs4 import BeautifulSoup
from loguru import logger

from app.utils.clean_figure import clean_text, get_informative_terms


def extract_figures_from_html(paper_html: str, paper_id: str):
    """Estrae le figure dall'HTML e restituisce una lista di dizionari validi"""
    soup = BeautifulSoup(paper_html, 'lxml')

    candidates = []

    wrappers = soup.find_all(['figure', 'div', 'p'], class_=re.compile(r'fig|image', re.I))
    for w in wrappers:
        img = w.find('img')
        if img:
            candidates.append({'element': w, 'type': 'wrapper'})

    all_images = soup.find_all('img')
    for img in all_images:
        if img.find_parents(['figure', 'div', 'p'], class_=re.compile(r'fig|image', re.I)):
            continue
        candidates.append({'element': img, 'type': 'standalone_img'})

    valid_figures = []
    current_index = 0

    for item in candidates:
        element = item['element']

        if item['type'] == 'standalone_img':
            img_tag = element
            caption_wrapper = element.parent
        else:
            img_tag = element.find('img')
            caption_wrapper = element

        if not img_tag:
            continue

        src = img_tag.get('src')
        if not src or 'placeholder' in src.lower() or len(src) < 5:
            continue

        caption_text = ""
        if item['type'] == 'wrapper':
            caption_tag = caption_wrapper.find(['figcaption', 'div', 'span', 'p'], class_=re.compile(r'caption', re.I))
            if caption_tag:
                caption_text = clean_text(caption_tag.get_text())

        if not caption_text:
            parent = caption_wrapper
            if parent:
                text = clean_text(parent.get_text())
                if 'Figure' in text or 'Fig.' in text:
                    caption_text = text

        if not caption_text:
            caption_text = f"Figure {current_index + 1}"

        valid_figures.append({
            'figure_id': f"fig_{current_index}",
            'caption': caption_text,
            'url': src
        })

        current_index += 1

    return valid_figures


def extract_detailed_figures(json_file: str) -> int:
    """Estrae figure + contesto dai paper in JSON corpus"""
    with open(json_file, 'r', encoding='utf-8') as f:
        papers = json.load(f)

    all_extracted_data = []

    for paper in papers:
        html_content = paper.get('html_content')
        if not html_content:
            continue

        soup = BeautifulSoup(html_content, 'lxml')
        # PMC_ID > PAPER_ID
        paper_id = paper.get('pmc_id') or paper.get('paper_id')

        paper_title = paper.get('title', '')
        pmc_id = paper.get('pmc_id')

        paragraphs = [clean_text(p.get_text()) for p in soup.find_all('p') if len(p.get_text()) > 20]

        figures_data = extract_figures_from_html(html_content, paper_id)

        for i, fig in enumerate(figures_data):
            caption = fig['caption']
            url = fig['url']

            label_match = re.search(r'(?:Figure|Fig)\s*(\d+[\.\d+]*)', caption, re.I)
            label = label_match.group(1) if label_match else str(i + 1)

            mentions = [p for p in paragraphs if re.search(rf'\b(Figure|Fig)\s*{label}\b', p, re.I)]

            keywords = list(set(get_informative_terms(caption)))[:10]

            context_paragraphs = []
            for p in paragraphs:
                if p in mentions:
                    continue
                paragraph_words = set(re.findall(r'\w{4,}', p.lower()))
                if len(set(keywords) & paragraph_words) >= 1:
                    context_paragraphs.append(p)

            all_extracted_data.append({
                "figure_id": fig['figure_id'],
                "paper_id": paper_id,  # non è un id numerico ma è tipo PMC12744729
                "pmc_id": pmc_id,
                "paper_title": paper_title,
                "url": url,
                "caption": caption,
                "mentions": mentions,
                "context_paragraphs": context_paragraphs
            })

        logger.info(f"Paper {paper_id}: estratte {len(figures_data)} figure con contesto (PMC: {pmc_id}).")

    output_path = os.path.join(os.path.dirname(json_file), "figures_with_context.json")
    with open(output_path, "w", encoding='utf-8') as f:
        json.dump(all_extracted_data, f, indent=4, ensure_ascii=False)

    return len(all_extracted_data)


if __name__ == "__main__":
    json_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "corpus.json"
    )
    num = extract_detailed_figures(json_path)
    print(f"\nOPERAZIONE COMPLETATA: Estratte {num} figure complete di contesto.")
    print("I dati sono pronti nel file 'figures_with_context.json' per essere indicizzati.")