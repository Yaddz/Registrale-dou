import gzip
import json
import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.models import Settings, db
from app.runtime.pdf_archiver import build_pdf_target_path


def _seed_pdf_settings(app, folder: Path, layout: str, enabled: bool = True) -> None:
    with app.app_context():
        rec = Settings.query.filter_by(key="global_settings").first()
        if not rec:
            rec = Settings(key="global_settings")
            db.session.add(rec)
        val = rec.get_value() if rec.value else {}
        if not isinstance(val, dict):
            val = {}
        val["pdf_archive"] = {
            "enabled": enabled,
            "folder": str(folder),
            "layout": layout,
            "sections": ["1", "2", "3", "extra"],
        }
        rec.set_value(val)
        db.session.commit()


@pytest.mark.parametrize("layout", ["ano_mes", "ano", "nenhum"])
def test_pdf_storage_stats_three_layouts(auth_client, app, tmp_path, monkeypatch, layout):
    monkeypatch.delenv("REGISTRALE_PDF_DIR", raising=False)
    pdf_root = tmp_path / f"pdfs_{layout}"
    pdf_root.mkdir(parents=True, exist_ok=True)
    _seed_pdf_settings(app, pdf_root, layout, enabled=True)

    # Cria PDFs sintéticos em 2 meses (2 dias em nov/2026, 1 dia em out/2026)
    samples = [
        ("2026-11-03", "1", b"%PDF-1.4\nnov3-s1\n" + b"a" * 100),
        ("2026-11-03", "2", b"%PDF-1.4\nnov3-s2\n" + b"b" * 200),
        ("2026-11-23", "1", b"%PDF-1.4\nnov23-s1\n" + b"c" * 300),
        ("2026-10-15", "1", b"%PDF-1.4\nout15-s1\n" + b"d" * 150),
    ]
    expected_bytes = sum(len(payload) for _, _, payload in samples)
    for date_iso, sec, payload in samples:
        target = build_pdf_target_path(pdf_root, date_iso, sec, layout=layout)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    resp = auth_client.get("/api/pdf_storage_stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "success"
    assert data["layout"] == layout
    assert data["folder"] == str(pdf_root)
    assert data["folder_exists"] is True

    assert data["totals"]["months"] == 2
    assert data["totals"]["days"] == 3
    assert data["totals"]["files"] == 4
    assert data["totals"]["size_bytes"] == expected_bytes

    months = data["months"]
    assert [m["month"] for m in months] == ["2026-11", "2026-10"]
    nov, out = months[0], months[1]
    assert nov["month_label"] == "11/2026"
    assert nov["days"] == 2
    assert nov["files"] == 3
    assert nov["size_bytes"] == sum(len(p) for d, _, p in samples if d.startswith("2026-11"))

    assert out["month_label"] == "10/2026"
    assert out["days"] == 1
    assert out["files"] == 1
    assert out["size_bytes"] == len(samples[3][2])


def test_pdf_storage_stats_internal_cache_separated(auth_client, app, tmp_path, monkeypatch):
    monkeypatch.delenv("REGISTRALE_PDF_DIR", raising=False)
    analyst_dir = tmp_path / "analyst_pdfs"
    analyst_dir.mkdir(parents=True, exist_ok=True)
    _seed_pdf_settings(app, analyst_dir, "ano_mes", enabled=False)

    data_dir = tmp_path / "registrale_data"
    cache_pdf = data_dir / "pdf_cache" / "2026" / "11" / "DOU_2026-11-24_Secao1.pdf"
    cache_pdf.parent.mkdir(parents=True, exist_ok=True)
    cache_pdf.write_bytes(b"%PDF-1.4\ncache\n" + b"x" * 250)

    text_dir = data_dir / "pdf_text"
    text_dir.mkdir(parents=True, exist_ok=True)
    text_file = text_dir / "DOU_2026-11-24_Secao1.json.gz"
    with gzip.open(text_file, "wt", encoding="utf-8") as fh:
        json.dump(["pagina 1"], fh)

    resp = auth_client.get("/api/pdf_storage_stats")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["enabled"] is False
    assert data["totals"]["files"] == 0
    assert data["internal_cache"]["pdf_cache"]["files"] == 1
    assert data["internal_cache"]["pdf_cache"]["size_bytes"] == cache_pdf.stat().st_size
    assert data["internal_cache"]["pdf_text"]["files"] == 1
    assert data["internal_cache"]["pdf_text"]["size_bytes"] == text_file.stat().st_size
    assert data["internal_cache"]["total_files"] == 2


def test_open_pdf_storage_folder_validation_and_launch(auth_client, app, tmp_path, monkeypatch):
    monkeypatch.delenv("REGISTRALE_PDF_DIR", raising=False)
    analyst_dir = tmp_path / "missing_pdfs"
    _seed_pdf_settings(app, analyst_dir, "ano_mes", enabled=True)

    # Destino inválido
    bad = auth_client.post("/api/pdf_storage/open_folder", json={"target": "../etc"})
    assert bad.status_code == 400

    # Pasta ainda não criada
    missing = auth_client.post("/api/pdf_storage/open_folder", json={"target": "analyst"})
    assert missing.status_code == 404

    # Pasta existente: abre sem erro (subprocess mockado)
    analyst_dir.mkdir(parents=True, exist_ok=True)
    with patch("subprocess.Popen") as popen_mock:
        ok = auth_client.post("/api/pdf_storage/open_folder", json={"target": "analyst"})
        assert ok.status_code == 200
        assert ok.get_json()["path"] == str(analyst_dir)
        popen_mock.assert_called_once()


def test_pdf_storage_stats_counts_root_and_old_layout(auth_client, app, tmp_path, monkeypatch):
    monkeypatch.delenv("REGISTRALE_PDF_DIR", raising=False)
    pdf_root = tmp_path / "pdfs_misto"
    pdf_root.mkdir()
    _seed_pdf_settings(app, pdf_root, "nenhum", enabled=True)

    # Layout ativo (nenhum): PDF na raiz.
    (pdf_root / "DOU_2026-11-03_S1.pdf").write_bytes(b"%PDF-1.4\n" + b"a" * 100)
    # Layout antigo (ano_mes): AAAA/MM/arquivo, mesmo dia e outro mês.
    old = pdf_root / "2026" / "11"
    old.mkdir(parents=True)
    (old / "DOU_2026-11-04_S2.pdf").write_bytes(b"%PDF-1.4\n" + b"b" * 200)
    old_oct = pdf_root / "2026" / "10"
    old_oct.mkdir()
    (old_oct / "DOU_2026-10-15_S1.pdf").write_bytes(b"%PDF-1.4\n" + b"c" * 50)
    # Layout antigo (ano) com nome sem data: cai na data de modificação.
    year_dir = pdf_root / "2025"
    year_dir.mkdir()
    avulso = year_dir / "avulso.pdf"
    avulso.write_bytes(b"%PDF-1.4\n")
    ts = datetime(2025, 7, 9, 12, 0).timestamp()
    os.utime(avulso, (ts, ts))

    data = auth_client.get("/api/pdf_storage_stats").get_json()
    assert data["status"] == "success"
    assert data["totals"]["files"] == 4
    by_month = {m["month"]: m for m in data["months"]}
    assert by_month["2026-11"]["files"] == 2
    assert by_month["2026-11"]["days"] == 2
    assert by_month["2026-10"]["files"] == 1
    assert by_month["2025-07"]["files"] == 1
    assert sum(m["files"] for m in data["months"]) == 4
