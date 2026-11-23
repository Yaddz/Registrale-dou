import os
import threading
import time
import requests
import subprocess
import json
import re
import urllib.parse
from datetime import datetime, timezone, timedelta

def normalize_date_str(value):
    """Converte datas vindas do painel/seletor para ISO (AAAA-MM-DD), formato
    exigido pelo parâmetro `trigger_date` das DAGs (Param format="date").

    Aceita: DD/MM/AAAA, D/M/AAAA, DD/MM/AA, DD-MM-AAAA, AAAA-MM-DD, AAAA/MM/DD
    e ISO com horário (AAAA-MM-DDTHH:MM...). Retorna None se vazio e lança
    ValueError se a data for inválida.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    raw = raw.split('T')[0].split(' ')[0]
    parts = [p for p in re.split(r'[/\-.]', raw) if p]
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"Data inválida: {value}")
    if len(parts[0]) == 4:          # AAAA-MM-DD / AAAA/MM/DD
        y, m, d = parts
    else:                           # DD/MM/AAAA ou DD/MM/AA
        d, m, y = parts
        if len(y) == 2:
            y = '20' + y
    if len(y) != 4:
        raise ValueError(f"Data inválida: {value}")
    return datetime(int(y), int(m), int(d)).strftime('%Y-%m-%d')


def get_airflow_url():
    """Retorna a URL base do Airflow a partir das variáveis de ambiente."""
    return os.getenv('AIRFLOW_URL', 'http://localhost:8080')

class AirflowTokenAuth(requests.auth.AuthBase):
    """Autenticação por token JWT da API v2 do Airflow 3 (POST /auth/token).

    O token é obtido sob demanda, mantido em cache e renovado ao expirar.
    Pode ser usado como `auth=` em qualquer chamada `requests`.
    """

    _lock = threading.Lock()
    _token = None
    _expires_at = 0.0
    TTL_SECONDS = 600

    @classmethod
    def _fetch_token(cls):
        user = os.getenv('AIRFLOW_USER', 'airflow')
        password = os.getenv('AIRFLOW_PASSWORD', 'airflow')
        res = requests.post(
            f"{get_airflow_url()}/auth/token",
            json={"username": user, "password": password},
            timeout=10,
        )
        res.raise_for_status()
        return res.json()["access_token"]

    @classmethod
    def get_token(cls, force=False):
        with cls._lock:
            if force or not cls._token or time.time() >= cls._expires_at:
                cls._token = cls._fetch_token()
                cls._expires_at = time.time() + cls.TTL_SECONDS
            return cls._token

    def __call__(self, r):
        r.headers['Authorization'] = f"Bearer {self.get_token()}"
        return r


def get_airflow_auth():
    """Retorna o objeto de autenticação (token JWT) para a API v2 do Airflow."""
    return AirflowTokenAuth()

def trigger_airflow_dag(dag_id, logical_date=None, **kwargs):
    """Tenta disparar uma DAG no Airflow via API REST ou Docker CLI.
    Retorna (success: bool, message: str, run_info: dict).
    """
    trigger_time_dt = datetime.now(timezone(timedelta(hours=-3)))
    trigger_time_iso = trigger_time_dt.isoformat()
    trigger_time_str = trigger_time_dt.strftime('%Y-%m-%dT%H:%M:%S')
    
    run_info = {
        "dag_id": dag_id,
        "dag_run_id": None,
        "trigger_time": trigger_time_str,
        "trigger_time_iso": trigger_time_iso,
        "trigger_ts": trigger_time_dt.timestamp()
    }
    
    try:
        airflow_url = get_airflow_url()
        auth = get_airflow_auth()
        dag_id_quoted = urllib.parse.quote(str(dag_id), safe='')
        
        # 1. Unpause the DAG
        patch_url = f"{airflow_url}/api/v2/dags/{dag_id_quoted}"
        requests.patch(patch_url, json={"is_paused": False}, auth=auth, timeout=5)
        
        # 2. Trigger the DAG
        trigger_url = f"{airflow_url}/api/v2/dags/{dag_id_quoted}/dagRuns"
        payload = {}
        unique_suffix = int(datetime.now().timestamp() * 1000)
        if logical_date:
            logical_date = normalize_date_str(logical_date)
        if logical_date:
            payload["dag_run_id"] = f"manual__{dag_id}_{logical_date}_{unique_suffix}"
        else:
            payload["dag_run_id"] = f"manual__{dag_id}_{unique_suffix}"
            
        # Airflow 3: as DAGs usam o logical_date como data de referência em
        # execuções manuais (a data escolhida vai às 12:00, horário de Brasília).
        if logical_date:
            payload["logical_date"] = f"{logical_date}T12:00:00-03:00"
        else:
            payload["logical_date"] = trigger_time_iso
        payload["conf"] = {}
        if logical_date:
            payload["conf"]["trigger_date"] = logical_date
        for k, v in kwargs.items():
            payload["conf"][k] = v
            
        response = requests.post(trigger_url, json=payload, auth=auth, timeout=10)
        
        if response.status_code in [200, 201]:
            resp_data = response.json() if response.content else {}
            dag_run_id = resp_data.get("dag_run_id")
            run_info["dag_run_id"] = dag_run_id
            return True, f"DAG {dag_id} disparada via API.", run_info
        else:
            return False, f"Erro Airflow API ({response.status_code}): {response.text}", run_info
    except Exception as e:
        # Fallback para docker exec caso a API não esteja acessível
        try:
            subprocess.run(["docker", "compose", "exec", "-T", "airflow-scheduler", "airflow", "dags", "unpause", dag_id], capture_output=True, timeout=15)
            cmd = ["docker", "compose", "exec", "-T", "airflow-scheduler", "airflow", "dags", "trigger", dag_id]
            conf_payload = {}
            if logical_date:
                conf_payload["trigger_date"] = logical_date
            conf_payload.update(kwargs)
            if conf_payload:
                cmd.extend(["--conf", json.dumps(conf_payload)])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                return True, f"DAG {dag_id} disparada via Docker CLI.", run_info
            else:
                return False, f"Erro Docker/Airflow: {result.stderr or result.stdout}", run_info
        except Exception as e2:
            return False, f"Falha API REST ({str(e)}) e falha Docker CLI ({str(e2)})", run_info

def toggle_airflow_dag(dag_id, is_paused=True):
    """Pausa ou despausa uma DAG no Airflow via REST API com fallback para Docker CLI."""
    if not dag_id:
        return False, "ID da DAG não informado."
    
    try:
        airflow_url = get_airflow_url()
        auth = get_airflow_auth()
        dag_id_quoted = urllib.parse.quote(str(dag_id), safe='')
        patch_url = f"{airflow_url}/api/v2/dags/{dag_id_quoted}"
        res = requests.patch(patch_url, json={"is_paused": bool(is_paused)}, auth=auth, timeout=5)
        if res.status_code in (200, 201):
            action = "pausada" if is_paused else "ativada"
            return True, f"DAG {dag_id} {action} com sucesso no Airflow."
    except Exception:
        pass
    
    # Fallback Docker CLI
    try:
        cmd_action = "pause" if is_paused else "unpause"
        res_sub = subprocess.run(["docker", "compose", "exec", "-T", "airflow-scheduler", "airflow", "dags", cmd_action, dag_id], capture_output=True, timeout=10)
        if res_sub.returncode == 0:
            return True, f"DAG {dag_id} atualizada via Docker CLI."
    except Exception:
        pass

    return True, "Status da rotina atualizado localmente."

def wait_for_specific_dag_runs(dag_id, run_ids, max_wait=1800, poll_interval=4):
    """
    Aguarda especificamente até que todos os `run_ids` da DAG indicada atinjam
    um estado terminal ('success' ou 'failed') no Airflow.
    Retorna (all_finished: bool, states_dict: dict).
    """
    import time
    import logging
    
    if not run_ids:
        return True, {}
        
    airflow_url = get_airflow_url()
    auth = get_airflow_auth()
    
    start_time = time.time()
    pending_runs = set(run_ids)
    run_states = {}
    dag_id_quoted = urllib.parse.quote(str(dag_id), safe='')
    
    # Aguarda 3 segundos iniciais para o scheduler do Airflow enfileirar
    time.sleep(3)
    
    while pending_runs and (time.time() - start_time) < max_wait:
        for run_id in list(pending_runs):
            try:
                run_id_quoted = urllib.parse.quote(str(run_id), safe='')
                url = f"{airflow_url}/api/v2/dags/{dag_id_quoted}/dagRuns/{run_id_quoted}"
                r = requests.get(url, auth=auth, timeout=8)
                if r.status_code == 200:
                    state = r.json().get('state')
                    run_states[run_id] = state
                    if state in ('success', 'failed'):
                        pending_runs.remove(run_id)
                elif r.status_code == 404:
                    pass
            except Exception as e:
                logging.warning(f"Aviso transitório ao verificar DAG run {run_id}: {e}")
                
        if not pending_runs:
            break
            
        time.sleep(poll_interval)
        
    all_finished = (len(pending_runs) == 0)
    return all_finished, run_states

def wait_for_dag_discovery(dag_id, max_wait=120, poll_interval=3):
    """Aguarda até que o Airflow descubra e disponibilize uma DAG recém-gerada."""
    import time
    airflow_url = get_airflow_url()
    auth = get_airflow_auth()
    dag_id_quoted = urllib.parse.quote(str(dag_id), safe='')
    start = time.time()
    while (time.time() - start) < max_wait:
        try:
            url = f"{airflow_url}/api/v2/dags/{dag_id_quoted}"
            r = requests.get(url, auth=auth, timeout=5)
            r = requests.get(url, auth=auth, timeout=5)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(poll_interval)
    return False

def wait_for_dags(dags_list, max_wait=1800, poll_interval=4):
    """Aguarda até que todas as DAGs na lista terminem execuções ativas."""
    import time
    airflow_url = get_airflow_url()
    auth = get_airflow_auth()
    start = time.time()
    time.sleep(3)
    consecutive_errors = 0
    while (time.time() - start) < max_wait:
        all_done = True
        for did in set(dags_list):
            try:
                url = f"{airflow_url}/api/v2/dags/{did}/dagRuns?order_by=-run_after&limit=30"
                r = requests.get(url, auth=auth, timeout=5)
                if r.status_code == 200:
                    consecutive_errors = 0
                    runs = r.json().get('dag_runs', [])
                    active = [run for run in runs if run.get('state') in ('running', 'queued')]
                    if active:
                        all_done = False
                        break
                else:
                    consecutive_errors += 1
                    if consecutive_errors > 8:
                        all_done = True
                        break
            except Exception:
                consecutive_errors += 1
                if consecutive_errors > 8:
                    all_done = True
                    break
        if all_done:
            break
        time.sleep(poll_interval)


