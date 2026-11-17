"""Fixtures compartidas. Los tests de busqueda se omiten si Ollama no esta disponible."""

import pytest

from ticketsearch.anonymizer import get_anonymizer
from ticketsearch.embedder import EmbeddingServiceError, OllamaEmbedder
from ticketsearch.ingest import load_tickets


@pytest.fixture(scope="session")
def anonymizer():
    return get_anonymizer()


@pytest.fixture(scope="session")
def tickets():
    return load_tickets()


@pytest.fixture(scope="session")
def embedder():
    emb = OllamaEmbedder()
    try:
        emb.check_available()
    except EmbeddingServiceError as exc:
        pytest.skip(f"Ollama no disponible: {exc}")
    return emb
