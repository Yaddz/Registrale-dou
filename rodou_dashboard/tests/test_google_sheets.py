"""Testes completos para a integração do Google Sheets API v4 (Service Account, extração, parsing e sync)."""

import pytest
import json
from unittest.mock import patch, MagicMock
from app.services.sheets_service import (
    extract_spreadsheet_id,
    get_credentials_info,
    parse_sheet_grid,
    test_sheets_connection as verify_sheets_connection,
    fetch_and_parse_sheet_api,
    executar_sincronizacao_sheets,
    start_sheets_scheduler
)
from app.models import db, Company, Settings, SyncHistory


# Mock de credenciais válidas para testes
MOCK_CREDENTIALS = {
    "type": "service_account",
    "project_id": "registrale-test",
    "private_key_id": "key12345",
    "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC3\n-----END PRIVATE KEY-----\n",
    "client_email": "registrale-sync@registrale-test.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token"
}
MOCK_CREDENTIALS_STR = json.dumps(MOCK_CREDENTIALS)


class TestSpreadsheetIdExtraction:
    """Testes de validação e extração do ID da planilha Google."""

    def test_extract_from_full_url(self):
        url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0"
        assert extract_spreadsheet_id(url) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    def test_extract_from_short_url(self):
        url = "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        assert extract_spreadsheet_id(url) == "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"

    def test_extract_from_raw_id(self):
        sheet_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        assert extract_spreadsheet_id(sheet_id) == sheet_id

    def test_extract_invalid_url_raises(self):
        with pytest.raises(ValueError, match="inválido"):
            extract_spreadsheet_id("https://google.com/not-a-sheet")

    def test_extract_empty_raises(self):
        with pytest.raises(ValueError, match="não foi informado"):
            extract_spreadsheet_id("")


class TestCredentialsValidation:
    """Testes para conversão e validação das credenciais da Service Account."""

    def test_valid_dict(self):
        creds = get_credentials_info(MOCK_CREDENTIALS)
        assert creds['client_email'] == "registrale-sync@registrale-test.iam.gserviceaccount.com"

    def test_valid_json_string(self):
        creds = get_credentials_info(MOCK_CREDENTIALS_STR)
        assert creds['client_email'] == "registrale-sync@registrale-test.iam.gserviceaccount.com"

    def test_missing_private_key_raises(self):
        invalid = {"client_email": "test@test.com"}
        with pytest.raises(ValueError, match="private_key"):
            get_credentials_info(invalid)

    def test_invalid_json_string_raises(self):
        with pytest.raises(ValueError, match="Formato JSON inválido"):
            get_credentials_info("{not a json}")

    def test_empty_credentials_raises(self):
        with pytest.raises(ValueError, match="não foram fornecidas"):
            get_credentials_info("")


class TestSheetParsing:
    """Testes de processamento da matriz de dados (linhas e colunas)."""

    def test_parse_rows_orientation(self):
        values = [
            ["Razão Social", "CNPJ", "E-mail", "Telefone", "UF", "Cidade"],
            ["Empresa Alpha Ltda", "11.222.333/0001-44", "alpha@teste.com", "11999990000", "SP", "São Paulo"],
            ["Empresa Beta S.A.", "22.333.444/0001-55", "beta@teste.com", "21988887777", "RJ", "Rio de Janeiro"]
        ]
        mapping = {
            "empresa": "Razão Social",
            "cnpj": "CNPJ",
            "email": "E-mail",
            "telefone": "Telefone",
            "uf": "UF",
            "cidade": "Cidade"
        }
        res = parse_sheet_grid(values, orientation='rows', mapping=mapping)
        assert len(res) == 2
        assert res[0]["nome"] == "Empresa Alpha Ltda"
        assert res[0]["cnpj_norm"] == "11222333000144"
        assert res[0]["cnpj"] == "11.222.333/0001-44"
        assert res[0]["origem"] == "Google Sheets"
        assert res[0]["status"] is True

        assert res[1]["nome"] == "Empresa Beta S.A."
        assert res[1]["cnpj_norm"] == "22333444000155"

    def test_parse_columns_orientation(self):
        values = [
            ["Razão Social", "Empresa Coluna A", "Empresa Coluna B"],
            ["CNPJ", "33.444.555/0001-66", "44.555.666/0001-77"],
            ["E-mail", "col_a@teste.com", "col_b@teste.com"],
            ["Telefone", "11911112222", "11933334444"],
            ["UF", "MG", "PR"],
            ["Cidade", "Belo Horizonte", "Curitiba"]
        ]
        mapping = {
            "empresa": "Razão Social",
            "cnpj": "CNPJ",
            "email": "E-mail",
            "telefone": "Telefone",
            "uf": "UF",
            "cidade": "Cidade"
        }
        res = parse_sheet_grid(values, orientation='columns', mapping=mapping)
        assert len(res) == 2
        assert res[0]["nome"] == "Empresa Coluna A"
        assert res[0]["cnpj_norm"] == "33444555000166"
        assert res[0]["origem"] == "Google Sheets"
        assert res[1]["nome"] == "Empresa Coluna B"
        assert res[1]["cnpj_norm"] == "44555666000177"

    def test_parse_empty_grid(self):
        assert parse_sheet_grid([], orientation='rows') == []
        assert parse_sheet_grid([["Header 1"]], orientation='rows') == []


