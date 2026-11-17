"""Configuracion central del proyecto. Todo corre en la maquina local."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_CSV = PROJECT_ROOT / "data" / "tickets_sinteticos.csv"
CHROMA_DIR = PROJECT_ROOT / "chroma_db"
COLLECTION_NAME = "tickets_anonimizados"

# Ollama local: el host apunta a 127.0.0.1 para que ningun texto salga de la maquina
OLLAMA_HOST = "http://127.0.0.1:11434"
EMBEDDING_MODEL = "bge-m3"

SPACY_MODEL = "es_core_news_md"
