"""Leitura e renderização do Manual do usuário (``docs/manual/``).

O Markdown de ``docs/manual/`` é a única fonte do manual: o painel mostra o
mesmo texto na aba Manual (HTML gerado aqui) e oferece o download em ``.md``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import markdown
from markdown.extensions.toc import slugify_unicode

# Link entre capítulos: "02_empresas.md" ou "02_empresas.md#ancora".
_CHAPTER_LINK = re.compile(r'href="(?P<file>[\w.-]+\.md)(?:#(?P<anchor>[^"]*))?"')


@dataclass(frozen=True)
class ManualSection:
    """Um capítulo do manual, já em HTML."""

    id: str
    title: str
    html: str


def find_manual_dir(candidates: list[Path]) -> Path | None:
    """Retorna o primeiro diretório existente da lista."""
    return next((d for d in candidates if d.is_dir()), None)


def list_manual_files(manual_dir: Path) -> list[Path]:
    """Capítulos em ordem: ``README.md`` primeiro, depois por nome."""
    files = [f for f in manual_dir.glob("*.md") if f.is_file()]
    return sorted(files, key=lambda p: (0 if p.name.lower() == "readme.md" else 1, p.name))


def build_manual_markdown(files: list[Path]) -> str:
    """Junta os capítulos num único Markdown (download ``MANUAL.md``)."""
    parts = [f.read_text(encoding="utf-8").strip() for f in files]
    joined = "\n\n---\n\n".join(p for p in parts if p)
    return joined + "\n" if joined else ""


def _section_id(path: Path) -> str:
    return "manual-" + slugify_unicode(path.stem, "-")


def _first_heading(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def build_manual_sections(files: list[Path]) -> list[ManualSection]:
    """Renderiza cada capítulo em HTML, com links entre capítulos apontando para a própria página."""
    ids = {f.name: _section_id(f) for f in files}

    def _rewrite(match: re.Match[str]) -> str:
        target = ids.get(match.group("file"))
        if target is None:
            return match.group(0)
        anchor = match.group("anchor")
        return f'href="#{anchor or target}"'

    sections: list[ManualSection] = []
    for path in files:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        html = markdown.markdown(
            text,
            extensions=["tables", "sane_lists", "toc"],
            extension_configs={"toc": {"slugify": slugify_unicode}},
        )
        html = _CHAPTER_LINK.sub(_rewrite, html)
        sections.append(ManualSection(id=ids[path.name], title=_first_heading(text, path.stem), html=html))
    return sections
