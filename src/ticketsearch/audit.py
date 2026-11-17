"""Auditoria de privacidad sobre lo que realmente quedo guardado en ChromaDB.

Es una segunda linea de defensa independiente de Presidio: usa expresiones
regulares simples y revisa TODOS los documentos y TODOS los metadatos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .anonymizer import is_valid_cedula

# Hallazgos que hacen FALLAR la auditoria
BLOCKING_PATTERNS = {
    "CEDULA": re.compile(r"(?<!\d)\d{10}(?!\d)"),
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
    "TELEFONO": re.compile(r"(?<![\d+])09\d(?:[\s-]?\d){7}(?!\d)|\+593[\s-]?\d(?:[\s-]?\d){7,8}"),
}
# Senales sospechosas que se reportan como advertencia (no hacen fallar)
WARNING_PATTERNS = {
    "POSIBLE_EMAIL_OFUSCADO": re.compile(r"\b\S+\s+arroba\s+\S+(?:\s+punto\s+\S+)+", re.IGNORECASE),
    "SECUENCIA_NUMERICA_LARGA": re.compile(r"(?<!\d)\d{7,9}(?!\d)"),
}


@dataclass
class Finding:
    doc_id: str
    field: str
    kind: str
    excerpt: str
    blocking: bool


@dataclass
class AuditReport:
    documents_scanned: int = 0
    fields_scanned: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.blocking]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if not f.blocking]

    @property
    def passed(self) -> bool:
        return not self.blocking


def _mask_excerpt(value: str) -> str:
    """Ni el reporte debe reimprimir el dato completo: se muestra truncado."""
    return value[:3] + "*" * max(len(value) - 3, 0)


# Si dos patrones calzan sobre el mismo texto se reporta uno solo, por prioridad
# (una cedula de Guayas empieza con 09 y tambien calza como celular).
_PRIORITY = {"CEDULA": 0, "EMAIL": 1, "TELEFONO": 2, "NUMERO_10_DIGITOS": 3}


def scan_text(doc_id: str, field_name: str, text: str, report: AuditReport) -> None:
    report.fields_scanned += 1
    matches = []
    for kind, pattern in BLOCKING_PATTERNS.items():
        for m in pattern.finditer(text):
            label = kind
            if kind == "CEDULA":
                label = "CEDULA" if is_valid_cedula(m.group(0)) else "NUMERO_10_DIGITOS"
            matches.append((_PRIORITY[label], m.start(), m.end(), label, m.group(0)))
    kept: list[tuple] = []
    for match in sorted(matches):
        if all(match[2] <= k[1] or match[1] >= k[2] for k in kept):
            kept.append(match)
    for _, start, _, label, value in sorted(kept, key=lambda x: x[1]):
        report.findings.append(Finding(doc_id, field_name, label, _mask_excerpt(value), True))
    for kind, pattern in WARNING_PATTERNS.items():
        for m in pattern.finditer(text):
            report.findings.append(Finding(doc_id, field_name, kind, _mask_excerpt(m.group(0)), False))


def audit_collection(collection, page_size: int = 500) -> AuditReport:
    """Recorre la coleccion completa (paginando) y revisa cada campo de texto."""
    report = AuditReport()
    scan_text("(coleccion)", "metadata", str(collection.metadata or {}), report)
    total = collection.count()
    for offset in range(0, total, page_size):
        page = collection.get(include=["documents", "metadatas"], limit=page_size, offset=offset)
        for doc_id, doc, meta in zip(page["ids"], page["documents"], page["metadatas"]):
            report.documents_scanned += 1
            scan_text(doc_id, "id", doc_id, report)
            scan_text(doc_id, "document", doc or "", report)
            for key, value in (meta or {}).items():
                scan_text(doc_id, f"metadata.{key}", str(value), report)
    return report
