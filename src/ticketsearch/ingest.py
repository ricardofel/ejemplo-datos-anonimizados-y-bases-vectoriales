"""Ingesta: CSV crudo -> anonimizacion -> embedding -> ChromaDB.

Regla de privacidad: el texto crudo solo vive en memoria durante este paso.
A ChromaDB llegan unicamente el texto anonimizado y metadatos sin PII.
Nunca se escribe el texto crudo en logs.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Callable

from . import vectorstore
from .anonymizer import get_anonymizer
from .config import DATA_CSV
from .embedder import OllamaEmbedder


def load_tickets(csv_path: Path | str = DATA_CSV) -> list[dict]:
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def prepare_records(tickets: list[dict], anonymize: bool = True) -> list[dict]:
    """Construye documento y metadatos por ticket.

    anonymize=False existe solo para la evaluacion comparativa, que trabaja
    en una base en memoria y nunca toca la carpeta chroma_db.
    """
    anon = get_anonymizer() if anonymize else None
    records = []
    for t in tickets:
        if anon:
            result = anon.anonymize(t["texto"])
            document = result.text
            resolution = anon.anonymize(t["resolucion"]).text
            pii_count = result.total
        else:
            document, resolution, pii_count = t["texto"], t["resolucion"], 0
        records.append({
            "id": t["id"],
            "document": document,
            "metadata": {
                "categoria": t["categoria"],
                "fecha": t["fecha"],
                "resolucion": resolution,
                "pii_enmascaradas": pii_count,
            },
        })
    return records


def index_records(collection, records: list[dict], embedder: OllamaEmbedder,
                  on_batch: Callable[[int], None] | None = None,
                  batch_size: int = 16) -> int:
    """Vectoriza e inserta por lotes. Devuelve el total de la coleccion."""
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        vectors = embedder.embed([r["document"] for r in batch])
        vectorstore.add_documents(
            collection,
            ids=[r["id"] for r in batch],
            embeddings=vectors,
            documents=[r["document"] for r in batch],
            metadatas=[r["metadata"] for r in batch],
        )
        if on_batch:
            on_batch(len(batch))
    return collection.count()


def ingest(csv_path: Path | str = DATA_CSV, client=None, reset: bool = True,
           on_batch: Callable[[int], None] | None = None):
    """Pipeline completo. Devuelve (coleccion, cantidad de documentos)."""
    embedder = OllamaEmbedder()
    embedder.check_available()
    client = client or vectorstore.get_client()
    collection = vectorstore.get_collection(client, reset=reset)
    records = prepare_records(load_tickets(csv_path), anonymize=True)
    count = index_records(collection, records, embedder, on_batch=on_batch)
    return collection, count
