"""Testes da página destacada do DOU por menção (Etapa 5)."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
import sys
import time

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas
from sqlalchemy import create_engine

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from rodou_dashboard.app import create_app
from rodou_dashboard.app.models import Mention, Settings, User, db
from rodou_dashboard.app.runtime.migrations import apply_migrations, get_schema_version
from rodou_dashboard.app.runtime.pdf_highlight import (
    generate_highlight_pdf_for_mention,
    generate_highlights_for_ids,
)
from rodou_dashboard.app.services.email_service import (
    EmailSender,
    is_email_attach_highlight_enabled,
)


def _make_3page_pdf(dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(dest))
    c.drawString(72, 720, "Pagina 1 - Diario Oficial sem ocorrencia relevante.")
    c.showPage()
    c.drawString(72, 720, "Pagina 2 - RESOLUCAO-RE: CNPJ 24.684.423/0002-30 e raiz 24.684.423.")
    c.showPage()
    c.drawString(72, 720, "Pagina 3 - Valor monetario R$ 24.684.423,00 nao deve contar.")
    c.save()


@pytest.fixture
def app_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "data"
    pdf_dir = tmp_path / "pdfs"
    data_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("REGISTRALE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("REGISTRALE_DB_PATH", str(data_dir / "database.db"))
    monkeypatch.setenv("REGISTRALE_PDF_DIR", str(pdf_dir))
    monkeypatch.setenv("FLASK_ENV", "testing")
    monkeypatch.setenv("REGISTRALE_DISABLE_SCHEDULER", "1")
    app = create_app()
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            u = User(username="admin", role="master")
            u.set_password("admin")
            db.session.add(u)
            db.session.commit()
        rec = Settings.query.filter_by(key="global_settings").first() or Settings(key="global_settings")
        rec.set_value({"pdf_archive": {"enabled": True, "folder": str(pdf_dir), "layout": "ano_mes"}})
        db.session.add(rec)
        db.session.commit()
        yield app, pdf_dir


def test_generate_highlight_extracts_page_2_and_adds_annotations(app_ctx) -> None:
    app, pdf_dir = app_ctx
    archived = pdf_dir / "2026" / "11" / "DOU_2026-11-23_Secao1.pdf"
    _make_3page_pdf(archived)

    out = generate_highlight_pdf_for_mention(
        mention_id="m/123",
        cnpj="24.684.423/0001-50",
        date_str="23/11/2026",
        section_str="DOU - Seção 1",
        pdf_folder=pdf_dir,
    )
    assert out is not None
    out_path = Path(out)
    assert out_path.is_file()
    assert out_path == pdf_dir / "destaques" / "2026-11-23" / "24684423_m_123.pdf"

    reader = PdfReader(str(out_path))
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert "Pagina 2" in (page.extract_text() or "")
    annots = page.get("/Annots")
    assert annots is not None and len(annots) >= 1
    subtypes = [a.get_object().get("/Subtype") for a in annots]
    assert "/Highlight" in subtypes


def test_generate_highlight_without_archived_pdf_returns_none(app_ctx) -> None:
    _app, pdf_dir = app_ctx
    out = generate_highlight_pdf_for_mention(
        mention_id="m-sem-pdf",
        cnpj="24.684.423/0001-50",
        date_str="19/11/2026",
        section_str="DOU - Seção 1",
        pdf_folder=pdf_dir,
    )
    assert out is None


def test_route_mention_highlight_pdf_and_background_helper(app_ctx) -> None:
    app, pdf_dir = app_ctx
    archived = pdf_dir / "2026" / "11" / "DOU_2026-11-23_Secao1.pdf"
    _make_3page_pdf(archived)

    db.session.add(Mention(
        id="m-hl-1",
        empresa="SURGITEC",
        cnpj="24.684.423/0001-50",
        cnpj_norm="24684423000150",
        secao="DOU - Seção 1",
        data="23/11/2026",
        trecho="CNPJ 24.684.423/0002-30",
        link="https://www.in.gov.br/web/dou/-/x",
    ))
    db.session.add(Mention(
        id="m-no-hl",
        empresa="OUTRA",
        cnpj="11.111.111/0001-11",
        cnpj_norm="11111111000111",
        secao="DOU - Seção 1",
        data="19/11/2026",
        trecho="sem pdf",
        link="https://www.in.gov.br/web/dou/-/y",
    ))
    db.session.commit()

    assert generate_highlights_for_ids(app, ["m-hl-1", "m-no-hl"]) == 1
    m1 = db.session.get(Mention, "m-hl-1")
    m2 = db.session.get(Mention, "m-no-hl")
    assert m1.highlight_pdf_path and os.path.isfile(m1.highlight_pdf_path)
    assert m2.highlight_pdf_path is None

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = {"username": "admin", "role": "master"}
        sess["expires_at"] = time.time() + 1800

    r_ok = client.get("/api/mention_highlight_pdf?mention_id=m-hl-1")
    assert r_ok.status_code == 200
    assert r_ok.mimetype == "application/pdf"
    assert r_ok.data.startswith(b"%PDF")

    r_404 = client.get("/api/mention_highlight_pdf?mention_id=m-no-hl")
    assert r_404.status_code == 404


def test_migration_003_adds_highlight_pdf_path(tmp_path: Path) -> None:
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE mentions (id TEXT PRIMARY KEY, empresa TEXT, pdf_path TEXT);")
    conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL);")
    conn.execute("INSERT INTO schema_version VALUES (1, 'baseline', '2026-01-01');")
    conn.execute("INSERT INTO schema_version VALUES (2, 'job_runs', '2026-01-01');")
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{db_file}")
    applied = apply_migrations(engine)
    assert applied == [3]
    assert get_schema_version(engine) == 3

    conn = sqlite3.connect(str(db_file))
    cols = [r[1] for r in conn.execute("PRAGMA table_info(mentions);").fetchall()]
    conn.close()
    assert "highlight_pdf_path" in cols


def test_email_attach_highlight_default_off_and_attachment(app_ctx, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert is_email_attach_highlight_enabled({}) is False
    assert is_email_attach_highlight_enabled({"email_attach_highlight": True}) is True

    att_file = tmp_path / "destaque.pdf"
    att_file.write_bytes(b"%PDF-1.4\n%test\n")

    sent_msgs: list[str] = []

    class FakeSMTP:
        def __init__(self, *args, **kwargs):
            pass
        def starttls(self):
            pass
        def login(self, u, p):
            pass
        def sendmail(self, frm, to, raw_msg):
            sent_msgs.append(raw_msg)
        def quit(self):
            pass

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    sender = EmailSender({"enabled": True, "server": "smtp.ex.com", "port": 587})
    assert sender.send_custom_email(["a@ex.com"], "Assunto", "<p>Oi</p>", attachments=[str(att_file)]) is True
    assert len(sent_msgs) == 1
    assert "application/pdf" in sent_msgs[0]
    assert "destaque.pdf" in sent_msgs[0]
