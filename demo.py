"""Demo guiada en 3 momentos para la exposicion.

    python demo.py                     # demo completa (menos de 60 s)
    python demo.py --pausa             # espera ENTER entre momentos (para exponer)
    python demo.py --casos-dificiles   # agrega los casos donde el enmascarado falla
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from ticketsearch.console import setup_console  # noqa: E402

console = setup_console()

from rich.columns import Columns  # noqa: E402
from rich.panel import Panel  # noqa: E402
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn  # noqa: E402
from rich.rule import Rule  # noqa: E402
from rich.table import Table  # noqa: E402
from rich.text import Text  # noqa: E402

from ticketsearch import vectorstore  # noqa: E402
from ticketsearch.anonymizer import ENTITY_LABELS, get_anonymizer  # noqa: E402
from ticketsearch.config import CHROMA_DIR, EMBEDDING_MODEL  # noqa: E402
from ticketsearch.embedder import EmbeddingServiceError, OllamaEmbedder  # noqa: E402
from ticketsearch.ingest import index_records, load_tickets, prepare_records  # noqa: E402
from ticketsearch.search import TicketSearcher, keyword_tokens  # noqa: E402

SHOWCASE_TICKET = "TCK-0003"

DEMO_QUERIES = [
    "se me bloqueó el acceso al portal",
    "me cobraron dos veces la pensión",
    # Consulta con PII: tambien se anonimiza antes de vectorizar
    "Hola, soy Pedro Páez (cédula 1710034065, cel 0991234567). La aplicación se me cierra sola.",
]

# Casos dificiles del dataset y el fragmento que NO deberia sobrevivir
HARD_CASES = [
    ("TCK-0074", "Nombre en minúsculas", "gabriela"),
    ("TCK-0013", "Apodo", "Panchito"),
    ("TCK-0044", "Cuasi-identificador", "decano de la Facultad de Ingeniería de la sede Loja"),
    ("TCK-0085", "Correo ofuscado", "arroba"),
]


def pause(enabled: bool) -> None:
    if enabled:
        console.input("[dim]Presiona ENTER para continuar...[/dim]")


def highlight_raw(text: str, results) -> Text:
    """Resalta en rojo la PII detectada (solo en pantalla, no se guarda)."""
    out = Text(text)
    for r in results:
        out.stylize("bold white on red", r.start, r.end)
    return out


def highlight_labels(text: str) -> Text:
    out = Text(text)
    for label in ENTITY_LABELS.values():
        out.highlight_words([label], style="bold black on green")
    return out


def moment_1(tickets: dict) -> None:
    console.print(Rule("[bold cyan]MOMENTO 1: del ticket crudo al ticket anonimizado"))
    anon = get_anonymizer()
    raw = tickets[SHOWCASE_TICKET]["texto"]
    results = anon.analyze(raw)
    masked = anon.anonymize(raw)

    console.print(Columns([
        Panel(highlight_raw(raw, results), title="Ticket crudo (con PII)",
              border_style="red", width=58),
        Panel(highlight_labels(masked.text), title="Ticket anonimizado (lo único que se guarda)",
              border_style="green", width=58),
    ]))

    table = Table(title="Entidades detectadas", title_justify="left")
    table.add_column("Tipo")
    table.add_column("Reemplazo")
    table.add_column("Detector")
    table.add_column("Score", justify="right")
    for r in results:
        detector = (r.recognition_metadata or {}).get("recognizer_name", "")
        table.add_row(r.entity_type, ENTITY_LABELS[r.entity_type], detector, f"{r.score:.2f}")
    console.print(table)
    console.print("[green]Enmascarado irreversible:[/green] no existe tabla de mapeo, "
                  "el dato original no se puede recuperar desde la base.\n")


def moment_2(raw_tickets: list[dict], embedder: OllamaEmbedder):
    console.print(Rule("[bold cyan]MOMENTO 2: ingesta en la base vectorial ChromaDB"))
    t0 = time.perf_counter()
    records = prepare_records(raw_tickets, anonymize=True)
    total_pii = sum(r["metadata"]["pii_enmascaradas"] for r in records)
    console.print(f"Anonimizados [bold]{len(records)}[/bold] tickets "
                  f"([bold]{total_pii}[/bold] datos personales enmascarados) "
                  f"en {time.perf_counter() - t0:.1f} s")

    client = vectorstore.get_client()
    collection = vectorstore.get_collection(client, reset=True)
    t1 = time.perf_counter()
    with Progress(TextColumn(f"Embeddings con Ollama ({EMBEDDING_MODEL}) -> ChromaDB"),
                  BarColumn(), MofNCompleteColumn(), console=console) as progress:
        task = progress.add_task("ingesta", total=len(records))
        count = index_records(collection, records, embedder,
                              on_batch=lambda n: progress.advance(task, n))
    console.print(f"[bold green]{count}[/bold green] vectores guardados en "
                  f"[bold]{CHROMA_DIR.name}/[/bold] (métrica coseno, 1024 dimensiones) "
                  f"en {time.perf_counter() - t1:.1f} s")

    sample = collection.get(ids=[SHOWCASE_TICKET], include=["documents", "metadatas"])
    stored = Table(title=f"Así quedó guardado {SHOWCASE_TICKET} en ChromaDB",
                   title_justify="left", show_header=False)
    stored.add_column("Campo", style="bold")
    stored.add_column("Valor")
    stored.add_row("document", sample["documents"][0])
    for key, value in sample["metadatas"][0].items():
        stored.add_row(f"metadata.{key}", str(value))
    console.print(stored)
    console.print()
    return collection


def moment_3(collection, embedder: OllamaEmbedder) -> None:
    console.print(Rule("[bold cyan]MOMENTO 3: búsqueda semántica de tickets similares"))
    searcher = TicketSearcher(collection=collection, embedder=embedder)
    anon = get_anonymizer()
    for i, query in enumerate(DEMO_QUERIES, start=1):
        safe_query = anon.anonymize(query).text
        console.print(f"[bold]Consulta {i}:[/bold] {safe_query}")
        if safe_query != query:
            console.print("[dim](la consulta traía PII y se anonimizó antes de generar el embedding)[/dim]")
        q_tokens = keyword_tokens(safe_query)
        table = Table(show_lines=True)
        table.add_column("#", justify="right")
        table.add_column("Ticket")
        table.add_column("Score", justify="right")
        table.add_column("Categoría")
        table.add_column("Palabras en común", justify="center")
        table.add_column("Resolución aplicada", max_width=55)
        for rank, hit in enumerate(searcher.search(query, k=3), start=1):
            common = q_tokens & keyword_tokens(hit["document"])
            table.add_row(str(rank), hit["id"], f"{hit['score']:.3f}",
                          hit["metadata"]["categoria"],
                          ", ".join(sorted(common)) or "ninguna",
                          hit["metadata"]["resolucion"])
        console.print(table)
    console.print("[dim]Score = similitud coseno (1 = mismo significado). "
                  "Pocas o ninguna palabra en común: encuentra por significado, no por texto.[/dim]\n")


def hard_cases(tickets: dict) -> None:
    console.print(Rule("[bold yellow]EXTRA: casos difíciles (límites del enmascarado)"))
    anon = get_anonymizer()
    table = Table(show_lines=True)
    table.add_column("Ticket")
    table.add_column("Caso")
    table.add_column("Texto anonimizado", max_width=70)
    table.add_column("Resultado")
    for ticket_id, case, fragment in HARD_CASES:
        masked = anon.anonymize(tickets[ticket_id]["texto"]).text
        leaked = fragment.lower() in masked.lower()
        verdict = "[bold red]FALLA: se filtra[/bold red]" if leaked else "[bold green]OK[/bold green]"
        table.add_row(ticket_id, case, masked, verdict)
    console.print(table)
    console.print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo del buscador de tickets anonimizados")
    parser.add_argument("--pausa", action="store_true", help="espera ENTER entre momentos")
    parser.add_argument("--casos-dificiles", action="store_true",
                        help="muestra los casos donde el enmascarado falla")
    args = parser.parse_args()

    start = time.perf_counter()
    console.print(Panel.fit(
        "[bold]Buscador semántico de tickets de soporte con anonimización previa de PII[/bold]\n"
        "ticket crudo -> detección de PII -> enmascarado irreversible -> "
        "embedding local -> ChromaDB -> búsqueda semántica",
        border_style="cyan"))

    embedder = OllamaEmbedder()
    try:
        embedder.check_available()
    except EmbeddingServiceError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        return 1

    with console.status("Cargando modelo de spaCy y reconocedores de Presidio..."):
        get_anonymizer()
        embedder.embed_one("calentamiento")  # carga bge-m3 en memoria de Ollama

    raw_tickets = load_tickets()
    tickets = {t["id"]: t for t in raw_tickets}

    moment_1(tickets)
    pause(args.pausa)
    collection = moment_2(raw_tickets, embedder)
    pause(args.pausa)
    moment_3(collection, embedder)
    if args.casos_dificiles:
        pause(args.pausa)
        hard_cases(tickets)

    console.print(f"[bold green]Demo completa en {time.perf_counter() - start:.1f} s.[/bold green] "
                  "Siguiente paso: python scripts/audit_privacy.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
