"""Shim mínimo do pacote ``airflow`` para execução local sem Airflow."""

from __future__ import annotations

__is_registrale_shim__ = True


class DAG:
    """Stub de ``airflow.DAG`` — não utilizado no modo local."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "airflow.DAG não é suportado no modo local do Registrale-DOU; "
            "as buscas são executadas diretamente sem geração de DAGs."
        )
