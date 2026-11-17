"""Deteccion y enmascarado irreversible de PII en tickets en espanol.

Se usa Presidio con:
- spaCy es_core_news_md (NER + etiquetas gramaticales) y reglas de
  contexto para nombres de personas (PERSON).
- Reconocedores propios para cedula ecuatoriana (con digito verificador),
  telefonos ecuatorianos y correos electronicos.

No se cargan los reconocedores predefinidos de Presidio: estan pensados
para ingles, generan falsos positivos (por ejemplo URL dentro de correos)
y algunos dependen de tldextract, que puede intentar conectarse a internet.

El enmascarado es IRREVERSIBLE: cada dato se reemplaza por una etiqueta
fija ([PERSONA], [CEDULA], ...). No se genera ni se guarda ninguna tabla
de mapeo entre el valor original y la etiqueta.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

from presidio_analyzer import (
    LocalRecognizer,
    AnalyzerEngine,
    Pattern,
    PatternRecognizer,
    RecognizerRegistry,
    RecognizerResult,
)
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from .config import SPACY_MODEL

LANGUAGE = "es"

# Entidad de Presidio -> etiqueta que queda en el texto
ENTITY_LABELS = {
    "PERSON": "[PERSONA]",
    "EC_CEDULA": "[CEDULA]",
    "EMAIL_ADDRESS": "[EMAIL]",
    "EC_PHONE": "[TELEFONO]",
}

# Terminos del dominio que el NER de spaCy confunde a veces con nombres de
# personas. Enmascararlos no filtra datos, pero si quita contexto util.
DOMAIN_ALLOW_LIST = [
    "Cálculo II", "Programación I", "Programación II", "Física", "Matlab",
    "Office", "Android", "iPhone", "Huawei", "SRI", "IESS", "RUC", "SMS",
    "Trámites", "Contabilidad", "CI", "C.I.",
]

MIN_SCORE = 0.5


def is_valid_cedula(value: str) -> bool:
    """Valida una cedula ecuatoriana de persona natural.

    Reglas: 10 digitos, provincia 01-24, tercer digito 0-5 y digito
    verificador por modulo 10 con coeficientes 2,1,2,1,2,1,2,1,2.
    """
    if not re.fullmatch(r"\d{10}", value):
        return False
    province = int(value[:2])
    if not 1 <= province <= 24:
        return False
    if int(value[2]) > 5:
        return False
    total = 0
    for i, ch in enumerate(value[:9]):
        product = int(ch) * (2 if i % 2 == 0 else 1)
        total += product - 9 if product > 9 else product
    check = (10 - total % 10) % 10
    return check == int(value[9])


class EcuadorCedulaRecognizer(PatternRecognizer):
    """Cedula ecuatoriana: 10 digitos validados con el digito verificador."""

    PATTERNS = [Pattern("cedula_10_digitos", r"(?<!\d)\d{10}(?!\d)", 0.4)]
    CONTEXT = ["cédula", "cedula", "ci", "c.i.", "identidad", "identificación"]

    def __init__(self) -> None:
        super().__init__(
            supported_entity="EC_CEDULA",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=LANGUAGE,
            name="EcuadorCedulaRecognizer",
        )

    def validate_result(self, pattern_text: str) -> bool:
        # True sube el score a 1.0; False descarta la coincidencia
        return is_valid_cedula(pattern_text)


class EcuadorPhoneRecognizer(PatternRecognizer):
    """Telefonos de Ecuador: celular 09xxxxxxxx y formato internacional +593."""

    PATTERNS = [
        # Celular nacional: 0987654321, 098 765 4321, 098-765-4321
        Pattern("celular_nacional", r"(?<![\d+])09\d(?:[\s-]?\d){7}(?!\d)", 0.6),
        # Internacional: +593987654321, +593 98 765 4321, +593 2 234 5678
        Pattern("internacional_593", r"\+593[\s-]?\d(?:[\s-]?\d){7,8}(?!\d)", 0.7),
    ]
    CONTEXT = ["celular", "teléfono", "telefono", "número", "numero", "celu",
               "llamar", "whatsapp", "contactarme"]

    def __init__(self) -> None:
        super().__init__(
            supported_entity="EC_PHONE",
            patterns=self.PATTERNS,
            context=self.CONTEXT,
            supported_language=LANGUAGE,
            name="EcuadorPhoneRecognizer",
        )


class EmailRecognizer(PatternRecognizer):
    """Correo electronico por expresion regular (sin consultas a internet)."""

    PATTERNS = [Pattern("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\b", 0.9)]

    def __init__(self) -> None:
        super().__init__(
            supported_entity="EMAIL_ADDRESS",
            patterns=self.PATTERNS,
            supported_language=LANGUAGE,
            name="EmailRecognizerEs",
        )


class SpanishPersonRecognizer(LocalRecognizer):
    """Nombres de personas combinando el NER de spaCy con reglas simples.

    Por que no basta el NER solo (lo medimos con el dataset):
    - A veces etiqueta como persona palabras comunes ("Gracias", "Pueden", "hola").
    - A veces corta el nombre ("Wilson" queda fuera de "Ruiz Pazmiño").
    - Tras "Soy" suele etiquetar la frase como MISC y el nombre se escapa.

    Reglas:
    1. Entidades PERSON del NER: se recortan saludos y palabras vacias de los
       bordes y se descartan si no queda ningun nombre propio (PROPN).
    2. Se extienden a los nombres propios contiguos.
    3. Regla de contexto: los nombres propios que siguen a "soy", "me llamo",
       "mi nombre es", "les escribe" o "habla" se marcan como persona.
    """

    NER_SCORE = 0.85
    CUE_SCORE = 0.75
    CUE_WORDS = {"soy", "llamo", "escribe", "habla", "atentamente"}
    CONNECTORS = {"de", "del", "la", "los"}
    NOT_NAMES = {
        "hola", "buenas", "buenos", "saludos", "gracias", "estimados", "estimado",
        "soy", "cédula", "cedula", "ci", "c.i.", "datos", "adjunto", "pueden",
        "email", "correo", "teléfono", "telefono", "celular", "número", "contacto",
    }

    def __init__(self) -> None:
        super().__init__(supported_entities=["PERSON"], supported_language=LANGUAGE,
                         name="SpanishPersonRecognizer")

    def load(self) -> None:  # el modelo de spaCy ya lo carga el NlpEngine
        pass

    def _is_name_token(self, token) -> bool:
        return (token.pos_ == "PROPN" and token.is_alpha
                and token.lower_ not in self.NOT_NAMES
                and token.text not in DOMAIN_ALLOW_LIST)

    def _cue_spans(self, doc) -> list[tuple[int, int]]:
        spans = []
        for i, tok in enumerate(doc):
            is_cue = tok.lower_ in self.CUE_WORDS or (
                tok.lower_ == "es" and i > 0 and doc[i - 1].lower_ == "nombre")
            if not is_cue:
                continue
            j = i + 1
            end = j
            while j < len(doc) and (self._is_name_token(doc[j])
                                    or (doc[j].lower_ in self.CONNECTORS and end > i + 1)):
                j += 1
                if self._is_name_token(doc[j - 1]):
                    end = j
            if end > i + 1:
                spans.append((i + 1, end))
        return spans

    def analyze(self, text, entities, nlp_artifacts=None):
        if not nlp_artifacts or "PERSON" not in entities:
            return []
        doc = nlp_artifacts.tokens
        candidates = [(ent.start, ent.end, self.NER_SCORE)
                      for ent in nlp_artifacts.entities if ent.label_ == "PERSON"]
        candidates += [(s, e, self.CUE_SCORE) for s, e in self._cue_spans(doc)]

        results = []
        for start, end, score in candidates:
            # 1. recortar bordes que no son nombres
            while start < end and not self._is_name_token(doc[start]):
                start += 1
            while end > start and not self._is_name_token(doc[end - 1]):
                end -= 1
            if start >= end:
                continue
            # 2. extender a nombres propios contiguos
            while start > 0 and self._is_name_token(doc[start - 1]):
                start -= 1
            while end < len(doc) and self._is_name_token(doc[end]):
                end += 1
            span = doc[start:end]
            results.append(RecognizerResult("PERSON", span.start_char, span.end_char, score))
        return results


@dataclass
class AnonymizedText:
    """Resultado del enmascarado. Solo guarda el texto ya anonimizado y
    cuantas entidades de cada tipo se encontraron; nunca los valores."""

    text: str
    counts: Counter = field(default_factory=Counter)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def _resolve_overlaps(results: list[RecognizerResult]) -> list[RecognizerResult]:
    """Si dos detecciones se solapan, gana la de mayor score (y luego la mas larga).

    Ejemplo: una cedula de Guayas (09...) tambien calza con el patron de
    celular; la validacion del digito verificador le da score 1.0 y gana.
    """
    ordered = sorted(results, key=lambda r: (-r.score, -(r.end - r.start)))
    kept: list[RecognizerResult] = []
    for res in ordered:
        if all(res.end <= k.start or res.start >= k.end for k in kept):
            kept.append(res)
    return sorted(kept, key=lambda r: r.start)


class PiiAnonymizer:
    """Envuelve Presidio con la configuracion para espanol de Ecuador."""

    def __init__(self, spacy_model: str = SPACY_MODEL) -> None:
        nlp_config = {
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": LANGUAGE, "model_name": spacy_model}],
        }
        nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()

        registry = RecognizerRegistry(supported_languages=[LANGUAGE])
        registry.add_recognizer(SpanishPersonRecognizer())
        registry.add_recognizer(EcuadorCedulaRecognizer())
        registry.add_recognizer(EcuadorPhoneRecognizer())
        registry.add_recognizer(EmailRecognizer())

        self.analyzer = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine,
                                       supported_languages=[LANGUAGE])
        self.anonymizer = AnonymizerEngine()
        self.operators = {
            entity: OperatorConfig("replace", {"new_value": label})
            for entity, label in ENTITY_LABELS.items()
        }

    def analyze(self, text: str) -> list[RecognizerResult]:
        """Devuelve las posiciones de PII detectadas (solo en memoria)."""
        results = self.analyzer.analyze(
            text=text,
            language=LANGUAGE,
            entities=list(ENTITY_LABELS),
            score_threshold=MIN_SCORE,
            allow_list=DOMAIN_ALLOW_LIST,
        )
        return _resolve_overlaps(results)

    def anonymize(self, text: str) -> AnonymizedText:
        """Reemplaza cada PII por su etiqueta. Irreversible por diseno."""
        results = self.analyze(text)
        output = self.anonymizer.anonymize(text=text, analyzer_results=results,
                                           operators=self.operators)
        counts = Counter(ENTITY_LABELS[r.entity_type] for r in results)
        return AnonymizedText(text=output.text, counts=counts)


@lru_cache(maxsize=1)
def get_anonymizer() -> PiiAnonymizer:
    """Instancia unica (cargar spaCy toma unos segundos)."""
    return PiiAnonymizer()
