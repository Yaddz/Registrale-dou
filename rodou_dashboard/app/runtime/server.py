"""Ponto de entrada único (`uv run registrale`) para o modo local do Registrale-DOU.

Sobe o painel Flask via `waitress` (1 processo, 8 threads), garante instância única
com lock de arquivo no diretório de dados, configura logs com rotação e inicia o
APScheduler com jobstore SQLite.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import logging
import os
from pathlib import Path
import sys
from typing import IO, Iterator, Optional

from .logging_setup import configure_logging
from .paths import get_data_dir, get_db_path

logger = logging.getLogger(__name__)


class InstanceLockError(RuntimeError):
    """Lançada quando outra instância do Registrale já está em execução."""


def _lock_file_descriptor(fh: IO[str]) -> None:
    if os.name == "nt":
        import msvcrt

        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file_descriptor(fh: IO[str]) -> None:
    if os.name == "nt":
        import msvcrt

        try:
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
    else:
        import fcntl

        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass


@contextmanager
def acquire_instance_lock(lock_path: Optional[Path] = None) -> Iterator[Path]:
    """Adquire lock exclusivo não-bloqueante para impedir múltiplas instâncias."""
    target = Path(lock_path) if lock_path is not None else (get_data_dir(create=True) / "registrale.lock")
    target.parent.mkdir(parents=True, exist_ok=True)

    # Abre em r+/a+ para não truncar antes de obter o lock
    fh = open(target, "a+", encoding="utf-8")
    try:
        try:
            _lock_file_descriptor(fh)
        except OSError as exc:
            raise InstanceLockError(
                f"Outra instância do Registrale já está em execução (lock: {target})."
            ) from exc

        fh.seek(0)
        fh.truncate()
        fh.write(f"{os.getpid()}\n")
        fh.flush()
        yield target
    finally:
        _unlock_file_descriptor(fh)
        try:
            fh.close()
        except Exception:
            pass


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="registrale",
        description="Servidor local do Registrale-DOU (waitress + APScheduler).",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("REGISTRALE_HOST", "127.0.0.1"),
        help="Endereço de escuta HTTP (padrão: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("REGISTRALE_PORT", "5000")),
        help="Porta HTTP (padrão: 5000).",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=int(os.getenv("REGISTRALE_THREADS", "8")),
        help="Número de threads do waitress (padrão: 8).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    """Inicia o servidor local do Registrale-DOU."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = _parse_args(argv)
    os.environ.setdefault("REGISTRALE_DB_PATH", str(get_db_path()))

    log_file = configure_logging()
    logger.info("Iniciando Registrale-DOU (log=%s)...", log_file)

    try:
        with acquire_instance_lock():
            from waitress import serve

            from .. import create_app
            from .executor import get_executor
            from .pg_portable import start_portable_postgres, stop_portable_postgres
            from .scheduler import init_scheduler, shutdown_scheduler

            app = create_app()
            pg_port = start_portable_postgres()
            if pg_port is not None:
                logger.info("PostgreSQL portátil INLABS ativo na porta %d.", pg_port)
            init_scheduler(app, start=True)

            logger.info(
                "Painel Registrale-DOU disponível em http://%s:%d (threads=%d)",
                args.host,
                args.port,
                args.threads,
            )
            try:
                serve(app, host=args.host, port=args.port, threads=args.threads)
            except KeyboardInterrupt:
                logger.info("Encerramento solicitado pelo usuário.")
            finally:
                shutdown_scheduler(wait=False)
                executor = get_executor(app)
                if hasattr(executor, "shutdown"):
                    executor.shutdown(wait=False)
                stop_portable_postgres()
    except InstanceLockError as exc:
        logger.error("%s", exc)
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
