"""Bootstrap do shim do Airflow para o modo local do Registrale-DOU."""

from __future__ import annotations

import importlib.machinery
import sys
from pathlib import Path

SHIM_DIR = Path(__file__).resolve().parent / "airflow_shim"


def is_airflow_installed() -> bool:
    """Retorna True se o Apache Airflow real estiver disponível no ambiente."""
    loaded = sys.modules.get("airflow")
    if loaded is not None:
        return not getattr(loaded, "__is_registrale_shim__", False)

    non_shim_paths = [
        p for p in sys.path if Path(p).resolve() != SHIM_DIR
    ]
    spec = importlib.machinery.PathFinder.find_spec("airflow", path=non_shim_paths)
    return spec is not None


def install_airflow_shim() -> bool:
    """Instala o shim ``compat/airflow_shim`` no ``sys.path`` se o Airflow real não existir.

    Retorna ``True`` se o shim foi ativado (ou já estava ativo) e ``False`` se o
    Airflow real já estiver instalado no ambiente.
    """
    if is_airflow_installed():
        return False

    shim_str = str(SHIM_DIR)
    if shim_str not in sys.path:
        sys.path.insert(0, shim_str)
    return True


def uninstall_airflow_shim() -> None:
    """Remove o shim do ``sys.path`` e limpa módulos do shim em ``sys.modules``."""
    shim_str = str(SHIM_DIR)
    sys.path[:] = [p for p in sys.path if p != shim_str]
    loaded = sys.modules.get("airflow")
    if loaded is not None and getattr(loaded, "__is_registrale_shim__", False):
        for name in list(sys.modules):
            if name == "airflow" or name.startswith("airflow."):
                del sys.modules[name]
