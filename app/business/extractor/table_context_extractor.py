import json
import os
import re
from bs4 import BeautifulSoup
from loguru import logger

from app.utils.check_caption import is_valid_caption
from app.utils.clean_figure import clean_text, get_informative_terms


def canonical_paper_id(paper: dict) -> str:
    return (
            paper.get("paper_id")
            or paper.get("pmc_id")
            or paper.get("arxiv_id")
            or "unknown"
    )

def extract_tables_from_html(html: str):
    soup = BeautifulSoup(html, 'lxml')

    wrappers = soup.find_all(
        ['figure', 'div', 'table'],
        class_=re.compile(r'ltx_table|tbl|ltx-table', re.I)
    )

    for table in soup.find_all('table'):
        if not any(parent in wrappers for parent in table.parents):
            wrappers.append(table)

    wrappers = sorted(wrappers, key=lambda el: (
        list(soup.descendants).index(el) if el in soup.descendants else float('inf')
    ))

    seen = set()
    valid_tables = []

    for wrapper in wrappers:
        if wrapper in seen:
            continue
        seen.add(wrapper)

        # skip equazioni e matrici
        class_str = str(wrapper.get('class', []))
        table_tag = wrapper if wrapper.name == 'table' else wrapper.find('table')
        table_class_str = str(table_tag.get('class', [])) if table_tag else ""
        combined_classes = class_str + " " + table_class_str

        if 'eqn' in combined_classes or 'math' in combined_classes or 'matrix' in combined_classes:
            continue

        if not table_tag:
            continue

        rows = table_tag.find_all('tr')
        if len(rows) < 2:
            continue

        raw_text = table_tag.get_text(separator=' ')
        real_words = re.findall(r'\b[a-zA-Z]{4,}\b', raw_text)
        if len(real_words) < 3:
            continue

        has_image = bool(table_tag.find('img'))
        all_cells = table_tag.find_all(['td', 'th'])

        if has_image:
            if len(all_cells) < 10:
                continue
            text_content = re.sub(r'\s+', ' ', raw_text or '').strip()
            if len(text_content) < 40:
                continue

        if len(all_cells) < 4:
            continue

        caption_text = ""

        # tag <caption> e <figcaption> (HTML standard)
        official_captions = wrapper.find_all(['caption', 'figcaption'])
        for cap in official_captions:
            text = clean_text(cap.get_text())
            if text and len(text) > 5:
                caption_text = text
                break

        # elementi con class="caption"
        if not caption_text:
            class_captions = wrapper.find_all(['p', 'div', 'span'], class_=re.compile(r'caption', re.I))
            for c in class_captions:
                if c.find('table'):
                    continue
                text = clean_text(c.get_text())
                if is_valid_caption(text):
                    caption_text = text
                    break

        # paragrafi vicini (solo se non trovato)
        if not caption_text:
            nearby = wrapper.find_all_previous(['p', 'div'], limit=3) + wrapper.find_all_next(['p', 'div'], limit=2)
            for c in nearby:
                if c.find('table'):
                    continue
                text = clean_text(c.get_text())
                if is_valid_caption(text):
                    caption_text = text
                    break

        # prima cella della tabella
        if not caption_text and rows:
            first_row = rows[0].find_all(['th', 'td'])
            if first_row:
                fallback_text = clean_text(first_row[0].get_text())
                if len(fallback_text) > 5:
                    caption_text = fallback_text

        if not caption_text:
            caption_text = "Table (caption not found)"

        extracted_rows = []
        for tr in rows:
            cells = [clean_text(td.get_text(separator=' ')) for td in tr.find_all(['td', 'th'])]
            if cells:
                extracted_rows.append(cells)

        if not extracted_rows:
            continue

        table_number = len(valid_tables) + 1

        valid_tables.append({
            "table_index": len(valid_tables),
            "table_number": table_number,
            "caption": caption_text,
            "rows": extracted_rows
        })

    return valid_tables

def extract_detailed_tables(corpus_json: str) -> int:
    with open(corpus_json, 'r', encoding='utf-8') as f:
        papers = json.load(f)

    all_tables = []
    stats = {"total_papers": 0, "papers_with_tables": 0, "total_tables": 0}

    for paper in papers:
        stats["total_papers"] += 1
        html = paper.get("html_content")
        if not html:
            continue

        soup = BeautifulSoup(html, 'lxml')
        paragraphs = [clean_text(p.get_text()) for p in soup.find_all('p') if len(p.get_text()) > 20]

        paper_id = canonical_paper_id(paper)
        title = paper.get("title", "")

        tables = extract_tables_from_html(html)

        if tables:
            stats["papers_with_tables"] += 1
            stats["total_tables"] += len(tables)

        for t in tables:
            caption = t["caption"]
            body = ' '.join([' '.join(r) for r in t["rows"]])

            label_match = re.search(r'(?:Table|Tabella)\s*(\d+)', caption, re.I)
            label = label_match.group(1) if label_match else str(t["table_number"])

            mentions = [
                p for p in paragraphs
                if re.search(rf'\b(Table|Tabella)\s*{label}\b', p, re.I)
            ]

            keywords = set(get_informative_terms(caption) + get_informative_terms(body)[:10])

            context = []
            for p in paragraphs:
                if p in mentions:
                    continue
                paragraph_words = set(re.findall(r'\w{4,}', p.lower()))
                if len(paragraph_words & keywords) >= 2:
                    context.append(p)

            all_tables.append({
                "paper_id": paper_id,
                "paper_title": title,
                "table_index": t["table_index"],
                "table_number": t["table_number"],
                "table_id": f"{paper_id}_table_{t['table_number']}",
                "caption": caption,
                "body": body,
                "mentions": mentions,
                "context_paragraphs": context
            })

        if len(tables) > 0:
            logger.info(f"{paper_id}: estratte {len(tables)} tabelle")

    output = os.path.join(os.path.dirname(corpus_json), "tables_with_context.json")
    with open(output, "w", encoding="utf-8") as f:
        json.dump(all_tables, f, indent=2, ensure_ascii=False)


    return len(all_tables)


if __name__ == "__main__":
    json_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..",
        "corpus.json"
    )
    num = extract_detailed_tables(json_path)
    print(f"\nOPERAZIONE COMPLETATA: Estratte {num} figure complete di contesto.")
    print("I dati sono pronti nel file 'figures_with_context.json' per essere indicizzati.")