"""Deteccion de cada tipo de PII y verificacion de que el enmascarado no deja PII."""

import re

import pytest

from generate_data import FIRST_NAMES, LAST_NAMES
from ticketsearch.anonymizer import AnonymizedText
from ticketsearch.audit import BLOCKING_PATTERNS

# Casos dificiles documentados donde se ESPERA que el enmascarado falle
KNOWN_HARD_FAILURES = {"TCK-0085"}  # correo escrito como "x arroba example punto com"


def entity_types(anonymizer, text):
    return [r.entity_type for r in anonymizer.analyze(text)]


# ---------------------------- deteccion por tipo ----------------------------

@pytest.mark.parametrize("text", [
    "Buenos días, mi nombre es María Fernanda Torres.",
    "Hola, les escribe Juan Pablo Quishpe.",
    "Buenas tardes. Soy Mónica Guerrero Jaramillo.",
    "Me llamo Pedro Pablo León y necesito ayuda.",
])
def test_detects_person(anonymizer, text):
    assert "PERSON" in entity_types(anonymizer, text)


@pytest.mark.parametrize("text", [
    "Mi cédula es 1710034065.",
    "C.I. 0912345675, gracias.",
])
def test_detects_valid_cedula(anonymizer, text):
    assert "EC_CEDULA" in entity_types(anonymizer, text)


def test_ignores_invalid_cedula(anonymizer):
    # 10 digitos con verificador incorrecto: no es cedula (y no empieza con 09)
    assert "EC_CEDULA" not in entity_types(anonymizer, "Pedido 1710034064 registrado")


@pytest.mark.parametrize("text", [
    "mi celular 0987654321",
    "llamar al 098 765 4321",
    "teléfono 098-765-4321",
    "WhatsApp +593987654321",
    "número +593 98 765 4321",
])
def test_detects_ecuadorian_phone(anonymizer, text):
    assert "EC_PHONE" in entity_types(anonymizer, text)


@pytest.mark.parametrize("text", [
    "escríbanme a ana.torres12@example.com",
    "correo: jperez@correo.example por favor",
])
def test_detects_email(anonymizer, text):
    assert "EMAIL_ADDRESS" in entity_types(anonymizer, text)


def test_guayas_cedula_is_labeled_as_cedula_not_phone(anonymizer):
    # 0912345675 tambien calza con el patron de celular 09...; gana la cedula validada
    masked = anonymizer.anonymize("Cédula 0912345675").text
    assert masked == "Cédula [CEDULA]"


def test_no_false_positives_on_common_words(anonymizer):
    text = "Gracias de antemano. Pueden contactarme. Olvidé mi contraseña de Office en Android."
    assert anonymizer.anonymize(text).text == text


# ---------------------------- enmascarado ----------------------------

def test_full_ticket_masking(anonymizer):
    raw = ("Saludos, soy Wilson Ruiz Pazmiño. La app se cierra. Gracias de antemano. "
           "Wilson Ruiz Pazmiño, CI 1710034065, wilson.ruiz52@example.net, 0999432627.")
    result = anonymizer.anonymize(raw)
    assert result.text == ("Saludos, soy [PERSONA]. La app se cierra. Gracias de antemano. "
                           "[PERSONA], CI [CEDULA], [EMAIL], [TELEFONO].")
    assert result.counts == {"[PERSONA]": 2, "[CEDULA]": 1, "[EMAIL]": 1, "[TELEFONO]": 1}


def test_result_keeps_no_mapping_to_original_values(anonymizer):
    # Irreversibilidad: el resultado solo expone el texto enmascarado y conteos
    result = anonymizer.anonymize("Soy Ana Paredes, cédula 1710034065")
    assert set(vars(result)) == {"text", "counts"}
    assert isinstance(result, AnonymizedText)
    assert "1710034065" not in repr(result) and "Ana" not in repr(result)


def test_masking_leaves_no_structured_pii_in_dataset(anonymizer, tickets):
    """Ningun ticket anonimizado conserva cedula, correo o telefono (regex de la auditoria)."""
    leaks = {}
    for t in tickets:
        masked = anonymizer.anonymize(t["texto"]).text
        found = [k for k, p in BLOCKING_PATTERNS.items() if p.search(masked)]
        if found:
            leaks[t["id"]] = found
    assert leaks == {}


def test_masking_removes_generated_names(anonymizer, tickets):
    """Ninguna palabra de los nombres generados sobrevive, salvo casos dificiles documentados."""
    name_words = {w.lower() for n in FIRST_NAMES + LAST_NAMES for w in n.split()}
    leaks = {}
    for t in tickets:
        masked = anonymizer.anonymize(t["texto"]).text
        left = [w for w in re.findall(r"\w+", masked) if w.lower() in name_words]
        if left:
            leaks[t["id"]] = left
    assert set(leaks) == KNOWN_HARD_FAILURES, leaks


def test_quasi_identifier_is_not_detected(anonymizer):
    """Limite conocido: un cargo unico identifica a la persona y NO se enmascara."""
    text = "Les escribe el decano de la Facultad de Ingeniería de la sede Loja."
    assert anonymizer.anonymize(text).text == text
