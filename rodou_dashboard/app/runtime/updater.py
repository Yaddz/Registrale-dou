"""Verificação e download seguro de atualizações via Releases do GitHub."""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from urllib.parse import urlparse

import requests

from .paths import get_data_dir
from .version import get_app_version, is_newer_version

logger = logging.getLogger(__name__)

DEFAULT_GITHUB_REPO = "Yaddz/Registrale-dou"
_TRUSTED_HOSTS = {
    "github.com",
    "api.github.com",
    "objects.githubusercontent.com",
    "release-assets.githubusercontent.com",
}
_SHA256_RE = re.compile(r"\b([0-9a-fA-F]{64})\b")


def get_github_repo() -> str:
    return (os.getenv("REGISTRALE_GITHUB_REPO") or DEFAULT_GITHUB_REPO).strip()


def _validate_trusted_url(url: str) -> None:
    parsed = urlparse(url or "")
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"URL de atualização não confiável (HTTPS obrigatório): {url}")
    host = parsed.hostname.lower()
    if host not in _TRUSTED_HOSTS and not host.endswith(".githubusercontent.com"):
        raise ValueError(f"Host de atualização não confiável: {host}")


def verify_sha256(file_path: Path, expected_sha256: str) -> bool:
    """Verifica o hash SHA-256 de um arquivo contra o valor esperado."""
    match = _SHA256_RE.search(expected_sha256 or "")
    if not match:
        return False
    expected_hex = match.group(1).lower()
    digest = hashlib.sha256()
    with open(file_path, "rb") as fh:
        while True:
            chunk = fh.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest().lower() == expected_hex


def check_for_updates(repo: str | None = None, timeout: int = 10) -> dict[str, Any]:
    """Consulta a última Release no GitHub e compara com a versão instalada."""
    target_repo = (repo or get_github_repo()).strip("/")
    current = get_app_version()
    api_url = f"https://api.github.com/repos/{target_repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Registrale-DOU/{current}",
    }

    resp = requests.get(api_url, headers=headers, timeout=timeout)
    if resp.status_code == 404:
        return {
            "update_available": False,
            "current_version": current,
            "latest_version": current,
            "repo": target_repo,
            "message": "Nenhuma release publicada no repositório.",
        }
    resp.raise_for_status()
    payload = resp.json() or {}

    tag_name = str(payload.get("tag_name") or "").strip()
    latest = tag_name.lstrip("vV") or current
    assets = payload.get("assets") or []

    installer_asset = None
    sha_asset = None
    for asset in assets:
        name = str(asset.get("name") or "")
        low = name.lower()
        if low.endswith(".exe") and "registrale-setup" in low:
            installer_asset = asset
        elif low.endswith(".sha256"):
            sha_asset = asset

    return {
        "update_available": is_newer_version(latest, current),
        "current_version": current,
        "latest_version": latest,
        "repo": target_repo,
        "release_url": payload.get("html_url"),
        "release_notes": payload.get("body") or "",
        "published_at": payload.get("published_at"),
        "installer_name": installer_asset.get("name") if installer_asset else None,
        "installer_url": installer_asset.get("browser_download_url") if installer_asset else None,
        "installer_size": installer_asset.get("size") if installer_asset else None,
        "sha256_url": sha_asset.get("browser_download_url") if sha_asset else None,
    }


def download_and_verify_update(
    installer_url: str,
    sha256_url: str,
    dest_dir: Path | None = None,
    expected_filename: str | None = None,
    timeout: int = 120,
) -> Path:
    """Baixa o instalador e o arquivo .sha256, valida o hash e retorna o caminho final."""
    _validate_trusted_url(installer_url)
    _validate_trusted_url(sha256_url)

    updates_dir = Path(dest_dir) if dest_dir else (get_data_dir(create=True) / "updates")
    updates_dir.mkdir(parents=True, exist_ok=True)

    raw_name = expected_filename or Path(urlparse(installer_url).path).name or "Registrale-Setup.exe"
    safe_name = Path(raw_name).name
    if not safe_name.lower().endswith(".exe"):
        safe_name = f"{safe_name}.exe"

    sha_resp = requests.get(sha256_url, timeout=30)
    sha_resp.raise_for_status()
    sha_text = sha_resp.text.strip()
    if not _SHA256_RE.search(sha_text):
        raise ValueError("Arquivo .sha256 inválido ou sem hash SHA-256 reconhecível.")

    target_path = updates_dir / safe_name
    tmp_path = updates_dir / f"{safe_name}.tmp"
    try:
        with requests.get(installer_url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            with open(tmp_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)

        if not verify_sha256(tmp_path, sha_text):
            raise ValueError("Falha na verificação SHA-256 do instalador baixado.")

        os.replace(tmp_path, target_path)
        logger.info("Instalador verificado salvo em %s", target_path)
        return target_path
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def launch_installer_windows(installer_path: Path) -> None:
    """Inicia o instalador baixado no Windows (preservando dados em %LOCALAPPDATA%\\Registrale)."""
    if os.name != "nt":
        raise RuntimeError("Execução automática do instalador .exe suportada apenas no Windows.")
    subprocess.Popen([str(installer_path)], close_fds=True)
