from abc import ABC, abstractmethod
from typing import List
from corpus_builder.models import Paper


class DocumentSource(ABC):
    """
    Interfaccia generica per qualsiasi sorgente di articoli scientifici
    """

    @abstractmethod
    def search(self, query: str) -> List[Paper]:
        """
        Ritorna una lista di Paper SENZA contenuto HTML
        """
        pass

    @abstractmethod
    def fetch_html(self, paper: Paper) -> None:
        """
        Aggiunge html_content al Paper (se disponibile)
        """
        pass
