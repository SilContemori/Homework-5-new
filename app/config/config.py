import os
from pydantic_settings import BaseSettings,SettingsConfigDict

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
DOTENV = os.path.join(SRC_DIR, '.env')

class ConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=DOTENV, env_ignore_empty=True, extra="ignore")
    HOST_ELASTIC : str
    PASSWORD_ELASTIC : str = ""
    #QUERY : str = 'ti:"Entity resolution" OR abs:"Entity resolution" OR ti:"Entity matching" OR abs:"Entity matching"'
    HEADERS: dict[str, str] = {"User-Agent": "AcademicSearchProject/1.0"}
    DELAY: int = 3
    QUERY: str = ('"cancer risk" AND "coffee consumption" AND free full text[filter] OR glyphosate AND cancer risk AND free full text[filter] OR glyphosate AND cancer risk AND free full text[filter]'
            'OR ultra-processed foods AND cardiovascular risk AND free full text[filter]')

    SOURCE : str = "pubmed"  #  arxiv, pubmed

config = ConfigSettings()
