import os
import re
import yaml
import json
import logging
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import math
import copy
from typing import List, Dict

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

logging.basicConfig(level=logging.INFO)

# Dinamicamente descobre o BASE_DIR baseado no app/services/sync_cnpj.py
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))

# Se estiver rodando dentro do docker, o BASE_DIR na verdade deveria ser / ou /app. 
# Como mapeamos /data no docker, vamos tentar usar o BASE_DIR e fazer fallback para /data se existir.
DATA_DIR = os.path.join(BASE_DIR, "data")
if not os.path.exists(DATA_DIR) and os.path.exists("/data"):
    DATA_DIR = "/data"

METADATA_FILE = os.path.join(DATA_DIR, "monitored_companies.json")

def formatar_cnpj(cnpj_bruto: str):
    if not cnpj_bruto:
        return None
    cnpj_limpo = re.sub(r'[^A-Za-z0-9]', '', str(cnpj_bruto)).upper()
    if len(cnpj_limpo) == 14:
        return f"{cnpj_limpo[:2]}.{cnpj_limpo[2:5]}.{cnpj_limpo[5:8]}/{cnpj_limpo[8:12]}-{cnpj_limpo[12:]}"
    return cnpj_bruto

def get_monitored_data(url_base: str, endpoint: str, headers: dict) -> List[Dict]:
    clientes_completos = []
    pagina_atual = 1
    url_completa = f"{url_base.rstrip('/')}/{endpoint.lstrip('/')}"
    
    # Configuração de sessão persistente com retry exponencial automático
    session = requests.Session()
    retry_strategy = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    while True:
        logging.info(f"Buscando {url_completa} - Página {pagina_atual}")
        try:
            resposta = session.get(
                url_completa,
                params={"pagina": pagina_atual, "limite": 100},
                headers=headers,
                timeout=45
            )
            
            if resposta.status_code == 404:
                logging.info(f"Fim dos registros atingido na página {pagina_atual} (Status 404).")
                break
                
            resposta.raise_for_status()
            
            dados_json = resposta.json()
            if not isinstance(dados_json, dict):
                logging.warning(f"Resposta inesperada na página {pagina_atual}: tipo {type(dados_json)}")
                break
                
            itens = dados_json.get("data", [])
            
            if not itens:
                logging.info(f"Nenhum registro retornado na página {pagina_atual}. Sincronização concluída.")
                break
            
            for item in itens:
                if not isinstance(item, dict):
                    continue
                cnpj = item.get("cnpj")
                if cnpj:
                    clientes_completos.append({
                        "nome": item.get("razao_social") or item.get("nome") or "N/A",
                        "cnpj": formatar_cnpj(str(cnpj).strip()),
                        "status": str(item.get("ativo", "1")) == "1"
                    })
            
            # Controle de paginação com suporte a múltiplos padrões da API
            meta = dados_json.get("meta")
            if isinstance(meta, dict):
                total_paginas = meta.get("total_paginas") or meta.get("paginas")
                if total_paginas:
                    try:
                        if pagina_atual >= int(total_paginas):
                            logging.info(f"Última página alcançada ({pagina_atual}/{total_paginas}).")
                            break
                    except (ValueError, TypeError):
                        pass

                proxima_pagina = meta.get("proxima_pagina")
                if proxima_pagina is not None:
                    # Se for numérico
                    try:
                        prox_num = int(proxima_pagina)
                        if prox_num <= pagina_atual:
                            logging.info(f"Próxima página ({prox_num}) menor ou igual à atual ({pagina_atual}). Fim.")
                            break
                        pagina_atual = prox_num
                        time.sleep(0.3)
                        continue
                    except (ValueError, TypeError):
                        # Caso venha como URL ou string
                        if isinstance(proxima_pagina, str) and "pagina=" in proxima_pagina:
                            match = re.search(r'pagina=(\d+)', proxima_pagina)
                            if match:
                                prox_num = int(match.group(1))
                                if prox_num <= pagina_atual:
                                    break
                                pagina_atual = prox_num
                                time.sleep(0.3)
                                continue

            # Se não houver indicador explícito no meta, incrementa pagina_atual
            pagina_atual += 1
            
            # Pequeno intervalo para respeitar o Rate Limit da API
            time.sleep(0.3)

        except requests.exceptions.RequestException as erro:
            logging.error(f"Erro persistente de rede/API na página {pagina_atual}: {erro}")
            if not clientes_completos:
                raise
            # Se já coletamos páginas anteriores mas houve falha irrecuperável, loga e interrompe
            break
        except Exception as erro:
            logging.error(f"Erro inesperado no processamento da página {pagina_atual}: {erro}")
            break
        
    logging.info(f"Total de registros obtidos da API: {len(clientes_completos)}")
    return clientes_completos

