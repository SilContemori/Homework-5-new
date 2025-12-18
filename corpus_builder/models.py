from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Paper:
    paper_id: str
    title: str
    authors: List[str]
    abstract: str
    published: Optional[str]
    updated: Optional[str]
    html_url: Optional[str]
    pdf_url: Optional[str]
    html_content: Optional[str] = None
