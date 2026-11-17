"""Validacion de cedula ecuatoriana (digito verificador modulo 10)."""

import pytest

from generate_data import cedula_check_digit, fake_cedula
from ticketsearch.anonymizer import is_valid_cedula


# Calculadas a mano: 171003406 -> suma 25 -> verificador 5
#                    091234567 -> suma 35 -> verificador 5
@pytest.mark.parametrize("value", ["1710034065", "0912345675"])
def test_valid_cedulas(value):
    assert is_valid_cedula(value)


@pytest.mark.parametrize("value, reason", [
    ("1710034064", "digito verificador incorrecto"),
    ("0912345678", "digito verificador incorrecto"),
    ("2510034065", "provincia 25 no existe"),
    ("0010034065", "provincia 00 no existe"),
    ("1760034065", "tercer digito 6 no es persona natural"),
    ("171003406", "solo 9 digitos"),
    ("17100340655", "11 digitos"),
    ("17100a4065", "contiene letras"),
])
def test_invalid_cedulas(value, reason):
    assert not is_valid_cedula(value), reason


def test_generator_only_produces_valid_cedulas():
    import random
    rng = random.Random(0)
    assert all(is_valid_cedula(fake_cedula(rng)) for _ in range(500))


def test_check_digit_examples():
    # 1*2 + 1*1 = 3 -> (10 - 3) % 10 = 7
    assert cedula_check_digit("110000000") == 7
    # producto mayor a 9 se le resta 9: 8*2=16->7, +1 = 8 -> verificador 2
    assert cedula_check_digit("810000000") == 2


def test_check_digit_when_sum_is_multiple_of_ten():
    # 0*2 + 9*1 + 0*2 + 1*1 = 10 -> el verificador es 0, no 10
    assert cedula_check_digit("090100000") == 0
    assert is_valid_cedula("0901000000")

