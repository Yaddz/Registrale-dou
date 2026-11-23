"""Sincroniza o repositório com o Ro-DOU oficial (remote ``upstream``).

Executa fetch, merge sem commit, preserva ``AGENTS.md`` e ``README.md``,
re-remove caminhos listados em ``REMOVED_PATHS``, roda os testes locais
(quando não há conflitos) e imprime um relatório objetivo.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Arquivos mantidos com a nossa versão em caso de modificação/conflito no merge.
OURS_FILES: tuple[str, ...] = (
    "AGENTS.md",
    "README.md",
)

# Caminhos do upstream removidos pelo projeto (preenchido no Sprint 8).
REMOVED_PATHS: tuple[str, ...] = ()


def _run_git(repo_root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=check,
    )


def _unmerged_files(repo_root: Path) -> list[str]:
    res = _run_git(repo_root, "diff", "--name-only", "--diff-filter=U", check=False)
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def _preserve_ours(repo_root: Path, paths: tuple[str, ...]) -> list[str]:
    preserved: list[str] = []
    unmerged = set(_unmerged_files(repo_root))
    for rel in paths:
        if rel in unmerged or (repo_root / rel).exists():
            had_diff = (
                rel in unmerged
                or _run_git(repo_root, "diff", "--quiet", "HEAD", "--", rel, check=False).returncode != 0
            )
            res = _run_git(repo_root, "checkout", "HEAD", "--", rel, check=False)
            if res.returncode == 0:
                _run_git(repo_root, "add", "--", rel, check=False)
                if had_diff:
                    preserved.append(rel)
    return preserved


def _reremove_paths(repo_root: Path, paths: tuple[str, ...]) -> list[str]:
    removed: list[str] = []
    for rel in paths:
        target = repo_root / rel
        if target.exists():
            res = _run_git(repo_root, "rm", "-rf", "--ignore-unmatch", "--", rel, check=False)
            if res.returncode == 0:
                removed.append(rel)
    return removed


def _run_local_tests(repo_root: Path) -> tuple[int, str]:
    res = subprocess.run(
        ["uv", "run", "pytest", "-m", "not live and not airflow", "-q"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (res.stdout or "") + (("\n" + res.stderr) if res.stderr else "")
    return res.returncode, output.strip()


def sync_upstream(
    remote: str = "upstream",
    branch: str = "main",
    run_tests: bool = True,
    repo_root: Path = REPO_ROOT,
) -> int:
    """Executa o fluxo de sincronização com o upstream e retorna código de saída."""
    dirty = _run_git(repo_root, "status", "--porcelain").stdout.strip()
    if dirty:
        print("ERRO: árvore de trabalho suja. Faça commit ou stash antes de sincronizar.")
        print(dirty)
        return 2

    current_branch = _run_git(repo_root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    print(f"Branch atual: {current_branch}")
    print(f"Buscando atualizações de {remote}/{branch}...")
    _run_git(repo_root, "fetch", remote)

    merge_res = _run_git(
        repo_root, "merge", "--no-commit", "--no-ff", f"{remote}/{branch}", check=False
    )
    preserved = _preserve_ours(repo_root, OURS_FILES)
    removed = _reremove_paths(repo_root, REMOVED_PATHS)
    conflicts = _unmerged_files(repo_root)

    print("\n=== Relatório de Sync com Upstream ===")
    print(f"Alvo: {remote}/{branch}")
    print(f"Merge exit code: {merge_res.returncode}")
    print(f"Arquivos preservados (--ours): {preserved or ['nenhum']}")
    print(f"Caminhos re-removidos: {removed or ['nenhum']}")
    print(f"Conflitos pendentes ({len(conflicts)}):")
    for path in conflicts:
        print(f"  - {path}")

    if conflicts:
        print("\nAção necessária: resolva os conflitos acima (consulte plano/UPSTREAM.md) e rode os testes.")
        return 1

    if run_tests:
        print("\nRodando testes locais: uv run pytest -m 'not live and not airflow' -q")
        code, test_out = _run_local_tests(repo_root)
        print(test_out)
        if code != 0:
            print("\nFALHA nos testes locais após o merge.")
            return code

    print("\nSync pronto para revisão (`git diff --cached`) e `git commit`.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza fork com upstream Ro-DOU.")
    parser.add_argument("--remote", default="upstream", help="Nome do remote upstream")
    parser.add_argument("--branch", default="main", help="Branch do upstream")
    parser.add_argument("--no-tests", action="store_true", help="Não executa pytest após o merge")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Raiz do repositório git")
    args = parser.parse_args()
    return sync_upstream(
        remote=args.remote,
        branch=args.branch,
        run_tests=not args.no_tests,
        repo_root=args.repo_root.resolve(),
    )


if __name__ == "__main__":
    sys.exit(main())
