import re


def is_valid_caption(text: str) -> bool:
    """ Valida se un testo è una buona caption (per paragrafi generici, NON per tag <caption>).
    """
    if not text or len(text.strip()) < 8 or len(text) > 500:
        return False

    lower = text.lower().strip()
    ui_phrases = [
        'open in a new tab', 'open in new tab', 'download',
        'view large image', 'powerpoint', 'supplementary material',
        'format: pdf', 'creative commons'
    ]
    if any(p in lower for p in ui_phrases) and len(text) < 40:
        return False

    if re.match(r'^\s*(Table|Tabella|Tbl)\s*\d+', text, re.I):
        return True

    table_mentions = re.findall(r'(?:Table|Tabella|Tbl)\s*\d+', text, re.I)
    if len(table_mentions) > 1:
        return False

    bad_phrases = [
        'shows that', 'consistent with', 'participants were',
        'we performed', 'associated with', 'indicated that',
        'as shown in', 'see table'
    ]
    if any(p in lower for p in bad_phrases) and len(text) > 100:
        return False

    return True