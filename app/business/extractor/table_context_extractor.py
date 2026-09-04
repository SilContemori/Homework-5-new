import json
import os
import re
from bs4 import BeautifulSoup
from loguru import logger

from app.utils.check_caption import is_valid_caption
from app.utils.clean_figure import clean_text, get_informative_terms
from app.config.constants import STOP_WORDS


def canonical_paper_id(paper: dict) -> str:
    return (
        paper.get("pmc_id")
        or paper.get("paper_id")
        or paper.get("arxiv_id")
        or "unknown"
    )

def extract_tables_from_html(html: str):
    soup = BeautifulSoup(html, 'lxml')

    raw_tables = soup.find_all('table')
    processed_containers = set()
    valid_tables = []

    for table in raw_tables:
        container = (
            table.find_parent(class_=re.compile(r'table-wrap|ltx_table|tbl-box|tw\b', re.I))
            or table.find_parent('figure')
            or table
        )

        if container in processed_containers:
            continue
        processed_containers.add(container)

        c_cls_list = container.get('class', [])
        c_cls = " ".join(c_cls_list if isinstance(c_cls_list, list) else [str(c_cls_list)]).lower()
        cid = (container.get('id') or "").lower()
        if any(bad in c_cls or bad in cid for bad in ['algorithm', 'code', 'listing', 'glossary', 'abbrev', 'ref-list', 'disp-formula', 'matrix']):
            continue

        rows = container.find_all('tr') if container != table else table.find_all('tr')
        if len(rows) < 2:
            continue

        all_cells = container.find_all(['td', 'th'])
        if len(all_cells) < 4:
            continue

        raw_text = clean_text(container.get_text(separator=' '))
        real_words = re.findall(r'\b[a-zA-Z]{3,}\b', raw_text)
        if len(real_words) < 3:
            continue

        element_id = container.get('id') or table.get('id') or ""

        caption_text = ""
        head_text = ""
        body_cap_text = ""

        head_tag = container.find(
            ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'],
            class_=re.compile(r'obj_head|head|label|table-label', re.I)
        )
        if head_tag:
            head_cand = clean_text(head_tag.get_text())
            if head_cand and len(head_cand) > 2:
                head_text = head_cand

        cap_el = container.find(['caption', 'figcaption']) or container.find(
            ['div', 'p', 'span'],
            class_=re.compile(r'caption|ltx_caption|tbl-caption|table-label', re.I)
        )
        if cap_el:
            cap_cand = clean_text(cap_el.get_text())
            if is_valid_caption(cap_cand):
                body_cap_text = cap_cand

        if head_text and body_cap_text:
            if head_text.lower() in body_cap_text.lower():
                caption_text = body_cap_text
            else:
                caption_text = f"{head_text} {body_cap_text}".strip()
        elif body_cap_text:
            caption_text = body_cap_text
        elif head_text:
            caption_text = head_text

        if not caption_text:
            caption_tags = container.find_all(
                ['caption', 'figcaption', 'h4', 'h5', 'h6']
            )
            for tag in caption_tags:
                cand = clean_text(tag.get_text())
                if is_valid_caption(cand):
                    caption_text = cand
                    break

        if not caption_text:
            class_captions = container.find_all(
                ['div', 'p', 'span'],
                class_=re.compile(r'caption|obj_head|tw-head|table-label', re.I)
            )
            for c in class_captions:
                cand = clean_text(c.get_text())
                if is_valid_caption(cand):
                    caption_text = cand
                    break

        if not caption_text:
            nearby = container.find_all_previous(['p', 'div', 'h3', 'h4'], limit=3)
            for c in nearby:
                cand = clean_text(c.get_text())
                if is_valid_caption(cand) and re.search(r'\b(Table|Tabella|Tbl)\b', cand, re.I):
                    caption_text = cand
                    break

        if re.match(r'^(?:Figure|Fig|Algorithm|Alg)\b', caption_text, re.I):
            continue

        num_match = re.search(r'\b(?:Table|Tabella|Tbl)\s*(\d+)', caption_text, re.I) if caption_text else None
        if not num_match:
            continue
        table_number = int(num_match.group(1))

        extracted_rows = []
        for tr in rows:
            cells = [clean_text(td.get_text(separator=' ')) for td in tr.find_all(['td', 'th'])]
            if cells:
                extracted_rows.append(cells)

        if not extracted_rows:
            continue

        valid_tables.append({
            "table_index": len(valid_tables),
            "table_number": table_number,
            "element_id": element_id,
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
        pmc_id = paper.get("pmc_id", "")
        pmid = paper.get("paper_id", "")

        tables = extract_tables_from_html(html)

        if tables:
            stats["papers_with_tables"] += 1
            stats["total_tables"] += len(tables)

        for t in tables:
            caption = t["caption"]
            body = ' '.join([' '.join(r) for r in t["rows"]])

            label_match = re.search(r'(?:Table|Tabella|Tbl)\s*(\d+)', caption, re.I)
            label = label_match.group(1) if label_match else str(t["table_number"])

            mentions = [
                p for p in paragraphs
                if re.search(rf'\b(Table|Tabella|Tbl)\s*{label}\b', p, re.I)
            ]

            caption_terms = [w for w in get_informative_terms(caption) if len(w) > 4 and w.lower() not in STOP_WORDS]
            body_terms = [w for w in get_informative_terms(body) if len(w) > 4 and w.lower() not in STOP_WORDS][:8]
            keywords = set(caption_terms + body_terms)

            context = []
            if keywords:
                for p in paragraphs:
                    if p in mentions:
                        continue
                    paragraph_words = set(re.findall(r'\b[a-zA-Z]{5,}\b', p.lower()))
                    if len(paragraph_words & keywords) >= 2:
                        context.append(p)
                    if len(context) >= 5:
                        break

            all_tables.append({
                "paper_id": paper_id,
                "pmc_id": pmc_id,
                "pmid": pmid,
                "paper_title": title,
                "table_index": t["table_index"],
                "table_number": t["table_number"],
                "table_id": f"{paper_id}_table_{t['table_number']}",
                "element_id": t.get("element_id", ""),
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
    logger.info(f"Estratte {num} tabelle con contesto.")