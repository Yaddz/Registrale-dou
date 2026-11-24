"""Utilitários de versão da aplicação Registrale-DOU."""

from __future__ import annotations

import re
from pathlib import Path

from .paths import get_base_dir

_DEFAULT_VERSION = "0.1.0"


def get_app_version() -> str:
    """Retorna a versão atual do aplicativo (lida de VERSION, pyproject.toml ou metadata)."""
    base_dir = get_base_dir()
    version_file = base_dir / "VERSION"
    if version_file.is_file():
        text = version_file.read_text(encoding="utf-8").strip()
        if text:
            return text.lstrip("vV")

    pyproject = base_dir / "pyproject.toml"
    if pyproject.is_file():
        try:
            content = pyproject.read_text(encoding="utf-8")
            match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
            if match:
                return match.group(1).strip().lstrip("vV")
        except OSError:
            pass

    try:
        from importlib.metadata import version

        return version("registrale-dou").lstrip("vV")
    except Exception:
        return _DEFAULT_VERSION


def parse_version(version_str: str) -> tuple[int, ...]:
    """Converte uma string semântica (ex.: 'v0.2.1') em tupla comparável de inteiros."""
    cleaned = (version_str or "").strip().lstrip("vV")
    parts: list[int] = []
    for token in re.split(r"[.\-+]", cleaned):
        digits = re.match(r"^(\d+)", token)
        if digits:
            parts.append(int(digits.group(1)))
        elif parts:
            break
    return tuple(parts) if parts else (0,)


def is_newer_version(candidate: str, current: str | None = None) -> bool:
    """Retorna True se ``candidate`` for estritamente maior que ``current``."""
    cur = current or get_app_version()
    c_parts = list(parse_version(candidate))
    cur_parts = list(parse_version(cur))
    max_len = max(len(c_parts), len(cur_parts))
    c_parts.extend([0] * (max_len - len(c_parts)))
    cur_parts.extend([0] * (max_len - len(cur_parts)))
    return tuple(c_parts) > tuple(cur_parts)
