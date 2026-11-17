"""Auditoria de privacidad de la base vectorial.

Recorre TODO lo almacenado en ChromaDB (documentos, ids y metadatos) y busca
patrones de PII con expresiones regulares independientes de Presidio.
Termina con codigo 1 si encuentra cedulas, correos o telefonos.

Uso (PowerShell, despues de correr demo.py o la ingesta):
    python scripts/audit_privacy.py
    python scripts/audit_privacy.py --control-negativo

--control-negativo indexa el texto CRUDO en una base temporal en memoria
(nunca en chroma_db) para demostrar que la auditoria si detecta la PII.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ticketsearch.console import setup_console  # noqa: E402

console = setup_console()

from rich.panel import Panel  # noqa: E402
from rich.table import Table  # noqa: E402

from ticketsearch import vectorstore  # noqa: E402
from ticketsearch.audit import audit_collection  # noqa: E402
from ticketsearch.config import CHROMA_DIR, COLLECTION_NAME  # noqa: E402
from ticketsearch.ingest import load_tickets, prepare_records  # noqa: E402


def raw_control_collection():
    """Coleccion en memoria con el texto crudo y vectores ficticios.

    La auditoria no necesita embeddings reales, solo el contenido guardado.
    """
    client = vectorstore.get_client(persistent=False)
    collection = vectorstore.get_collection(client, name="control_negativo_crudo", reset=True)
    records = prepare_records(load_tickets(), anonymize=False)
    vectorstore.add_documents(
        collection,
        ids=[r["id"] for r in records],
        embeddings=[[1.0, 0.0] for _ in records],
        documents=[r["document"] for r in records],
        metadatas=[r["metadata"] for r in records],
    )
    return collection


def main() -> int:
    parser = argparse.ArgumentParser(description="Auditoría de PII en ChromaDB")
    parser.add_argument("--control-negativo", action="store_true",
                        help="audita una copia CRUDA en memoria para mostrar que la auditoría falla")
    parser.add_argument("--max-detalle", type=int, default=15,
                        help="máximo de filas en la tabla de detalle")
    args = parser.parse_args()

    if args.control_negativo:
        collection = raw_control_collection()
        origin = "CONTROL NEGATIVO: texto crudo en memoria (no es la base real)"
    else:
        client = vectorstore.get_client()
        names = [c if isinstance(c, str) else c.name for c in client.list_collections()]
        if COLLECTION_NAME not in names:
            console.print(f"[bold red]No existe la colección {COLLECTION_NAME} en {CHROMA_DIR}.[/bold red] "
                          "Ejecuta primero: python demo.py")
            return 2
        collection = vectorstore.get_collection(client)
        origin = f"Base: {CHROMA_DIR}\nColección: {COLLECTION_NAME}"
    report = audit_collection(collection)

    console.print(Panel.fit(f"[bold]Auditoría de privacidad[/bold]\n{origin}",
                            border_style="red" if args.control_negativo else "cyan"))
    summary = Table(show_header=False)
    summary.add_column("Métrica", style="bold")
    summary.add_column("Valor", justify="right")
    summary.add_row("Documentos revisados", str(report.documents_scanned))
    summary.add_row("Campos revisados (id + documento + metadatos)", str(report.fields_scanned))
    blocking = Counter(f.kind for f in report.blocking)
    for kind in ("CEDULA", "NUMERO_10_DIGITOS", "EMAIL", "TELEFONO"):
        style = "red" if blocking.get(kind) else "green"
        summary.add_row(f"Hallazgos {kind}", f"[{style}]{blocking.get(kind, 0)}[/{style}]")
    summary.add_row("Advertencias (revisión humana)", str(len(report.warnings)))
    console.print(summary)

    if report.findings:
        detail = Table(title="Detalle (valores truncados a propósito)", title_justify="left")
        detail.add_column("Ticket")
        detail.add_column("Campo")
        detail.add_column("Tipo")
        detail.add_column("Fragmento")
        detail.add_column("Gravedad")
        for f in report.findings[:args.max_detalle]:
            severity = "[red]BLOQUEANTE[/red]" if f.blocking else "[yellow]ADVERTENCIA[/yellow]"
            detail.add_row(f.doc_id, f.field, f.kind, f.excerpt, severity)
        console.print(detail)
        if len(report.findings) > args.max_detalle:
            console.print(f"[dim]... y {len(report.findings) - args.max_detalle} hallazgos más.[/dim]")

    if report.passed:
        msg = "[bold green]AUDITORÍA APROBADA:[/bold green] no hay cédulas, correos ni teléfonos en la base."
        if report.warnings:
            msg += (f"\n[yellow]{len(report.warnings)} advertencia(s): patrones sospechosos que las reglas "
                    "no pueden confirmar. Requieren revisión humana.[/yellow]")
        console.print(msg)
        return 0
    console.print(f"[bold red]AUDITORÍA FALLIDA:[/bold red] {len(report.blocking)} hallazgo(s) de PII.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