def atualizar_configuracoes(caminho_arquivo: str, clientes: List[Dict]):
    if not caminho_arquivo:
        logging.error("Caminho do arquivo YAML não fornecido.")
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    
    with open(METADATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(clientes, f, indent=4, ensure_ascii=False)
    logging.info(f"Metadados salvos em {METADATA_FILE}")

    # Fallback paths for DAG configs
    if not os.path.exists(caminho_arquivo):
        logging.warning(f"Caminho original não encontrado: {caminho_arquivo}")
        nome_arquivo = os.path.basename(caminho_arquivo)
        tentativas = [
            os.path.join(BASE_DIR, "dag_confs", nome_arquivo),
            os.path.join("/dag_confs", nome_arquivo),
            os.path.join(DATA_DIR, "..", "dag_confs", nome_arquivo),
            nome_arquivo
        ]
        for t in tentativas:
            if os.path.exists(t):
                logging.info(f"Arquivo localizado em caminho alternativo: {t}")
                caminho_arquivo = t
                break
        else:
            logging.error(f"Arquivo base não encontrado após várias tentativas: {caminho_arquivo}")
            raise FileNotFoundError(f"Arquivo base não encontrado: {caminho_arquivo}")

    try:
        with open(caminho_arquivo, 'r', encoding='utf-8') as f:
            config_template = yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Erro ao ler template: {e}")
        return

    arquivo_sync = caminho_arquivo
    cnpjs_ativos = []

    def _norm(cnpj): return re.sub(r'[^0-9]', '', str(cnpj))

    from flask import current_app
    if current_app:
        from app.models import db, Company
        try:
            # Sync to local DB
            for item in clientes:
                cnpj = item.get('cnpj')
                if not cnpj: continue
                cnpj_norm = _norm(cnpj)
                status = item.get('status', True)
                
                existing = Company.query.filter_by(cnpj_norm=cnpj_norm).first()
                if not existing:
                    new_comp = Company(
                        nome=item.get('nome', 'N/A'),
                        cnpj=cnpj,
                        cnpj_norm=cnpj_norm,
                        origem='GestãoClick',
                        status=status
                    )
                    db.session.add(new_comp)
                else:
                    if existing.origem != 'Manual':
                        existing.nome = item.get('nome', existing.nome)
                        existing.status = status
            
            db.session.commit()
            
            # Puxa apenas CNPJs ativos e monitorados (status=True)
            active_comps = Company.query.filter_by(status=True).all()
            cnpjs_ativos = sorted(list(set([c.cnpj for c in active_comps])))
        except Exception as e:
            logging.error(f"Erro no banco de dados via SQLAlchemy: {e}")
            cnpjs_ativos = sorted(list(set([c['cnpj'] for c in clientes if c.get('status', True)])))
    else:
        cnpjs_ativos = sorted(list(set([c['cnpj'] for c in clientes if c.get('status', True)])))

    if not cnpjs_ativos:
        logging.warning("Nenhum CNPJ ativo para monitorar.")
        return

    CHUNK_SIZE = 1500
    num_chunks = math.ceil(len(cnpjs_ativos) / CHUNK_SIZE)
    
    config_sync = copy.deepcopy(config_template)
    
    if 'dag' in config_sync:
        sessao_busca = config_sync['dag']['search']
        alvo_busca_template = sessao_busca[0] if isinstance(sessao_busca, list) else sessao_busca
        
        lista_buscas = []
        class QuotedString(str): pass
        def quoted_scalar_representer(dumper, data):
            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style="'")
        yaml.SafeDumper.add_representer(QuotedString, quoted_scalar_representer)

        for i in range(num_chunks):
            chunk = [QuotedString(c) for c in cnpjs_ativos[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]]
            alvo_busca = copy.deepcopy(alvo_busca_template)
            alvo_busca['terms'] = chunk
            alvo_busca['is_exact_search'] = True
            alvo_busca['force_rematch'] = True
            alvo_busca['full_text'] = False
            
            header_base = alvo_busca.get('header', 'SINCRONIZAÇÃO AUTOMÁTICA')
            header_base = re.sub(r'\s*-\s*PARTE\s*\d+', '', header_base)
            alvo_busca['header'] = f"{header_base} - PARTE {i+1}"
            lista_buscas.append(alvo_busca)
            logging.info(f"Parte {i+1} unificada com {len(chunk)} CNPJs")
            
        config_sync['dag']['search'] = lista_buscas

        tmp_arquivo_sync = arquivo_sync + ".tmp"
        with open(tmp_arquivo_sync, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config_sync, f, allow_unicode=True, sort_keys=False)
        os.replace(tmp_arquivo_sync, arquivo_sync)
        logging.info(f"Sincronização salva em {arquivo_sync} com {len(cnpjs_ativos)} CNPJs divididos em {num_chunks} blocos.")

def executar_sincronizacao():
    if load_dotenv: load_dotenv(override=True)

    url_api = os.getenv("BASE_URL")
    access_token = os.getenv("ACCESS_TOKEN")
    secret_token = os.getenv("SECRET_ACCESS_TOKEN")
    arquivo_yaml = os.getenv("YAML_PATH")

    # Fallback para configurações salvas no banco SQLite (dashboard)
    if not all([url_api, access_token, secret_token]):
        from flask import current_app
        if current_app:
            from app.models import Settings
            settings_record = Settings.query.filter_by(key='global_settings').first()
            if settings_record:
                ak = settings_record.get_value().get('api_keys', {})
                url_api = url_api or ak.get('gestaoclick_base_url')
                access_token = access_token or ak.get('gestaoclick_access_token')
                secret_token = secret_token or ak.get('gestaoclick_secret_token')
                arquivo_yaml = arquivo_yaml or ak.get('yaml_path')

    url_api = url_api or "https://api.gestaoclick.com/franquias"
    arquivo_yaml = arquivo_yaml or "Pesquisa_cnpj.yaml"
    if arquivo_yaml and arquivo_yaml.endswith("_sync.yaml"):
        arquivo_yaml = arquivo_yaml.replace("_sync.yaml", ".yaml")
        
    if not all([url_api, access_token, secret_token]):
        logging.error("Credenciais ausentes no .env, settings.json e banco local")
        return

    headers = {"access-token": access_token, "secret-access-token": secret_token, "Accept": "application/json"}
    
    logging.info(f"Iniciando sincronização completa via API: {url_api}...")
    clientes = get_monitored_data(url_api, "clientes", headers)

    if not clientes:
        logging.warning("Nenhum dado retornado da API")
        return
    
    atualizar_configuracoes(arquivo_yaml, clientes)
