import os
import re
import json
import time
import logging
import threading
import warnings
from datetime import datetime, timezone, timedelta

# Suprime avisos de fim de vida do Python 3.10 emitidos pelo google.api_core
warnings.filterwarnings("ignore", category=FutureWarning, module="google")
warnings.filterwarnings("ignore", message=".*Python version.*")

logger = logging.getLogger(__name__)

# Scopes necessários para ler e interagir com planilhas Google
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    'https://www.googleapis.com/auth/spreadsheets'
]

_scheduler_thread = None
_scheduler_lock = threading.Lock()
_last_sync_timestamp = 0


def extract_spreadsheet_id(spreadsheet_url_or_id: str) -> str:
    """
    Extrai o ID da planilha a partir de uma URL completa do Google Sheets ou valida o ID informado diretamente.
    Exemplos de URL suportadas:
      - https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0
      - https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
      - 1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms
    """
    if not spreadsheet_url_or_id:
        raise ValueError("URL ou ID da planilha não foi informado.")

    raw_input = str(spreadsheet_url_or_id).strip()

    # Busca padrão /d/<ID>
    match = re.search(r'/d/([a-zA-Z0-9-_]+)', raw_input)
    if match:
        return match.group(1)

    # Se não contém barra e tem formato válido de ID do Google
    if re.match(r'^[a-zA-Z0-9-_]{15,}$', raw_input):
        return raw_input

    raise ValueError("URL ou ID da planilha inválido. Certifique-se de que é um link válido do Google Sheets.")


def get_credentials_info(credentials_json_or_dict):
    """
    Converte o valor de credenciais (string JSON ou dict) em um dicionário validado.
    """
    if not credentials_json_or_dict:
        raise ValueError("Credenciais da Conta de Serviço (JSON) não foram fornecidas.")

    if isinstance(credentials_json_or_dict, dict):
        creds_dict = credentials_json_or_dict
    elif isinstance(credentials_json_or_dict, str):
        raw_str = credentials_json_or_dict.strip()
        if not raw_str:
            raise ValueError("O campo de credenciais JSON está vazio.")
        try:
            creds_dict = json.loads(raw_str)
        except Exception as e:
            raise ValueError(f"Formato JSON inválido nas credenciais: {str(e)}")
    else:
        raise ValueError("Tipo inválido para credenciais. Esperado string JSON ou dict.")

    if not isinstance(creds_dict, dict):
        raise ValueError("As credenciais devem ser um objeto JSON válido.")

    client_email = creds_dict.get('client_email')
    private_key = creds_dict.get('private_key')

    if not client_email or not private_key:
        raise ValueError("O arquivo JSON de credenciais deve conter os campos 'client_email' e 'private_key'.")

    return creds_dict


def get_sheets_client(credentials_json_or_dict):
    """
    Cria e retorna um cliente autenticado da Google Sheets API v4 usando a Conta de Serviço (Service Account).
    """
    try:
        import googleapiclient.discovery
        from google.oauth2 import service_account
    except ImportError:
        raise ImportError("Bibliotecas do Google Sheets não instaladas. Certifique-se de instalar 'google-api-python-client' e 'google-auth'.")

    creds_info = get_credentials_info(credentials_json_or_dict)
    creds = service_account.Credentials.from_service_account_info(
        creds_info,
        scopes=SCOPES
    )
    service = googleapiclient.discovery.build('sheets', 'v4', credentials=creds, cache_discovery=False)
    return service, creds_info


