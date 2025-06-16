from .config import BaseConfig
from dotenv import load_dotenv

load_dotenv()


class ProductionConfig(BaseConfig):
    DEBUG = False
