import os
from pydantic_settings import BaseSettings, SettingsConfigDict

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DOTENV = os.path.join(SRC_DIR, '.env')


class ConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=DOTENV, env_ignore_empty=True, extra="ignore")
    HOST_ELASTIC: str = "https://localhost:9200"
    PASSWORD_ELASTIC: str = ""
    NCBI_API_KEY: str = ""
    HEADERS: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    DELAY: float = 1.5

    # sorgente attiva di default: 'all', 'arxiv' o 'pubmed'
    SOURCE: str = "all"

    # query arxiv gruppo a
    QUERY_ARXIV: str = 'ti:"entity resolution" OR abs:"entity resolution" OR ti:"entity matching" OR abs:"entity matching"'

    # query pubmed
    QUERY_PUBMED: str = (
        '(("cancer risk" AND "coffee consumption") OR '
        '("glyphosate" AND "cancer risk") OR '
        '("air pollution" AND "cognitive decline") OR '
        '("ultra-processed foods" AND "cardiovascular risk")) '
        'AND (free full text[filter] OR open access[filter])'
    )

    QUERY: str = ""

    def model_post_init(self, __context):
        if not self.QUERY:
            if self.SOURCE.lower() == "pubmed":
                self.QUERY = self.QUERY_PUBMED
            elif self.SOURCE.lower() == "arxiv":
                self.QUERY = self.QUERY_ARXIV
            else:
                self.QUERY = self.QUERY_PUBMED


config = ConfigSettings()
