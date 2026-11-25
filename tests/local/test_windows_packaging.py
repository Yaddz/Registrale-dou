"""Testes offline para empacotamento Windows, migração de primeira execução e atualizador."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text


def _load_launcher_module():
    import importlib.machinery

    launcher_path = Path(__file__).resolve().parents[2] / "windows" / "launcher.pyw"
    loader = importlib.machinery.SourceFileLoader("windows_launcher", str(launcher_path))
    spec = importlib.util.spec_from_loader("windows_launcher", loader)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["windows_launcher"] = mod
    spec.loader.exec_module(mod)
    return mod


class TestVersionAndMigrations:
    def test_version_parsing_and_comparison(self):
        from rodou_dashboard.app.runtime.version import (
            get_app_version,
            is_newer_version,
            parse_version,
        )

        assert get_app_version()
        assert parse_version("v0.2.1") == (0, 2, 1)
        assert is_newer_version("v0.2.0", "0.1.0") is True
        assert is_newer_version("0.1.1", "0.1.0") is True
        assert is_newer_version("0.1.0", "0.1.0") is False
        assert is_newer_version("0.0.9", "0.1.0") is False

    def test_schema_migrations_idempotent(self, tmp_path):
        from rodou_dashboard.app.runtime.migrations import (
            MIGRATIONS,
            apply_migrations,
            get_schema_version,
        )

        db_file = tmp_path / "test_mig.db"
        engine = create_engine(f"sqlite:///{db_file}")
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE mentions (id TEXT PRIMARY KEY, cnpj_norm TEXT, data TEXT);"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE companies (id INTEGER PRIMARY KEY, status BOOLEAN, origem TEXT);"
                )
            )

        assert get_schema_version(engine) == 0
        applied_first = apply_migrations(engine)
        assert applied_first == [m[0] for m in MIGRATIONS]
        assert get_schema_version(engine) == MIGRATIONS[-1][0]

        # Segunda execução deve ser idempotente (nenhuma migração pendente)
        applied_second = apply_migrations(engine)
        assert applied_second == []

        with engine.connect() as conn:
            cols = [r[1] for r in conn.execute(text("PRAGMA table_info(mentions);")).fetchall()]
            assert "pdf_path" in cols


class TestMigrator:
    def _create_sample_db(self, db_path: Path, with_data: bool = True) -> None:
        conn = sqlite3.connect(str(db_path))
        with conn:
            conn.executescript(
                """
                CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, role TEXT);
                CREATE TABLE companies (id INTEGER PRIMARY KEY, nome TEXT, cnpj TEXT UNIQUE, cnpj_norm TEXT UNIQUE, origem TEXT, status BOOLEAN);
                CREATE TABLE mentions (id TEXT PRIMARY KEY, empresa TEXT, cnpj TEXT, cnpj_norm TEXT, secao TEXT, data TEXT, detected_at TEXT, trecho TEXT, link TEXT, pdf_path TEXT);
                CREATE TABLE settings (id INTEGER PRIMARY KEY, key TEXT UNIQUE, value TEXT);
                CREATE TABLE email_templates (id INTEGER PRIMARY KEY, name TEXT UNIQUE, subject TEXT, body_html TEXT);
                CREATE TABLE sync_history (id INTEGER PRIMARY KEY, data TEXT, evento TEXT, detalhes TEXT);
                CREATE TABLE inlabs_download_log (id INTEGER PRIMARY KEY, date_str TEXT UNIQUE, downloaded_at TEXT, status TEXT);
                """
            )
            if with_data:
                conn.execute(
                    "INSERT INTO companies (nome, cnpj, cnpj_norm, origem, status) VALUES (?, ?, ?, ?, ?);",
                    ("EMPRESA TESTE LTDA", "12.345.678/0001-90", "12345678000190", "Manual", 1),
                )
                conn.execute(
                    "INSERT INTO mentions (id, empresa, cnpj, cnpj_norm, secao, data, detected_at, trecho, link, pdf_path) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                    ("m-1", "EMPRESA TESTE LTDA", "12.345.678/0001-90", "12345678000190", "Seção 1", "2026-11-23", "23/11/2026", "Trecho", "https://in.gov.br/1", None),
                )
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?);",
                    ("global_settings", json.dumps({"smtp": {"host": "smtp.exemplo.local"}})),
                )
                conn.execute(
                    "INSERT INTO email_templates (name, subject, body_html) VALUES (?, ?, ?);",
                    ("Custom", "Assunto", "<p>Corpo</p>"),
                )
                conn.execute(
                    "INSERT INTO sync_history (data, evento, detalhes) VALUES (?, ?, ?);",
                    ("23/11/2026 08:00:00", "Busca DOU", "1 menção"),
                )
                conn.execute(
                    "INSERT INTO inlabs_download_log (date_str, downloaded_at, status) VALUES (?, ?, ?);",
                    ("2026-11-23", "23/11/2026 07:00:00", "success"),
                )
        conn.close()

    def test_import_docker_database_with_backup_and_idempotency(self, tmp_path, monkeypatch):
        from rodou_dashboard.app.runtime.migrator import import_docker_database

        monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "local_data"))

        src_db = tmp_path / "docker_database.db"
        dst_db = tmp_path / "local_data" / "database.db"
        dst_db.parent.mkdir(parents=True, exist_ok=True)
        self._create_sample_db(src_db, with_data=True)
        self._create_sample_db(dst_db, with_data=False)

        result = import_docker_database(src_db, target_db_path=dst_db)
        assert result["backup_path"] is not None
        assert Path(result["backup_path"]).is_file()
        assert result["imported"]["companies"] == 1
        assert result["imported"]["mentions"] == 1
        assert result["imported"]["settings"] == 1
        assert result["imported"]["email_templates"] == 1
        assert result["imported"]["sync_history"] == 1
        assert result["imported"]["inlabs_download_log"] == 1

        # Re-execução não duplica empresas/menções
        result2 = import_docker_database(src_db, target_db_path=dst_db)
        assert result2["imported"]["companies"] == 0
        assert result2["imported"]["mentions"] == 0

    def test_import_rejects_invalid_sqlite(self, tmp_path):
        from rodou_dashboard.app.runtime.migrator import import_docker_database

        bad_db = tmp_path / "invalid.db"
        conn = sqlite3.connect(str(bad_db))
        conn.execute("CREATE TABLE unrelated (id INTEGER);")
        conn.close()

        dst_db = tmp_path / "target.db"
        self._create_sample_db(dst_db, with_data=False)

        with pytest.raises(ValueError, match="banco válido"):
            import_docker_database(bad_db, target_db_path=dst_db)

    def test_import_routines_filters_temp_and_part_files(self, tmp_path):
        from rodou_dashboard.app.runtime.migrator import import_routines_from_dir

        src_dir = tmp_path / "dag_confs"
        dst_dir = tmp_path / "rotinas"
        src_dir.mkdir()
        (src_dir / "Pesquisa_cnpj.yaml").write_text("dag:\n  id: Pesquisa_cnpj\n", encoding="utf-8")
        (src_dir / "temp_123.yaml").write_text("ignored", encoding="utf-8")
        (src_dir / "Pesquisa_cnpj_part_1.yaml").write_text("ignored", encoding="utf-8")
        (src_dir / "Pesquisa_cnpj_sync.yaml").write_text("ignored", encoding="utf-8")

        res = import_routines_from_dir(src_dir, target_dir=dst_dir)
        assert res["copied"] == ["Pesquisa_cnpj.yaml"]
        assert (dst_dir / "Pesquisa_cnpj.yaml").is_file()
        assert not (dst_dir / "temp_123.yaml").exists()


class TestUpdater:
    def test_check_for_updates_detects_new_release(self):
        from rodou_dashboard.app.runtime.updater import check_for_updates

        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "tag_name": "v9.9.9",
            "html_url": "https://github.com/Yaddz/Registrale-dou/releases/tag/v9.9.9",
            "body": "Melhorias",
            "published_at": "2026-11-23T12:00:00Z",
            "assets": [
                {
                    "name": "Registrale-Setup-9.9.9.exe",
                    "browser_download_url": "https://github.com/Yaddz/Registrale-dou/releases/download/v9.9.9/Registrale-Setup-9.9.9.exe",
                    "size": 123456,
                },
                {
                    "name": "Registrale-Setup-9.9.9.exe.sha256",
                    "browser_download_url": "https://github.com/Yaddz/Registrale-dou/releases/download/v9.9.9/Registrale-Setup-9.9.9.exe.sha256",
                },
            ],
        }
        with patch("rodou_dashboard.app.runtime.updater.requests.get", return_value=fake_resp):
            info = check_for_updates(repo="Yaddz/Registrale-dou")

        assert info["update_available"] is True
        assert info["latest_version"] == "9.9.9"
        assert info["installer_name"] == "Registrale-Setup-9.9.9.exe"
        assert info["sha256_url"].endswith(".sha256")

    def test_download_and_verify_update_validates_sha256_and_host(self, tmp_path):
        from rodou_dashboard.app.runtime.updater import download_and_verify_update

        # Host não confiável deve ser bloqueado
        with pytest.raises(ValueError, match="não confiável"):
            download_and_verify_update(
                "https://evil.example.com/setup.exe",
                "https://github.com/Yaddz/Registrale-dou/releases/download/v1.0.0/setup.exe.sha256",
                dest_dir=tmp_path,
            )

        payload = b"MZfake-installer-binary"
        good_hash = hashlib.sha256(payload).hexdigest()

        def fake_get(url, stream=False, timeout=30):
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            if url.endswith(".sha256"):
                resp.text = f"{good_hash}  Registrale-Setup-0.2.0.exe\n"
                return resp
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            resp.iter_content = MagicMock(return_value=[payload])
            return resp

        with patch("rodou_dashboard.app.runtime.updater.requests.get", side_effect=fake_get):
            out = download_and_verify_update(
                "https://github.com/Yaddz/Registrale-dou/releases/download/v0.2.0/Registrale-Setup-0.2.0.exe",
                "https://github.com/Yaddz/Registrale-dou/releases/download/v0.2.0/Registrale-Setup-0.2.0.exe.sha256",
                dest_dir=tmp_path,
            )
        assert out.is_file()
        assert out.read_bytes() == payload

        # Hash adulterado deve falhar e limpar .tmp
        def fake_get_bad_hash(url, stream=False, timeout=30):
            resp = fake_get(url, stream=stream, timeout=timeout)
            if url.endswith(".sha256"):
                resp.text = "0" * 64
            return resp

        with patch("rodou_dashboard.app.runtime.updater.requests.get", side_effect=fake_get_bad_hash):
            with pytest.raises(ValueError, match="SHA-256"):
                download_and_verify_update(
                    "https://github.com/Yaddz/Registrale-dou/releases/download/v0.2.0/Registrale-Setup-0.2.0.exe",
                    "https://github.com/Yaddz/Registrale-dou/releases/download/v0.2.0/Registrale-Setup-0.2.0.exe.sha256",
                    dest_dir=tmp_path,
                )
        assert not (tmp_path / "Registrale-Setup-0.2.0.exe.tmp").exists()


class TestAdminRoutesSprint6:
    def test_first_run_and_updates_endpoints(self, tmp_path, monkeypatch):
        from rodou_dashboard.app import create_app

        monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
        monkeypatch.setenv("REGISTRALE_DB_PATH", str(tmp_path / "data" / "database.db"))

        app = create_app({"TESTING": True})
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {"username": "admin", "role": "master"}

        resp = client.get("/api/admin/first_run_status")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] == "success"
        assert data["schema_version"] >= 2
        assert data["is_fresh_install"] is True

        fake_404 = MagicMock()
        fake_404.status_code = 404
        with patch("rodou_dashboard.app.runtime.updater.requests.get", return_value=fake_404):
            up_resp = client.get("/api/admin/updates/check")
        assert up_resp.status_code == 200
        assert up_resp.get_json()["update_available"] is False


class TestWindowsLauncherAndArtifacts:
    def test_launcher_command_and_controller(self, tmp_path):
        launcher = _load_launcher_module()

        fake_dir = tmp_path / "python"
        fake_dir.mkdir()
        (fake_dir / "python.exe").write_text("", encoding="utf-8")
        (fake_dir / "pythonw.exe").write_text("", encoding="utf-8")

        resolved = launcher.resolve_python_executable(str(fake_dir / "pythonw.exe"))
        assert resolved.endswith("python.exe")

        cmd = launcher.build_server_command(host="127.0.0.1", port=5055, python_exe=str(fake_dir / "pythonw.exe"))
        assert "rodou_dashboard.app.runtime.server" in cmd
        assert "5055" in cmd

        ctrl = launcher.RegistraleTrayController(host="127.0.0.1", port=5055, open_browser_on_start=True)
        fake_proc = MagicMock()
        fake_proc.pid = 4321
        fake_proc.poll.return_value = None

        with patch.object(launcher.subprocess, "Popen", return_value=fake_proc), \
             patch.object(launcher, "wait_for_server", return_value=True), \
             patch.object(launcher.webbrowser, "open") as mock_open:
            assert ctrl.start_server() is True
            mock_open.assert_called_once_with("http://127.0.0.1:5055")

        ctrl.stop_server()
        fake_proc.terminate.assert_called_once()

    def test_packaging_files_exist_and_contain_required_directives(self):
        root = Path(__file__).resolve().parents[2]
        ico = root / "windows" / "registrale.ico"
        iss = root / "windows" / "installer.iss"
        ps1 = root / "windows" / "build.ps1"
        yml = root / ".github" / "workflows" / "windows-build.yml"

        assert ico.is_file() and ico.stat().st_size > 100
        iss_text = iss.read_text(encoding="utf-8")
        assert "{localappdata}\\Programs\\Registrale" in iss_text
        assert "{userstartup}\\{#AppName}" in iss_text
        assert "CurUninstallStepChanged" in iss_text

    def test_installer_upgrade_and_uninstall_are_clean_and_silent(self):
        """Atualização não deixa arquivos antigos e a desinstalação silenciosa não trava."""
        import re

        iss_text = (Path(__file__).resolve().parents[2] / "windows" / "installer.iss").read_text(encoding="utf-8-sig")

        def section(name: str) -> str:
            m = re.search(rf"^\[{name}\]\s*$(.*?)(?=^\[|\Z)", iss_text, re.M | re.S)
            assert m, f"seção [{name}] ausente"
            return m.group(1)

        for name in ("InstallDelete", "UninstallDelete"):
            body = section(name)
            for folder in ("app", "site-packages", "python"):
                assert f'Type: filesandordirs; Name: "{{app}}\\{folder}"' in body, (name, folder)
            # Os dados do analista nunca podem estar nessas listas.
            assert "localappdata}\\Registrale\"" not in body and "pgdata" not in body

        code = section("Code")
        assert re.search(r"\bMsgBox\(", code) is None, "use SuppressibleMsgBox para não travar /VERYSILENT"
        assert re.search(r"SuppressibleMsgBox\([^;]*IDNO\s*\)", code, re.S), "o padrão silencioso deve preservar os dados"

    def test_packaging_build_and_ci_files(self):
        root = Path(__file__).resolve().parents[2]
        ps1 = root / "windows" / "build.ps1"
        yml = root / ".github" / "workflows" / "windows-build.yml"

        ps1_text = ps1.read_text(encoding="utf-8")
        assert "009d6bf7e3b2ddca3d784fa09f90fe54336d5b60f0e0f305c37f400bf83cfd3b" in ps1_text
        assert "Registrale-Setup-" in ps1_text

        yml_text = yml.read_text(encoding="utf-8")
        assert "windows-latest" in yml_text
        assert "windows\\build.ps1" in yml_text or "windows/build.ps1" in yml_text

    def test_launcher_webview_hide_reopen_and_fallback(self, monkeypatch, caplog):
        """Launcher esconde janela ao fechar, reabre pela bandeja e cai para navegador sem pywebview."""
        import importlib.machinery
        import importlib.util
        import types
        import webbrowser

        root = Path(__file__).resolve().parents[2]
        launcher_path = root / "windows" / "launcher.pyw"
        loader = importlib.machinery.SourceFileLoader("registrale_launcher_test", str(launcher_path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)

        ctrl = mod.RegistraleTrayController(host="127.0.0.1", port=5099)

        fake_win_calls = []

        class FakeWindow:
            def show(self):
                fake_win_calls.append("show")

            def restore(self):
                fake_win_calls.append("restore")

            def hide(self):
                fake_win_calls.append("hide")

            def destroy(self):
                fake_win_calls.append("destroy")

        ctrl._window = FakeWindow()
        ctrl._use_webview = True

        # Fechar a janela só a esconde
        assert ctrl._on_window_closing() is False
        assert "hide" in fake_win_calls

        # Abrir painel reabre a janela
        ctrl.open_panel()
        assert fake_win_calls[-2:] == ["show", "restore"]

        # Sair destrói a janela e permite fechamento
        ctrl.quit_app()
        assert ctrl._stopping is True
        assert "destroy" in fake_win_calls
        assert ctrl._on_window_closing() is True

        # Sem pywebview -> _run_webview retorna False e registra no log
        monkeypatch.setitem(sys.modules, "webview", None)
        assert ctrl._run_webview() is False

        # JsApi open_external só aceita http/https
        opened = []
        monkeypatch.setattr(webbrowser, "open", lambda u: opened.append(u) or True)
        api = mod.RegistraleJsApi()
        assert api.open_external("https://www.in.gov.br/web/dou") is True
        assert api.open_external("file:///etc/passwd") is False
        assert opened == ["https://www.in.gov.br/web/dou"]

    def test_make_icon_and_build_ps1_freshness_check(self, tmp_path):
        """make_icon.py gera .ico com os 7 tamanhos a partir do SVG e build.ps1 valida idade."""
        from PIL import Image

        root = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(root / "windows"))
        try:
            import make_icon
        finally:
            sys.path.pop(0)

        svg = root / "rodou_dashboard" / "static" / "icon.svg"
        out_ico = tmp_path / "test_registrale.ico"
        make_icon.generate_ico(svg, out_ico)

        im = Image.open(out_ico)
        assert sorted(im.info.get("sizes", [])) == [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

        repo_ico = root / "windows" / "registrale.ico"
        assert repo_ico.is_file()
        repo_im = Image.open(repo_ico)
        assert sorted(repo_im.info.get("sizes", [])) == [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

        ps1_text = (root / "windows" / "build.ps1").read_text(encoding="utf-8")
        assert "icon.svg" in ps1_text
        assert "LastWriteTimeUtc" in ps1_text

    def test_apply_window_icon_sends_wm_seticon(self, tmp_path, monkeypatch):
        """No Windows, o ícone do site vai para a janela via WM_SETICON (pequeno e grande)."""
        launcher = _load_launcher_module()
        ico = tmp_path / "registrale.ico"
        ico.write_bytes(b"\x00\x00\x01\x00")

        calls = []
        user32 = MagicMock()
        user32.GetSystemMetrics.side_effect = lambda m: 16 if m == 49 else 32
        user32.LoadImageW.side_effect = lambda _h, path, kind, w, h, flags: 1000 + w
        user32.SendMessageW.side_effect = lambda hwnd, msg, kind, hicon: calls.append((hwnd, msg, kind, hicon))
        fake_ctypes = MagicMock()
        fake_ctypes.windll.user32 = user32

        monkeypatch.setattr(launcher.os, "name", "nt")
        monkeypatch.setattr(launcher, "ctypes", fake_ctypes)

        class _Handle:
            def ToInt64(self):
                return 4242

        window = MagicMock()
        window.native.Handle = _Handle()
        assert launcher.apply_window_icon(window, ico_path=ico) is True
        assert calls == [(4242, 0x0080, 0, 1016), (4242, 0x0080, 1, 1032)]

        # Sem handle nativo: procura a janela pelo título; sem janela, não envia nada.
        calls.clear()
        user32.FindWindowW.return_value = 0
        assert launcher.apply_window_icon(object(), ico_path=ico) is False
        assert calls == []

        # Fora do Windows não faz nada.
        monkeypatch.setattr(launcher.os, "name", "posix")
        assert launcher.apply_window_icon(window, ico_path=ico) is False

    def test_installer_refreshes_icon_cache(self):
        """O atalho mostra o ícone novo depois de atualizar (cache de ícones renovado)."""
        iss = (Path(__file__).resolve().parents[2] / "windows" / "installer.iss").read_text(encoding="utf-8-sig")
        assert "ChangesAssociations=yes" in iss
        run = iss.split("[Run]", 1)[1].split("[Code]", 1)[0]
        line = next(l for l in run.splitlines() if "ie4uinit.exe" in l)
        assert '"-show"' in line and "runhidden" in line and "postinstall" not in line

    def test_seed_routines_creates_empty_main_routine_without_client_cnpjs(self, tmp_path, monkeypatch):
        """Primeiro uso cria Pesquisa_cnpj.yaml vazia e nunca copia rotina com CNPJs de dag_confs/."""
        import yaml
        from rodou_dashboard.app.runtime import paths

        fake_base = tmp_path / "app_base"
        dag_confs = fake_base / "dag_confs"
        dag_confs.mkdir(parents=True)
        (dag_confs / "Pesquisa_cnpj.yaml").write_text(
            "dag:\n  id: pesquisa_cnpj_anvisa\n  search:\n    - terms:\n        - '12.345.678'\n",
            encoding="utf-8",
        )
        (dag_confs / "exemplo_modelo.yaml").write_text("dag:\n  id: exemplo\n", encoding="utf-8")

        monkeypatch.setattr(paths, "get_base_dir", lambda: fake_base)
        rotinas_dir = tmp_path / "rotinas"
        rotinas_dir.mkdir()

        paths._seed_routines_if_empty(rotinas_dir)

        main_yaml = rotinas_dir / "Pesquisa_cnpj.yaml"
        assert main_yaml.is_file()
        parsed = yaml.safe_load(main_yaml.read_text(encoding="utf-8"))
        assert parsed["dag"]["search"][0]["terms"] == []
        assert (rotinas_dir / "exemplo_modelo.yaml").is_file()

    def test_build_excludes_client_routine_and_git_does_not_track_it(self):
        """build.ps1 remove Pesquisa_cnpj*.yaml do stage e Pesquisa_cnpj.yaml não está versionado."""
        import shutil
        import subprocess

        repo_root = Path(__file__).resolve().parents[2]
        build_ps1 = (repo_root / "windows" / "build.ps1").read_text(encoding="utf-8")
        assert "Pesquisa_cnpj*.y*ml" in build_ps1
        assert "LeakedRoutines" in build_ps1
        assert "docs\\manual" in build_ps1

        gitignore = (repo_root / ".gitignore").read_text(encoding="utf-8")
        assert "dag_confs/Pesquisa_cnpj*.yaml" in gitignore

        if not (repo_root / ".git").exists() or shutil.which("git") is None:
            pytest.skip("Repositório .git ou executável git indisponível neste ambiente")

        tracked = subprocess.check_output(
            ["git", "ls-files", "dag_confs/Pesquisa_cnpj.yaml"],
            cwd=str(repo_root),
            text=True,
        ).strip()
        assert tracked == ""
