"""Lädt calc.py direkt per Dateipfad.

Ein normaler Import über das Paket würde custom_components/pv_management_fix/
__init__.py ausführen und damit Home Assistant voraussetzen. calc.py ist
bewusst HA-frei und wird hier isoliert geladen.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

_CALC_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components" / "pv_management_fix" / "calc.py"
)


def _load_calc():
    spec = importlib.util.spec_from_file_location("pv_management_fix_calc", _CALC_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def calc():
    return _load_calc()
