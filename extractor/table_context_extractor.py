import json
import os
import re
from bs4 import BeautifulSoup
from loguru import logger

# Lista di parole non informative (stop-words) da ignorare per il contesto
STOP_WORDS = set(['il', 'lo', 'la', 'i', 'gli', 'le', 'di', 'a', 'da', 'in', 'con', 'su', 'per', 'tra', 'fra', 'and', 'the', 'of', 'in', 'with', 'for', 'table', 'tabella', 'figure'])

def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip()

def get_informative_terms(text):
    # Estrae termini informativi (parole > 3 lettere, non stop-words)
    words = re.findall(r'\b\w{4,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS]

def extract_detailed_tables(json_file):
    with open(json_file, 'r', encoding='utf-8') as f:
        papers = json.load(f)

    all_extracted_data = []

    for paper in papers:
        if not paper.get('html_content'):
            continue
        
        soup = BeautifulSoup(paper['html_content'], 'lxml')
        paper_id = paper['paper_id']
        
        # Estraiamo tutti i paragrafi puliti per cercare citazioni e contesto
        paragraphs = [clean_text(p.get_text()) for p in soup.find_all('p') if len(p.get_text()) > 20]
        
        # Cerchiamo le tabelle nell'HTML (spesso dentro tag <figure> o <table>)
        table_wrappers = soup.find_all(['figure', 'div', 'table'], class_=re.compile(r'table', re.I))
        
        for i, wrapper in enumerate(table_wrappers):
            # 1. Estrazione CAPTION
            caption_tag = wrapper.find(['figcaption', 'span', 'div'], class_=re.compile(r'caption', re.I))
            caption = clean_text(caption_tag.get_text()) if caption_tag else f"Table {i+1}"
            
            # 2. Estrazione CORPO (testo della tabella)
            table_tag = wrapper if wrapper.name == 'table' else wrapper.find('table')
            if not table_tag: continue
            body = clean_text(table_tag.get_text(separator=" "))
            
            # 3. Estrazione MENTIONS (Paragrafi che citano la tabella, es: "Table 1")
            # Cerchiamo l'etichetta (es: "1.1" o "1") dalla caption o dall'indice
            label_match = re.search(r'(?:Table|Tabella)\s*(\d+[\.\d+]*)', caption, re.I)
            label = label_match.group(1) if label_match else str(i+1)
            
            mentions = [p for p in paragraphs if re.search(rf'\b(Table|Tabella)\s*{label}\b', p, re.I)]
            
            # 4. Estrazione CONTEXT PARAGRAPHS
            # Prendiamo termini informativi da caption e corpo (prime righe)
            keywords = get_informative_terms(caption) + get_informative_terms(body)[:10]
            keywords = list(set(keywords))[:15] # Limite per efficienza
            
            context_paragraphs = []
            for p in paragraphs:
                if p in mentions: continue # Evitiamo duplicati
                # Se il paragrafo contiene almeno 2 termini informativi della tabella
                matches = [kw for kw in keywords if kw in p.lower()]
                if len(matches) >= 2:
                    context_paragraphs.append(p)

            # Salviamo il pacchetto completo richiesto dal Punto 4
            table_data = {
                "paper_id": paper_id,
                "paper_title": paper.get('title', ''),  # Titolo del paper
                "table_index": i,
                "caption": caption,
                "body": body,
                "mentions": mentions,
                "context_paragraphs": context_paragraphs
            }
            all_extracted_data.append(table_data)
            
        logger.info(f"Paper {paper_id}: estratte {len(table_wrappers)} tabelle con contesto.")

    # Salviamo i risultati in un nuovo file JSON dedicato alle tabelle
    with open("../tables_with_context.json", "w", encoding='utf-8') as f:
        json.dump(all_extracted_data, f, indent=4)
    
    return len(all_extracted_data)

if __name__ == "__main__":
    num = extract_detailed_tables("../corpus.json")
    print(f"\nOPERAZIONE COMPLETATA: Estratte {num} tabelle complete di contesto.")
    print("I dati sono pronti nel file 'tables_with_context.json' per essere indicizzati.")