"""Launcher de bandeja do sistema (System Tray) para o Registrale-DOU no Windows.

Sobe o servidor `rodou_dashboard.app.runtime.server` sem janela de console,
abre o navegador padrão ao iniciar e oferece menu na bandeja:
Abrir painel, Status, Ver logs, Reiniciar e Sair.
"""

from __future__ import annotations

import argparse
import ctypes
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.request
import webbrowser


def _resolve_paths() -> tuple[Path, Path]:
    """Retorna `(app_root, site_packages_dir)` para ambiente empacotado ou dev."""
    here = Path(__file__).resolve()
    app_root = here.parents[1]
    site_packages = app_root.parent / "site-packages"
    return app_root, site_packages


APP_ROOT, SITE_PACKAGES = _resolve_paths()
for _candidate in (str(APP_ROOT), str(SITE_PACKAGES)):
    if Path(_candidate).is_dir() and _candidate not in sys.path:
        sys.path.insert(0, _candidate)

from rodou_dashboard.app.runtime.paths import get_data_dir, get_logs_dir  # noqa: E402
from rodou_dashboard.app.runtime.version import get_app_version  # noqa: E402

logger = logging.getLogger("registrale.launcher")


def _configure_launcher_logging() -> Path:
    logs_dir = get_logs_dir(create=True)
    log_path = logs_dir / "launcher.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
    )
    return log_path


def resolve_python_executable(current_exe: str | None = None) -> str:
    """Prefere `python.exe` ao lado de `pythonw.exe` para rodar o servidor em subprocesso."""
    exe = Path(current_exe or sys.executable)
    if exe.name.lower() == "pythonw.exe":
        console_py = exe.with_name("python.exe")
        if console_py.is_file():
            return str(console_py)
    return str(exe)


def build_server_command(
    host: str = "127.0.0.1",
    port: int = 5000,
    python_exe: str | None = None,
) -> list[str]:
    """Monta a linha de comando para iniciar o servidor local sem terminal."""
    exe = resolve_python_executable(python_exe)
    return [
        exe,
        "-m",
        "rodou_dashboard.app.runtime.server",
        "--host",
        str(host),
        "--port",
        str(port),
    ]


def check_server_health(host: str = "127.0.0.1", port: int = 5000, timeout: float = 2.0) -> bool:
    """Verifica se o painel HTTP está respondendo."""
    url = f"http://{host}:{port}/login"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


