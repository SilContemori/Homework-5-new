import json
import os
import re
from bs4 import BeautifulSoup
from loguru import logger

from app.utils.clean_figure import clean_text, get_informative_terms
from app.config.constants import STOP_WORDS


def fix_url(url: str, paper_id: str) -> str:
    """Risolve URL relativi di immagini o oggetti SVG verso arXiv o URL assoluti"""
    if not url:
        return ""
    url = url.strip()
    if url.startswith('http://') or url.startswith('https://') or url.startswith('//'):
        return url
    if url.startswith('/'):
        return f"https://arxiv.org{url}"
    if paper_id and url.startswith(f"{paper_id}/"):
        return f"https://arxiv.org/html/{url}"
    if paper_id:
        return f"https://arxiv.org/html/{paper_id}/{url}"
    return url


def get_figure_caption(element) -> str:
    cap_tags = element.find_all(['figcaption', 'caption'], recursive=False)
    if not cap_tags:
        for c in element.find_all(['figcaption', 'caption', 'p', 'div'], class_=re.compile(r'caption|ltx_caption|fig-caption', re.I)):
            parent_fig = c.find_parent('figure')
            if parent_fig == element:
                cap_tags.append(c)

    if not cap_tags:
        cap_tags = element.find_all(['figcaption', 'caption'])

    for ct in cap_tags:
        txt = clean_text(ct.get_text(' ', strip=True))
        if re.search(r'\b(?:Figure|Fig)\s*\d+', txt, re.I):
            return txt

    if cap_tags:
        return clean_text(cap_tags[0].get_text(' ', strip=True))

    head = element.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'div', 'p', 'span'],
                        class_=re.compile(r'obj_head|fig-label|image-label|ltx_caption', re.I))
    if head:
        return clean_text(head.get_text(' ', strip=True))

    return ""


def get_figure_visual(element) -> str:
    img = element.find('img')
    if img:
        src = img.get('src') or img.get('data-src') or ""
        if src and 'placeholder' not in src.lower() and len(src) > 4:
            return src

    obj = element.find('object')
    if obj:
        data = obj.get('data') or obj.get('src') or ""
        if data and len(data) > 4:
            return data

    emb = element.find('embed')
    if emb:
        src = emb.get('src') or ""
        if src and len(src) > 4:
            return src

    return ""


def extract_figures_from_html(paper_html: str, paper_id: str):
    soup = BeautifulSoup(paper_html, 'lxml')
    raw_candidates = soup.find_all(['figure', 'div', 'p'], class_=re.compile(r'\b(?:ltx_figure|fig|image|figure-box)\b', re.I))
    
    valid_figures = []
    seen_elements = set()
    current_index = 0

    for fig in raw_candidates:
        if fig in seen_elements:
            continue

        cls_str = " ".join(fig.get('class', []) if isinstance(fig.get('class'), list) else [str(fig.get('class', ''))]).lower()
        if any(bad in cls_str for bad in ['ltx_table', 'table-wrap', 'table', 'algorithm']):
            continue

        child_figs = [cf for cf in fig.find_all('figure') if cf != fig]
        has_independent_children = False
        for cf in child_figs:
            cap_child = get_figure_caption(cf)
            if re.search(r'\b(?:Figure|Fig)\s*\d+', cap_child, re.I):
                has_independent_children = True
                break
        if has_independent_children:
            continue

        parent_fig = fig.find_parent('figure')
        if parent_fig:
            parent_direct_caps = [clean_text(c.get_text(' ', strip=True))
                                  for c in parent_fig.find_all(['figcaption', 'caption'], recursive=False)]
            if any(re.search(r'\b(?:Figure|Fig)\s*\d+', c, re.I) for c in parent_direct_caps):
                continue

        visual_url = get_figure_visual(fig)
        if not visual_url:
            continue

        caption = get_figure_caption(fig)
        if re.match(r'^(?:Table|Tabella|Algorithm|Alg)\b', caption, re.I):
            continue

        junk_patterns = ['logo', 'banner', 'icon', 'button', 'badge', 'avatar', 'advertisement', 'sprite']
        if any(junk in visual_url.lower() for junk in junk_patterns):
            continue

        num_match = re.search(r'\b(?:Figure|Fig)\s*(\d+)', caption, re.I)
        fig_num = int(num_match.group(1)) if num_match else (current_index + 1)

        if not caption:
            caption = f"Figure {fig_num}"

        element_id = fig.get('id') or ""
        resolved_url = fix_url(visual_url, paper_id)

        valid_figures.append({
            'figure_id': f"fig_{current_index}",
            'figure_number': fig_num,
            'element_id': element_id,
            'caption': caption,
            'url': resolved_url
        })
        seen_elements.add(fig)
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
        paper_id = paper.get('pmc_id') or paper.get('paper_id') or "unknown"
        pmc_id = paper.get('pmc_id', '')
        pmid = paper.get('paper_id', '')
        paper_title = paper.get('title', '')

        paragraphs = [clean_text(p.get_text()) for p in soup.find_all('p') if len(p.get_text()) > 20]

        figures_data = extract_figures_from_html(html_content, paper_id)

        for fig in figures_data:
            caption = fig['caption']
            url = fig['url']

            label_match = re.search(r'(?:Figure|Fig)\s*(\d+[\.\d+]*)', caption, re.I)
            label = label_match.group(1) if label_match else str(fig['figure_number'])

            mentions = [p for p in paragraphs if re.search(rf'\b(Figure|Fig)\s*{label}\b', p, re.I)]

            raw_kw = get_informative_terms(caption)
            keywords = [w for w in set(raw_kw) if len(w) > 4 and w.lower() not in STOP_WORDS][:8]

            context_paragraphs = []
            if keywords:
                for p in paragraphs:
                    if p in mentions:
                        continue
                    paragraph_words = set(re.findall(r'\b[a-zA-Z]{5,}\b', p.lower()))
                    if len(set(keywords) & paragraph_words) >= 2:
                        context_paragraphs.append(p)
                    if len(context_paragraphs) >= 5:
                        break

            all_extracted_data.append({
                "figure_id": fig['figure_id'],
                "figure_number": fig['figure_number'],
                "element_id": fig.get('element_id', ''),
                "paper_id": paper_id,
                "pmc_id": pmc_id,
                "pmid": pmid,
                "paper_title": paper_title,
                "url": url,
                "caption": caption,
                "mentions": mentions,
                "context_paragraphs": context_paragraphs
            })

        if figures_data:
            logger.info(f"Paper {paper_id}: estratte {len(figures_data)} figure con contesto.")

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
    logger.info(f"Estratte {num} figure con contesto.")