class TestGoogleSheetsApiAndSync:
    """Testes de integração com a API mockada e sincronização com banco de dados SQLite."""

    @patch('app.services.sheets_service.get_sheets_client')
    def test_test_sheets_connection_success(self, mock_get_client):
        # Configura mock do Google Sheets API
        mock_service = MagicMock()
        mock_get_client.return_value = (mock_service, MOCK_CREDENTIALS)

        # Mock metadata
        mock_service.spreadsheets().get().execute.return_value = {
            "properties": {"title": "Minha Planilha de Clientes"},
            "sheets": [{"properties": {"title": "Clientes 2026"}}, {"properties": {"title": "Aba Secundária"}}]
        }

        # Mock sample rows
        mock_service.spreadsheets().values().get().execute.return_value = {
            "values": [
                ["Razão Social", "CNPJ", "E-mail"],
                ["Empresa Teste", "12.345.678/0001-99", "teste@teste.com"]
            ]
        }

        res = verify_sheets_connection(MOCK_CREDENTIALS, "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms", sheet_name="Clientes 2026")
        assert res["status"] == "success"
        assert res["title"] == "Minha Planilha de Clientes"
        assert "Clientes 2026" in res["sheets"]
        assert res["selected_sheet"] == "Clientes 2026"
        assert len(res["sample_rows"]) == 2

    @patch('app.services.sheets_service.fetch_and_parse_sheet_api')
    def test_executar_sincronizacao_sheets(self, mock_fetch, app):
        with app.app_context():
            db.create_all()
            
            # 1. Configura Settings
            settings_record = Settings.query.filter_by(key='global_settings').first()
            if not settings_record:
                settings_record = Settings(key='global_settings')
                db.session.add(settings_record)

            settings_record.set_value({
                "google_sheets": {
                    "spreadsheet_url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
                    "credentials_json": MOCK_CREDENTIALS_STR,
                    "sheet_name": "Aba1",
                    "orientation": "rows",
                    "mapping": {"empresa": "Razão Social", "cnpj": "CNPJ"}
                }
            })
            db.session.commit()

            # 2. Mock dos dados retornados da API
            mock_fetch.return_value = [
                {
                    "nome": "Empresa Importada 1",
                    "cnpj": "55.666.777/0001-88",
                    "cnpj_norm": "55666777000188",
                    "email": "imp1@teste.com",
                    "telefone": "11988880000",
                    "uf": "SP",
                    "cidade": "Campinas",
                    "situacao": "Ativa",
                    "origem": "Google Sheets"
                },
                {
                    "nome": "Empresa Importada 2",
                    "cnpj": "66.777.888/0001-99",
                    "cnpj_norm": "66777888000199",
                    "email": "imp2@teste.com",
                    "telefone": "21977770000",
                    "uf": "RJ",
                    "cidade": "Niterói",
                    "situacao": "Ativa",
                    "origem": "Google Sheets"
                }
            ]

            # 3. Executa sincronização
            result = executar_sincronizacao_sheets(app=app)
            assert result["status"] == "success"
            assert result["imported"] == 2
            assert result["total"] == 2

            # 4. Verifica inserção no banco
            comp1 = Company.query.filter_by(cnpj_norm="55666777000188").first()
            assert comp1 is not None
            assert comp1.nome == "Empresa Importada 1"
            assert comp1.origem == "Google Sheets"
            assert comp1.status is True

            comp2 = Company.query.filter_by(cnpj_norm="66777888000199").first()
            assert comp2 is not None
            assert comp2.nome == "Empresa Importada 2"
            assert comp2.origem == "Google Sheets"

            # 5. Verifica registro no SyncHistory
            history = SyncHistory.query.filter(SyncHistory.evento.like("%Google Sheets%")).first()
            assert history is not None

            # 6. Re-executa com atualização de dados
            mock_fetch.return_value = [
                {
                    "nome": "Empresa Importada 1 Atualizada",
                    "cnpj": "55.666.777/0001-88",
                    "cnpj_norm": "55666777000188",
                    "origem": "Google Sheets",
                    "status": True
                }
            ]
            result_update = executar_sincronizacao_sheets(app=app)
            assert result_update["status"] == "success"
            assert result_update["updated"] == 1
            assert result_update["imported"] == 0

            comp1_updated = Company.query.filter_by(cnpj_norm="55666777000188").first()
            assert comp1_updated.nome == "Empresa Importada 1 Atualizada"


