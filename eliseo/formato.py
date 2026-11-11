"""Formateo para mostrarle datos al vecino (sin calcular nada)."""
import unicodedata
from decimal import Decimal

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def pesos(monto: Decimal) -> str:
    """Decimal('340000.00') → '$ 340.000,00'."""
    entero, dec = f"{monto:,.2f}".split(".")
    return f"$ {entero.replace(',', '.')},{dec}"


def nombre_periodo(periodo: str) -> str:
    """'2026-10' → 'octubre 2026'."""
    anio, mes = periodo.split("-")
    return f"{MESES[int(mes) - 1]} {anio}"


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y con espacios simples, para comparar textos."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return " ".join(sin_tildes.lower().split())
