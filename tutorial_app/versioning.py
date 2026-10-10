"""Versiones calendario compartidas por la aplicación y el empaquetado."""
import re
from datetime import date


def version_key(value: str) -> tuple[int, int, int, int]:
    if value == "0.6.0":
        return (0, 0, 0, 0)
    match = re.fullmatch(r"(\d{4})\.(\d{2})\.(\d{2})(?:\.([2-9]\d*|1\d+))?", value)
    if not match:
        raise ValueError(f"Versión calendario inválida: {value}")
    year, month, day = map(int, match.group(1, 2, 3))
    date(year, month, day)
    sequence = int(match.group(4) or 1)
    if sequence > 65535:
        raise ValueError("Consecutivo fuera del rango de Windows")
    return year, month, day, sequence


def release_version(tag: str) -> str:
    if not tag.startswith("v."):
        raise ValueError("La etiqueta debe comenzar por v.")
    value = tag[2:]
    if version_key(value)[0] == 0:
        raise ValueError("La publicación debe usar una fecha")
    return value