def test_sheets_connection(credentials_json_or_dict, spreadsheet_url_or_id: str, sheet_name: str = None):
    """
    Testa a autenticação com a API do Google Sheets e o acesso à planilha privada especificada.
    Retorna metadados da planilha e uma prévia das primeiras linhas para validação.
    """
    spreadsheet_id = extract_spreadsheet_id(spreadsheet_url_or_id)
    service, creds_info = get_sheets_client(credentials_json_or_dict)

    try:
        # 1. Obtém metadados da planilha
        spreadsheet_meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        title = spreadsheet_meta.get('properties', {}).get('title', 'Sem título')
        sheets = [s.get('properties', {}).get('title') for s in spreadsheet_meta.get('sheets', [])]

        # 2. Define a aba a consultar
        target_sheet = sheet_name.strip() if sheet_name and sheet_name.strip() else (sheets[0] if sheets else None)
        if not target_sheet:
            raise ValueError("A planilha não possui nenhuma aba visível.")

        # 3. Lê uma amostra de até 10 linhas
        range_sample = f"'{target_sheet}'!A1:Z10"
        values_res = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_sample,
            valueRenderOption='FORMATTED_VALUE'
        ).execute()

        sample_rows = values_res.get('values', [])

        return {
            "status": "success",
            "message": f"Conexão com a planilha '{title}' estabelecida com sucesso!",
            "spreadsheet_id": spreadsheet_id,
            "title": title,
            "sheets": sheets,
            "selected_sheet": target_sheet,
            "client_email": creds_info.get('client_email', ''),
            "sample_rows": sample_rows,
            "total_sample_rows": len(sample_rows)
        }

    except Exception as e:
        error_msg = str(e)
        client_email = creds_info.get('client_email', 'conta de serviço')
        if "403" in error_msg or "permission" in error_msg.lower():
            raise Exception(
                f"Permissão negada (403). Certifique-se de ter compartilhado a planilha com o e-mail da Conta de Serviço: '{client_email}' com permissão de 'Leitor' (Viewer)."
            )
        elif "404" in error_msg or "not found" in error_msg.lower():
            raise Exception(
                f"Planilha não encontrada (404). Verifique se o ID '{spreadsheet_id}' está correto."
            )
        else:
            raise Exception(f"Erro ao acessar Google Sheets API: {error_msg}")


def parse_sheet_grid(values: list, orientation: str = 'rows', mapping: dict = None) -> list:
    """
    Processa a matriz de valores brutos da planilha e retorna lista de dicionários mapeados.
    Suporta orientação por linhas (cabeçalho na linha 1) ou por colunas (cabeçalho na coluna 1).
    """
    if not values or not isinstance(values, list):
        return []

    if not mapping:
        mapping = {}

    raw_data = []

    if orientation == 'rows':
        # Cabeçalhos na primeira linha
        if len(values) < 2:
            return []
        headers = [str(h).strip() for h in values[0]]
        for row in values[1:]:
            record = {}
            for i, val in enumerate(row):
                if i < len(headers):
                    header_name = headers[i]
                    if header_name:
                        record[header_name] = str(val).strip()
            if record:
                raw_data.append(record)

    elif orientation == 'columns':
        # Cabeçalhos na primeira coluna
        if not values or not values[0]:
            return []

        max_cols = max(len(row) for row in values if row)
        headers = [str(r[0]).strip() if r and len(r) > 0 else "" for r in values]

        for col_idx in range(1, max_cols):
            record = {}
            for row_idx, row in enumerate(values):
                if row_idx < len(headers):
                    header_name = headers[row_idx]
                    if header_name and len(row) > col_idx:
                        record[header_name] = str(row[col_idx]).strip()
            if record:
                raw_data.append(record)
    else:
        raise ValueError(f"Orientação inválida: '{orientation}'. Use 'rows' ou 'columns'.")

    # Mapeamento dos campos
    target_empresa = mapping.get("empresa") or "Razão Social"
    target_cnpj = mapping.get("cnpj") or "CNPJ"

    def _get_val(record, target_name, fallbacks=None):
        if not fallbacks:
            fallbacks = []
        if target_name in record and record[target_name]:
            return record[target_name]
        for k, v in record.items():
            if k.lower() == target_name.lower() and v:
                return v
        for fb in fallbacks:
            if fb in record and record[fb]:
                return record[fb]
            for k, v in record.items():
                if k.lower() == fb.lower() and v:
                    return v
        return ""

    mapped_data = []
    for record in raw_data:
        nome_val = _get_val(record, target_empresa, ["Empresa", "Nome", "Razao Social", "Nome Fantasia", "Cliente"])
        cnpj_val = _get_val(record, target_cnpj, ["CNPJ/CPF", "Documento", "CPF/CNPJ"])

        cnpj_norm = re.sub(r'[^0-9]', '', cnpj_val) if cnpj_val else ""

        # Formata CNPJ se tiver 14 dígitos
        cnpj_formatted = cnpj_val
        if len(cnpj_norm) == 14:
            cnpj_formatted = f"{cnpj_norm[:2]}.{cnpj_norm[2:5]}.{cnpj_norm[5:8]}/{cnpj_norm[8:12]}-{cnpj_norm[12:]}"

        if nome_val or cnpj_norm:
            mapped_data.append({
                "nome": nome_val or "N/A",
                "cnpj": cnpj_formatted or cnpj_val or "N/A",
                "cnpj_norm": cnpj_norm,
                "status": True,
                "origem": "Google Sheets"
            })

    return mapped_data


