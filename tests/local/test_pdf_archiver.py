"""Testes do arquivador de PDFs integrais do DOU (Sprint 5)."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

from pypdf import PdfReader, PdfWriter
import pytest

from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import Mention, db
from rodou_dashboard.app.runtime.pdf_archiver import (
    archive_date_pdfs,
    archive_month_pdfs,
    build_pdf_target_path,
    is_valid_pdf_file,
    link_mentions_to_pdfs,
    normalize_date_iso,
    normalize_section_key,
    resolve_pdf_for_mention,
)


def _make_sample_pdf_bytes(num_pages: int = 1) -> bytes:
    """Gera bytes de um PDF válido com `num_pages` páginas em branco."""
    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, text: str = "", content: bytes = b""):
        self.status_code = status_code
        self.text = text
        self.content = content or text.encode("utf-8")
        self.cookies = {}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"HTTP {self.status_code}")


@pytest.fixture()
def app_ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REGISTRALE_PDF_DIR", str(tmp_path / "pdfs"))
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        yield app, tmp_path


def test_normalize_date_and_section():
    assert normalize_date_iso("23/11/2026") == "2026-11-23"
    assert normalize_date_iso("23/11/26") == "2026-11-23"
    assert normalize_date_iso("2026-11-23") == "2026-11-23"
    assert normalize_section_key("DO1") == "1"
    assert normalize_section_key("Seção 2") == "2"
    assert normalize_section_key("DO3") == "3"
    assert normalize_section_key("DO1E") == "extra"
    assert normalize_section_key("Edição Extra") == "extra"


def test_archive_pesquisa_assemble_idempotent_and_corrupted_repair(app_ctx):
    _, tmp_path = app_ctx
    pdf_dir = tmp_path / "pdfs"
    page_pdf = _make_sample_pdf_bytes(1)

    calls = []

    class FakeSession:
        def request(self, method, url, headers=None, timeout=30):
            calls.append(url)
            if "visualiza/index.jsp" in url:
                if "jornal=515" in url:
                    return _FakeResponse(text="totalArquivos=2")
                return _FakeResponse(text="Sem edicao")
            if "INPDFViewer" in url:
                # Simula falha transitória na primeira tentativa da página 2
                if "pagina=2" in url and calls.count(url) == 1:
                    return _FakeResponse(status_code=503, text="Service Unavailable")
                return _FakeResponse(content=page_pdf)
            raise AssertionError(f"URL inesperada: {url}")

    res1 = archive_date_pdfs(
        "23/11/2026",
        folder=pdf_dir,
        sections=["1"],
        prefer_inlabs=False,
        session_factory=FakeSession,
        max_workers=2,
        sleep_fn=lambda _: None,
    )
    assert res1["status"] == "success"
    target = build_pdf_target_path(pdf_dir, "2026-11-23", "1")
    assert target == pdf_dir / "2026" / "11" / "DOU_2026-11-23_Secao1.pdf"
    assert is_valid_pdf_file(target)
    reader = PdfReader(str(target))
    assert len(reader.pages) == 2

    # Segunda execução: idempotente, não faz nenhuma requisição HTTP
    calls_before = len(calls)
    res2 = archive_date_pdfs(
        "2026-11-23",
        folder=pdf_dir,
        sections=["1"],
        prefer_inlabs=False,
        session_factory=FakeSession,
        sleep_fn=lambda _: None,
    )
    assert res2["status"] == "skipped"
    assert res2["saved_files"] == []
    assert str(target) in res2["skipped_files"]
    assert len(calls) == calls_before

    # Se o arquivo no disco estiver corrompido, rebaixa automaticamente
    target.write_bytes(b"NOT_A_PDF_CORRUPTED")
    res3 = archive_date_pdfs(
        "2026-11-23",
        folder=pdf_dir,
        sections=["1"],
        prefer_inlabs=False,
        session_factory=FakeSession,
        sleep_fn=lambda _: None,
    )
    assert res3["status"] == "success"
    assert is_valid_pdf_file(target)


def test_archive_inlabs_maintenance_falls_back_to_pesquisa(app_ctx, monkeypatch):
    _, tmp_path = app_ctx
    pdf_dir = tmp_path / "pdfs"
    page_pdf = _make_sample_pdf_bytes(1)

    # Simula conexão inlabs_portal configurada, mas portal em manutenção
    from compat.bootstrap import install_airflow_shim

    install_airflow_shim()
    from airflow.sdk.bases.hook import BaseHook

    fake_conn = MagicMock(host="https://inlabs.in.gov.br/", login="u@x.com", password="123")
    monkeypatch.setattr(BaseHook, "get_connection", lambda cid: fake_conn)

    class FakeSession:
        def __init__(self):
            self.cookies = requests_cookies = MagicMock()
            requests_cookies.get = lambda k, d=None: None

        def get(self, url, **kwargs):
            return _FakeResponse(text="<html><title>Manutenção Programada — INLABS</title></html>")

        def request(self, method, url, headers=None, timeout=30):
            if "inlabs.in.gov.br" in url:
                return _FakeResponse(text="<html><title>Manutenção Programada — INLABS</title></html>")
            if "visualiza/index.jsp" in url and "jornal=515" in url:
                return _FakeResponse(text="totalArquivos=1")
            if "INPDFViewer" in url:
                return _FakeResponse(content=page_pdf)
            return _FakeResponse(text="")

    res = archive_date_pdfs(
        "2026-11-23",
        folder=pdf_dir,
        sections=["1"],
        prefer_inlabs=True,
        session_factory=FakeSession,
        sleep_fn=lambda _: None,
    )
    assert res["status"] == "success"
    assert res["source"] == "pesquisa.in.gov.br"
    assert len(res["saved_files"]) == 1


def test_archive_empty_on_weekend_or_holiday(app_ctx):
    _, tmp_path = app_ctx
    pdf_dir = tmp_path / "pdfs"

    class FakeSession:
        def request(self, method, url, headers=None, timeout=30):
            return _FakeResponse(text="<html>Edição não encontrada</html>")

    res = archive_date_pdfs(
        "20/11/2026",
        folder=pdf_dir,
        sections=["1", "2"],
        prefer_inlabs=False,
        session_factory=FakeSession,
        sleep_fn=lambda _: None,
    )
    assert res["status"] == "empty"
    assert res["saved_files"] == []


def test_archive_month_skips_weekends(app_ctx):
    _, tmp_path = app_ctx
    pdf_dir = tmp_path / "pdfs"
    page_pdf = _make_sample_pdf_bytes(1)
    seen_dates = []

    class FakeSession:
        def request(self, method, url, headers=None, timeout=30):
            if "visualiza/index.jsp" in url:
                seen_dates.append(url)
                if "data=03/11/2026" in url and "jornal=515" in url:
                    return _FakeResponse(text="totalArquivos=1")
                return _FakeResponse(text="")
            if "INPDFViewer" in url:
                return _FakeResponse(content=page_pdf)
            return _FakeResponse(text="")

    res = archive_month_pdfs(
        2026,
        11,
        folder=pdf_dir,
        sections=["1"],
        prefer_inlabs=False,
        session_factory=FakeSession,
        sleep_fn=lambda _: None,
    )
    assert res["status"] == "success"
    assert res["processed_days"] >= 1
    assert len(res["saved_files"]) == 1
    # Sábado 07/11/2026 não deve ser consultado
    assert not any("07/11/2026" in u for u in seen_dates)


def test_mention_link_and_api_routes(app_ctx):
    app, tmp_path = app_ctx
    pdf_dir = tmp_path / "pdfs"
    target = build_pdf_target_path(pdf_dir, "2026-11-23", "1")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_make_sample_pdf_bytes(1))

    m = Mention(
        id="m-test-1",
        empresa="SURGITEC",
        cnpj="24.684.423",
        cnpj_norm="24684423",
        secao="DO1",
        data="23/11/2026",
        detected_at="23/11/2026 08:00:00",
        trecho="Resumo teste",
        link="https://www.in.gov.br/web/dou/-/teste",
    )
    db.session.add(m)
    db.session.commit()

    assert resolve_pdf_for_mention("23/11/2026", "DO1", folder=pdf_dir) == str(target)
    updated = link_mentions_to_pdfs(date_iso="2026-11-23", folder=pdf_dir)
    assert updated == 1
    assert db.session.get(Mention, "m-test-1").pdf_path == str(target)

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}

    r_status = client.get("/api/pdf_archive/status")
    assert r_status.status_code == 200
    assert r_status.get_json()["config"]["folder"] == str(pdf_dir)

    r_open = client.get("/api/pdf_archive/open?mention_id=m-test-1")
    assert r_open.status_code == 200
    assert r_open.mimetype == "application/pdf"
    assert r_open.data.startswith(b"%PDF")

    # Proteção contra acesso fora da pasta configurada
    outside_pdf = tmp_path / "fora.pdf"
    outside_pdf.write_bytes(_make_sample_pdf_bytes(1))
    m_out = Mention(
        id="m-outside",
        empresa="OUT",
        cnpj="111",
        cnpj_norm="111",
        secao="DO1",
        data="23/11/2026",
        pdf_path=str(outside_pdf),
    )
    db.session.add(m_out)
    db.session.commit()
    r_forbidden = client.get("/api/pdf_archive/open?mention_id=m-outside")
    assert r_forbidden.status_code == 403

    # Validação de entrada e permissão em POST /api/pdf_archive/run
    r_bad_month = client.post("/api/pdf_archive/run", json={"year": 2026, "month": 13})
    assert r_bad_month.status_code == 400
    r_bad_date = client.post("/api/pdf_archive/run", json={"date": "data-invalida"})
    assert r_bad_date.status_code == 400

    with client.session_transaction() as sess:
        sess["user"] = {"username": "viewer", "role": "user"}
    r_non_master = client.post("/api/pdf_archive/run", json={"date": "23/11/2026"})
    assert r_non_master.status_code == 403


def test_layouts_target_path_resolve_and_ensure_day_pdfs(app_ctx, monkeypatch):
    """Testa os 3 layouts (ano_mes, ano, nenhum), fallback de localização e ensure_day_pdfs."""
    from rodou_dashboard.app.models import Settings
    from rodou_dashboard.app.runtime.pdf_search import ensure_day_pdfs

    _, tmp_path = app_ctx
    base = tmp_path / "pdfs"

    assert build_pdf_target_path(base, "2026-11-23", "1", layout="ano_mes") == (
        base / "2026" / "11" / "DOU_2026-11-23_Secao1.pdf"
    )
    assert build_pdf_target_path(base, "2026-11-23", "1", layout="ano") == (
        base / "2026" / "DOU_2026-11-23_Secao1.pdf"
    )
    assert build_pdf_target_path(base, "2026-11-23", "1", layout="nenhum") == (
        base / "DOU_2026-11-23_Secao1.pdf"
    )

    sample_pdf = _make_sample_pdf_bytes(1)
    for lay in ("ano_mes", "ano", "nenhum"):
        lay_dir = tmp_path / f"dir_{lay}"
        p = build_pdf_target_path(lay_dir, "2026-11-23", "1", layout=lay)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(sample_pdf)

        # ensure_day_pdfs encontra no layout configurado sem baixar da rede
        monkeypatch.setenv("REGISTRALE_PDF_DIR", str(lay_dir))
        rec = Settings.query.filter_by(key="global_settings").first()
        if not rec:
            rec = Settings(key="global_settings")
            db.session.add(rec)
        rec.set_value({"pdf_archive": {"enabled": True, "folder": str(lay_dir), "layout": lay, "sections": ["1"]}})
        db.session.commit()

        files, errors = ensure_day_pdfs("2026-11-23", ["1"])
        assert errors == []
        assert len(files) == 1
        assert files[0][0] == "1"
        assert files[0][2] == p

    # Troca de layout sem mover arquivos antigos: resolve_pdf_for_mention ainda acha em ano_mes
    old_dir = tmp_path / "dir_ano_mes"
    assert resolve_pdf_for_mention("23/11/2026", "DO1", folder=old_dir, layout="nenhum") == str(
        old_dir / "2026" / "11" / "DOU_2026-11-23_Secao1.pdf"
    )


def test_reorganize_pdfs_without_overwrite_and_api_confirm(app_ctx, monkeypatch):
    """Reorganização move para o novo layout, não sobrescreve existentes e exige confirmação na API."""
    from rodou_dashboard.app.models import Settings
    from rodou_dashboard.app.runtime.pdf_archiver import reorganize_pdfs

    app, tmp_path = app_ctx
    pdf_dir = tmp_path / "pdfs_reorg"
    monkeypatch.setenv("REGISTRALE_PDF_DIR", str(pdf_dir))
    sample_a = _make_sample_pdf_bytes(1)
    sample_b = _make_sample_pdf_bytes(2)

    # Arquivo em ano_mes que será movido para nenhum
    src1 = build_pdf_target_path(pdf_dir, "2026-11-23", "1", layout="ano_mes")
    src1.parent.mkdir(parents=True, exist_ok=True)
    src1.write_bytes(sample_a)

    # Arquivo duplicado (existe em ano_mes E no destino nenhum): destino NÃO deve ser sobrescrito
    src2 = build_pdf_target_path(pdf_dir, "2026-11-23", "2", layout="ano_mes")
    src2.write_bytes(sample_a)
    dest2 = build_pdf_target_path(pdf_dir, "2026-11-23", "2", layout="nenhum")
    dest2.write_bytes(sample_b)

    m = Mention(id="m-reorg-1", empresa="EMP", cnpj="111", cnpj_norm="111", secao="DO1", data="23/11/2026", pdf_path=str(src1))
    db.session.add(m)
    rec = Settings.query.filter_by(key="global_settings").first()
    if not rec:
        rec = Settings(key="global_settings")
        db.session.add(rec)
    rec.set_value({"pdf_archive": {"enabled": True, "folder": str(pdf_dir), "layout": "nenhum", "sections": ["1", "2"]}})
    db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}

    # Sem confirm=True -> 400 e nada movido
    r_no_confirm = client.post("/api/pdf_archive/reorganize", json={"layout": "nenhum"})
    assert r_no_confirm.status_code == 400
    assert src1.is_file()

    # Com confirm=True -> move src1, pula src2 sem sobrescrever dest2, atualiza Mention.pdf_path e persiste layout
    r_ok = client.post("/api/pdf_archive/reorganize", json={"layout": "nenhum", "confirm": True})
    assert r_ok.status_code == 200
    data = r_ok.get_json()
    assert data["moved"] == 1
    assert data["skipped"] == 1
    assert not src1.exists()
    assert (pdf_dir / "DOU_2026-11-23_Secao1.pdf").is_file()
    assert src2.is_file()
    assert dest2.read_bytes() == sample_b

    from rodou_dashboard.app.runtime.pdf_archiver import get_pdf_archive_config
    assert get_pdf_archive_config()["layout"] == "nenhum"

    db.session.refresh(m)
    assert m.pdf_path == str(pdf_dir / "DOU_2026-11-23_Secao1.pdf")

    # Idempotente se rodar de novo
    res2 = reorganize_pdfs(pdf_dir, "nenhum")
    assert res2["moved"] == 0
    assert res2["skipped"] == 1
    assert res2["already_in_place"] == 2


def test_validate_pdf_folder_and_onboarding_flow(app_ctx, monkeypatch):
    """Validação rejeita relativo, traversal, pasta do programa e sem escrita; onboarding grava e marca feito."""
    from pathlib import Path as RealPath
    from rodou_dashboard.app.models import Company
    from rodou_dashboard.app.runtime.paths import get_base_dir
    from rodou_dashboard.app.runtime.pdf_archiver import validate_pdf_folder

    app, tmp_path = app_ctx

    with pytest.raises(ValueError, match="absoluto"):
        validate_pdf_folder("pasta/relativa")

    with pytest.raises(ValueError, match=r"\.\."):
        validate_pdf_folder(str(tmp_path / "a" / ".." / "b"))

    with pytest.raises(ValueError, match="instalação"):
        validate_pdf_folder(str(get_base_dir()))

    # Simula falta de permissão de escrita
    readonly_dir = tmp_path / "sem_permissao"
    readonly_dir.mkdir()
    orig_write_text = RealPath.write_text

    def _deny_write(self, *args, **kwargs):
        if self.parent == readonly_dir:
            raise PermissionError("Permissão negada")
        return orig_write_text(self, *args, **kwargs)

    monkeypatch.setattr(RealPath, "write_text", _deny_write)
    with pytest.raises(ValueError, match="permissão de escrita"):
        validate_pdf_folder(str(readonly_dir))
    monkeypatch.undo()

    # Mesmo com dados existentes, needs_pdf_onboarding é True para quem nunca escolheu
    db.session.add(Company(nome="Emp Existente", cnpj="24.684.423/0001-36", cnpj_norm="24684423000136", status=True))
    db.session.commit()

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}

    r_status1 = client.get("/api/admin/first_run_status")
    assert r_status1.status_code == 200
    assert r_status1.get_json()["needs_pdf_onboarding"] is True

    # Onboarding rejeita pasta inválida
    r_bad = client.post("/api/admin/pdf_onboarding", json={"folder": "relativo", "layout": "ano"})
    assert r_bad.status_code == 400

    # Onboarding válido grava pdf_archive e marca pdf_onboarding_done
    target_dir = tmp_path / "meus_pdfs"
    r_good = client.post(
        "/api/admin/pdf_onboarding",
        json={"enabled": True, "folder": str(target_dir), "layout": "ano", "sections": ["1", "3"]},
    )
    assert r_good.status_code == 200
    assert r_good.get_json()["pdf_onboarding_done"] is True
    assert r_good.get_json()["pdf_archive"]["layout"] == "ano"

    r_status2 = client.get("/api/admin/first_run_status")
    assert r_status2.get_json()["needs_pdf_onboarding"] is False


@pytest.mark.live
def test_live_archive_extra_edition_nov2026(tmp_path):
    """Teste ao vivo real: baixa a Edição Extra A (2 páginas) de 23/11/2026 via pesquisa.in.gov.br."""
    res = archive_date_pdfs(
        "2026-11-23",
        folder=tmp_path,
        sections=["extra"],
        prefer_inlabs=False,
    )
    assert res["status"] == "success"
    assert len(res["saved_files"]) >= 1
    saved_path = Path(res["saved_files"][0])
    assert is_valid_pdf_file(saved_path)
    assert len(PdfReader(str(saved_path)).pages) == 2
