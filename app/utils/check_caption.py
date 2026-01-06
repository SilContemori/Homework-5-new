import re


def is_valid_caption(text: str) -> bool:
    """ valida se un testo è una buona caption (per paragrafi generici, NON per tag <caption>).
    """
    if not text or len(text) > 350:
        return False

    if re.match(r'^\s*(Table|Tabella)\s*\d+', text, re.I):
        return True

    table_mentions = re.findall(r'(?:Table|Tabella)\s*\d+', text, re.I)
    if len(table_mentions) > 1:
        return False

    bad_phrases = [
        'shows that', 'consistent with', 'participants were',
        'we performed', 'associated with', 'indicated that'
    ]
    lower = text.lower()
    if any(p in lower for p in bad_phrases) and len(text) > 100:
        return False

    return True