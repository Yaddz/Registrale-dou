"""Busca na API do DOU com limite de tempo por termo e parada antecipada (circuit breaker).

O ``DOUSearcher`` do upstream empilha duas camadas de retry: o hook
(``DOUHook._request_page``: N tentativas × timeout + backoff) dentro de
``_search_text_with_retry`` (5 tentativas × 30 s). Com o portal ``in.gov.br`` fora do ar
(26/11/2026: ReadTimeout de 35 s e 502), cada CNPJ ficava ~12 min preso e a rotina de
122 CNPJs passaria de 24 h; o primeiro termo que esgotasse as tentativas abortava a
rotina inteira.

Este buscador troca só a camada de fora:

* no máximo ``REGISTRALE_DOU_TERM_RETRIES`` novas tentativas (padrão 1) depois de
  ``REGISTRALE_DOU_TERM_RETRY_SLEEP`` segundos (padrão 10); ``SSLError`` não repete;
* falha isolada de um termo: ``WARNING``, termo guardado em ``failed_terms`` e ``[]``
  (a rotina segue para o próximo CNPJ);
* ``REGISTRALE_DOU_BREAKER`` falhas **consecutivas** (padrão 3) levantam
  ``DouPortalUnavailable``; um sucesso zera o contador.

Pior caso com o portal fora (padrões; hook com ``REGISTRALE_DOU_TIMEOUT=20`` e
``REGISTRALE_DOU_MAX_RETRIES=2``):

* uma chamada do hook: 20 s + 5 s (backoff) + 20 s = **45 s**;
* um CNPJ: 45 s + 10 s + 45 s = **100 s** (mais o intervalo de raspagem de até 2 s);
* a rotina inteira: o breaker abre no 3º CNPJ seguido → 3 × 100 s ≈ **5 min**, não importa
  quantos CNPJs existam. Erros rápidos (502) custam bem menos: ~5 s + 10 s + 5 s por CNPJ.

O estado (``failed_terms`` e o contador) é da instância e reiniciado a cada
``exec_search``; não há estado global.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import requests

from .runner import _ensure_src_imports

_ensure_src_imports()
from searchers import DOUSearcher  # noqa: E402  (depende do sys.path montado acima)
from utils.cnpj import cnpj_root, format_root  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_TERM_RETRIES = 1
DEFAULT_TERM_RETRY_SLEEP = 10.0
DEFAULT_BREAKER = 3


class DouPortalUnavailable(RuntimeError):
    """O portal do DOU falhou em ``threshold`` termos seguidos: a API foi abandonada."""

    def __init__(self, last_error: str, failures: int, failed_terms: Optional[List[str]] = None) -> None:
        self.last_error = last_error
        self.failures = failures
        self.failed_terms = list(failed_terms or [])
        super().__init__(f"{failures} consultas seguidas sem resposta; último erro: {last_error}")


def _env_int(name: str, default: int, minimum: int = 0) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


class ResilientDOUSearcher(DOUSearcher):
    """``DOUSearcher`` que não trava a rotina quando o portal está fora do ar."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.failed_terms: List[str] = []
        self.consecutive_failures = 0
        self.last_error = ""
        self._query_to_terms: Dict[str, List[str]] = {}

    def exec_search(self, *args: Any, **kwargs: Any) -> Any:
        self.failed_terms = []
        self.consecutive_failures = 0
        self.last_error = ""
        term_list = kwargs.get("term_list", args[0] if args else None)
        self._query_to_terms = self._map_queries(term_list)
        return super().exec_search(*args, **kwargs)

    def _map_queries(self, term_list: Any) -> Dict[str, List[str]]:
        """Consulta enviada à API (raiz ``XX.XXX.XXX`` para CNPJ) → termos originais da rotina."""
        mapping: Dict[str, List[str]] = {}
        try:
            terms = self._cast_term_list(term_list) or []
        except ValueError:  # formato que o upstream também rejeitaria: ele mesmo levantará o erro
            return mapping
        for term in terms:
            term = str(term)
            root = cnpj_root(term) if term and term != "*" else None
            query = format_root(root) if root else term
            mapping.setdefault(query, []).append(term)
        return mapping

    def _search_text_with_retry(
        self,
        search_term,
        sections,
        reference_date,
        search_date,
        field,
        is_exact_search,
        max_retries=None,
    ) -> list:
        retries = _env_int("REGISTRALE_DOU_TERM_RETRIES", DEFAULT_TERM_RETRIES) if max_retries is None else max_retries
        pause = _env_float("REGISTRALE_DOU_TERM_RETRY_SLEEP", DEFAULT_TERM_RETRY_SLEEP)
        threshold = _env_int("REGISTRALE_DOU_BREAKER", DEFAULT_BREAKER, minimum=1)

        attempt = 0
        while True:
            try:
                results = self.dou_hook.search_text(
                    search_term=search_term,
                    sections=sections,
                    reference_date=reference_date,
                    search_date=search_date,
                    field=field,
                    is_exact_search=is_exact_search,
                )
            except requests.exceptions.SSLError as exc:
                # Como no upstream: erro de SSL é tratado como permanente, sem nova tentativa.
                return self._register_failure(search_term, exc, threshold)
            except Exception as exc:  # noqa: BLE001 - mesma abrangência do upstream (rede, 5xx, HTML inesperado)
                if attempt < retries:
                    attempt += 1
                    logger.info(
                        "API do DOU falhou para '%s' (%s): nova tentativa %d de %d em %.0f s.",
                        search_term, exc, attempt, retries, pause,
                    )
                    time.sleep(pause)
                    continue
                return self._register_failure(search_term, exc, threshold)
            self.consecutive_failures = 0
            return results

    def _register_failure(self, search_term: str, exc: BaseException, threshold: int) -> list:
        self.consecutive_failures += 1
        self.last_error = f"{type(exc).__name__}: {exc}"
        for term in self._query_to_terms.get(search_term) or [search_term]:
            if term not in self.failed_terms:
                self.failed_terms.append(term)
        logger.warning(
            "API do DOU sem resposta para '%s' (%d falha(s) seguida(s)): %s",
            search_term, self.consecutive_failures, self.last_error,
        )
        if self.consecutive_failures >= threshold:
            raise DouPortalUnavailable(self.last_error, self.consecutive_failures, self.failed_terms) from exc
        return []
