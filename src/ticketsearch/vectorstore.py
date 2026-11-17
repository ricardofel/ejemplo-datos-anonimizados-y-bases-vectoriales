"""Acceso a ChromaDB (cliente persistente local, metrica coseno, sin Docker)."""

from __future__ import annotations

from pathlib import Path

import chromadb
from chromadb.config import Settings

from .config import CHROMA_DIR, COLLECTION_NAME

# Sin telemetria: ningun evento sale de la maquina
_SETTINGS = Settings(anonymized_telemetry=False)


def get_client(path: Path | str | None = CHROMA_DIR, persistent: bool = True):
    """Cliente persistente en disco o, para pruebas y evaluacion, en memoria."""
    if not persistent:
        return chromadb.EphemeralClient(settings=_SETTINGS)
    Path(path).mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path), settings=_SETTINGS)


def get_collection(client, name: str = COLLECTION_NAME, reset: bool = False):
    """Obtiene (o crea) la coleccion con distancia coseno.

    embedding_function=None: los vectores siempre los calculamos nosotros con
    Ollama, asi Chroma nunca descarga su modelo por defecto desde internet.
    """
    if reset:
        existing = [c if isinstance(c, str) else c.name for c in client.list_collections()]
        if name in existing:
            client.delete_collection(name)
    return client.get_or_create_collection(
        name=name,
        embedding_function=None,
        configuration={"hnsw": {"space": "cosine"}},
        metadata={"descripcion": "Tickets de soporte anonimizados"},
    )


def add_documents(collection, ids, embeddings, documents, metadatas) -> None:
    collection.upsert(ids=ids, embeddings=embeddings, documents=documents,
                      metadatas=metadatas)


def query(collection, embedding: list[float], k: int = 3,
          where: dict | None = None) -> list[dict]:
    """Devuelve los k vecinos mas cercanos con score = 1 - distancia coseno."""
    res = collection.query(query_embeddings=[embedding], n_results=k, where=where,
                           include=["documents", "metadatas", "distances"])
    hits = []
    for doc_id, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                       res["metadatas"][0], res["distances"][0]):
        hits.append({"id": doc_id, "document": doc, "metadata": meta,
                     "score": 1.0 - dist})
    return hits
