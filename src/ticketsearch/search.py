"""Busqueda semantica de tickets similares.

La consulta tambien se anonimiza antes de vectorizarla: un agente podria
pegar el ticket nuevo completo, con nombre y cedula incluidos.
"""

from __future__ import annotations

import re
import unicodedata

from . import vectorstore
from .anonymizer import get_anonymizer
from .embedder import OllamaEmbedder


class TicketSearcher:
    def __init__(self, collection=None, embedder: OllamaEmbedder | None = None) -> None:
        self.embedder = embedder or OllamaEmbedder()
        if collection is None:
            collection = vectorstore.get_collection(vectorstore.get_client())
        self.collection = collection

    def search(self, query: str, k: int = 3, category: str | None = None,
               anonymize_query: bool = True) -> list[dict]:
        """Top k tickets mas parecidos por significado (score coseno 0 a 1)."""
        text = get_anonymizer().anonymize(query).text if anonymize_query else query
        where = {"categoria": category} if category else None
        return vectorstore.query(self.collection, self.embedder.embed_one(text),
                                 k=k, where=where)


# ---------------------------------------------------------------------------
# Linea base por palabras clave (para comparar contra la busqueda vectorial)
# ---------------------------------------------------------------------------

STOPWORDS = set("""
a al algo ante como con contra cual cuando de del desde donde e el ella en entre
era es esa ese eso esta este esto estoy fue ha hace han hay la las le les lo los
me mi mis muy nada ni no nos o otra otro para pero por porque que se si sin sobre
son su sus te tengo ti tu un una uno y ya yo puedo puede mas hola soy buenos dias
buenas tardes saludos estimados gracias antemano datos adjunto nombre persona
cedula email telefono correo celular numero ci pueden contactarme
""".split())


def keyword_tokens(text: str) -> set[str]:
    """Palabras significativas en minusculas y sin tildes."""
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return {w for w in re.findall(r"[a-z0-9]+", folded) if w not in STOPWORDS and len(w) > 2}


class KeywordSearcher:
    """Busqueda clasica: ordena por cantidad de palabras en comun (sin significado)."""

    def __init__(self, records: list[dict]) -> None:
        self.records = records
        self.tokens = [keyword_tokens(r["document"]) for r in records]

    def search(self, query: str, k: int = 3) -> list[dict]:
        q = keyword_tokens(query)
        scored = [(len(q & toks), i) for i, toks in enumerate(self.tokens)]
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [{"id": self.records[i]["id"], "score": float(s),
                 "metadata": self.records[i]["metadata"],
                 "document": self.records[i]["document"]}
                for s, i in scored[:k] if s > 0]