def fetch_and_parse_sheet_api(credentials_json_or_dict, spreadsheet_url_or_id: str, sheet_name: str = None, range_name: str = None, orientation: str = 'rows', mapping: dict = None) -> list:
    """
    Busca os dados de uma planilha privada utilizando a Google Sheets API v4 e os converte em registros mapeados.
    """
    spreadsheet_id = extract_spreadsheet_id(spreadsheet_url_or_id)
    service, _ = get_sheets_client(credentials_json_or_dict)

    if not sheet_name or not sheet_name.strip():
        meta = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = meta.get('sheets', [])
        if not sheets:
            raise ValueError("A planilha não possui abas disponíveis.")
        sheet_name = sheets[0].get('properties', {}).get('title', 'Página1')
    else:
        sheet_name = sheet_name.strip()

    target_range = range_name.strip() if range_name and range_name.strip() else f"'{sheet_name}'"

    res = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=target_range,
        valueRenderOption='FORMATTED_VALUE'
    ).execute()

    values = res.get('values', [])
    if not values:
        logger.warning(f"Planilha {spreadsheet_id} (aba {sheet_name}) retornou vazia.")
        return []

    return parse_sheet_grid(values, orientation=orientation, mapping=mapping)


def get_sheet_cnpjs_list(credentials_json=None, spreadsheet_url=None, sheet_name=None) -> list:
    """Retorna uma lista de CNPJs únicos e normalizados extraídos da planilha do Google Sheets."""
    from ..models import Settings
    if not spreadsheet_url or not credentials_json:
        settings_record = Settings.query.filter_by(key='global_settings').first()
        if settings_record:
            gs = settings_record.get_value().get('google_sheets', {})
            spreadsheet_url = spreadsheet_url or gs.get('spreadsheet_url') or gs.get('spreadsheet_id')
            credentials_json = credentials_json or gs.get('credentials_json')
            sheet_name = sheet_name or gs.get('sheet_name')

    if not spreadsheet_url or not credentials_json:
        return []

    records = fetch_and_parse_sheet_api(
        credentials_json_or_dict=credentials_json,
        spreadsheet_url_or_id=spreadsheet_url,
        sheet_name=sheet_name
    )

    cnpjs = []
    seen = set()
    for r in records:
        c = r.get('cnpj')
        cn = r.get('cnpj_norm')
        if cn and cn not in seen:
            seen.add(cn)
            cnpjs.append({
                "cnpj": c or cn,
                "cnpj_norm": cn,
                "nome": r.get('nome', 'N/A')
            })
    return cnpjs


def executar_sincronizacao_sheets(app=None, config_override=None) -> dict:
    """
    Executa a sincronização completa da planilha Google Sheets com o banco de dados do Registrale.
    Atualiza/insere registros na tabela Company, atualiza os arquivos YAML de busca e registra no SyncHistory.
    """
    from ..models import db, Settings, Company, SyncHistory
    from ..services.dag_config_service import rebuild_yaml_from_db, normalize_cnpj

    gs_config = {}
    if config_override:
        gs_config = config_override
    else:
        settings_record = Settings.query.filter_by(key='global_settings').first()
        if settings_record:
            all_settings = settings_record.get_value()
            if isinstance(all_settings, dict):
                gs_config = all_settings.get('google_sheets', {})

    spreadsheet_url = gs_config.get('spreadsheet_url') or gs_config.get('spreadsheet_id')
    credentials_json = gs_config.get('credentials_json')

    if not spreadsheet_url:
        raise ValueError("URL ou ID da planilha não configurada no Google Sheets.")
    if not credentials_json:
        raise ValueError("Credenciais da Conta de Serviço (JSON) não configuradas.")

    orientation = gs_config.get('orientation', 'rows')
    mapping = gs_config.get('mapping', {})
    sheet_name = gs_config.get('sheet_name', '')

    logger.info(f"Iniciando sincronização via Google Sheets API para: {spreadsheet_url}")

    # 2. Buscar e processar os dados da API
    imported_data = fetch_and_parse_sheet_api(
        credentials_json_or_dict=credentials_json,
        spreadsheet_url_or_id=spreadsheet_url,
        sheet_name=sheet_name,
        orientation=orientation,
        mapping=mapping
    )

    if not imported_data:
        msg = "A planilha não contém dados válidos ou está vazia."
        _registrar_historico("Aviso Google Sheets", msg)
        return {"status": "warning", "message": msg, "imported": 0, "updated": 0, "total": 0}

    # 3. Persistir no banco de dados SQLite
    imported_count = 0
    updated_count = 0

    for record in imported_data:
        cnpj_norm_val = record.get('cnpj_norm') or normalize_cnpj(record.get('cnpj'))
        if not cnpj_norm_val:
            continue

        company = Company.query.filter_by(cnpj_norm=cnpj_norm_val).first()
        if not company:
            company = Company.query.filter_by(cnpj=record.get('cnpj')).first()

        if company:
            if company.origem != 'Manual':
                company.nome = record.get('nome') or company.nome
                company.cnpj = record.get('cnpj') or company.cnpj
                company.cnpj_norm = cnpj_norm_val
                company.status = True
                updated_count += 1
            else:
                company.status = True
        else:
            new_company = Company(
                nome=record.get('nome') or "N/A",
                cnpj=record.get('cnpj') or cnpj_norm_val,
                cnpj_norm=cnpj_norm_val,
                status=True,
                origem='Google Sheets'
            )
            db.session.add(new_company)
            imported_count += 1

    db.session.commit()

    # 4. Atualizar o YAML de busca das DAGs
    try:
        rebuild_yaml_from_db()
    except Exception as err_rebuild:
        logger.error(f"Erro ao reconstruir YAML após sincronização Google Sheets: {err_rebuild}")

    # 5. Registrar no histórico
    global _last_sync_timestamp
    _last_sync_timestamp = time.time()

    detalhes = f"Google Sheets sincronizado com sucesso: {imported_count} inserida(s), {updated_count} atualizada(s). Total na planilha: {len(imported_data)}."
    _registrar_historico("Sincronização Google Sheets OK", detalhes)

    logger.info(detalhes)
    return {
        "status": "success",
        "message": detalhes,
        "imported": imported_count,
        "updated": updated_count,
        "total": len(imported_data)
    }


