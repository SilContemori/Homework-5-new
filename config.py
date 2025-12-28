import os
from pydantic_settings import BaseSettings,SettingsConfigDict

SRC_DIR = os.path.dirname(os.path.realpath(__file__))
DOTENV = os.path.join(SRC_DIR, '.env')

class ConfigSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=DOTENV, env_ignore_empty=True, extra="ignore")
    HOST_ELASTIC : str
    PASSWORD_ELASTC : str
    QUERY : str = 'ti:"Entity resolution" OR abs:"Entity resolution" OR ti:"Entity matching" OR abs:"Entity matching"'


config = ConfigSettings()


