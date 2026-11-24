"""Testes offline do Sprint 4: PostgreSQL portátil, shim de conexões, loader INLABS e integração."""

from __future__ import annotations

import io
import json
from pathlib import Path
import socket
import stat
import sys
from types import SimpleNamespace
import zipfile

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(REPO_ROOT / "rodou_dashboard") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "rodou_dashboard"))

from compat.bootstrap import install_airflow_shim

install_airflow_shim()

from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import JobRun, Settings, SyncHistory, db
from rodou_dashboard.app.runtime import inlabs_loader, pg_portable
from rodou_dashboard.app.runtime.executor import LocalExecutor
from rodou_dashboard.app.runtime.scheduler import init_scheduler, shutdown_scheduler


@pytest.fixture()
def local_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "database.db"
    monkeypatch.setenv("REGISTRALE_EXECUTOR", "local")
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(db_path))
    monkeypatch.setenv("REGISTRALE_SCHEDULER_DB_PATH", str(data_dir / "scheduler_jobs.db"))
    monkeypatch.setenv("REGISTRALE_LOGS_DIR", str(data_dir / "logs"))
    monkeypatch.setenv("REGISTRALE_INLABS_DIR", str(data_dir / "inlabs"))
    monkeypatch.setenv("REGISTRALE_PGDATA_DIR", str(data_dir / "pgdata"))
    monkeypatch.setenv("REGISTRALE_ROUTINES_DIR", str(data_dir / "rotinas"))
    monkeypatch.setenv("SESSION_FILE_DIR", str(data_dir / "sessions"))
    monkeypatch.delenv("INLABS_DB_URL", raising=False)
    pg_portable.reset_portable_postgres_for_tests()
    yield data_dir
    pg_portable.reset_portable_postgres_for_tests()


def _make_dou_xml(
    art_id: int,
    pub_name: str,
    pub_date: str,
    texto_html: str,
    identifica: str = "RESOLUÇÃO-RE Nº 1.000",
    art_type: str = "Resolução",
) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<xml>
  <article id="{art_id}" name="art_{art_id}.xml" idOficio="10" pubName="{pub_name}"
           artType="{art_type}" pubDate="{pub_date}" artClass="0001"
           artCategory="Ministério da Saúde/ANVISA" artSize="12" artNotes=""
           numberPage="1" pdfPage="https://www.in.gov.br/web/dou/-/art-{art_id}"
           editionNumber="200" highlightType="" highlightPriority="" highlight=""
           highlightImage="" highlightImageName="" idMateria="{art_id}">
    <body>
      <Identifica>{identifica}</Identifica>
      <Data>{pub_date}</Data>
      <Ementa>Ementa teste</Ementa>
      <Titulo>{identifica}</Titulo>
      <SubTitulo></SubTitulo>
      <Texto><![CDATA[{texto_html}]]></Texto>
    </body>
  </article>
