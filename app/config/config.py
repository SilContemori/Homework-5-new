import os
from pydantic_settings import BaseSettings, SettingsConfigDict

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DOTENV = os.path.join(SRC_DIR, '.env')


class ConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=DOTENV, env_ignore_empty=True, extra="ignore")
    HOST_ELASTIC: str
    PASSWORD_ELASTIC: str = ""
    NCBI_API_KEY: str = ""
    HEADERS: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    DELAY: int = 3

    # sorgente attiva di default: 'arxiv' oppure 'pubmed' (sovrascrivibile da .env)
    SOURCE: str = "arxiv"

    #Query arXiv estesa
    #QUERY: str = 'all:"entity resolution" OR all:"entity matching" OR all:"record linkage" OR all:"data deduplication"'

    # Query arXiv alternativa (singola):
    # QUERY: str = 'ti:"entity resolution"'

    # Query PubMed (Cancer risk, coffee, glyphosate, ultra-processed foods: ~705 articoli):
    QUERY: str = (
         '"cancer risk" AND "coffee consumption" AND free full text[filter] '
         'OR glyphosate AND cancer risk AND free full text[filter] '
         'OR ultra-processed foods AND cardiovascular risk AND free full text[filter]'
     )


config = ConfigSettings()
