"""Ciclo de vida do servidor no launcher Windows: sem servidor órfão quando o launcher cai."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time
import uuid

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Job Object, mutex e OpenProcess são do Windows")

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_PATH = ROOT / "windows" / "launcher.pyw"


def _load_launcher():
    loader = importlib.machinery.SourceFileLoader("launcher_lifecycle", str(LAUNCHER_PATH))
    spec = importlib.util.spec_from_loader("launcher_lifecycle", loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["launcher_lifecycle"] = mod
    loader.exec_module(mod)
    return mod


def _alive(launcher, pid: int) -> bool:
    return launcher.process_image_path(pid) is not None


def _wait_dead(launcher, pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(launcher, pid):
            return True
        time.sleep(0.2)
    return False


def test_job_object_encerra_servidor_quando_launcher_morre(tmp_path):
    launcher = _load_launcher()
    pid_file = tmp_path / "child.pid"
    parent_code = textwrap.dedent(f"""
        import importlib.machinery, importlib.util, os, subprocess, sys, time
        loader = importlib.machinery.SourceFileLoader("lch", {str(LAUNCHER_PATH)!r})
        spec = importlib.util.spec_from_loader("lch", loader)
        mod = importlib.util.module_from_spec(spec); loader.exec_module(mod)
        job = mod.create_kill_on_close_job()
        assert job, "job não criado"
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
        assert mod.assign_process_to_job(job, child)
        open({str(pid_file)!r}, "w").write(str(child.pid))
        time.sleep(0.5)
        os._exit(0)  # morte abrupta, sem stop_server (como "Finalizar tarefa")
    """)
    subprocess.run([sys.executable, "-c", parent_code], check=True, timeout=60, cwd=str(ROOT))
    child_pid = int(pid_file.read_text())
    try:
        assert _wait_dead(launcher, child_pid), "servidor sobreviveu ao launcher"
    finally:
        if _alive(launcher, child_pid):
            subprocess.run(["taskkill", "/F", "/PID", str(child_pid)], capture_output=True)


def test_terminate_orphan_server_so_encerra_o_python_do_app(tmp_path):
    launcher = _load_launcher()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        time.sleep(0.5)
        image = launcher.process_image_path(child.pid)
        assert image
        lock = tmp_path / "registrale.pid"
        lock.write_text(f"{child.pid}\n", encoding="utf-8")

        # Executável diferente (ex.: servidor de dev em outro Python): não mexe.
        assert launcher.terminate_orphan_server(lock, str(tmp_path / "outro" / "python.exe")) is False
        assert child.poll() is None

        assert launcher.terminate_orphan_server(lock, image) is True
        child.wait(timeout=5)
    finally:
        if child.poll() is None:
            child.kill()


def test_terminate_orphan_server_ignora_lock_vazio_ou_pid_morto(tmp_path):
    launcher = _load_launcher()
    lock = tmp_path / "registrale.pid"
    assert launcher.terminate_orphan_server(lock, sys.executable) is False  # sem arquivo
    lock.write_text("", encoding="utf-8")
    assert launcher.terminate_orphan_server(lock, sys.executable) is False
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait(timeout=30)
    lock.write_text(str(dead.pid), encoding="utf-8")
    assert launcher.terminate_orphan_server(lock, sys.executable) is False


def test_mutex_impede_segundo_launcher():
    launcher = _load_launcher()
    name = f"Local\RegistraleDOU.Test.{uuid.uuid4().hex}"
    first, h1 = launcher.acquire_launcher_mutex(name)
    second, h2 = launcher.acquire_launcher_mutex(name)
    assert first is True
    assert second is False
    k32 = launcher._kernel32()
    k32.CloseHandle(h2)
    k32.CloseHandle(h1)
    third, h3 = launcher.acquire_launcher_mutex(name)
    assert third is True
    k32.CloseHandle(h3)


def test_servidor_grava_pid_legivel_enquanto_segura_o_lock(tmp_path):
    """O launcher precisa ler o PID com o lock tomado (no Windows o byte travado não é legível)."""
    launcher = _load_launcher()
    sys.path.insert(0, str(ROOT))
    from rodou_dashboard.app.runtime.server import acquire_instance_lock

    lock = tmp_path / "registrale.lock"
    code = "\n".join([
        "import sys, time",
        f"sys.path.insert(0, {str(ROOT)!r})",
        "from pathlib import Path",
        "from rodou_dashboard.app.runtime.server import acquire_instance_lock",
        f"with acquire_instance_lock(Path({str(lock)!r})):",
        "    print('ok', flush=True); time.sleep(60)",
    ])
    proc = subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "ok"
        assert launcher.read_lock_pid(lock) is None  # byte travado: ilegível de fora
        pid_path = tmp_path / "registrale.pid"
        pid = launcher.read_lock_pid(pid_path)
        image = launcher.process_image_path(pid) if pid else None
        assert image
        assert launcher.terminate_orphan_server(pid_path, image)
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()
    with acquire_instance_lock(lock):  # lock liberado após o órfão morrer
        pass