def wait_for_server(
    host: str = "127.0.0.1",
    port: int = 5000,
    timeout_seconds: float = 25.0,
    poll_interval: float = 0.4,
    is_alive: Callable[[], bool] | None = None,
) -> bool:
    """Aguarda o servidor responder HTTP dentro do tempo limite."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if is_alive is not None and not is_alive():
            return False
        if check_server_health(host=host, port=port, timeout=1.5):
            return True
        time.sleep(poll_interval)
    return False


def create_tray_image():
    """Carrega `windows/registrale.ico` ou gera um ícone de fallback em memória."""
    from PIL import Image, ImageDraw

    ico_path = Path(__file__).resolve().with_name("registrale.ico")
    if ico_path.is_file():
        try:
            return Image.open(ico_path)
        except Exception:
            pass

    img = Image.new("RGBA", (64, 64), (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([4, 4, 60, 60], radius=12, fill=(15, 23, 42, 255), outline=(6, 172, 255, 255), width=4)
    draw.rectangle([20, 18, 28, 46], fill=(255, 255, 255, 255))
    draw.rectangle([28, 18, 44, 26], fill=(255, 255, 255, 255))
    draw.rectangle([28, 30, 42, 37], fill=(6, 172, 255, 255))
    return img


def _show_message_box(title: str, text: str) -> None:
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(0, text, title, 0x40)
            return
        except Exception:
            pass
    print(f"[{title}] {text}")


def _open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        webbrowser.open(path.as_uri())


class RegistraleJsApi:
    """Ponte JS exposta ao painel dentro da janela pywebview."""

    def __init__(self) -> None:
        self._window: Any = None

    def attach_window(self, window: Any) -> None:
        self._window = window

    def pick_folder(self, initial_dir: str = "") -> str | None:
        if self._window is None:
            return None
        try:
            import webview  # type: ignore

            dialog_type = getattr(getattr(webview, "FileDialog", None), "FOLDER", None)
            if dialog_type is None:
                dialog_type = getattr(webview, "FOLDER_DIALOG", 20)
            kwargs: dict[str, Any] = {}
            if initial_dir and Path(initial_dir).is_dir():
                kwargs["directory"] = initial_dir
            result = self._window.create_file_dialog(dialog_type, **kwargs)
            if result and len(result) > 0:
                return str(result[0])
        except Exception as exc:
            logger.warning("Falha ao abrir seletor nativo de pastas: %s", exc)
        return None

    def open_external(self, url: str) -> bool:
        s = str(url or "").strip()
        if s.startswith(("http://", "https://")):
            webbrowser.open(s)
            return True
        return False


def get_icon_path() -> Path | None:
    """Retorna o caminho de ``windows/registrale.ico`` se existir."""
    ico = Path(__file__).resolve().with_name("registrale.ico")
    return ico if ico.is_file() else None


_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010


def _native_window_handle(window: Any, title: str) -> int:
    """Handle (HWND) da janela do pywebview: via ``window.native`` ou pelo título."""
    native = getattr(window, "native", None)
    handle = getattr(native, "Handle", None)
    if handle is not None:
        try:
            return int(handle.ToInt64()) if hasattr(handle, "ToInt64") else int(handle)
        except Exception:
            pass
    try:
        return int(ctypes.windll.user32.FindWindowW(None, title) or 0)  # type: ignore[attr-defined]
    except Exception:
        return 0


def apply_window_icon(window: Any, ico_path: Path | None = None, title: str = "Registrale-DOU") -> bool:
    """Aplica ``registrale.ico`` à barra de título e ao Alt+Tab da janela própria.

    No Windows o pywebview (WinForms/WebView2) ignora ``webview.start(icon=...)`` e
    herda o ícone do ``pythonw.exe``; por isso o ícone é enviado direto à janela
    com ``WM_SETICON`` (tamanhos pequeno e grande).
    """
    if os.name != "nt":
        return False
    ico = ico_path or get_icon_path()
    if ico is None:
        return False
    hwnd = _native_window_handle(window, title)
    if not hwnd:
        logger.warning("Janela '%s' não encontrada para aplicar o ícone.", title)
        return False
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        ok = False
        for kind, metric in ((_ICON_SMALL, 49), (_ICON_BIG, 11)):  # SM_CXSMICON, SM_CXICON
            size = int(user32.GetSystemMetrics(metric) or 0)
            hicon = user32.LoadImageW(None, str(ico), _IMAGE_ICON, size, size, _LR_LOADFROMFILE)
            if hicon:
                user32.SendMessageW(hwnd, _WM_SETICON, kind, hicon)
                ok = True
        return ok
    except Exception as exc:
        logger.warning("Falha ao aplicar o ícone na janela (%s).", exc)
        return False


class RegistraleTrayController:
    """Controla o ciclo de vida do servidor local, janela própria e bandeja."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5000,
        open_browser_on_start: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.open_browser_on_start = open_browser_on_start
        self.panel_url = f"http://{host}:{port}"
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._stopping = False
        self.icon: Any = None
        self._window: Any = None
        self._use_webview = False
        self._js_api = RegistraleJsApi()

    def is_server_running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    def start_server(self) -> bool:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None:
                return True
            cmd = build_server_command(host=self.host, port=self.port)
            env = os.environ.copy()
            env.setdefault("PYTHONUTF8", "1")
            kwargs: dict[str, Any] = {
                "cwd": str(APP_ROOT),
                "env": env,
                "stdin": subprocess.DEVNULL,
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if os.name == "nt":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            logger.info("Iniciando servidor: %s", " ".join(cmd))
            self._proc = subprocess.Popen(cmd, **kwargs)

        ready = wait_for_server(
            host=self.host,
            port=self.port,
            timeout_seconds=25.0,
            is_alive=self.is_server_running,
        )
        if ready and self.open_browser_on_start and not self._use_webview:
            self.open_panel()
        return ready

    def stop_server(self, timeout: float = 10.0) -> None:
        with self._lock:
            proc = self._proc
            self._proc = None
        if proc is None or proc.poll() is not None:
            return
        logger.info("Encerrando servidor (pid=%s)...", proc.pid)
        try:
            proc.terminate()
            proc.wait(timeout=timeout)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=3.0)
            except Exception:
                pass

    def open_panel(self, *_args) -> None:
        if self._window is not None and self._use_webview:
            try:
                self._window.show()
                self._window.restore()
                apply_window_icon(self._window)
                return
            except Exception as exc:
                logger.warning("Não foi possível reabrir janela pywebview (%s); abrindo navegador.", exc)
        webbrowser.open(self.panel_url)

    def show_status(self, *_args) -> None:
        running = self.is_server_running()
        healthy = check_server_health(host=self.host, port=self.port) if running else False
        version = get_app_version()
        data_dir = get_data_dir(create=False)
        status_label = "Ativo e respondendo" if healthy else ("Iniciando..." if running else "Parado")
        msg = (
            f"Registrale-DOU v{version}\n"
            f"Status do servidor: {status_label}\n"
            f"Painel: {self.panel_url}\n"
            f"Dados: {data_dir}"
        )
        _show_message_box("Status — Registrale-DOU", msg)

    def open_logs(self, *_args) -> None:
        logs_dir = get_logs_dir(create=True)
        main_log = logs_dir / "registrale.log"
        _open_path(main_log if main_log.is_file() else logs_dir)

    def restart_server(self, *_args) -> None:
        logger.info("Reiniciando servidor...")
        self.stop_server()
        self.start_server()

    def quit_app(self, *_args) -> None:
        self._stopping = True
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
        self.stop_server()
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass

    def _on_window_closing(self) -> bool:
        """Ao clicar no X, esconde a janela em vez de encerrar o app (retorna False para cancelar fechamento)."""
        if self._stopping:
            return True
        if self._window is not None:
            try:
                self._window.hide()
            except Exception:
                pass
        return False

    def _run_webview(self) -> bool:
        """Tenta abrir a janela própria via pywebview/WebView2. Retorna False se precisar de fallback."""
        try:
            import webview  # type: ignore
        except Exception as exc:
            logger.warning("pywebview indisponível (%s); usando navegador padrão.", exc)
            return False

        try:
            if hasattr(webview, "settings"):
                webview.settings["ALLOW_DOWNLOADS"] = True

            storage_dir = get_data_dir(create=True) / "webview"
            storage_dir.mkdir(parents=True, exist_ok=True)

            window = webview.create_window(
                "Registrale-DOU",
                url=self.panel_url,
                width=1280,
                height=820,
                min_size=(960, 640),
                hidden=True,
                js_api=self._js_api,
            )
            self._window = window
            self._js_api.attach_window(window)
            self._use_webview = True
            window.events.closing += self._on_window_closing
            window.events.shown += lambda: apply_window_icon(window)

            ico_path = get_icon_path()
            start_kwargs: dict[str, Any] = {
                "private_mode": False,
                "storage_path": str(storage_dir),
            }
            if os.name == "nt":
                start_kwargs["gui"] = "edgechromium"
            if ico_path is not None:
                start_kwargs["icon"] = str(ico_path)

            try:
                webview.start(**start_kwargs)
            except TypeError:
                start_kwargs.pop("icon", None)
                webview.start(**start_kwargs)
            return True
        except Exception as exc:
            logger.warning("Falha ao iniciar janela WebView2 (%s); abrindo no navegador padrão.", exc)
            self._use_webview = False
            self._window = None
            return False

    def run(self) -> int:
        import pystray

        def _boot():
            ok = self.start_server()
            if not ok and not self._stopping:
                _show_message_box(
                    "Registrale-DOU — Aviso",
                    "Não foi possível iniciar o servidor local.\n"
                    "Clique com o botão direito no ícone da bandeja e selecione 'Ver logs' para detalhes.",
                )
            elif ok and self._use_webview and self._window is not None:
                try:
                    self._window.load_url(self.panel_url)
                    if self.open_browser_on_start:
                        self._window.show()
                        apply_window_icon(self._window)
                except Exception as exc:
                    logger.warning("Falha ao carregar URL na janela (%s); abrindo navegador.", exc)
                    if self.open_browser_on_start:
                        webbrowser.open(self.panel_url)

        menu = pystray.Menu(
            pystray.MenuItem("Abrir painel", self.open_panel, default=True),
            pystray.MenuItem("Status", self.show_status),
            pystray.MenuItem("Ver logs", self.open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Reiniciar", self.restart_server),
            pystray.MenuItem("Sair", self.quit_app),
        )
        self.icon = pystray.Icon(
            "Registrale-DOU",
            create_tray_image(),
            "Registrale-DOU",
            menu,
        )

        threading.Thread(target=_boot, daemon=True).start()

        # Bandeja em background para liberar a thread principal para o WebView2 (pywebview).
        if hasattr(self.icon, "run_detached"):
            self.icon.run_detached()
            webview_ok = self._run_webview()
            if not webview_ok:
                if self.open_browser_on_start and check_server_health(host=self.host, port=self.port):
                    webbrowser.open(self.panel_url)
                while not self._stopping:
                    time.sleep(0.5)
        else:
            self.icon.run()

        self.stop_server()
        return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launcher de bandeja do Registrale-DOU.")
    parser.add_argument("--host", default=os.getenv("REGISTRALE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("REGISTRALE_PORT", "5000")))
    parser.add_argument("--no-browser", action="store_true", help="Não abre o navegador ao iniciar.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _configure_launcher_logging()
    args = _parse_args(argv)
    controller = RegistraleTrayController(
        host=args.host,
        port=args.port,
        open_browser_on_start=not args.no_browser,
    )
    return controller.run()


if __name__ == "__main__":
    raise SystemExit(main())
