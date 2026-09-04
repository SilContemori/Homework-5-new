import re
from app.config.constants import STOP_WORDS



def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'(?i)\bopen in (a )?new tab\b', '', text)
    text = re.sub(r'(?i)\bdownload (slide|powerpoint|pdf)\b', '', text)
    text = re.sub(r'(?i)\bview large image\b', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def get_informative_terms(text: str):
    words = re.findall(r'\b\w{4,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS]

