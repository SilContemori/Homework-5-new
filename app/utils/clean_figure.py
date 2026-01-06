import re
from app.config.constants import STOP_WORDS



def clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def get_informative_terms(text: str):
    words = re.findall(r'\b\w{4,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS]

