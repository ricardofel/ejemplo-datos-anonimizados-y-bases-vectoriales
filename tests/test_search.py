"""La busqueda semantica devuelve la categoria correcta en casos obvios.

Requiere Ollama corriendo con bge-m3 (si no, se omiten). Usa una base en
memoria para no tocar chroma_db.
"""

import pytest

from ticketsearch import vectorstore
from ticketsearch.audit import audit_collection
from ticketsearch.ingest import index_records, prepare_records
from ticketsearch.search import TicketSearcher


@pytest.fixture(scope="module")
def searcher(tickets, embedder):
    client = vectorstore.get_client(persistent=False)
    col = vectorstore.get_collection(client, name="test_search", reset=True)
    index_records(col, prepare_records(tickets, anonymize=True), embedder)
    return TicketSearcher(collection=col, embedder=embedder)


@pytest.mark.parametrize("query, category", [
    ("no puedo entrar a mi cuenta porque se bloqueó", "acceso/contraseña"),
    ("olvidé mi contraseña", "acceso/contraseña"),
    ("me cobraron dos veces la matrícula", "pagos"),
    ("la factura electrónica no me llegó al correo", "facturación"),
    ("la aplicación del celular se cierra sola", "app móvil"),
    ("no hay cupos para inscribirme en la materia", "matrícula/académico"),
    ("no me conecta el wifi de la universidad", "soporte técnico"),
])
def test_top_result_has_expected_category(searcher, query, category):
    hits = searcher.search(query, k=3)
    assert hits[0]["metadata"]["categoria"] == category
    assert 0.0 < hits[0]["score"] <= 1.0
    assert hits[0]["score"] >= hits[-1]["score"]


def test_query_with_pii_is_anonymized_and_still_works(searcher):
    hits = searcher.search("Soy Ana Paredes, cédula 1710034065. Me debitaron doble la pensión.", k=3)
    assert hits[0]["metadata"]["categoria"] == "pagos"


def test_category_filter(searcher):
    hits = searcher.search("tengo un problema", k=3, category="facturación")
    assert {h["metadata"]["categoria"] for h in hits} == {"facturación"}


def test_indexed_collection_passes_audit(searcher):
    assert audit_collection(searcher.collection).passed
