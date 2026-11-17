"""Evaluacion: cuanto se degrada la busqueda al anonimizar?

Compara tres configuraciones con las mismas 15 consultas parafraseadas:
  1. Busqueda vectorial indexando el texto CRUDO (con PII)
  2. Busqueda vectorial indexando el texto ANONIMIZADO (la solucion)
  3. Busqueda por palabras clave sobre el texto anonimizado (linea base)

Metricas:
  - recall@3: proporcion de consultas cuyo ticket esperado aparece en el top 3.
  - hit@3 escenario: el top 3 trae al menos un ticket con la misma resolucion
    (en el dataset cada problema tiene 3 tickets redactados distinto).
  - MRR: promedio de 1/posicion del ticket esperado (0 si no aparece en el top 10).

Ambos indices viven SOLO en memoria (EphemeralClient): el texto crudo nunca
se escribe en la carpeta chroma_db. Los numeros se calculan en cada corrida;
no hay valores fijos en el codigo.

Uso (PowerShell):
    python scripts/evaluate.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ticketsearch.console import setup_console  # noqa: E402

console = setup_console()

from rich.table import Table  # noqa: E402

from ticketsearch import vectorstore  # noqa: E402
from ticketsearch.anonymizer import get_anonymizer  # noqa: E402
from ticketsearch.embedder import OllamaEmbedder  # noqa: E402
from ticketsearch.ingest import index_records, load_tickets, prepare_records  # noqa: E402
from ticketsearch.search import KeywordSearcher  # noqa: E402

K = 3
DEPTH = 10  # profundidad para calcular MRR

# (consulta parafraseada, ticket esperado). Las consultas evitan a proposito
# las palabras exactas del ticket esperado.
EVAL_QUERIES = [
    ("el sistema me dejó afuera después de fallar la clave varias veces", "TCK-0074"),
    ("no recibo el link para recuperar mi password", "TCK-0050"),
    ("aparece el mismo cargo de la mensualidad duplicado en mi tarjeta", "TCK-0008"),
    ("transferí hace días pero sigo figurando como moroso", "TCK-0034"),
    ("¿puedo cancelar el semestre por partes, mes a mes?", "TCK-0014"),
    ("el comprobante tiene equivocado el número tributario de la compañía", "TCK-0090"),
    ("quiero que el comprobante lo emitan para la empresa donde trabajo, que es quien paga el posgrado", "TCK-0069"),
    ("todavía no me ha llegado el documento electrónico de lo que aboné la semana pasada", "TCK-0085"),
    ("la aplicación se cae al iniciarla en mi teléfono", "TCK-0021"),
    ("ya no me avisan en el celular cuando suben las notas", "TCK-0039"),
    ("no alcancé lugar en la asignatura porque el paralelo está completo", "TCK-0059"),
    ("aprobé la materia previa pero el sistema no me habilita la siguiente", "TCK-0052"),
    ("requiero una constancia de matrícula para el seguro social", "TCK-0027"),
    ("mi portátil no se engancha a la red sin cables del campus", "TCK-0053"),
    ("la plataforma no me deja entregar el deber, sale error al subir el documento", "TCK-0068"),
]


def rank_of(expected: str, ids: list[str]) -> int | None:
    return ids.index(expected) + 1 if expected in ids else None


def evaluate_config(search_fn, resolution_of: dict) -> dict:
    ranks, hits, details = [], 0, []
    for query, expected in EVAL_QUERIES:
        ids = search_fn(query)
        rank = rank_of(expected, ids)
        ranks.append(rank)
        same_scenario = any(resolution_of[i] == resolution_of[expected] for i in ids[:K])
        hits += same_scenario
        details.append(rank)
    n = len(EVAL_QUERIES)
    return {
        "recall": sum(1 for r in ranks if r and r <= K) / n,
        "hit_scenario": hits / n,
        "mrr": sum(1 / r for r in ranks if r) / n,
        "ranks": details,
    }


def main() -> int:
    t0 = time.perf_counter()
    embedder = OllamaEmbedder()
    embedder.check_available()
    anonymizer = get_anonymizer()

    tickets = load_tickets()
    resolution_of = {t["id"]: t["resolucion"] for t in tickets}
    raw_records = prepare_records(tickets, anonymize=False)
    anon_records = prepare_records(tickets, anonymize=True)

    client = vectorstore.get_client(persistent=False)
    raw_col = vectorstore.get_collection(client, name="eval_crudo", reset=True)
    anon_col = vectorstore.get_collection(client, name="eval_anonimizado", reset=True)
    with console.status("Generando embeddings para ambos índices (en memoria)..."):
        index_records(raw_col, raw_records, embedder)
        index_records(anon_col, anon_records, embedder)
        query_vectors = {q: embedder.embed_one(anonymizer.anonymize(q).text) for q, _ in EVAL_QUERIES}
    keyword = KeywordSearcher(anon_records)

    def vector_search(collection):
        return lambda q: [h["id"] for h in vectorstore.query(collection, query_vectors[q], k=DEPTH)]

    results = {
        "Vectorial, texto crudo (con PII)": evaluate_config(vector_search(raw_col), resolution_of),
        "Vectorial, texto anonimizado": evaluate_config(vector_search(anon_col), resolution_of),
        "Palabras clave, texto anonimizado": evaluate_config(
            lambda q: [h["id"] for h in keyword.search(q, k=DEPTH)], resolution_of),
    }

    summary = Table(title=f"Resultados con {len(EVAL_QUERIES)} consultas parafraseadas "
                          f"sobre {len(tickets)} tickets", title_justify="left")
    summary.add_column("Configuración", style="bold")
    summary.add_column("recall@3", justify="right")
    summary.add_column("hit@3 escenario", justify="right")
    summary.add_column("MRR", justify="right")
    for name, r in results.items():
        summary.add_row(name, f"{r['recall']:.2f}", f"{r['hit_scenario']:.2f}", f"{r['mrr']:.3f}")
    console.print(summary)

    detail = Table(title="Posición del ticket esperado por consulta (- = fuera del top 10)",
                   title_justify="left")
    detail.add_column("#", justify="right")
    detail.add_column("Consulta", max_width=60)
    detail.add_column("Esperado")
    for name in ("Crudo", "Anonimizado", "Palabras clave"):
        detail.add_column(name, justify="center")
    columns = [r["ranks"] for r in results.values()]
    for i, (query, expected) in enumerate(EVAL_QUERIES):
        cells = []
        for ranks in columns:
            rank = ranks[i]
            style = "green" if rank and rank <= K else "red"
            cells.append(f"[{style}]{rank if rank else '-'}[/{style}]")
        detail.add_row(str(i + 1), query, expected, *cells)
    console.print(detail)

    raw_r = results["Vectorial, texto crudo (con PII)"]["recall"]
    anon_r = results["Vectorial, texto anonimizado"]["recall"]
    kw_r = results["Palabras clave, texto anonimizado"]["recall"]
    console.print(f"Diferencia recall@3 (anonimizado - crudo): [bold]{anon_r - raw_r:+.2f}[/bold]  |  "
                  f"vectorial anonimizado vs palabras clave: [bold]{anon_r - kw_r:+.2f}[/bold]")
    console.print(f"[dim]Tiempo total: {time.perf_counter() - t0:.1f} s. "
                  "Los índices de evaluación se descartan al terminar.[/dim]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