def _registrar_historico(evento: str, detalhes: str):
    """Auxiliar para adicionar registros na tabela SyncHistory."""
    try:
        from ..models import SyncHistory
        SyncHistory.log_event(evento, detalhes)
    except Exception as e:
        logger.error(f"Falha ao registrar histórico de sincronização: {e}")


def _sheets_scheduler_worker(app):
    """
    Worker em segundo plano para sincronização recorrente automática da planilha Google Sheets.
    """
    logger.info("Iniciando scheduler de sincronização recorrente do Google Sheets...")
    global _last_sync_timestamp

    while True:
        try:
            time.sleep(30)  # Verifica periodicamente a cada 30 segundos
            with app.app_context():
                from ..models import Settings
                settings_record = Settings.query.filter_by(key='global_settings').first()
                if not settings_record:
                    continue

                all_settings = settings_record.get_value()
                if not isinstance(all_settings, dict):
                    continue

                gs = all_settings.get('google_sheets', {})
                auto_sync = gs.get('auto_sync', False)
                spreadsheet_url = gs.get('spreadsheet_url') or gs.get('spreadsheet_id')
                credentials_json = gs.get('credentials_json')

                if not auto_sync or not spreadsheet_url or not credentials_json:
                    continue

                # Intervalo configurado em minutos (padrão: 60 minutos)
                interval_minutes = int(gs.get('sync_interval', 60) or 60)
                interval_seconds = max(60, interval_minutes * 60)

                now = time.time()
                if (now - _last_sync_timestamp) >= interval_seconds:
                    logger.info(f"Executando rotina de sincronização recorrente do Google Sheets (intervalo: {interval_minutes}m)...")
                    try:
                        executar_sincronizacao_sheets(app)
                    except Exception as sync_err:
                        logger.error(f"Erro na sincronização recorrente do Google Sheets: {sync_err}")
                        _registrar_historico("Erro Sync Google Sheets", str(sync_err))
                    finally:
                        _last_sync_timestamp = now
        except Exception as loop_err:
            logger.error(f"Erro no loop do scheduler Google Sheets: {loop_err}")
            time.sleep(10)


def start_sheets_scheduler(app):
    """
    Inicia o daemon de sincronização recorrente caso ainda não esteja rodando.
    """
    global _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread is None or not _scheduler_thread.is_alive():
            _scheduler_thread = threading.Thread(
                target=_sheets_scheduler_worker,
                args=(app,),
                daemon=True,
                name="GoogleSheetsSchedulerThread"
            )
            _scheduler_thread.start()
            logger.info("Thread de scheduler Google Sheets iniciada.")