class TestGoogleSheetsRoutes:
    """Testes das rotas HTTP /api/google_sheets/test e /api/google_sheets/sync."""

    @patch('app.services.sheets_service.test_sheets_connection')
    def test_route_test_connection_endpoint(self, mock_test, auth_client, app):
        with app.app_context():
            db.create_all()

        mock_test.return_value = {
            "status": "success",
            "message": "Conexão estabelecida com sucesso!",
            "title": "Planilha Teste",
            "sheets": ["Página1"],
            "sample_rows": [["Razão Social", "CNPJ"]]
        }

        response = auth_client.post('/api/google_sheets/test', json={
            "spreadsheet_url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
            "credentials_json": MOCK_CREDENTIALS_STR
        })
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "success"
        assert data["title"] == "Planilha Teste"

    def test_route_test_connection_missing_fields(self, auth_client, app):
        with app.app_context():
            db.create_all()

        response = auth_client.post('/api/google_sheets/test', json={})
        assert response.status_code == 400

    @patch('app.services.sheets_service.executar_sincronizacao_sheets')
    def test_route_sync_endpoint(self, mock_sync, auth_client, app):
        with app.app_context():
            db.create_all()

        mock_sync.return_value = {
            "status": "success",
            "message": "Sincronização concluída: 5 inseridas.",
            "imported": 5,
            "updated": 0,
            "total": 5
        }

        response = auth_client.post('/api/google_sheets/sync', json={})
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "success"
        assert data["imported"] == 5

    @patch('app.services.sheets_service.executar_sincronizacao_sheets')
    def test_route_sync_with_custom_config(self, mock_sync, auth_client, app):
        with app.app_context():
            db.create_all()

        mock_sync.return_value = {
            "status": "success",
            "message": "Importado via config",
            "imported": 2,
            "updated": 1,
            "deleted": 0,
            "total": 3
        }

        response = auth_client.post('/api/google_sheets/sync', json={"google_sheets": {"spreadsheet_url": "https://docs.google.com/spreadsheets/d/abc/edit"}})
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "success"
        assert data["imported"] == 2

    @patch('app.services.sheets_service.fetch_and_parse_sheet_api')
    def test_sync_delete_obsolete_enabled_removes_deleted_sheet_companies(self, mock_fetch, app):
        with app.app_context():
            db.create_all()
            
            # Cria empresa prévia do Google Sheets que foi "apagada" da planilha
            old_sheet_comp = Company(
                nome="Empresa Deletada",
                cnpj="11.111.111/0001-11",
                cnpj_norm="11111111000111",
                status=True,
                origem="Google Sheets"
            )
            # Cria empresa manual (que nunca deve ser deletada)
            manual_comp = Company(
                nome="Empresa Manual",
                cnpj="99.999.999/0001-99",
                cnpj_norm="99999999000199",
                status=True,
                origem="Manual"
            )
            db.session.add_all([old_sheet_comp, manual_comp])
            db.session.commit()

            # Config com delete_obsolete = True
            settings_record = Settings.query.filter_by(key='global_settings').first()
            if not settings_record:
                settings_record = Settings(key='global_settings')
                db.session.add(settings_record)

            settings_record.set_value({
                "google_sheets": {
                    "spreadsheet_url": "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit",
                    "credentials_json": MOCK_CREDENTIALS_STR,
                    "sheet_name": "Aba1",
                    "orientation": "rows",
                    "delete_obsolete": True
                }
            })
            db.session.commit()

            # Nova importação que contém apenas uma empresa diferente
            mock_fetch.return_value = [
                {
                    "nome": "Empresa Nova Planilha",
                    "cnpj": "22.222.222/0001-22",
                    "cnpj_norm": "22222222000122",
                    "origem": "Google Sheets"
                }
            ]

            result = executar_sincronizacao_sheets(app=app)
            assert result["status"] == "success"
            assert result["deleted"] == 1
            assert result["imported"] == 1

            # Empresa antiga do Google Sheets foi removida
            assert Company.query.filter_by(cnpj_norm="11111111000111").first() is None
            # Empresa nova foi adicionada
            assert Company.query.filter_by(cnpj_norm="22222222000122").first() is not None
            # Empresa manual foi preservada
            assert Company.query.filter_by(cnpj_norm="99999999000199").first() is not None