</xml>
"""


def _build_zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


class TestPortablePostgres:
    def test_find_free_port_fallback_when_occupied(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as occupied:
            occupied.bind(("127.0.0.1", 0))
            occupied.listen(1)
            busy_port = occupied.getsockname()[1]

            free_port = pg_portable.find_free_port(preferred=busy_port, host="127.0.0.1")
            assert free_port != busy_port
            assert free_port > 0

    def test_missing_binaries_raises_clear_error(self, local_env, monkeypatch):
        monkeypatch.setattr(pg_portable, "get_pg_bin_dir", lambda: None)
        pg = pg_portable.PortablePostgres()
        with pytest.raises(pg_portable.PostgresBinariesNotFoundError):
            pg.start()

    def test_start_stop_initdb_and_schema(self, local_env, monkeypatch):
        app = create_app({"TESTING": True})
        fake_bin = local_env / "fake_pgsql" / "bin"
        fake_bin.mkdir(parents=True)
        suffix = ".exe" if pg_portable.os.name == "nt" else ""
        (fake_bin / f"initdb{suffix}").write_text("", encoding="utf-8")
        (fake_bin / f"pg_ctl{suffix}").write_text("", encoding="utf-8")

        commands = []
        pgdata = local_env / "pgdata"
        running_state = {"up": False}

        def fake_run(cmd, **kwargs):
            commands.append(cmd)
            exe = Path(cmd[0]).name
            if exe.startswith("initdb"):
                pgdata.mkdir(parents=True, exist_ok=True)
                (pgdata / "PG_VERSION").write_text("17\n", encoding="utf-8")
                (pgdata / "postgresql.conf").write_text("# conf\n", encoding="utf-8")
            elif exe.startswith("pg_ctl"):
                action = cmd[-1]
                if action == "start":
                    running_state["up"] = True
                    (pgdata / "postmaster.pid").write_text("12345\n", encoding="utf-8")
                elif action == "stop":
                    running_state["up"] = False
                    if (pgdata / "postmaster.pid").exists():
                        (pgdata / "postmaster.pid").unlink()
                elif action == "status":
                    return SimpleNamespace(returncode=0 if running_state["up"] else 3, stdout="", stderr="")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        executed_sql = []

        class FakeCursor:
            def __init__(self, dbname):
                self._dbname = dbname
                self._last = None

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def execute(self, sql, params=None):
                executed_sql.append((self._dbname, str(sql).strip()))
                self._last = None if "pg_database" in str(sql) else (1,)

            def fetchone(self):
                return self._last

        class FakePsycopgConn:
            def __init__(self, dbname):
                self._dbname = dbname

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def cursor(self):
                return FakeCursor(self._dbname)

        import psycopg

        monkeypatch.setattr(pg_portable.subprocess, "run", fake_run)
        monkeypatch.setattr(
            psycopg,
            "connect",
            lambda **kwargs: FakePsycopgConn(kwargs.get("dbname", "postgres")),
        )

        pg = pg_portable.PortablePostgres(pgdata_dir=pgdata, bin_dir=fake_bin, preferred_port=54329)
        port = pg.start()
        assert port > 0
        assert pg.is_running() is True

        # Verifica bind apenas em 127.0.0.1
        assert "listen_addresses = '127.0.0.1'" in (pgdata / "postgresql.conf").read_text(encoding="utf-8")
        assert any("-h 127.0.0.1" in " ".join(c) for c in commands if Path(c[0]).name.startswith("pg_ctl"))

        # Verifica criação do banco, schema dou_inlabs, tabela article_raw e extensão unaccent
        sql_joined = "\n".join(s for _, s in executed_sql)
        assert 'CREATE DATABASE "inlabs"' in sql_joined
        assert "CREATE SCHEMA IF NOT EXISTS dou_inlabs" in sql_joined
        assert "CREATE TABLE IF NOT EXISTS dou_inlabs.article_raw" in sql_joined
        assert "CREATE EXTENSION IF NOT EXISTS unaccent SCHEMA dou_inlabs" in sql_joined

        # Senha gerada e persistida no SQLite
        with app.app_context():
            rec = Settings.query.filter_by(key="inlabs_pg_config").first()
            assert rec is not None
            cfg = json.loads(rec.value)
            assert cfg["port"] == port
            assert len(cfg["password"]) >= 16

        pg.stop()
        assert pg.is_running() is False


class TestShimConnections:
    def test_resolves_inlabs_portal_and_inlabs_db_from_sqlite(self, local_env):
        from airflow.sdk.bases.hook import BaseHook

        app = create_app({"TESTING": True})
        with app.app_context():
            Settings.query.delete()
            db.session.add(
                Settings(
                    key="global_settings",
                    value=json.dumps(
                        {"inlabs": {"user": "analista@empresa.com", "password": "segredo-inlabs"}}
                    ),
                )
            )
            db.session.add(
                Settings(
                    key="inlabs_pg_config",
                    value=json.dumps(
                        {"user": "postgres", "password": "pg-secret", "database": "inlabs", "port": 54329}
                    ),
                )
            )
            db.session.commit()

        portal = BaseHook.get_connection("inlabs_portal")
        assert portal.host == "https://inlabs.in.gov.br/"
        assert portal.login == "analista@empresa.com"
        assert portal.password == "segredo-inlabs"

        db_conn = BaseHook.get_connection("inlabs_db")
        assert db_conn.host == "127.0.0.1"
        assert db_conn.port == 54329
        assert db_conn.schema == "inlabs"
        assert db_conn.login == "postgres"
        assert db_conn.password == "pg-secret"


class TestInlabsLoaderSecurityAndPipeline:
    def test_safe_extract_zip_blocks_zip_slip_symlink_and_limits(self, tmp_path):
        extract_dir = tmp_path / "extracted"

        # 1. Zip Slip com '..'
        slip_zip = tmp_path / "slip.zip"
        slip_zip.write_bytes(_build_zip_bytes({"../../evil.xml": b"<xml/>"}))
        with pytest.raises(inlabs_loader.InlabsSecurityError, match="Zip Slip"):
            inlabs_loader.safe_extract_zip(slip_zip, extract_dir)
        assert not (tmp_path / "evil.xml").exists()

        # 2. Caminho absoluto
        abs_zip = tmp_path / "abs.zip"
        abs_zip.write_bytes(_build_zip_bytes({"/tmp/evil.xml": b"<xml/>"}))
        with pytest.raises(inlabs_loader.InlabsSecurityError, match="Zip Slip"):
            inlabs_loader.safe_extract_zip(abs_zip, extract_dir)

        # 3. Symlink
        sym_zip = tmp_path / "sym.zip"
        with zipfile.ZipFile(sym_zip, "w") as zf:
            zi = zipfile.ZipInfo("link.xml")
            zi.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(zi, "/etc/passwd")
        with pytest.raises(inlabs_loader.InlabsSecurityError, match="symlink"):
            inlabs_loader.safe_extract_zip(sym_zip, extract_dir)

        # 4. Limite de arquivos
        many_zip = tmp_path / "many.zip"
        many_zip.write_bytes(_build_zip_bytes({f"a_{i}.xml": b"<x/>" for i in range(5)}))
        with pytest.raises(inlabs_loader.InlabsSecurityError, match="limite"):
            inlabs_loader.safe_extract_zip(many_zip, extract_dir, max_files=3)

        # 5. Limite de tamanho
        big_zip = tmp_path / "big.zip"
        big_zip.write_bytes(_build_zip_bytes({"big.xml": b"A" * 2048}))
        with pytest.raises(inlabs_loader.InlabsSecurityError, match="limite"):
            inlabs_loader.safe_extract_zip(big_zip, extract_dir, max_file_bytes=512)

    def test_parse_xml_files_normalizes_and_deduplicates(self, tmp_path):
        extract_dir = tmp_path / "xmls"
        extract_dir.mkdir()
        xml1 = _make_dou_xml(
            101,
            "DO1",
            "23/11/2026",
            '<p>Empresa 24.684.423/0001-36 citada.</p><p class="assina">MARIA SILVA</p>',
        )
        xml2 = _make_dou_xml(
            101,
            "DO1",
            "23/11/2026",
            '<p>Empresa 24.684.423/0002-17 atualizada.</p><p class="assina">JOÃO SOUZA</p>',
        )
        (extract_dir / "01.xml").write_text(xml1, encoding="utf-8")
        (extract_dir / "02.xml").write_text(xml2, encoding="utf-8")

        df = inlabs_loader.parse_xml_files(extract_dir)
        assert list(df.columns) == inlabs_loader.RAW_COLUMNS
        assert len(df) == 1
        assert int(df.iloc[0]["id"]) == 101
        assert df.iloc[0]["assina"] == "JOÃO SOUZA"
        assert pd.Timestamp(df.iloc[0]["pubdate"]).strftime("%Y-%m-%d") == "2026-11-23"

    def test_load_inlabs_date_maintenance_fails_fast(self, local_env, monkeypatch):
        from airflow.sdk.bases.hook import BaseHook

        app = create_app({"TESTING": True})
        with app.app_context():
            db.session.add(
                Settings(
                    key="global_settings",
                    value=json.dumps({"inlabs": {"user": "u@x.com", "password": "pw"}}),
                )
            )
            db.session.commit()

        calls = {"post": 0}

        class FakeSession:
            def __init__(self):
                self.cookies = {}

            def get(self, url, **kwargs):
                return SimpleNamespace(
                    status_code=200,
                    content="<html><body>Manutenção Programada</body></html>".encode("utf-8"),
                    text="Manutenção Programada",
                    url=url,
                )

            def post(self, *args, **kwargs):
                calls["post"] += 1
                raise AssertionError("Não deveria tentar login quando portal está em manutenção")

        assert BaseHook.get_connection("inlabs_portal").login == "u@x.com"
        with pytest.raises(inlabs_loader.InlabsMaintenanceError):
            inlabs_loader.load_inlabs_date(
                "2026-11-23",
                session_factory=FakeSession,
                sleep_fn=lambda _: None,
            )
        assert calls["post"] == 0

    def test_load_inlabs_date_full_flow_with_synthetic_zip(self, local_env, monkeypatch):
        app = create_app({"TESTING": True})
        with app.app_context():
            db.session.add(
                Settings(
                    key="global_settings",
                    value=json.dumps({"inlabs": {"user": "u@x.com", "password": "pw"}}),
                )
            )
            db.session.commit()

        xml_ok = _make_dou_xml(
            555,
            "DO1",
            "23/11/2026",
            "<p>Autorizar empresa CNPJ 24.684.423.</p>",
        )
        zip_bytes = _build_zip_bytes({"2026-11-23/555.xml": xml_ok.encode("utf-8")})

        class FakeCookies(dict):
            def set(self, k, v):
                self[k] = v

        class FakeSession:
            def __init__(self):
                self.cookies = FakeCookies()

            def get(self, url, **kwargs):
                return SimpleNamespace(status_code=200, content=b"Portal INLABS", text="Portal INLABS", url=url)

            def post(self, url, **kwargs):
                self.cookies["inlabs_session_cookie"] = "cookie-ok"
                return SimpleNamespace(status_code=302, cookies={"inlabs_session_cookie": "cookie-ok"})

            def request(self, method, url, **kwargs):
                if "index.php?p=2026-11-23" in url and "dl=" not in url:
                    html = '<a title="Baixar Arquivo" href="?p=2026-11-23&dl=2026-11-23-DO1.zip">Baixar</a>'
                    return SimpleNamespace(status_code=200, text=html, raise_for_status=lambda: None)
                return SimpleNamespace(status_code=200, content=zip_bytes, raise_for_status=lambda: None)

        upserted_dfs = []
        monkeypatch.setattr(
            inlabs_loader,
            "upsert_articles",
            lambda df, conn_id="inlabs_db": upserted_dfs.append(df) or len(df),
        )
        monkeypatch.setattr(inlabs_loader, "check_loaded_data", lambda d, conn_id="inlabs_db": True)
        retention_calls = []
        from rodou_dashboard.app.services import inlabs_service

        monkeypatch.setattr(
            inlabs_service,
            "enforce_inlabs_retention_limit",
            lambda max_days=120, protected_dates=None: retention_calls.append((max_days, protected_dates)) or 0,
        )

        with app.app_context():
            res = inlabs_loader.load_inlabs_date(
                "2026-11-23",
                session_factory=FakeSession,
                sleep_fn=lambda _: None,
            )

        assert res["status"] == "success"
        assert res["rows"] == 1
        assert len(upserted_dfs) == 1
        assert int(upserted_dfs[0].iloc[0]["id"]) == 555
        assert retention_calls == [(120, ["2026-11-23"])]
        # Temporário limpo após conclusão
        assert not (local_env / "inlabs" / "download_inlabs" / "2026-11-23").exists()


class TestINLABSSQLModeCnpjRootRules:
    def test_sql_pattern_and_text_handler_match_only_valid_cnpj_roots(self):
        from hooks.inlabs_hook_sql_mode import INLABSSQLModeHook

        hook = INLABSSQLModeHook()
        queries = hook._generate_sql(
            {
                "pubdate": ["2026-11-23", "2026-11-23"],
                "pubname": ["DO1"],
                "texto": ["24.684.423/0001-36"],
            }
        )
        assert "CREATE EXTENSION IF NOT EXISTS unaccent SCHEMA dou_inlabs" == queries["create_extension"]
        assert "24\\.684\\.423" in queries["select"]

        # Simula 5 artigos retornados para validar o filtro exato de raiz/falso-positivo no TextDictHandler
        df = pd.DataFrame(
            [
                {
                    "id": 1,
                    "name": "art_1.xml",
                    "pubname": "DO1",
                    "arttype": "Resolução",
                    "pubdate": pd.Timestamp("2026-11-23"),
                    "artcategory": "ANVISA",
                    "artnotes": "",
                    "numberpage": 1,
                    "pdfpage": "https://in.gov.br/1",
                    "editionnumber": "200",
                    "identifica": "Matriz",
                    "titulo": "Matriz",
                    "subtitulo": "",
                    "texto": "<p>Empresa CNPJ 24.684.423/0001-36 autorizada.</p>",
                    "assina": None,
                },
                {
                    "id": 2,
                    "name": "art_2.xml",
                    "pubname": "DO1",
                    "arttype": "Resolução",
                    "pubdate": pd.Timestamp("2026-11-23"),
                    "artcategory": "ANVISA",
                    "artnotes": "",
                    "numberpage": 2,
                    "pdfpage": "https://in.gov.br/2",
                    "editionnumber": "200",
                    "identifica": "Filial",
                    "titulo": "Filial",
                    "subtitulo": "",
                    "texto": "<p>Filial CNPJ 24.684.423/0002-17 autorizada.</p>",
                    "assina": None,
                },
                {
                    "id": 3,
                    "name": "art_3.xml",
                    "pubname": "DO1",
                    "arttype": "Resolução",
                    "pubdate": pd.Timestamp("2026-11-23"),
                    "artcategory": "ANVISA",
                    "artnotes": "",
                    "numberpage": 3,
                    "pdfpage": "https://in.gov.br/3",
                    "editionnumber": "200",
                    "identifica": "Raiz isolada",
                    "titulo": "Raiz isolada",
                    "subtitulo": "",
                    "texto": "<p>SURGITEC CNPJ 24.684.423 - Processo 25351.</p>",
                    "assina": None,
                },
                {
                    "id": 4,
                    "name": "art_4.xml",
                    "pubname": "DO1",
                    "arttype": "Resolução",
                    "pubdate": pd.Timestamp("2026-11-23"),
                    "artcategory": "ANVISA",
                    "artnotes": "",
                    "numberpage": 4,
                    "pdfpage": "https://in.gov.br/4",
                    "editionnumber": "200",
                    "identifica": "Valor monetário",
                    "titulo": "Valor monetário",
                    "subtitulo": "",
                    "texto": "<p>Crédito de R$ 24.684.423,00 aprovado.</p>",
                    "assina": None,
                },
                {
                    "id": 5,
                    "name": "art_5.xml",
                    "pubname": "DO1",
                    "arttype": "Resolução",
                    "pubdate": pd.Timestamp("2026-11-23"),
                    "artcategory": "ANVISA",
                    "artnotes": "",
                    "numberpage": 5,
                    "pdfpage": "https://in.gov.br/5",
                    "editionnumber": "200",
                    "identifica": "Sem pontos",
                    "titulo": "Sem pontos",
                    "subtitulo": "",
                    "texto": "<p>Protocolo 24684423 registrado.</p>",
                    "assina": None,
                },
            ]
        )

        class FakePostgresHook:
            def __init__(self, conn_id):
                self.conn_id = conn_id

            def run(self, sql, autocommit=False):
                pass

            def get_pandas_df(self, sql):
                # Retorna apenas DO1 na busca principal e vazio na extra
                if "DO1E" in sql:
                    return df.iloc[0:0]
                return df

        import hooks.inlabs_hook_sql_mode as sql_mode_mod

        orig_hook = sql_mode_mod.PostgresHook
        sql_mode_mod.PostgresHook = FakePostgresHook
        try:
            result = hook.search_text(
                ai_config={},
                ai_search_config={},
                search_terms={
                    "pubdate": ["2026-11-23", "2026-11-23"],
                    "pubname": ["DO1"],
                    "texto": ["24.684.423/0001-36"],
                },
                ignore_signature_match=True,
                full_text=True,
                text_length=400,
                use_summary=False,
            )
        finally:
            sql_mode_mod.PostgresHook = orig_hook

        items = result["24.684.423/0001-36"]
        matched_hrefs = {item["href"] for item in items}
        assert matched_hrefs == {
            "https://in.gov.br/1",
            "https://in.gov.br/2",
            "https://in.gov.br/3",
        }


class TestSchedulerExecutorAndRoutesIntegration:
    def test_scheduler_registers_inlabs_daily_load_job(self, local_env):
        app = create_app({"TESTING": True})
        sched = init_scheduler(app, db_path=local_env / "scheduler_jobs.db", start=False)
        try:
            jobs = {j["id"]: j for j in sched.list_jobs()}
            assert "inlabs_daily_load" in jobs
            assert "59 6,23 * * *" in jobs["inlabs_daily_load"]["name"]
        finally:
            shutdown_scheduler(wait=False)

    def test_local_executor_triggers_inlabs_loader(self, local_env, monkeypatch):
        app = create_app({"TESTING": True})
        monkeypatch.setattr(
            inlabs_loader,
            "load_inlabs_date",
            lambda dt: {"status": "success", "date": dt, "rows": 42, "message": "ok"},
        )
        executor = LocalExecutor(app=app, max_workers=1)
        try:
            with app.app_context():
                run_id = executor.trigger("ro-dou_inlabs_load_pg", date="2026-11-23")
                finished, states = executor.wait([run_id], timeout=10)
                assert finished is True
                assert states[run_id] == "success"
                res = executor.result(run_id)
                assert res[0]["rows"] == 42
                job = db.session.get(JobRun, run_id)
                assert job.rotina == "ro-dou_inlabs_load_pg"
        finally:
            executor.shutdown(wait=True)

    def test_download_missing_inlabs_respects_maintenance(self, local_env, monkeypatch):
        app = create_app({"TESTING": True})
        monkeypatch.setenv("INLABS_DB_URL", "postgresql+psycopg://u:p@127.0.0.1:54329/inlabs")
        from rodou_dashboard.app.services import inlabs_service

        monkeypatch.setattr(
            inlabs_service,
            "check_inlabs_portal_status",
            lambda: (False, "Portal INLABS em manutenção programada"),
        )

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user"] = {"username": "admin", "role": "master"}
            sess["expires_at"] = 9999999999

        resp = client.post("/api/routines/download_missing_inlabs", json={"days": ["2026-11-23"]})
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["status"] == "ok"
        assert "manutenção" in body["message"].lower()
