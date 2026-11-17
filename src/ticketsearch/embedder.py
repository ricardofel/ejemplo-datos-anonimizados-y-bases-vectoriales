"""Embeddings locales con Ollama (modelo bge-m3, multilingue, 1024 dimensiones).

El cliente apunta a 127.0.0.1: el texto (ya anonimizado) nunca sale de la maquina.
"""

from __future__ import annotations

import ollama

from .config import EMBEDDING_MODEL, OLLAMA_HOST


class EmbeddingServiceError(RuntimeError):
    """Ollama no esta disponible o falta el modelo."""


class OllamaEmbedder:
    def __init__(self, model: str = EMBEDDING_MODEL, host: str = OLLAMA_HOST,
                 batch_size: int = 32) -> None:
        self.model = model
        self.batch_size = batch_size
        self.client = ollama.Client(host=host)

    def check_available(self) -> None:
        """Falla con un mensaje claro si Ollama esta apagado o falta el modelo."""
        try:
            models = self.client.list()
        except Exception as exc:  # conexion rechazada, timeout, etc.
            raise EmbeddingServiceError(
                "No se pudo conectar con Ollama en 127.0.0.1:11434. "
                "Abre la aplicacion Ollama o ejecuta: ollama serve"
            ) from exc
        names = {m.model.split(":")[0] for m in models.models}
        if self.model.split(":")[0] not in names:
            raise EmbeddingServiceError(
                f"El modelo {self.model} no esta descargado. Ejecuta: ollama pull {self.model}"
            )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Devuelve un vector por texto, procesando por lotes."""
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            response = self.client.embed(model=self.model, input=batch)
            vectors.extend(list(v) for v in response.embeddings)
        return vectors

    def embed_one(self, text: str) -> list[float]:
        return self.embed([text])[0]
