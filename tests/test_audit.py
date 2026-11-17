"""La auditoria aprueba la base anonimizada y reprueba una base con texto crudo."""

from ticketsearch import vectorstore
from ticketsearch.audit import audit_collection
from ticketsearch.ingest import prepare_records


def build_collection(name, records):
    client = vectorstore.get_client(persistent=False)
    col = vectorstore.get_collection(client, name=name, reset=True)
    vectorstore.add_documents(col, ids=[r["id"] for r in records],
                              embeddings=[[1.0, 0.0] for _ in records],
                              documents=[r["document"] for r in records],
                              metadatas=[r["metadata"] for r in records])
    return col


def test_audit_passes_on_anonymized_records(tickets):
    report = audit_collection(build_collection("test_audit_anon", prepare_records(tickets, True)))
    assert report.documents_scanned == len(tickets)
    assert report.passed
    # el correo ofuscado del caso dificil queda como advertencia para revision humana
    assert {f.doc_id for f in report.warnings} == {"TCK-0085"}


def test_audit_fails_on_raw_records(tickets):
    report = audit_collection(build_collection("test_audit_raw", prepare_records(tickets, False)))
    assert not report.passed
    kinds = {f.kind for f in report.blocking}
    assert {"CEDULA", "EMAIL", "TELEFONO"} <= kinds


def test_metadata_has_no_raw_text(tickets):
    records = prepare_records(tickets, anonymize=True)
    raw_texts = {t["texto"] for t in tickets}
    for r in records:
        assert set(r["metadata"]) == {"categoria", "fecha", "resolucion", "pii_enmascaradas"}
        # todos los tickets del dataset traen PII, asi que ninguno queda igual al crudo
        assert r["document"] not in raw_texts
